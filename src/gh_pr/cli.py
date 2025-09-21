#!/usr/bin/env python3
"""Command-line interface for gh-pr."""

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from github import GithubException
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .auth.permissions import PermissionChecker
from .auth.token import TokenManager
from .core.batch import BatchOperations, BatchSummary
from .core.github import GitHubClient
from .core.pr_manager import PRManager
from .ui.display import DisplayManager
from .utils.cache import CacheManager
from .utils.clipboard import ClipboardManager
from .utils.config import ConfigManager
from .utils.export import ExportManager

console = Console()

# Constants for backwards compatibility with tests
MAX_CONTEXT_LINES = 3

@dataclass
class CLIConfig:
    """Configuration for CLI command."""
    pr_identifier: Optional[str] = None
    interactive: bool = False
    tui: bool = False
    repo: Optional[str] = None
    token: Optional[str] = None
    token_info: bool = False
    show_all: bool = False
    resolved_active: bool = False
    unresolved_outdated: bool = False
    current_unresolved: bool = False
    checks: bool = False
    verbose: bool = False
    context: int = 3
    no_code: bool = False
    no_cache: bool = False
    clear_cache: bool = False
    resolve_outdated: bool = False
    accept_suggestions: bool = False
    copy: bool = False
    export: Optional[str] = None
    config: Optional[str] = None
    batch_file: Optional[str] = None
    review_report: bool = False
    rate_limit: float = 2.0


@click.command()
@click.argument("pr_identifier", required=False)
@click.option(
    "-i", "--interactive", is_flag=True, help="Show interactive list of all open PRs to choose from"
)
@click.option(
    "--tui", is_flag=True, help="Launch interactive TUI mode (Terminal User Interface)"
)
@click.option(
    "-r", "--repo", help="Specify the repository (default: current repo)", metavar="OWNER/REPO"
)
@click.option(
    "--token", help="GitHub token (can also use GH_TOKEN or GITHUB_TOKEN env vars)", metavar="TOKEN"
)
@click.option(
    "--token-info", is_flag=True, help="Display detailed token information and exit"
)
@click.option(
    "-a", "--all", "show_all", is_flag=True, help="Show all comments, not just unresolved"
)
@click.option(
    "--resolved-active", is_flag=True, help="Show resolved but not outdated comments"
)
@click.option(
    "--unresolved-outdated", is_flag=True, help="Show unresolved comments where code has changed"
)
@click.option(
    "--current-unresolved", is_flag=True, help="Show only unresolved comments on current code"
)
@click.option(
    "--checks", is_flag=True, help="Show detailed CI/CD check status and logs"
)
@click.option(
    "-v", "--verbose", is_flag=True, help="Show additional details (timestamps, resolved status)"
)
@click.option(
    "-c", "--context",
    default=3,
    help="Number of context lines to show (default: 3)",
    type=click.IntRange(0, 50)  # Prevent negative or huge values
)
@click.option("--no-code", is_flag=True, help="Don't show code context")
@click.option("--no-cache", is_flag=True, help="Bypass cache and fetch fresh data")
@click.option("--clear-cache", is_flag=True, help="Clear all cached PR data")
@click.option(
    "--resolve-outdated", is_flag=True, help="Auto-resolve all outdated unresolved comments"
)
@click.option("--accept-suggestions", is_flag=True, help="Auto-commit all PR suggestions")
@click.option("--copy", is_flag=True, help="Copy output to clipboard (WSL2 compatible)")
@click.option(
    "--export", type=click.Choice(["markdown", "csv", "json"]), help="Export output format"
)
@click.option("--config", type=click.Path(exists=True), help="Path to config file")
@click.option(
    "--batch-file",
    type=click.Path(exists=True),
    help="File with list of PR identifiers for batch operations (one per line)"
)
@click.option(
    "--review-report", is_flag=True, help="Generate a review report for the PR"
)
@click.option(
    "--rate-limit",
    type=click.FloatRange(0.1, 10.0),
    default=2.0,
    help="Rate limit for batch operations (seconds between API calls, default: 2.0)"
)
def main(**kwargs) -> None:
    """
    GitHub PR Review Comments Tool

    Fetch review comments from a GitHub PR with various filtering options and automation features.

    When run without arguments:
    - Automatically finds and uses PR for current branch
    - If multiple git repos found in subdirs, lets you choose
    - Falls back to showing helpful message if no PR found

    Examples:
        gh-pr                        # Auto-detect PR from current/sub directories
        gh-pr -i                     # Interactive mode - choose from all open PRs
        gh-pr --tui                  # Launch interactive TUI mode
        gh-pr 53
        gh-pr https://github.com/owner/repo/pull/53
        gh-pr --unresolved-outdated  # Auto-detect PR, show likely fixed issues
        gh-pr --resolve-outdated     # Auto-resolve outdated comments
        gh-pr --accept-suggestions   # Accept all code suggestions
        gh-pr --copy                 # Copy output to clipboard
        gh-pr --review-report        # Generate a review report
        gh-pr --batch-file prs.txt --resolve-outdated  # Batch resolve outdated comments
        gh-pr --token-info           # Display detailed token information
    """
    # Create config from kwargs
    cfg = CLIConfig(**kwargs)

    # Launch TUI mode if requested
    if cfg.tui:
        _launch_tui(cfg)
        return

    try:
        # Initialize services
        result = _initialize_services(
            cfg.config, cfg.no_cache, cfg.clear_cache, cfg.token
        )
        if result is None:
            return  # Cache was cleared
        config_manager, cache_manager, token_manager = result

        # Handle --token-info flag
        if cfg.token_info:
            _display_detailed_token_info(token_manager)
            return

        # Display token info and check expiration
        _display_token_info(token_manager, cfg.verbose)
        _check_token_expiration(token_manager)

        # Check automation permissions
        _check_automation_permissions(token_manager, cfg.resolve_outdated, cfg.accept_suggestions)

        # Initialize clients and managers
        token = token_manager.get_token()
        github_client = GitHubClient(token)
        pr_manager = PRManager(github_client, cache_manager, token)
        display_manager = DisplayManager(console, verbose=cfg.verbose)

        # Handle batch operations
        if cfg.batch_file:
            permission_checker = PermissionChecker(token_manager)
            batch_ops = BatchOperations(pr_manager, permission_checker, rate_limit=cfg.rate_limit)
            _handle_batch_operations(batch_ops, cfg.batch_file, cfg.resolve_outdated, cfg.accept_suggestions)
            return

        # Determine filter mode
        filter_mode = _determine_filter_mode(cfg.show_all, cfg.resolved_active, cfg.unresolved_outdated, cfg.current_unresolved)

        # Get PR identifier
        pr_identifier = _get_pr_identifier(pr_manager, cfg.pr_identifier, cfg.interactive, cfg.repo)

        # Parse PR identifier
        owner, repo_name, pr_number = pr_manager.parse_pr_identifier(pr_identifier, cfg.repo)

        # Show repository info
        _show_repo_pr_count(github_client, owner, repo_name, cfg.verbose)

        # Fetch PR data
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Fetching PR #{pr_number}...", total=None)
            pr_data = pr_manager.fetch_pr_data(owner, repo_name, pr_number)
            progress.remove_task(task)

        # Handle automation
        _handle_automation(pr_manager, owner, repo_name, pr_number, cfg.resolve_outdated, cfg.accept_suggestions)

        # Display PR information
        display_manager.display_pr_header(pr_data)

        # Fetch and display comments
        comments = pr_manager.fetch_pr_comments(owner, repo_name, pr_number, filter_mode)

        if cfg.checks:
            check_status = pr_manager.fetch_check_status(owner, repo_name, pr_number)
            display_manager.display_check_status(check_status)

        display_manager.display_comments(comments, show_code=not cfg.no_code, context_lines=cfg.context)

        # Display summary
        summary = pr_manager.get_pr_summary(owner, repo_name, pr_number)
        display_manager.display_summary(summary)

        # Handle output
        _handle_output(display_manager, pr_data, comments, summary, cfg.export, cfg.copy, cfg.review_report)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if cfg.verbose:
            console.print_exception()
        sys.exit(1)


def _initialize_services(config_path: Optional[str], no_cache: bool, clear_cache: bool, token: Optional[str]):
    """Initialize configuration, cache, and token services."""
    config_manager = ConfigManager(config_path=config_path)

    cache_manager = CacheManager(
        enabled=not no_cache,
        location=config_manager.get("cache.location", "~/.cache/gh-pr")
    )

    if clear_cache:
        cache_manager.clear()
        console.print("[green]✓ Cache cleared successfully[/green]")
        return None

    token_manager = TokenManager(token=token, config_manager=config_manager)

    if not token_manager.validate_token():
        console.print("[red]✗ Invalid or expired GitHub token[/red]")
        sys.exit(1)

    return config_manager, cache_manager, token_manager


def _display_token_info(token_manager: TokenManager, verbose: bool):
    """Display token information if verbose mode."""
    if not verbose:
        return

    token_info = token_manager.get_token_info()
    if token_info:
        # Check expiration status
        expiration = token_manager.check_expiration()
        expires_text = "Never"
        days_text = "N/A"

        if expiration:
            expires_text = expiration['expires_at']
            days_remaining = expiration['days_remaining']
            if expiration['expired']:
                days_text = "[red]EXPIRED[/red]"
            elif expiration['warning']:
                days_text = f"[yellow]{days_remaining} days (expiring soon)[/yellow]"
            else:
                days_text = f"[green]{days_remaining} days[/green]"

        console.print(Panel(
            f"Token: {token_info['type']}\n"
            f"Rate Limit: {token_info.get('rate_limit', {}).get('remaining', 'N/A')} / "
            f"{token_info.get('rate_limit', {}).get('limit', 'N/A')}\n"
            f"Expires: {expires_text}\n"
            f"Days remaining: {days_text}",
            title="Token Information",
            border_style="blue"
        ))


def _display_detailed_token_info(token_manager: TokenManager):
    """Display detailed token information."""
    console.print("\n[bold]GitHub Token Information[/bold]\n")

    # Validate token first
    if not token_manager.validate_token():
        console.print("[red]✗ Token is invalid or expired[/red]")
        sys.exit(1)

    token_info = token_manager.get_token_info()
    if not token_info:
        console.print("[yellow]⚠ Unable to retrieve token information[/yellow]")
        sys.exit(1)

    # Display token type
    token_type = token_info['type']
    console.print(f"[bold]Token Type:[/bold] {token_type}")

    # Display scopes (if available)
    scopes = token_info.get('scopes', [])
    if scopes:
        console.print(f"[bold]Scopes:[/bold] {', '.join(scopes)}")
    else:
        console.print("[bold]Scopes:[/bold] [dim]Unable to determine (may be fine-grained token)[/dim]")

    # Display rate limit info
    rate_limit = token_info.get('rate_limit', {})
    if rate_limit:
        remaining = rate_limit.get('remaining', 'N/A')
        limit = rate_limit.get('limit', 'N/A')
        reset_time = rate_limit.get('reset', 'N/A')

        console.print("\n[bold]Rate Limit:[/bold]")
        console.print(f"  Remaining: {remaining} / {limit}")
        if reset_time and reset_time != 'N/A':
            try:
                reset_dt = datetime.fromisoformat(reset_time.replace('Z', '+00:00'))
                console.print(f"  Resets: {reset_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            except (ValueError, AttributeError):
                # Log parsing issue but continue gracefully
                console.print("  [dim]Reset time unavailable[/dim]")

    # Display expiration info
    expiration = token_manager.check_expiration()
    if expiration:
        console.print("\n[bold]Expiration:[/bold]")
        expires_at = expiration['expires_at']
        days_remaining = expiration['days_remaining']

        # Accept both 'Z' and offset forms
        expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        console.print(f"  Expires: {expires_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        if expiration['expired']:
            console.print("  Status: [red]✗ EXPIRED[/red]")
        elif expiration['warning']:
            console.print(f"  Status: [yellow]⚠ Expiring in {days_remaining} days[/yellow]")
        else:
            console.print(f"  Status: [green]✓ Valid for {days_remaining} more days[/green]")
    else:
        console.print("\n[bold]Expiration:[/bold] No expiration (token does not expire)")

    # Test repository access
    console.print("\n[bold]Testing Permissions:[/bold]")
    try:
        github = token_manager.get_github_client()
        user = github.get_user()
        console.print(f"  Authenticated as: {user.login}")

        # Check basic permissions
        permissions_to_check = [
            ("repo", "Repository access"),
            ("write:discussion", "Discussion write access"),
            ("read:org", "Organization read access")
        ]

        console.print("\n[bold]Permission Check:[/bold]")
        for scope, description in permissions_to_check:
            has_perm = token_manager.has_permissions([scope])
            status = "[green]✓[/green]" if has_perm else "[red]✗[/red]"
            console.print(f"  {status} {description}")

    except GithubException as e:
        console.print(f"[red]Error testing permissions: {e}[/red]")

    console.print()  # Empty line at the end


def _check_token_expiration(token_manager: TokenManager):
    """Check and warn about token expiration."""
    if expiration := token_manager.check_expiration():
        if expiration['expired']:
            console.print("[red]⚠ Your GitHub token has EXPIRED! Please generate a new token.[/red]")
            if not click.confirm("Continue anyway?"):
                sys.exit(1)
        elif expiration['warning']:
            days = expiration['days_remaining']
            console.print(f"[yellow]⚠ Your GitHub token expires in {days} days. Consider renewing it soon.[/yellow]")


def _check_automation_permissions(token_manager: TokenManager, resolve_outdated: bool, accept_suggestions: bool):
    """Check if token has permissions for automation commands."""
    if not (resolve_outdated or accept_suggestions):
        return

    required_scopes = set()
    if resolve_outdated:
        required_scopes.update(["repo", "write:discussion"])
    if accept_suggestions:
        required_scopes.update(["repo"])

    if not token_manager.has_permissions(list(required_scopes)):
        console.print(
            f"[yellow]⚠ Warning: Token lacks required permissions: {', '.join(required_scopes)}[/yellow]"
        )
        if not click.confirm("Continue anyway?"):
            sys.exit(1)


def _determine_filter_mode(show_all: bool, resolved_active: bool, unresolved_outdated: bool, current_unresolved: bool) -> str:
    """Determine filter mode based on flags."""
    if show_all:
        return "all"
    elif resolved_active:
        return "resolved_active"
    elif unresolved_outdated:
        return "unresolved_outdated"
    elif current_unresolved:
        return "current_unresolved"
    return "unresolved"


def _get_pr_identifier(pr_manager: PRManager, pr_identifier: Optional[str], interactive: bool, repo: Optional[str]) -> str:
    """Get PR identifier through various methods."""
    if interactive:
        pr_identifier = pr_manager.select_pr_interactive(repo)
        if not pr_identifier:
            console.print("[yellow]No PR selected[/yellow]")
            sys.exit(0)
    elif not pr_identifier:
        pr_identifier = pr_manager.auto_detect_pr()
        if not pr_identifier:
            console.print("[yellow]No PR found for current branch[/yellow]")
            console.print("[dim]Tip: Use -i for interactive mode or specify a PR number/URL directly[/dim]")
            sys.exit(1)
    return pr_identifier


def _show_repo_pr_count(github_client: GitHubClient, owner: str, repo_name: str, verbose: bool):
    """Show repository PR count if verbose."""
    if not verbose:
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Fetching repository information...", total=None)
        open_prs = github_client.get_open_pr_count(owner, repo_name)
        progress.remove_task(task)

    console.print(f"[blue]Repository has {open_prs} open PRs[/blue]")


def _handle_automation(
    pr_manager: PRManager,
    owner: str,
    repo_name: str,
    pr_number: int,
    resolve_outdated: bool,
    accept_suggestions: bool
):
    """Handle automation commands."""
    if resolve_outdated:
        resolved_count, errors = pr_manager.resolve_outdated_comments(owner, repo_name, pr_number)
        if resolved_count > 0:
            console.print(f"[green]✓ Resolved {resolved_count} outdated comments[/green]")
        if errors:
            for error in errors:
                console.print(f"[yellow]⚠ {error}[/yellow]")
        if resolved_count == 0 and not errors:
            console.print("[dim]No outdated comments to resolve[/dim]")

    if accept_suggestions:
        accepted_count, errors = pr_manager.accept_all_suggestions(owner, repo_name, pr_number)
        if accepted_count > 0:
            console.print(f"[green]✓ Accepted {accepted_count} suggestions[/green]")
        if errors:
            for error in errors:
                console.print(f"[yellow]⚠ {error}[/yellow]")
        if accepted_count == 0 and not errors:
            console.print("[dim]No suggestions to accept[/dim]")


def _handle_batch_operations(
    batch_ops: BatchOperations,
    batch_file: str,
    resolve_outdated: bool,
    accept_suggestions: bool
):
    """Handle batch operations for multiple PRs."""

    # Read PR identifiers from file
    batch_path = Path(batch_file)
    pr_identifiers = []

    with batch_path.open() as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):  # Skip empty lines and comments
                pr_identifiers.append(line)

    if not pr_identifiers:
        console.print("[yellow]No PR identifiers found in batch file[/yellow]")
        return

    console.print(f"[blue]Processing {len(pr_identifiers)} PRs from batch file[/blue]")

    # Execute batch operations
    with Progress(console=console) as progress:
        if resolve_outdated:
            console.print("\n[bold]Resolving outdated comments...[/bold]")
            results = batch_ops.resolve_outdated_comments_batch(pr_identifiers, progress)
            _display_batch_results(results, "resolve_outdated")

        if accept_suggestions:
            console.print("\n[bold]Accepting suggestions...[/bold]")
            results = batch_ops.accept_suggestions_batch(pr_identifiers, progress)
            _display_batch_results(results, "accept_suggestions")


def _display_batch_results(results, operation: str):
    """Display batch operation results."""

    # Create summary from results
    summary = BatchSummary(total=len(results))
    for result in results:
        summary.results.append(result)
        if result.success:
            summary.successful += 1
        else:
            summary.failed += 1
            if result.error:
                summary.errors.append(f"{result.pr_identifier}: {result.error}")

    console.print("\n[bold]Batch Operation Summary[/bold]")
    console.print(f"Total: {summary.total}")
    console.print(f"Successful: [green]{summary.successful}[/green]")
    console.print(f"Failed: [red]{summary.failed}[/red]")
    console.print(f"Success Rate: {summary.success_rate:.1f}%")

    if summary.errors:
        console.print("\n[yellow]Errors:[/yellow]")
        for error in summary.errors[:5]:  # Show first 5 errors
            console.print(f"  - {error}")
        if len(summary.errors) > 5:
            console.print(f"  ... and {len(summary.errors) - 5} more errors")

    # Export results
    export_manager = ExportManager()
    results_dicts = [
        {
            "pr_identifier": r.pr_identifier,
            "success": r.success,
            "message": r.message,
            "details": r.details,
            "error": r.error
        }
        for r in summary.results
    ]
    output_file = export_manager.export_batch_results(results_dicts, operation)
    console.print(f"\n[green]✓ Batch results exported to {output_file}[/green]")


def _handle_output(
    display_manager: DisplayManager,
    pr_data: dict,
    comments: list,
    summary: dict,
    export: Optional[str],
    copy: bool,
    review_report: bool
):
    """Handle export and clipboard operations."""
    if export:
        export_manager = ExportManager()
        output_file = export_manager.export(pr_data, comments, format=export)
        console.print(f"[green]✓ Exported to {output_file}[/green]")

    if review_report:
        export_manager = ExportManager()
        report_file = export_manager.export_review_report(pr_data, summary)
        console.print(f"[green]✓ Generated review report: {report_file}[/green]")

    if copy:
        clipboard_timeout = cfg.get("clipboard.timeout_seconds", 5.0)
        clipboard = ClipboardManager(timeout=clipboard_timeout)
        plain_output = display_manager.generate_plain_output(pr_data, comments, summary)
        if clipboard.copy(plain_output):
            console.print("[green]✓ Copied to clipboard (plain text)[/green]")
        else:
            console.print("[yellow]⚠ Could not copy to clipboard[/yellow]")


def _launch_tui(cfg: CLIConfig) -> None:
    """Launch the interactive TUI mode."""
    try:
        from .ui.interactive import GhPrTUI

        # Initialize services
        result = _initialize_services(
            cfg.config, cfg.no_cache, cfg.clear_cache, cfg.token
        )
        if result is None:
            return  # Cache was cleared
        config_manager, cache_manager, token_manager = result

        # Initialize GitHub client
        github_client = GitHubClient(token_manager.get_token())

        # Initialize PR Manager
        from .core.pr_manager import PRManager
        pr_manager = PRManager(github_client, cache_manager, token=token_manager.get_token())

        # Launch the TUI
        app = GhPrTUI(
            github_client=github_client,
            pr_manager=pr_manager,
            config_manager=config_manager,
            initial_repo=cfg.repo or config_manager.get("default_repo")
        )
        app.run()

    except ImportError:
        console.print("[red]✗ TUI mode requires Textual library[/red]")
        console.print("[dim]Install with: pip install textual[/dim]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]TUI mode interrupted[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Error launching TUI: {e}[/red]")
        if cfg.verbose:
            console.print_exception()
        sys.exit(1)

if __name__ == "__main__":
    main()

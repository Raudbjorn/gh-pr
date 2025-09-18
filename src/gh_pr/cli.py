#!/usr/bin/env python3
"""Command-line interface for gh-pr."""

import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .auth.token import TokenManager
from .core.github import GitHubClient
from .core.pr_manager import PRManager
from .ui.display import DisplayManager
from .utils.cache import CacheManager
from .utils.clipboard import ClipboardManager
from .utils.config import ConfigManager

console = Console()


@click.command()
@click.argument("pr_identifier", required=False)
@click.option(
    "-i", "--interactive", is_flag=True, help="Show interactive list of all open PRs to choose from"
)
@click.option(
    "-r", "--repo", help="Specify the repository (default: current repo)", metavar="OWNER/REPO"
)
@click.option(
    "--token", help="GitHub token (can also use GH_TOKEN or GITHUB_TOKEN env vars)", metavar="TOKEN"
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
    "-c", "--context", default=3, help="Number of context lines to show (default: 3)", type=int
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
def main(
    pr_identifier: Optional[str],
    interactive: bool,
    repo: Optional[str],
    token: Optional[str],
    show_all: bool,
    resolved_active: bool,
    unresolved_outdated: bool,
    current_unresolved: bool,
    checks: bool,
    verbose: bool,
    context: int,
    no_code: bool,
    no_cache: bool,
    clear_cache: bool,
    resolve_outdated: bool,
    accept_suggestions: bool,
    copy: bool,
    export: Optional[str],
    config: Optional[str],
) -> None:
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
        gh-pr 53
        gh-pr https://github.com/owner/repo/pull/53
        gh-pr --unresolved-outdated  # Auto-detect PR, show likely fixed issues
        gh-pr --resolve-outdated     # Auto-resolve outdated comments
        gh-pr --accept-suggestions   # Accept all code suggestions
        gh-pr --copy                 # Copy output to clipboard
    """
    try:
        # Initialize configuration
        config_manager = ConfigManager(config_path=config)

        # Initialize cache manager
        cache_manager = CacheManager(
            enabled=not no_cache,
            location=config_manager.get("cache.location", "~/.cache/gh-pr")
        )

        if clear_cache:
            cache_manager.clear()
            console.print("[green]✓ Cache cleared successfully[/green]")
            return

        # Initialize token manager
        token_manager = TokenManager(token=token)

        # Validate token and show info
        if not token_manager.validate_token():
            console.print("[red]✗ Invalid or expired GitHub token[/red]")
            sys.exit(1)

        token_info = token_manager.get_token_info()
        if token_info and verbose:
            console.print(Panel(
                f"Token: {token_info['type']}\n"
                f"Scopes: {', '.join(token_info.get('scopes', []))}\n"
                f"Expires: {token_info.get('expires_at', 'Never')}\n"
                f"Days remaining: {token_info.get('days_remaining', 'N/A')}",
                title="Token Information",
                border_style="blue"
            ))

        # Check permissions for automation commands
        if resolve_outdated or accept_suggestions:
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

        # Initialize GitHub client
        github_client = GitHubClient(token_manager.get_token())

        # Initialize PR manager
        pr_manager = PRManager(github_client, cache_manager)

        # Initialize display manager
        display_manager = DisplayManager(console, verbose=verbose)

        # Determine filter mode
        filter_mode = "unresolved"
        if show_all:
            filter_mode = "all"
        elif resolved_active:
            filter_mode = "resolved_active"
        elif unresolved_outdated:
            filter_mode = "unresolved_outdated"
        elif current_unresolved:
            filter_mode = "current_unresolved"

        # Handle PR selection
        if interactive:
            pr_identifier = pr_manager.select_pr_interactive(repo)
            if not pr_identifier:
                console.print("[yellow]No PR selected[/yellow]")
                sys.exit(0)
        elif not pr_identifier:
            # Auto-detect PR from current branch or subdirectories
            pr_identifier = pr_manager.auto_detect_pr()
            if not pr_identifier:
                console.print("[yellow]No PR found for current branch[/yellow]")
                console.print("[dim]Tip: Use -i for interactive mode or specify a PR number/URL directly[/dim]")
                sys.exit(1)

        # Parse PR identifier
        owner, repo_name, pr_number = pr_manager.parse_pr_identifier(pr_identifier, repo)

        # Show repository PR count
        if verbose:
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

        # Handle automation commands
        if resolve_outdated:
            resolved_count = pr_manager.resolve_outdated_comments(owner, repo_name, pr_number)
            console.print(f"[green]✓ Resolved {resolved_count} outdated comments[/green]")

        if accept_suggestions:
            accepted_count = pr_manager.accept_all_suggestions(owner, repo_name, pr_number)
            console.print(f"[green]✓ Accepted {accepted_count} suggestions[/green]")

        # Display PR information
        display_manager.display_pr_header(pr_data)

        # Fetch and display comments
        comments = pr_manager.fetch_pr_comments(
            owner, repo_name, pr_number, filter_mode
        )

        if checks:
            check_status = pr_manager.fetch_check_status(owner, repo_name, pr_number)
            display_manager.display_check_status(check_status)

        display_manager.display_comments(
            comments,
            show_code=not no_code,
            context_lines=context
        )

        # Display summary
        summary = pr_manager.get_pr_summary(owner, repo_name, pr_number)
        display_manager.display_summary(summary)

        # Handle export
        if export:
            from .utils.export import ExportManager
            export_manager = ExportManager()
            output_file = export_manager.export(pr_data, comments, format=export)
            console.print(f"[green]✓ Exported to {output_file}[/green]")

        # Handle clipboard
        if copy:
            clipboard = ClipboardManager()
            # Generate plain text output for clipboard
            plain_output = display_manager.generate_plain_output(pr_data, comments, summary)
            if clipboard.copy(plain_output):
                console.print("[green]✓ Copied to clipboard (plain text)[/green]")
            else:
                console.print("[yellow]⚠ Could not copy to clipboard[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
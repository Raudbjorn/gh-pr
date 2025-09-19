"""Display and formatting for PR data."""

import re
from typing import Any

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text


class DisplayManager:
    """Manage display and formatting of PR information."""

    def __init__(self, console: Console, verbose: bool = False):
        """
        Initialize DisplayManager.

        Args:
            console: Rich console instance
            verbose: Show verbose output
        """
        self.console = console
        self.verbose = verbose

    def display_pr_header(self, pr_data: dict[str, Any]) -> None:
        """
        Display PR header information.

        Args:
            pr_data: PR data dictionary
        """
        state_color = "green" if pr_data["state"] == "open" else "red"

        header = Panel(
            f"[bold]{pr_data['title']}[/bold]\n\n"
            f"PR #{pr_data['number']} • "
            f"[{state_color}]{pr_data['state'].upper()}[/{state_color}] • "
            f"by @{pr_data['author']}\n"
            f"📝 {pr_data.get('changed_files', 0)} files • "
            f"➕ {pr_data.get('additions', 0)} • "
            f"➖ {pr_data.get('deletions', 0)}",
            title="Pull Request",
            border_style="blue",
        )

        self.console.print(header)

    def display_comments(
        self,
        threads: list[dict[str, Any]],
        show_code: bool = True,
        context_lines: int = 3,
    ) -> None:
        """
        Display comment threads.

        Args:
            threads: List of thread dictionaries
            show_code: Whether to show code context
            context_lines: Number of context lines
        """
        if not threads:
            self.console.print("[yellow]No comments matching filter criteria[/yellow]")
            return

        for thread in threads:
            self._display_thread(thread, show_code, context_lines)

    def _display_thread(
        self,
        thread: dict[str, Any],
        show_code: bool,
        context_lines: int,
    ) -> None:
        """
        Display a single comment thread.

        Args:
            thread: Thread dictionary
            show_code: Whether to show code context (uses GitHub's diff_hunk)
            context_lines: Number of context lines (not used - GitHub provides its own context in diff_hunk)
        """
        # Build thread status
        status_parts = []

        if thread.get("is_resolved"):
            status_parts.append("[green]✓ Resolved[/green]")
        else:
            status_parts.append("[red]⚠ Unresolved[/red]")

        if thread.get("is_outdated"):
            status_parts.append("[yellow]🕒 Outdated[/yellow]")
        else:
            status_parts.append("[blue]📍 Current[/blue]")

        status = " • ".join(status_parts)

        # Build location string
        location = f"📄 {thread['path']}"
        if thread.get("line"):
            if thread.get("start_line"):
                location += f":{thread['start_line']}-{thread['line']}"
            else:
                location += f":{thread['line']}"

        # Build renderables list
        renderables = []
        renderables.append(Text(f"{location}\n{status}"))

        # Add code context if requested and available
        if show_code and thread.get("diff_hunk"):
            # Display diff hunk as syntax-highlighted code
            # Try to determine language from file extension
            file_path = thread.get("path", "")
            lang = self._get_language_from_path(file_path)

            renderables.append(Text("\n📝 Code Context:", style="bold"))
            renderables.append(Syntax(thread["diff_hunk"], lang, theme="monokai", line_numbers=False))

        # Add comments
        for comment in thread.get("comments", []):
            renderables.append(Text(f"\n👤 {comment['author']}:", style="bold"))

            # Check if body contains markdown
            body = comment.get("body", "")
            markdown_patterns = [
                r"^#",
                r"```",
                r"\[.*?\]\(.*?\)",
                r"^[-*] ",
                r"`[^`]+`",
            ]
            if any(re.search(pattern, body, re.MULTILINE) for pattern in markdown_patterns):
                # Render as markdown properly
                renderables.append(Markdown(body))
            else:
                renderables.append(Text(body))

            if self.verbose and comment.get("created_at"):
                renderables.append(Text(f"📅 {comment['created_at']}", style="dim"))

        # Create a group of renderables
        group = Group(*renderables)

        panel = Panel(
            group,
            border_style="yellow" if thread.get("is_outdated") else "white",
            expand=False,
        )

        self.console.print(panel)

    def _get_language_from_path(self, path: str) -> str:
        """Get syntax highlighting language from file path."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "jsx",
            ".tsx": "tsx",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".cs": "csharp",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".sh": "bash",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".json": "json",
            ".xml": "xml",
            ".html": "html",
            ".css": "css",
            ".md": "markdown",
        }

        for ext, lang in ext_map.items():
            if path.endswith(ext):
                return lang
        return "text"

    def display_check_status(self, check_status: dict[str, Any]) -> None:
        """
        Display CI/CD check status.

        Args:
            check_status: Check status dictionary
        """
        table = Table(title="CI/CD Status", show_header=True)
        table.add_column("Check", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Conclusion", justify="center")

        for check in check_status.get("checks", []):
            # Determine status icon and color based on status
            status = check.get("status", "unknown")
            if status == "in_progress":
                status_icon = "⏳"
                status_color = "yellow"
            elif status == "queued":
                status_icon = "🔄"
                status_color = "blue"
            elif status == "waiting":
                status_icon = "⏸️"
                status_color = "magenta"
            elif status == "completed":
                status_icon = "✓"
                status_color = "green"
            else:
                status_icon = "❓"
                status_color = "grey50"

            # Determine conclusion color
            conclusion = check.get("conclusion", "")
            if conclusion == "success":
                conclusion_color = "green"
            elif conclusion == "failure":
                conclusion_color = "red"
            elif conclusion == "cancelled":
                conclusion_color = "grey50"
            elif conclusion == "skipped":
                conclusion_color = "dim"
            elif conclusion == "neutral":
                conclusion_color = "blue"
            elif conclusion == "timed_out":
                conclusion_color = "red"
            elif conclusion == "action_required":
                conclusion_color = "yellow"
            else:
                conclusion_color = "yellow"

            # Format conclusion display
            if conclusion:
                conclusion_display = f"[{conclusion_color}]{conclusion}[/{conclusion_color}]"
            else:
                conclusion_display = "[yellow]pending[/yellow]"

            table.add_row(
                check.get("name", "Unknown"),
                f"[{status_color}]{status_icon} {status}[/{status_color}]",
                conclusion_display,
            )

        self.console.print(table)

        # Enhanced summary
        summary_parts = [f"Total: {check_status.get('total', 0)}"]

        if check_status.get('success', 0) > 0:
            summary_parts.append(f"[green]✓ {check_status['success']}[/green]")
        if check_status.get('failure', 0) > 0:
            summary_parts.append(f"[red]✗ {check_status['failure']}[/red]")
        if check_status.get('pending', 0) > 0:
            summary_parts.append(f"[yellow]⏳ {check_status['pending']}[/yellow]")
        if check_status.get('skipped', 0) > 0:
            summary_parts.append(f"[dim]⊘ {check_status['skipped']}[/dim]")
        if check_status.get('cancelled', 0) > 0:
            summary_parts.append(f"[grey50]✖ {check_status['cancelled']}[/grey50]")

        summary = " • ".join(summary_parts)

        self.console.print(Panel(summary, title="Check Summary", border_style="blue"))

    def display_summary(self, summary: dict[str, Any]) -> None:
        """
        Display PR summary.

        Args:
            summary: Summary dictionary
        """
        summary_text = (
            f"[bold]Thread Summary[/bold]\n\n"
            f"Total threads: {summary['total_threads']}\n\n"
            f"[bold]Unresolved:[/bold]\n"
            f"  [red]⚠ On current code: {summary['unresolved_active']}[/red]\n"
            f"  [yellow]🔍 On outdated code: {summary['unresolved_outdated']}[/yellow] (possibly fixed)\n\n"
            f"[bold]Resolved:[/bold]\n"
            f"  [green]✓ Active: {summary['resolved_active']}[/green]\n"
            f"  [green]✓ Outdated: {summary['resolved_outdated']}[/green]\n\n"
            f"[bold]Review Status:[/bold]\n"
            f"  [green]✅ Approvals: {summary['approvals']}[/green]\n"
            f"  [yellow]🔄 Changes requested: {summary['changes_requested']}[/yellow]\n"
            f"  [blue]💬 Comments: {summary['comments']}[/blue]"
        )

        # Add status message
        if summary["unresolved_active"] == 0 and summary["changes_requested"] == 0:
            if summary["unresolved_outdated"] > 0:
                status_msg = "[yellow]⚠ No active issues, but outdated comments need resolution[/yellow]"
            else:
                status_msg = "[green]✅ All checks passed and no unresolved comments![/green]"
        else:
            status_msg = f"[red]⚠ Action needed: {summary['unresolved_active']} active issues[/red]"

        summary_text += f"\n\n{status_msg}"

        self.console.print(Panel(summary_text, title="Summary", border_style="blue"))

    def generate_plain_output(
        self,
        pr_data: dict[str, Any],
        comments: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> str:
        """
        Generate plain text output for clipboard.

        Args:
            pr_data: PR data dictionary
            comments: List of comment threads
            summary: Summary dictionary

        Returns:
            Plain text string
        """
        output = []

        # Header
        output.append("=" * 50)
        output.append(f"PR #{pr_data['number']}: {pr_data['title']}")
        output.append(f"Status: {pr_data['state']}")
        output.append(f"Author: @{pr_data['author']}")
        output.append("=" * 50)
        output.append("")

        # Comments
        for thread in comments:
            output.append("-" * 40)
            output.append(f"File: {thread['path']}:{thread.get('line', 'N/A')}")

            status = []
            if thread.get("is_resolved"):
                status.append("RESOLVED")
            else:
                status.append("UNRESOLVED")

            if thread.get("is_outdated"):
                status.append("OUTDATED")

            output.append(f"Status: {' - '.join(status)}")
            output.append("")

            for comment in thread.get("comments", []):
                output.append(f"@{comment['author']}:")
                output.append(comment.get("body", ""))
                output.append("")

        # Summary
        output.append("=" * 50)
        output.append("SUMMARY")
        output.append("=" * 50)
        output.append(f"Unresolved (active): {summary['unresolved_active']}")
        output.append(f"Unresolved (outdated): {summary['unresolved_outdated']}")
        output.append(f"Resolved: {summary['resolved_active'] + summary['resolved_outdated']}")
        output.append(f"Approvals: {summary['approvals']}")
        output.append(f"Changes requested: {summary['changes_requested']}")

        return "\n".join(output)


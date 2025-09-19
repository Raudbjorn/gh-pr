"""Display and formatting for PR data."""

from datetime import datetime
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
            import re
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

    def display_pr_summary(self, pr_data: dict[str, Any]) -> None:
        """
        Display PR summary information.

        Args:
            pr_data: PR data dictionary
        """
        # Delegate to existing display_pr_header
        self.display_pr_header(pr_data)

    def display_comment_thread(self, thread: dict[str, Any]) -> None:
        """
        Display a single comment thread.

        Args:
            thread: Thread data dictionary
        """
        # Delegate to existing _display_thread method
        self._display_thread(thread)

    def format_timestamp(self, ts: Any) -> str:
        """
        Format timestamp for display.

        Args:
            ts: Timestamp (ISO string, datetime, or None)

        Returns:
            Formatted timestamp string
        """
        if ts is None:
            return "N/A"

        if isinstance(ts, str):
            try:
                # Handle ISO format with optional Z suffix
                if ts.endswith('Z'):
                    ts = ts[:-1] + '+00:00'
                dt = datetime.fromisoformat(ts)
                return dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                return str(ts)

        return str(ts)

    def format_diff_hunk(self, diff_hunk: str) -> str:
        """
        Format diff hunk for display.

        Args:
            diff_hunk: Diff hunk string

        Returns:
            Formatted diff string
        """
        if not diff_hunk:
            return ""

        lines = diff_hunk.split('\n')
        formatted = []

        for line in lines:
            if line.startswith('-'):
                formatted.append(line)  # Keep removed lines
            elif line.startswith('+'):
                formatted.append(line)  # Keep added lines
            else:
                formatted.append(line)

        return '\n'.join(formatted)

    def truncate_text(self, text: str, max_length: int) -> str:
        """
        Truncate text to maximum length.

        Args:
            text: Text to truncate
            max_length: Maximum length

        Returns:
            Truncated text with ellipsis if needed
        """
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."

    def create_table(self, title: str, columns: list[str]) -> Table:
        """
        Create a Rich table with title and columns.

        Args:
            title: Table title
            columns: Column names

        Returns:
            Rich Table instance
        """
        table = Table(title=title, show_header=True, header_style="bold")
        for column in columns:
            table.add_column(column)
        return table

    def display_pagination_info(self, current: int, total: int, page_size: int) -> None:
        """Display pagination information."""
        self.console.print(f"[dim]Showing {current} of {total} (page size: {page_size})[/dim]")

    def display_pr_reviews(self, reviews: list[dict[str, Any]]) -> None:
        """Display PR reviews."""
        for review in reviews:
            state_color = "green" if review.get("state") == "APPROVED" else "red"
            self.console.print(
                f"[{state_color}]{review.get('state', 'UNKNOWN')}[/{state_color}] by @{review.get('author', 'unknown')}"
            )
            if review.get("body"):
                self.console.print(f"  {review['body']}")

    def display_suggestions(self, suggestions: list[dict[str, Any]]) -> None:
        """Display code suggestions."""
        for suggestion in suggestions:
            self.console.print(f"\n[bold]Suggestion for {suggestion.get('path', 'unknown')}:{suggestion.get('line', '?')}[/bold]")
            if suggestion.get("original"):
                self.console.print("[red]- " + suggestion["original"] + "[/red]")
            if suggestion.get("suggestion"):
                self.console.print("[green]+ " + suggestion["suggestion"] + "[/green]")

    def display_pr_files(self, files: list[dict[str, Any]]) -> None:
        """Display PR files."""
        table = self.create_table("Changed Files", ["File", "Status", "+/-"])
        for file in files:
            status = file.get("status", "unknown")
            additions = file.get("additions", 0)
            deletions = file.get("deletions", 0)
            table.add_row(
                file.get("filename", "unknown"),
                status,
                f"+{additions}/-{deletions}"
            )
        self.console.print(table)

    def display_error(self, message: str) -> None:
        """Display error message."""
        self.console.print(f"[red]Error: {message}[/red]")

    def display_success(self, message: str) -> None:
        """Display success message."""
        self.console.print(f"[green]✓ {message}[/green]")

    def display_warning(self, message: str) -> None:
        """Display warning message."""
        self.console.print(f"[yellow]⚠ {message}[/yellow]")

    def get_status_color(self, status: str) -> str:
        """Get color for status."""
        colors = {
            "open": "green",
            "closed": "red",
            "merged": "purple",
        }
        return colors.get(status.lower(), "white")


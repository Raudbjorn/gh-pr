"""Display and formatting for PR data."""

from typing import Dict, List, Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text
from rich.markdown import Markdown


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

    def display_pr_header(self, pr_data: Dict[str, Any]) -> None:
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
        threads: List[Dict[str, Any]],
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
        thread: Dict[str, Any],
        show_code: bool,
        context_lines: int,
    ) -> None:
        """
        Display a single comment thread.

        Args:
            thread: Thread dictionary
            show_code: Whether to show code context
            context_lines: Number of context lines
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

        # Create panel for thread
        thread_content = f"{location}\n{status}\n"

        # Add comments
        for comment in thread.get("comments", []):
            thread_content += f"\n👤 [bold]{comment['author']}[/bold]:\n"

            # Check if body contains markdown
            body = comment.get("body", "")
            if "```" in body or "#" in body or "*" in body:
                # Render as markdown
                thread_content += str(Markdown(body)) + "\n"
            else:
                thread_content += f"{body}\n"

            if self.verbose and comment.get("created_at"):
                thread_content += f"[dim]📅 {comment['created_at']}[/dim]\n"

        panel = Panel(
            thread_content.strip(),
            border_style="yellow" if thread.get("is_outdated") else "white",
            expand=False,
        )

        self.console.print(panel)

    def display_check_status(self, check_status: Dict[str, Any]) -> None:
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
            status_icon = "⏳" if check["status"] == "in_progress" else "✓"
            conclusion_color = "green" if check["conclusion"] == "success" else "red"

            if check["conclusion"]:
                conclusion = f"[{conclusion_color}]{check['conclusion']}[/{conclusion_color}]"
            else:
                conclusion = "[yellow]pending[/yellow]"

            table.add_row(
                check["name"],
                f"{status_icon} {check['status']}",
                conclusion,
            )

        self.console.print(table)

        # Summary
        summary = (
            f"Total: {check_status['total']} • "
            f"[green]✓ {check_status['success']}[/green] • "
            f"[red]✗ {check_status['failure']}[/red] • "
            f"[yellow]⏳ {check_status['pending']}[/yellow]"
        )

        self.console.print(Panel(summary, title="Check Summary", border_style="blue"))

    def display_summary(self, summary: Dict[str, Any]) -> None:
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
        pr_data: Dict[str, Any],
        comments: List[Dict[str, Any]],
        summary: Dict[str, Any],
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
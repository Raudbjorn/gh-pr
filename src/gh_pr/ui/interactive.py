"""Interactive Terminal User Interface (TUI) for gh-pr using Textual."""

import asyncio
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, Button, ListView, ListItem, Label, Input
from textual.widget import Widget
from textual.reactive import reactive
from textual.binding import Binding
from textual.message import Message
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.text import Text
from rich import box

from ..core.github import GitHubClient
from ..core.pr_manager import PRManager
from ..auth.token import TokenManager
from ..utils.cache import CacheManager
from ..utils.config import ConfigManager


class PRListItem(ListItem):
    """Custom list item for PR display."""

    def __init__(self, pr_data: Dict[str, Any], *args, **kwargs):
        """Initialize PR list item.

        Args:
            pr_data: Dictionary containing PR information
        """
        self.pr_data = pr_data
        pr_number = pr_data.get("number", "?")
        title = pr_data.get("title", "Unknown")
        author = pr_data.get("author", "Unknown")
        state = pr_data.get("state", "unknown")

        # Create rich formatted label
        state_color = "green" if state == "open" else "red" if state == "closed" else "yellow"
        label = f"[bold]#{pr_number}[/bold] - {title[:50]}... by [cyan]{author}[/cyan] [{state_color}]{state}[/{state_color}]"

        super().__init__(Static(label), *args, **kwargs)


class FilterMenu(Widget):
    """Widget for filter selection menu."""

    DEFAULT_CSS = """
    FilterMenu {
        dock: left;
        width: 30;
        height: 100%;
        background: $surface;
        border-right: solid $primary;
        padding: 1 2;
    }

    FilterMenu Button {
        width: 100%;
        margin: 1 0;
    }
    """

    # Define available filters with descriptions
    FILTERS = {
        "all": "All Comments",
        "unresolved": "Unresolved Only",
        "resolved_active": "Resolved (Active)",
        "unresolved_outdated": "Unresolved (Outdated)",
        "current_unresolved": "Current Unresolved",
    }

    def __init__(self, on_filter_change: Optional[Callable] = None):
        """Initialize filter menu.

        Args:
            on_filter_change: Callback when filter selection changes
        """
        super().__init__()
        self.on_filter_change = on_filter_change
        self.current_filter = "unresolved"

    def compose(self) -> ComposeResult:
        """Compose the filter menu."""
        yield Static("[bold]Filter Comments[/bold]", classes="filter-title")

        for filter_key, filter_label in self.FILTERS.items():
            button = Button(filter_label, id=f"filter_{filter_key}", variant="primary" if filter_key == self.current_filter else "default")
            yield button

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle filter button press.

        Args:
            event: Button press event
        """
        if event.button.id and event.button.id.startswith("filter_"):
            filter_key = event.button.id.replace("filter_", "")
            self.current_filter = filter_key

            # Update button states
            for button in self.query(Button):
                if button.id == event.button.id:
                    button.variant = "primary"
                else:
                    button.variant = "default"

            # Trigger callback
            if self.on_filter_change:
                self.on_filter_change(filter_key)


class PRDetailsView(Widget):
    """Widget for displaying PR details and comments."""

    DEFAULT_CSS = """
    PRDetailsView {
        width: 100%;
        height: 100%;
        padding: 1 2;
    }
    """

    def __init__(self):
        """Initialize PR details view."""
        super().__init__()
        self.pr_data = None
        self.comments = []
        self.filter_mode = "unresolved"

    def update_pr(self, pr_data: Dict[str, Any], comments: List[Dict[str, Any]]) -> None:
        """Update the PR display.

        Args:
            pr_data: PR information dictionary
            comments: List of comment threads
        """
        self.pr_data = pr_data
        self.comments = comments
        self.refresh()

    def update_filter(self, filter_mode: str) -> None:
        """Update the filter mode.

        Args:
            filter_mode: New filter mode
        """
        self.filter_mode = filter_mode
        self.refresh()

    def render(self) -> Panel:
        """Render the PR details."""
        if not self.pr_data:
            return Panel(
                "[dim]No PR selected. Choose a PR from the list or search.[/dim]",
                title="PR Details",
                border_style="blue",
            )

        # Build PR header
        pr_number = self.pr_data.get("number", "?")
        title = self.pr_data.get("title", "Unknown")
        author = self.pr_data.get("author", "Unknown")
        state = self.pr_data.get("state", "unknown")
        created_at = self.pr_data.get("created_at", "")

        # Create header table
        header_table = Table(show_header=False, box=None, padding=0)
        header_table.add_column("Label", style="bold cyan", no_wrap=True)
        header_table.add_column("Value")

        header_table.add_row("PR:", f"#{pr_number}")
        header_table.add_row("Title:", title)
        header_table.add_row("Author:", author)
        header_table.add_row("State:", f"[{'green' if state == 'open' else 'red'}]{state}[/]")
        header_table.add_row("Created:", created_at[:10] if created_at else "Unknown")
        header_table.add_row("Files:", str(self.pr_data.get("changed_files", 0)))
        header_table.add_row("Comments:", str(len(self.comments)))

        return Panel(
            header_table,
            title=f"PR #{pr_number} - {title[:50]}...",
            border_style="blue",
            box=box.ROUNDED,
        )


class SearchBar(Widget):
    """Search bar widget for PR search."""

    DEFAULT_CSS = """
    SearchBar {
        dock: top;
        height: 3;
        background: $surface;
        padding: 0 2;
    }
    """

    def __init__(self, on_search: Optional[Callable] = None):
        """Initialize search bar.

        Args:
            on_search: Callback when search is triggered
        """
        super().__init__()
        self.on_search = on_search

    def compose(self) -> ComposeResult:
        """Compose the search bar."""
        with Horizontal():
            yield Input(placeholder="Search PRs (number, title, or URL)...", id="search_input")
            yield Button("Search", id="search_button", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle search button press.

        Args:
            event: Button press event
        """
        if event.button.id == "search_button":
            search_input = self.query_one("#search_input", Input)
            if self.on_search and search_input.value:
                self.on_search(search_input.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle enter key in search input.

        Args:
            event: Input submission event
        """
        if self.on_search and event.value:
            self.on_search(event.value)


class GhPrTUI(App):
    """Main TUI application for gh-pr."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 1fr 2fr;
        grid-rows: auto 1fr;
    }

    #search-container {
        column-span: 2;
        height: 3;
        background: $surface;
        border-bottom: solid $primary;
    }

    #pr-list-container {
        height: 100%;
        background: $surface;
        border-right: solid $primary;
        padding: 1;
    }

    #details-container {
        height: 100%;
        padding: 1;
    }

    ListView {
        height: 100%;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", key_display="Q"),
        Binding("r", "refresh", "Refresh", key_display="R"),
        Binding("f", "toggle_filter", "Filters", key_display="F"),
        Binding("s", "focus_search", "Search", key_display="S"),
        Binding("j", "next_pr", "Next PR", key_display="J"),
        Binding("k", "prev_pr", "Prev PR", key_display="K"),
        Binding("enter", "select_pr", "View PR", key_display="Enter"),
        Binding("?", "show_help", "Help", key_display="?"),
        Binding("ctrl+c", "copy_url", "Copy URL", key_display="Ctrl+C"),
    ]

    def __init__(
        self,
        github_client: GitHubClient,
        pr_manager: PRManager,
        config_manager: ConfigManager,
        initial_repo: Optional[str] = None,
    ):
        """Initialize the TUI application.

        Args:
            github_client: GitHub API client
            pr_manager: PR manager instance
            config_manager: Configuration manager
            initial_repo: Initial repository to load
        """
        super().__init__()
        self.github_client = github_client
        self.pr_manager = pr_manager
        self.config_manager = config_manager
        self.initial_repo = initial_repo

        # State
        self.current_repo = initial_repo
        self.prs = []
        self.current_pr = None
        self.current_comments = []
        self.filter_mode = "unresolved"
        self.show_filter_menu = False

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header()

        # Search bar at top
        with Container(id="search-container"):
            yield SearchBar(on_search=self.handle_search)

        # PR list on left
        with Container(id="pr-list-container"):
            yield Static("[bold]Pull Requests[/bold]", classes="section-title")
            yield ListView(id="pr-list")

        # Details/filters on right
        with Container(id="details-container"):
            yield PRDetailsView(id="pr-details")
            # Filter menu (initially hidden)
            self.filter_menu = FilterMenu(on_filter_change=self.handle_filter_change)

        yield Footer()

    async def on_mount(self) -> None:
        """Handle mount event - load initial data."""
        self.title = "GitHub PR Review - Interactive Mode"
        self.sub_title = f"Repository: {self.current_repo or 'Not selected'}"

        if self.current_repo:
            await self.load_prs()

    async def load_prs(self) -> None:
        """Load PRs for the current repository."""
        if not self.current_repo:
            return

        try:
            # Parse repo
            if "/" in self.current_repo:
                owner, repo = self.current_repo.split("/", 1)
            else:
                return

            # Load PRs
            self.prs = await asyncio.to_thread(
                self.github_client.get_open_prs, owner, repo, limit=50
            )

            # Update list
            pr_list = self.query_one("#pr-list", ListView)
            pr_list.clear()

            for pr in self.prs:
                pr_list.append(PRListItem(pr))

        except Exception as e:
            self.notify(f"Error loading PRs: {str(e)}", severity="error")

    async def handle_search(self, query: str) -> None:
        """Handle search query.

        Args:
            query: Search query string
        """
        try:
            # Try to parse as PR identifier
            owner, repo, pr_number = await asyncio.to_thread(
                self.pr_manager.parse_pr_identifier, query, self.current_repo
            )

            # Update current repo
            self.current_repo = f"{owner}/{repo}"
            self.sub_title = f"Repository: {self.current_repo}"

            # Load PR data
            pr_data = await asyncio.to_thread(
                self.pr_manager.fetch_pr_data, owner, repo, pr_number
            )

            # Load comments
            comments = await asyncio.to_thread(
                self.pr_manager.fetch_pr_comments,
                owner, repo, pr_number, self.filter_mode
            )

            # Update display
            self.current_pr = pr_data
            self.current_comments = comments

            details_view = self.query_one("#pr-details", PRDetailsView)
            details_view.update_pr(pr_data, comments)

            self.notify(f"Loaded PR #{pr_number}", severity="information")

        except Exception as e:
            self.notify(f"Search failed: {str(e)}", severity="error")

    def handle_filter_change(self, filter_mode: str) -> None:
        """Handle filter mode change.

        Args:
            filter_mode: New filter mode
        """
        self.filter_mode = filter_mode

        # Update details view
        details_view = self.query_one("#pr-details", PRDetailsView)
        details_view.update_filter(filter_mode)

        # Reload comments if PR is selected
        if self.current_pr:
            asyncio.create_task(self.reload_comments())

    async def reload_comments(self) -> None:
        """Reload comments for current PR with current filter."""
        if not self.current_pr or not self.current_repo:
            return

        try:
            owner, repo = self.current_repo.split("/", 1)
            pr_number = self.current_pr.get("number")

            comments = await asyncio.to_thread(
                self.pr_manager.fetch_pr_comments,
                owner, repo, pr_number, self.filter_mode
            )

            self.current_comments = comments

            details_view = self.query_one("#pr-details", PRDetailsView)
            details_view.update_pr(self.current_pr, comments)

        except Exception as e:
            self.notify(f"Error reloading comments: {str(e)}", severity="error")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle PR selection from list.

        Args:
            event: List selection event
        """
        if isinstance(event.item, PRListItem):
            pr_data = event.item.pr_data
            asyncio.create_task(
                self.handle_search(f"{self.current_repo}#{pr_data['number']}")
            )

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def action_refresh(self) -> None:
        """Refresh current view."""
        if self.current_repo:
            asyncio.create_task(self.load_prs())
        if self.current_pr:
            asyncio.create_task(self.reload_comments())
        self.notify("Refreshed", severity="information")

    def action_toggle_filter(self) -> None:
        """Toggle filter menu visibility."""
        self.show_filter_menu = not self.show_filter_menu

        details_container = self.query_one("#details-container")

        if self.show_filter_menu:
            # Add filter menu
            if not details_container.query("FilterMenu"):
                details_container.mount(self.filter_menu)
        else:
            # Remove filter menu
            for menu in details_container.query("FilterMenu"):
                menu.remove()

    def action_focus_search(self) -> None:
        """Focus the search input."""
        search_input = self.query_one("#search_input", Input)
        search_input.focus()

    def action_next_pr(self) -> None:
        """Navigate to next PR in list."""
        pr_list = self.query_one("#pr-list", ListView)
        pr_list.action_cursor_down()

    def action_prev_pr(self) -> None:
        """Navigate to previous PR in list."""
        pr_list = self.query_one("#pr-list", ListView)
        pr_list.action_cursor_up()

    def action_select_pr(self) -> None:
        """Select current PR from list."""
        pr_list = self.query_one("#pr-list", ListView)
        pr_list.action_select_cursor()

    def action_show_help(self) -> None:
        """Show help information."""
        help_text = """
[bold]Keyboard Shortcuts:[/bold]
  Q     - Quit application
  R     - Refresh PR list/comments
  F     - Toggle filter menu
  S     - Focus search bar
  J/K   - Navigate PR list
  Enter - View selected PR
  ?     - Show this help
  Ctrl+C - Copy PR URL to clipboard
        """
        self.notify(help_text, severity="information", timeout=10)

    def action_copy_url(self) -> None:
        """Copy current PR URL to clipboard."""
        if self.current_pr and self.current_repo:
            owner, repo = self.current_repo.split("/", 1)
            pr_number = self.current_pr.get("number")
            url = f"https://github.com/{owner}/{repo}/pull/{pr_number}"

            # Import clipboard manager
            from ..utils.clipboard import ClipboardManager
            clipboard = ClipboardManager()

            if clipboard.copy(url):
                self.notify(f"Copied: {url}", severity="information")
            else:
                self.notify("Failed to copy to clipboard", severity="error")


def run_tui(
    github_client: GitHubClient,
    pr_manager: PRManager,
    config_manager: ConfigManager,
    initial_repo: Optional[str] = None,
) -> None:
    """Run the TUI application.

    Args:
        github_client: GitHub API client
        pr_manager: PR manager instance
        config_manager: Configuration manager
        initial_repo: Initial repository to load
    """
    app = GhPrTUI(github_client, pr_manager, config_manager, initial_repo)
    app.run()
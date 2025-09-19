"""Interactive menu system for gh-pr TUI."""

from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass
from enum import Enum

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, Button, RadioSet, RadioButton, Select, Switch, Label
from textual.containers import Vertical, Horizontal, Grid
from textual.message import Message
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class MenuAction(Enum):
    """Available menu actions."""

    REFRESH = "refresh"
    FILTER = "filter"
    SORT = "sort"
    EXPORT = "export"
    COPY = "copy"
    OPEN_BROWSER = "open_browser"
    TOGGLE_CODE = "toggle_code"
    TOGGLE_RESOLVED = "toggle_resolved"
    SETTINGS = "settings"
    HELP = "help"
    QUIT = "quit"


@dataclass
class MenuItem:
    """Menu item definition."""

    label: str
    action: MenuAction
    shortcut: Optional[str] = None
    icon: Optional[str] = None
    enabled: bool = True
    description: Optional[str] = None


@dataclass
class KeyBinding:
    """Keyboard shortcut binding."""

    key: str
    action: MenuAction
    description: str
    configurable: bool = True


class ActionMenu(Widget):
    """Action menu widget with common PR operations."""

    DEFAULT_CSS = """
    ActionMenu {
        dock: top;
        height: auto;
        background: $surface;
        border-bottom: solid $primary;
        padding: 1 2;
    }

    ActionMenu Button {
        margin: 0 1;
    }
    """

    def __init__(self, on_action: Optional[Callable[[MenuAction], None]] = None):
        """Initialize action menu.

        Args:
            on_action: Callback when action is triggered
        """
        super().__init__()
        self.on_action = on_action

        # Define menu items
        self.menu_items = [
            MenuItem("🔄 Refresh", MenuAction.REFRESH, "R", "🔄"),
            MenuItem("🔍 Filter", MenuAction.FILTER, "F", "🔍"),
            MenuItem("📊 Sort", MenuAction.SORT, "S", "📊"),
            MenuItem("💾 Export", MenuAction.EXPORT, "E", "💾"),
            MenuItem("📋 Copy", MenuAction.COPY, "C", "📋"),
            MenuItem("🌐 Browser", MenuAction.OPEN_BROWSER, "O", "🌐"),
            MenuItem("⚙️ Settings", MenuAction.SETTINGS, ",", "⚙️"),
            MenuItem("❓ Help", MenuAction.HELP, "?", "❓"),
        ]

    def compose(self) -> ComposeResult:
        """Compose the action menu."""
        with Horizontal():
            for item in self.menu_items:
                if not item.enabled:
                    continue

                label = item.label
                if item.shortcut:
                    label = f"{item.label} [{item.shortcut}]"

                button = Button(
                    label,
                    id=f"action_{item.action.value}",
                    variant="default" if item.action != MenuAction.QUIT else "error",
                    disabled=not item.enabled,
                )
                yield button

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle action button press.

        Args:
            event: Button press event
        """
        if event.button.id and event.button.id.startswith("action_"):
            action_value = event.button.id.replace("action_", "")
            try:
                action = MenuAction(action_value)
                if self.on_action:
                    self.on_action(action)
            except ValueError:
                pass  # Invalid action value


class FilterOptionsMenu(Widget):
    """Advanced filter options menu."""

    DEFAULT_CSS = """
    FilterOptionsMenu {
        width: 40;
        height: auto;
        background: $surface;
        border: solid $border;
        padding: 1 2;
    }

    FilterOptionsMenu RadioSet {
        margin: 1 0;
    }

    FilterOptionsMenu Switch {
        margin: 1 0;
    }
    """

    class FilterChanged(Message):
        """Filter changed message."""

        def __init__(self, filters: Dict[str, Any]) -> None:
            """Initialize filter changed message.

            Args:
                filters: Current filter settings
            """
            super().__init__()
            self.filters = filters

    def __init__(self):
        """Initialize filter options menu."""
        super().__init__()

        # Current filter state
        self.filters = {
            "status": "all",  # all, unresolved, resolved
            "location": "all",  # all, current, outdated
            "author": None,  # Filter by specific author
            "has_suggestions": False,  # Only show comments with suggestions
            "needs_response": False,  # Only show comments needing response
            "show_system": False,  # Show system/bot comments
        }

    def compose(self) -> ComposeResult:
        """Compose the filter options menu."""
        yield Static("[bold]Filter Options[/bold]", classes="menu-title")

        # Comment status filter
        yield Label("Status:")
        with RadioSet(id="filter_status"):
            yield RadioButton("All Comments", value="all")
            yield RadioButton("Unresolved Only", value="unresolved")
            yield RadioButton("Resolved Only", value="resolved")

        # Comment location filter
        yield Label("Location:")
        with RadioSet(id="filter_location"):
            yield RadioButton("All Locations", value="all")
            yield RadioButton("Current Code", value="current")
            yield RadioButton("Outdated Code", value="outdated")

        # Additional filters
        yield Label("Additional Filters:")
        yield Switch("Has Suggestions", id="filter_suggestions")
        yield Switch("Needs Response", id="filter_needs_response")
        yield Switch("Show System Comments", id="filter_system")

        # Apply button
        yield Button("Apply Filters", id="apply_filters", variant="primary")

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle radio set change.

        Args:
            event: Radio set change event
        """
        if event.radio_set.id == "filter_status":
            self.filters["status"] = str(event.value)
        elif event.radio_set.id == "filter_location":
            self.filters["location"] = str(event.value)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle switch change.

        Args:
            event: Switch change event
        """
        if event.switch.id == "filter_suggestions":
            self.filters["has_suggestions"] = event.value
        elif event.switch.id == "filter_needs_response":
            self.filters["needs_response"] = event.value
        elif event.switch.id == "filter_system":
            self.filters["show_system"] = event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press.

        Args:
            event: Button press event
        """
        if event.button.id == "apply_filters":
            self.post_message(self.FilterChanged(self.filters.copy()))


class SortOptionsMenu(Widget):
    """Sort options menu for PR/comment ordering."""

    DEFAULT_CSS = """
    SortOptionsMenu {
        width: 35;
        height: auto;
        background: $surface;
        border: solid $border;
        padding: 1 2;
    }
    """

    SORT_OPTIONS = [
        ("newest", "Newest First"),
        ("oldest", "Oldest First"),
        ("most_comments", "Most Comments"),
        ("least_comments", "Least Comments"),
        ("recently_updated", "Recently Updated"),
        ("author", "By Author"),
        ("files_changed", "Files Changed"),
    ]

    class SortChanged(Message):
        """Sort changed message."""

        def __init__(self, sort_by: str, ascending: bool = True) -> None:
            """Initialize sort changed message.

            Args:
                sort_by: Sort field
                ascending: Sort direction
            """
            super().__init__()
            self.sort_by = sort_by
            self.ascending = ascending

    def __init__(self):
        """Initialize sort options menu."""
        super().__init__()
        self.current_sort = "newest"
        self.ascending = True

    def compose(self) -> ComposeResult:
        """Compose the sort options menu."""
        yield Static("[bold]Sort Options[/bold]", classes="menu-title")

        # Sort field selection
        yield Label("Sort By:")
        with RadioSet(id="sort_field"):
            for value, label in self.SORT_OPTIONS:
                yield RadioButton(label, value=value)

        # Sort direction
        yield Label("Direction:")
        yield Switch("Ascending Order", id="sort_ascending", value=True)

        # Apply button
        yield Button("Apply Sort", id="apply_sort", variant="primary")

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle radio set change.

        Args:
            event: Radio set change event
        """
        if event.radio_set.id == "sort_field":
            self.current_sort = str(event.value)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle switch change.

        Args:
            event: Switch change event
        """
        if event.switch.id == "sort_ascending":
            self.ascending = event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press.

        Args:
            event: Button press event
        """
        if event.button.id == "apply_sort":
            self.post_message(self.SortChanged(self.current_sort, self.ascending))


class ExportMenu(Widget):
    """Export options menu."""

    DEFAULT_CSS = """
    ExportMenu {
        width: 40;
        height: auto;
        background: $surface;
        border: solid $border;
        padding: 1 2;
    }
    """

    EXPORT_FORMATS = [
        ("markdown", "Markdown (.md)", "📝"),
        ("csv", "CSV (.csv)", "📊"),
        ("json", "JSON (.json)", "📄"),
        ("html", "HTML (.html)", "🌐"),
    ]

    class ExportRequested(Message):
        """Export requested message."""

        def __init__(self, format: str, options: Dict[str, Any]) -> None:
            """Initialize export requested message.

            Args:
                format: Export format
                options: Export options
            """
            super().__init__()
            self.format = format
            self.options = options

    def __init__(self):
        """Initialize export menu."""
        super().__init__()
        self.export_format = "markdown"
        self.options = {
            "include_code": True,
            "include_resolved": False,
            "include_outdated": False,
            "include_metadata": True,
        }

    def compose(self) -> ComposeResult:
        """Compose the export menu."""
        yield Static("[bold]Export Options[/bold]", classes="menu-title")

        # Format selection
        yield Label("Export Format:")
        with RadioSet(id="export_format"):
            for value, label, icon in self.EXPORT_FORMATS:
                yield RadioButton(f"{icon} {label}", value=value)

        # Export options
        yield Label("Include:")
        yield Switch("Code Context", id="include_code", value=True)
        yield Switch("Resolved Comments", id="include_resolved", value=False)
        yield Switch("Outdated Comments", id="include_outdated", value=False)
        yield Switch("Metadata", id="include_metadata", value=True)

        # Export button
        yield Button("Export", id="export_button", variant="primary")

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle radio set change.

        Args:
            event: Radio set change event
        """
        if event.radio_set.id == "export_format":
            self.export_format = str(event.value)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle switch change.

        Args:
            event: Switch change event
        """
        option_map = {
            "include_code": "include_code",
            "include_resolved": "include_resolved",
            "include_outdated": "include_outdated",
            "include_metadata": "include_metadata",
        }

        if event.switch.id in option_map:
            self.options[option_map[event.switch.id]] = event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press.

        Args:
            event: Button press event
        """
        if event.button.id == "export_button":
            self.post_message(self.ExportRequested(self.export_format, self.options.copy()))


class KeyBindingsDisplay(Widget):
    """Display keyboard shortcuts."""

    DEFAULT_CSS = """
    KeyBindingsDisplay {
        width: 50;
        height: auto;
        background: $surface;
        border: solid $border;
        padding: 1 2;
    }
    """

    # Default key bindings
    DEFAULT_BINDINGS = [
        KeyBinding("q", MenuAction.QUIT, "Quit application"),
        KeyBinding("r", MenuAction.REFRESH, "Refresh PR/comments"),
        KeyBinding("f", MenuAction.FILTER, "Toggle filter menu"),
        KeyBinding("s", MenuAction.SORT, "Toggle sort menu"),
        KeyBinding("e", MenuAction.EXPORT, "Export data"),
        KeyBinding("c", MenuAction.COPY, "Copy to clipboard"),
        KeyBinding("o", MenuAction.OPEN_BROWSER, "Open in browser"),
        KeyBinding("?", MenuAction.HELP, "Show help"),
        KeyBinding("j", MenuAction.NAVIGATE_DOWN, "Next item"),  # Navigation
        KeyBinding("k", MenuAction.NAVIGATE_UP, "Previous item"),  # Navigation
        KeyBinding("enter", MenuAction.SELECT, "Select item"),  # Navigation
        KeyBinding("/", MenuAction.SEARCH, "Search"),  # Search
        KeyBinding("tab", MenuAction.NEXT_PANE, "Next pane"),  # Navigation
        KeyBinding("shift+tab", MenuAction.PREV_PANE, "Previous pane"),  # Navigation
    ]

    def __init__(self, bindings: Optional[List[KeyBinding]] = None):
        """Initialize key bindings display.

        Args:
            bindings: Optional custom key bindings
        """
        super().__init__()
        self.bindings = bindings or self.DEFAULT_BINDINGS

    def render(self) -> Panel:
        """Render the key bindings display."""
        # Create table for key bindings
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("Key", style="bold yellow", no_wrap=True)
        table.add_column("Action", style="white")
        table.add_column("Description", style="dim")

        # Group bindings by category
        navigation_bindings = []
        action_bindings = []
        other_bindings = []

        for binding in self.bindings:
            if binding.key in ["j", "k", "enter", "tab", "shift+tab"]:
                navigation_bindings.append(binding)
            elif binding.action in [MenuAction.REFRESH, MenuAction.FILTER, MenuAction.SORT, MenuAction.EXPORT]:
                action_bindings.append(binding)
            else:
                other_bindings.append(binding)

        # Add navigation bindings
        if navigation_bindings:
            table.add_row("[dim]--- Navigation ---[/dim]", "", "", style="dim")
            for binding in navigation_bindings:
                table.add_row(binding.key.upper(), binding.action.value.title(), binding.description)

        # Add action bindings
        if action_bindings:
            table.add_row("[dim]--- Actions ---[/dim]", "", "", style="dim")
            for binding in action_bindings:
                table.add_row(binding.key.upper(), binding.action.value.title(), binding.description)

        # Add other bindings
        if other_bindings:
            table.add_row("[dim]--- Other ---[/dim]", "", "", style="dim")
            for binding in other_bindings:
                table.add_row(binding.key.upper(), binding.action.value.title(), binding.description)

        return Panel(
            table,
            title="⌨️ Keyboard Shortcuts",
            border_style="cyan",
            padding=(1, 2),
        )
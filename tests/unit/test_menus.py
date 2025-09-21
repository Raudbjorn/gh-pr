"""Unit tests for the interactive menu system."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from textual.widgets import Button, RadioSet, Switch

from src.gh_pr.ui.menus import (
    MenuAction,
    MenuItem,
    KeyBinding,
    ActionMenu,
    FilterOptionsMenu,
    SortOptionsMenu,
    ExportMenu,
    KeyBindingsDisplay,
)


class TestMenuItem:
    """Test the MenuItem dataclass."""

    def test_menu_item_creation(self):
        """Test MenuItem creation with all fields."""
        item = MenuItem(
            label="Test Item",
            action=MenuAction.REFRESH,
            shortcut="R",
            icon="🔄",
            enabled=True,
            description="Test description"
        )

        assert item.label == "Test Item"
        assert item.action == MenuAction.REFRESH
        assert item.shortcut == "R"
        assert item.icon == "🔄"
        assert item.enabled is True
        assert item.description == "Test description"

    def test_menu_item_defaults(self):
        """Test MenuItem with default values."""
        item = MenuItem(label="Test", action=MenuAction.HELP)

        assert item.label == "Test"
        assert item.action == MenuAction.HELP
        assert item.shortcut is None
        assert item.icon is None
        assert item.enabled is True
        assert item.description is None


class TestKeyBinding:
    """Test the KeyBinding dataclass."""

    def test_key_binding_creation(self):
        """Test KeyBinding creation."""
        binding = KeyBinding(
            key="q",
            action=MenuAction.QUIT,
            description="Quit application",
            configurable=False
        )

        assert binding.key == "q"
        assert binding.action == MenuAction.QUIT
        assert binding.description == "Quit application"
        assert binding.configurable is False

    def test_key_binding_defaults(self):
        """Test KeyBinding with default configurable value."""
        binding = KeyBinding(
            key="r",
            action=MenuAction.REFRESH,
            description="Refresh"
        )

        assert binding.configurable is True


class TestActionMenu:
    """Test the ActionMenu widget."""

    def test_action_menu_initialization(self):
        """Test ActionMenu initialization."""
        callback = Mock()
        menu = ActionMenu(on_action=callback)

        assert menu.on_action == callback
        assert len(menu.menu_items) > 0
        # Check that standard items are present
        item_actions = [item.action for item in menu.menu_items]
        assert MenuAction.REFRESH in item_actions
        assert MenuAction.FILTER in item_actions
        assert MenuAction.HELP in item_actions

    def test_action_menu_compose(self):
        """Test ActionMenu compose method - skipped as it requires Textual app context."""
        # This test requires a running Textual app context to work properly
        # It should be tested as part of integration tests instead
        pass

    @patch('src.gh_pr.ui.menus.Button')
    def test_action_menu_button_press(self, mock_button_class):
        """Test handling button press events."""
        callback = Mock()
        menu = ActionMenu(on_action=callback)

        # Create mock event
        mock_button = Mock()
        mock_button.id = "action_refresh"
        mock_event = Mock()
        mock_event.button = mock_button

        # Handle button press
        menu.on_button_pressed(mock_event)

        # Callback should be called with REFRESH action
        callback.assert_called_once_with(MenuAction.REFRESH)

    def test_action_menu_invalid_action(self):
        """Test handling invalid action ID."""
        callback = Mock()
        menu = ActionMenu(on_action=callback)

        # Create mock event with invalid action
        mock_button = Mock()
        mock_button.id = "action_invalid"
        mock_event = Mock()
        mock_event.button = mock_button

        # Should not raise exception
        menu.on_button_pressed(mock_event)
        # Callback should not be called
        callback.assert_not_called()

    def test_action_menu_no_button_id(self):
        """Test handling button with no ID."""
        callback = Mock()
        menu = ActionMenu(on_action=callback)

        # Create mock event with no button ID
        mock_button = Mock()
        mock_button.id = None
        mock_event = Mock()
        mock_event.button = mock_button

        # Should not raise exception
        menu.on_button_pressed(mock_event)
        # Callback should not be called
        callback.assert_not_called()

    def test_action_menu_malformed_button_id(self):
        """Test handling malformed button ID."""
        callback = Mock()
        menu = ActionMenu(on_action=callback)

        # Create mock event with malformed button ID
        mock_button = Mock()
        mock_button.id = "not_action_prefix"
        mock_event = Mock()
        mock_event.button = mock_button

        # Should not raise exception
        menu.on_button_pressed(mock_event)
        # Callback should not be called
        callback.assert_not_called()


class TestFilterOptionsMenu:
    """Test the FilterOptionsMenu widget."""

    def test_filter_options_initialization(self):
        """Test FilterOptionsMenu initialization."""
        menu = FilterOptionsMenu()

        assert menu.filters["status"] == "all"
        assert menu.filters["location"] == "all"
        assert menu.filters["has_suggestions"] is False
        assert menu.filters["needs_response"] is False

    def test_filter_radio_set_change(self):
        """Test handling radio set changes."""
        menu = FilterOptionsMenu()

        # Mock radio set event for status
        mock_radio_set = Mock()
        mock_radio_set.id = "filter_status"
        mock_event = Mock()
        mock_event.radio_set = mock_radio_set
        mock_event.value = "unresolved"

        menu.on_radio_set_changed(mock_event)
        assert menu.filters["status"] == "unresolved"

        # Mock radio set event for location
        mock_radio_set.id = "filter_location"
        mock_event.value = "outdated"

        menu.on_radio_set_changed(mock_event)
        assert menu.filters["location"] == "outdated"

    def test_filter_switch_change(self):
        """Test handling switch changes."""
        menu = FilterOptionsMenu()

        # Mock switch event
        mock_switch = Mock()
        mock_switch.id = "filter_suggestions"
        mock_event = Mock()
        mock_event.switch = mock_switch
        mock_event.value = True

        menu.on_switch_changed(mock_event)
        assert menu.filters["has_suggestions"] is True

    @patch.object(FilterOptionsMenu, 'post_message')
    def test_filter_apply_button(self, mock_post_message):
        """Test apply filters button."""
        menu = FilterOptionsMenu()
        menu.filters["status"] = "resolved"

        # Mock button event
        mock_button = Mock()
        mock_button.id = "apply_filters"
        mock_event = Mock()
        mock_event.button = mock_button

        menu.on_button_pressed(mock_event)

        # Should post FilterChanged message
        mock_post_message.assert_called_once()
        message = mock_post_message.call_args[0][0]
        assert message.filters["status"] == "resolved"

    def test_filter_invalid_radio_set(self):
        """Test handling unknown radio set ID."""
        menu = FilterOptionsMenu()
        original_filters = menu.filters.copy()

        # Mock radio set event with unknown ID
        mock_radio_set = Mock()
        mock_radio_set.id = "unknown_radio_set"
        mock_event = Mock()
        mock_event.radio_set = mock_radio_set
        mock_event.value = "some_value"

        # Should not raise exception and filters should remain unchanged
        menu.on_radio_set_changed(mock_event)
        assert menu.filters == original_filters

    def test_filter_invalid_switch(self):
        """Test handling unknown switch ID."""
        menu = FilterOptionsMenu()
        original_filters = menu.filters.copy()

        # Mock switch event with unknown ID
        mock_switch = Mock()
        mock_switch.id = "unknown_switch"
        mock_event = Mock()
        mock_event.switch = mock_switch
        mock_event.value = True

        # Should not raise exception and filters should remain unchanged
        menu.on_switch_changed(mock_event)
        assert menu.filters == original_filters

    def test_filter_invalid_button(self):
        """Test handling unknown button ID."""
        menu = FilterOptionsMenu()

        # Mock button event with unknown ID
        mock_button = Mock()
        mock_button.id = "unknown_button"
        mock_event = Mock()
        mock_event.button = mock_button

        # Should not raise exception
        menu.on_button_pressed(mock_event)


class TestSortOptionsMenu:
    """Test the SortOptionsMenu widget."""

    def test_sort_options_initialization(self):
        """Test SortOptionsMenu initialization."""
        menu = SortOptionsMenu()

        assert menu.current_sort == "newest"
        assert menu.ascending is True
        assert len(menu.SORT_OPTIONS) > 0

    def test_sort_radio_set_change(self):
        """Test handling sort field changes."""
        menu = SortOptionsMenu()

        # Mock radio set event with pressed button
        mock_radio_set = Mock()
        mock_radio_set.id = "sort_field"
        mock_pressed = Mock()
        mock_pressed.id = "sort_most_comments"
        mock_event = Mock()
        mock_event.radio_set = mock_radio_set
        mock_event.pressed = mock_pressed

        menu.on_radio_set_changed(mock_event)
        assert menu.current_sort == "most_comments"

    def test_sort_direction_change(self):
        """Test handling sort direction changes."""
        menu = SortOptionsMenu()

        # Mock switch event
        mock_switch = Mock()
        mock_switch.id = "sort_ascending"
        mock_event = Mock()
        mock_event.switch = mock_switch
        mock_event.value = False

        menu.on_switch_changed(mock_event)
        assert menu.ascending is False

    @patch.object(SortOptionsMenu, 'post_message')
    def test_sort_apply_button(self, mock_post_message):
        """Test apply sort button."""
        menu = SortOptionsMenu()
        menu.current_sort = "author"
        menu.ascending = False

        # Mock button event
        mock_button = Mock()
        mock_button.id = "apply_sort"
        mock_event = Mock()
        mock_event.button = mock_button

        menu.on_button_pressed(mock_event)

        # Should post SortChanged message
        mock_post_message.assert_called_once()
        message = mock_post_message.call_args[0][0]
        assert message.sort_by == "author"
        assert message.ascending is False

    def test_sort_invalid_radio_set(self):
        """Test handling unknown radio set ID."""
        menu = SortOptionsMenu()
        original_sort = menu.current_sort

        # Mock radio set event with unknown ID
        mock_radio_set = Mock()
        mock_radio_set.id = "unknown_sort_field"
        mock_event = Mock()
        mock_event.radio_set = mock_radio_set
        mock_event.value = "invalid_value"

        # Should not raise exception and sort should remain unchanged
        menu.on_radio_set_changed(mock_event)
        assert menu.current_sort == original_sort

    def test_sort_invalid_switch(self):
        """Test handling unknown switch ID."""
        menu = SortOptionsMenu()
        original_ascending = menu.ascending

        # Mock switch event with unknown ID
        mock_switch = Mock()
        mock_switch.id = "unknown_switch"
        mock_event = Mock()
        mock_event.switch = mock_switch
        mock_event.value = False

        # Should not raise exception and ascending should remain unchanged
        menu.on_switch_changed(mock_event)
        assert menu.ascending == original_ascending


class TestExportMenu:
    """Test the ExportMenu widget."""

    def test_export_menu_initialization(self):
        """Test ExportMenu initialization."""
        menu = ExportMenu()

        assert menu.export_format == "markdown"
        assert menu.options["include_code"] is True
        assert menu.options["include_resolved"] is False
        assert len(menu.EXPORT_FORMATS) > 0

    def test_export_format_change(self):
        """Test handling export format changes."""
        menu = ExportMenu()

        # Mock radio set event with pressed button
        mock_radio_set = Mock()
        mock_radio_set.id = "export_format"
        mock_pressed = Mock()
        mock_pressed.id = "fmt_json"
        mock_event = Mock()
        mock_event.radio_set = mock_radio_set
        mock_event.pressed = mock_pressed

        menu.on_radio_set_changed(mock_event)
        assert menu.export_format == "json"

    @pytest.mark.parametrize("switch_id,value", [
        ("include_code", False),
        ("include_resolved", True),
        ("include_outdated", True),
        ("include_metadata", False),
    ])
    def test_export_options_change(self, switch_id, value):
        """Test handling export option changes."""
        menu = ExportMenu()

        mock_switch = Mock()
        mock_switch.id = switch_id
        mock_event = Mock()
        mock_event.switch = mock_switch
        mock_event.value = value

        menu.on_switch_changed(mock_event)
        assert menu.options[switch_id] == value

    def test_export_invalid_switch(self):
        """Test handling invalid switch ID."""
        menu = ExportMenu()

        # Test invalid switch id
        invalid_switch_id = "invalid_option"
        mock_switch = Mock()
        mock_switch.id = invalid_switch_id
        mock_event = Mock()
        mock_event.switch = mock_switch
        mock_event.value = True

        # Capture current options before the event
        options_before = menu.options.copy()
        try:
            menu.on_switch_changed(mock_event)
        except Exception as e:
            assert False, f"on_switch_changed raised an exception for invalid switch id: {e}"
        # Ensure options dict is unchanged for invalid key
        assert menu.options == options_before

    @patch.object(ExportMenu, 'post_message')
    def test_export_button(self, mock_post_message):
        """Test export button."""
        menu = ExportMenu()
        menu.export_format = "csv"
        menu.options["include_resolved"] = True

        # Mock button event
        mock_button = Mock()
        mock_button.id = "export_button"
        mock_event = Mock()
        mock_event.button = mock_button

        menu.on_button_pressed(mock_event)

        # Should post ExportRequested message
        mock_post_message.assert_called_once()
        message = mock_post_message.call_args[0][0]
        assert message.format == "csv"
        assert message.options["include_resolved"] is True


class TestKeyBindingsDisplay:
    """Test the KeyBindingsDisplay widget."""

    def test_key_bindings_initialization(self):
        """Test KeyBindingsDisplay initialization."""
        display = KeyBindingsDisplay()

        assert len(display.bindings) > 0
        # Check for essential bindings
        binding_keys = [b.key for b in display.bindings]
        assert "q" in binding_keys
        assert "r" in binding_keys
        assert "?" in binding_keys

    def test_custom_bindings(self):
        """Test with custom key bindings."""
        custom_bindings = [
            KeyBinding("x", MenuAction.QUIT, "Exit"),
            KeyBinding("u", MenuAction.REFRESH, "Update"),
        ]

        display = KeyBindingsDisplay(bindings=custom_bindings)
        assert len(display.bindings) == 2
        assert display.bindings[0].key == "x"
        assert display.bindings[1].key == "u"

    def test_render_panel(self):
        """Test rendering the bindings panel."""
        display = KeyBindingsDisplay()
        panel = display.render()

        # Should return a Panel
        from rich.panel import Panel
        assert isinstance(panel, Panel)
        assert panel.title == "⌨️ Keyboard Shortcuts"
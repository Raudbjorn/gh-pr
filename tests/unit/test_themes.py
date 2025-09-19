"""Unit tests for the theme system."""

import pytest
from rich.theme import Theme
from rich.style import Style

from src.gh_pr.ui.themes import ColorScheme, ThemeManager


class TestColorScheme:
    """Test the ColorScheme dataclass."""

    def test_default_color_scheme(self):
        """Test default color scheme initialization."""
        scheme = ColorScheme()

        # Check primary colors
        assert scheme.primary == "#007ACC"
        assert scheme.success == "#28A745"
        assert scheme.error == "#DC3545"

        # Check background colors
        assert scheme.bg_primary == "#1E1E1E"
        assert scheme.bg_surface == "#252526"

        # Check text colors
        assert scheme.text_primary == "#FFFFFF"
        assert scheme.text_muted == "#808080"

    def test_custom_color_scheme(self):
        """Test custom color scheme initialization."""
        scheme = ColorScheme(
            primary="#FF0000",
            success="#00FF00",
            bg_primary="#000000"
        )

        assert scheme.primary == "#FF0000"
        assert scheme.success == "#00FF00"
        assert scheme.bg_primary == "#000000"
        # Other colors should still have defaults
        assert scheme.error == "#DC3545"


class TestThemeManager:
    """Test the ThemeManager class."""

    def test_default_theme_initialization(self):
        """Test default theme manager initialization."""
        manager = ThemeManager()

        assert manager.current_theme_name == "default"
        assert isinstance(manager.color_scheme, ColorScheme)
        assert manager.color_scheme.primary == "#007ACC"

    def test_predefined_theme_loading(self):
        """Test loading predefined themes."""
        manager = ThemeManager(theme_name="dark")

        assert manager.current_theme_name == "dark"
        assert manager.color_scheme.primary == "#0D6EFD"
        assert manager.color_scheme.bg_primary == "#0D1117"

    def test_invalid_theme_fallback(self):
        """Test fallback to default for invalid theme."""
        manager = ThemeManager(theme_name="nonexistent")

        # Should fallback to default
        assert manager.color_scheme.primary == "#007ACC"

    def test_custom_color_overrides(self):
        """Test custom color overrides."""
        custom_colors = {
            "primary": "#FF0000",
            "success": "#00FF00",
            "nonexistent_attr": "#IGNORED"  # Should be ignored
        }

        manager = ThemeManager(custom_colors=custom_colors)

        assert manager.color_scheme.primary == "#FF0000"
        assert manager.color_scheme.success == "#00FF00"
        # Other colors should remain default
        assert manager.color_scheme.error == "#DC3545"

    def test_get_rich_theme(self):
        """Test Rich theme generation."""
        manager = ThemeManager()
        rich_theme = manager.get_rich_theme()

        assert isinstance(rich_theme, Theme)
        # Check that styles are created
        assert "primary" in rich_theme.styles
        assert "success" in rich_theme.styles
        assert "pr.open" in rich_theme.styles
        assert "comment.resolved" in rich_theme.styles

    def test_get_textual_css_variables(self):
        """Test Textual CSS variable generation."""
        manager = ThemeManager()
        css_vars = manager.get_textual_css_variables()

        assert isinstance(css_vars, dict)
        assert "$primary" in css_vars
        assert "$background" in css_vars
        assert "$text" in css_vars
        assert css_vars["$primary"] == "#007ACC"

    def test_switch_theme(self):
        """Test theme switching."""
        manager = ThemeManager()

        # Start with default
        assert manager.color_scheme.primary == "#007ACC"

        # Switch to dark
        manager.switch_theme("dark")
        assert manager.current_theme_name == "dark"
        assert manager.color_scheme.primary == "#0D6EFD"

        # Switch to monokai
        manager.switch_theme("monokai")
        assert manager.current_theme_name == "monokai"
        assert manager.color_scheme.primary == "#66D9EF"

    def test_get_available_themes(self):
        """Test getting available theme list."""
        manager = ThemeManager()
        themes = manager.get_available_themes()

        assert isinstance(themes, list)
        assert "default" in themes
        assert "dark" in themes
        assert "light" in themes
        assert "monokai" in themes
        assert "dracula" in themes
        assert "github" in themes

    def test_export_css(self):
        """Test CSS export functionality."""
        manager = ThemeManager()
        css = manager.export_css()

        assert isinstance(css, str)
        assert ":root {" in css
        assert "$primary: #007ACC;" in css
        assert "$background: #1E1E1E;" in css
        assert "}" in css

    def test_export_dict(self):
        """Test dictionary export functionality."""
        manager = ThemeManager()
        color_dict = manager.export_dict()

        assert isinstance(color_dict, dict)
        assert "primary" in color_dict
        assert "success" in color_dict
        assert "bg_primary" in color_dict
        assert color_dict["primary"] == "#007ACC"

    def test_all_predefined_themes_valid(self):
        """Test that all predefined themes can be loaded."""
        manager = ThemeManager()
        themes = manager.get_available_themes()

        for theme_name in themes:
            manager.switch_theme(theme_name)
            # Should not raise any exceptions
            assert manager.current_theme_name == theme_name
            assert isinstance(manager.color_scheme, ColorScheme)
            # Test that theme can generate Rich theme
            rich_theme = manager.get_rich_theme()
            assert isinstance(rich_theme, Theme)
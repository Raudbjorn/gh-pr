"""Theme system for gh-pr TUI with customizable color schemes."""

from typing import Dict, Any, Optional, ClassVar
from dataclasses import dataclass, replace
import re
from rich.theme import Theme
from rich.style import Style


@dataclass
class ColorScheme:
    """Color scheme definition for the TUI."""

    # Primary colors
    primary: str = "#007ACC"          # Blue
    secondary: str = "#6C757D"        # Gray
    success: str = "#28A745"          # Green
    warning: str = "#FFC107"          # Yellow
    error: str = "#DC3545"            # Red
    info: str = "#17A2B8"             # Cyan

    # Background colors
    bg_primary: str = "#1E1E1E"       # Dark background
    bg_secondary: str = "#2D2D2D"     # Slightly lighter
    bg_surface: str = "#252526"       # Surface/card background

    # Text colors
    text_primary: str = "#FFFFFF"     # Primary text
    text_secondary: str = "#B0B0B0"   # Secondary text
    text_muted: str = "#808080"       # Muted text

    # Specific elements
    border: str = "#3C3C3C"           # Border color
    highlight: str = "#094771"        # Highlight background
    link: str = "#3794FF"              # Link color

    # PR states
    pr_open: str = "#28A745"          # Open PR
    pr_closed: str = "#DC3545"        # Closed PR
    pr_merged: str = "#6F42C1"        # Merged PR
    pr_draft: str = "#6C757D"         # Draft PR

    # Comment states
    comment_resolved: str = "#28A745"  # Resolved comment
    comment_unresolved: str = "#FFC107"  # Unresolved comment
    comment_outdated: str = "#6C757D"   # Outdated comment

    # Check states
    check_success: str = "#28A745"    # Check passed
    check_failure: str = "#DC3545"    # Check failed
    check_pending: str = "#FFC107"    # Check pending
    check_neutral: str = "#6C757D"    # Check neutral/skipped


class ThemeManager:
    """Manages themes and color schemes for the TUI."""

    # Predefined themes
    THEMES: ClassVar[Dict[str, Any]] = {
        "default": ColorScheme(),
        "dark": ColorScheme(
            primary="#0D6EFD",
            bg_primary="#0D1117",
            bg_secondary="#161B22",
            bg_surface="#21262D",
            text_primary="#C9D1D9",
            text_secondary="#8B949E",
            border="#30363D",
            highlight="#1F6FEB",
        ),
        "light": ColorScheme(
            primary="#0969DA",
            bg_primary="#FFFFFF",
            bg_secondary="#F6F8FA",
            bg_surface="#FFFFFF",
            text_primary="#24292F",
            text_secondary="#57606A",
            text_muted="#6E7781",
            border="#D0D7DE",
            highlight="#DDF4FF",
            pr_open="#1A7F37",
            pr_closed="#CF222E",
            pr_merged="#8250DF",
        ),
        "monokai": ColorScheme(
            primary="#66D9EF",
            secondary="#75715E",
            success="#A6E22E",
            warning="#E6DB74",
            error="#F92672",
            info="#AE81FF",
            bg_primary="#272822",
            bg_secondary="#3E3D32",
            bg_surface="#3E3D32",
            text_primary="#F8F8F2",
            text_secondary="#CFCFC2",
            border="#49483E",
            highlight="#49483E",
        ),
        "dracula": ColorScheme(
            primary="#BD93F9",
            secondary="#6272A4",
            success="#50FA7B",
            warning="#F1FA8C",
            error="#FF5555",
            info="#8BE9FD",
            bg_primary="#282A36",
            bg_secondary="#343746",
            bg_surface="#44475A",
            text_primary="#F8F8F2",
            text_secondary="#BFBFBF",
            border="#6272A4",
            highlight="#44475A",
            link="#8BE9FD",
        ),
        "github": ColorScheme(
            primary="#0366D6",
            secondary="#586069",
            success="#28A745",
            warning="#FFC107",
            error="#D73A49",
            info="#0366D6",
            bg_primary="#FFFFFF",
            bg_secondary="#FAFBFC",
            bg_surface="#F6F8FA",
            text_primary="#24292E",
            text_secondary="#586069",
            text_muted="#6A737D",
            border="#E1E4E8",
            highlight="#F6F8FA",
            link="#0366D6",
        ),
    }

    def __init__(self, theme_name: str = "default", custom_colors: Optional[Dict[str, str]] = None):
        """Initialize theme manager.

        Args:
            theme_name: Name of predefined theme to use
            custom_colors: Optional custom color overrides
        """
        self.current_theme_name = theme_name
        self.color_scheme = self._load_theme(theme_name)

        # Apply custom color overrides
        if custom_colors:
            for key, value in custom_colors.items():
                if hasattr(self.color_scheme, key):
                    if self._validate_color(value):
                        setattr(self.color_scheme, key, value)
                    else:
                        print(f"Warning: Invalid color value '{value}' for key '{key}'")

    def _validate_color(self, color: str) -> bool:
        """Validate color format.

        Args:
            color: Color value to validate

        Returns:
            True if valid color format
        """
        if not isinstance(color, str):
            return False

        # Allow common color names
        valid_names = {'black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white',
                       'gray', 'grey', 'transparent', 'none'}
        if color.lower() in valid_names:
            return True

        # Check hex color format (#RGB, #RRGGBB, #RRGGBBAA)
        hex_pattern = r'^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$'
        if re.match(hex_pattern, color):
            return True

        # Check rgb/rgba format
        rgb_pattern = r'^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+(\s*,\s*[0-9.]+)?\s*\)$'
        if re.match(rgb_pattern, color):
            return True

        return False

    def _load_theme(self, theme_name: str) -> ColorScheme:
        """Load a theme by name.

        Args:
            theme_name: Name of theme to load

        Returns:
            ColorScheme instance
        """
        base_theme = self.THEMES.get(theme_name, self.THEMES["default"])
        # Return a copy to avoid modifying the original
        return replace(base_theme)

    def get_rich_theme(self) -> Theme:
        """Get Rich theme object for terminal rendering.

        Returns:
            Rich Theme object
        """
        cs = self.color_scheme
        return Theme({
            # Base styles
            "primary": Style(color=cs.primary),
            "secondary": Style(color=cs.secondary),
            "success": Style(color=cs.success),
            "warning": Style(color=cs.warning),
            "error": Style(color=cs.error),
            "info": Style(color=cs.info),

            # Text styles
            "text": Style(color=cs.text_primary),
            "text.secondary": Style(color=cs.text_secondary),
            "text.muted": Style(color=cs.text_muted, dim=True),
            "link": Style(color=cs.link, underline=True),

            # PR states
            "pr.open": Style(color=cs.pr_open, bold=True),
            "pr.closed": Style(color=cs.pr_closed, bold=True),
            "pr.merged": Style(color=cs.pr_merged, bold=True),
            "pr.draft": Style(color=cs.pr_draft, italic=True),

            # Comment states
            "comment.resolved": Style(color=cs.comment_resolved),
            "comment.unresolved": Style(color=cs.comment_unresolved),
            "comment.outdated": Style(color=cs.comment_outdated, dim=True),

            # Check states
            "check.success": Style(color=cs.check_success),
            "check.failure": Style(color=cs.check_failure),
            "check.pending": Style(color=cs.check_pending),
            "check.neutral": Style(color=cs.check_neutral),

            # UI elements
            "border": Style(color=cs.border),
            "highlight": Style(bgcolor=cs.highlight),
            "header": Style(color=cs.text_primary, bold=True),
            "footer": Style(color=cs.text_secondary, dim=True),
            "title": Style(color=cs.primary, bold=True),
            "subtitle": Style(color=cs.secondary),

            # Panels and containers
            "panel.border": Style(color=cs.border),
            "panel.title": Style(color=cs.primary, bold=True),
            "container": Style(bgcolor=cs.bg_surface),

            # Status indicators
            "status.active": Style(color=cs.success),
            "status.inactive": Style(color=cs.text_muted),
            "status.error": Style(color=cs.error, bold=True),

            # Buttons
            "button": Style(color=cs.text_primary, bgcolor=cs.bg_secondary),
            "button.primary": Style(color=cs.text_primary, bgcolor=cs.primary),
            "button.danger": Style(color=cs.text_primary, bgcolor=cs.error),
            "button.success": Style(color=cs.text_primary, bgcolor=cs.success),

            # Code highlighting
            "code": Style(color=cs.info, bgcolor=cs.bg_surface),
            "code.keyword": Style(color=cs.primary, bold=True),
            "code.string": Style(color=cs.success),
            "code.comment": Style(color=cs.text_muted, italic=True),
            "code.function": Style(color=cs.warning),

            # Markdown elements
            "markdown.h1": Style(color=cs.primary, bold=True, underline=True),
            "markdown.h2": Style(color=cs.primary, bold=True),
            "markdown.h3": Style(color=cs.secondary, bold=True),
            "markdown.bold": Style(bold=True),
            "markdown.italic": Style(italic=True),
            "markdown.code": Style(color=cs.info, bgcolor=cs.bg_surface),
            "markdown.link": Style(color=cs.link, underline=True),
        })

    def get_textual_css_variables(self) -> Dict[str, str]:
        """Get CSS variables for Textual theming.

        Returns:
            Dictionary of CSS variable names to color values
        """
        cs = self.color_scheme
        return {
            # Primary colors
            "$primary": cs.primary,
            "$secondary": cs.secondary,
            "$success": cs.success,
            "$warning": cs.warning,
            "$error": cs.error,
            "$info": cs.info,

            # Backgrounds
            "$background": cs.bg_primary,
            "$surface": cs.bg_surface,
            "$panel": cs.bg_secondary,

            # Text
            "$text": cs.text_primary,
            "$text-muted": cs.text_muted,
            "$text-disabled": cs.text_muted,

            # Borders
            "$border": cs.border,
            "$border-focus": cs.primary,

            # Interactive states
            "$hover": cs.highlight,
            "$active": cs.primary,
            "$focus": cs.primary,
        }

    def switch_theme(self, theme_name: str) -> None:
        """Switch to a different theme.

        Args:
            theme_name: Name of theme to switch to
        """
        self.current_theme_name = theme_name
        self.color_scheme = self._load_theme(theme_name)

    def get_available_themes(self) -> list:
        """Get list of available theme names.

        Returns:
            List of theme names
        """
        return list(self.THEMES.keys())

    def export_css(self) -> str:
        """Export theme as CSS variables.

        Returns:
            CSS string with theme variables
        """
        css_vars = self.get_textual_css_variables()
        css_lines = [":root {"]
        css_lines.extend(
            f"  {var_name}: {color_value};"
            for var_name, color_value in css_vars.items()
        )
        css_lines.append("}")
        return "\n".join(css_lines)

    def export_dict(self) -> Dict[str, str]:
        """Export current color scheme as dictionary.

        Returns:
            Dictionary of color values
        """
        return {
            key: getattr(self.color_scheme, key)
            for key in dir(self.color_scheme)
            if not key.startswith("_") and isinstance(getattr(self.color_scheme, key), str)
        }
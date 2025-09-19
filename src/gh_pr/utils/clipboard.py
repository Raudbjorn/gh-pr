"""Clipboard management with WSL2 support."""

import shutil
import subprocess
from typing import Optional


class ClipboardManager:
    """Manage clipboard operations."""

    def __init__(self):
        """Initialize ClipboardManager."""
        self.clipboard_cmd = self._detect_clipboard_command()

    def _detect_clipboard_command(self) -> Optional[list[str]]:
        """
        Detect available clipboard command.

        Returns:
            Clipboard command as list of arguments or None
        """
        # Check for WSL
        try:
            with open("/proc/version") as f:
                if "microsoft" in f.read().lower():
                    # WSL detected
                    if shutil.which("clip.exe"):
                        return ["clip.exe"]
                    if shutil.which("/mnt/c/Windows/System32/clip.exe"):
                        return ["/mnt/c/Windows/System32/clip.exe"]
        except FileNotFoundError:
            pass

        # Check for Wayland
        if shutil.which("wl-copy"):
            return ["wl-copy"]

        # Check for X11
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard"]

        if shutil.which("xsel"):
            return ["xsel", "--clipboard", "--input"]

        # Check for macOS
        if shutil.which("pbcopy"):
            return ["pbcopy"]

        return None

    def copy(self, text: str) -> bool:
        """
        Copy text to clipboard.

        Args:
            text: Text to copy

        Returns:
            True if successful
        """
        if not self.clipboard_cmd:
            return False

        try:
            # Command list is pre-validated and safe - no user input injection possible
            # Using a list (not string) prevents shell injection attacks
            process = subprocess.Popen(
                self.clipboard_cmd,  # This is safe - it's a list, not a string
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            process.communicate(input=text.encode("utf-8"))
            return process.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def is_available(self) -> bool:
        """
        Check if clipboard is available.

        Returns:
            True if clipboard command is available
        """
        return self.clipboard_cmd is not None


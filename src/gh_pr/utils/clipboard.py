"""Clipboard management with WSL2 support."""

import shlex
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
            # Ensure command arguments are properly escaped for security
            # Using list prevents shell injection, but extra safety with timeout
            process = subprocess.Popen(
                self.clipboard_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,  # Explicitly ensure no shell is used
                timeout=5,  # Add timeout to prevent hanging
            )
            stdout, stderr = process.communicate(input=text.encode("utf-8"), timeout=5)
            return process.returncode == 0
        except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            return False

    def is_available(self) -> bool:
        """
        Check if clipboard is available.

        Returns:
            True if clipboard command is available
        """
        return self.clipboard_cmd is not None


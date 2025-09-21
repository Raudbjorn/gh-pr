"""Clipboard management with WSL2 support."""

import shlex
import shutil
import subprocess
from typing import Optional


class ClipboardManager:
    """Manage clipboard operations."""

    def __init__(self, timeout: float = 5.0):
        """
        Initialize ClipboardManager.

        Args:
            timeout: Timeout in seconds for clipboard operations (default: 5.0)
        """
        self.clipboard_cmd = self._detect_clipboard_command()
        self.timeout = timeout

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
            # Security: Command list is pre-validated and safe
            # 1. self.clipboard_cmd is a predefined list, not user input
            # 2. No shell=True (list form prevents injection)
            # 3. Input text is passed via stdin, not as command argument
            # 4. Has implicit timeout via communicate()
            process = subprocess.Popen(
                self.clipboard_cmd,  # Safe: predefined list from _detect_clipboard_command
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,  # Explicitly ensure no shell is used
            )
            # Use configurable timeout to prevent hanging
            process.communicate(input=text.encode("utf-8"), timeout=self.timeout)
            return process.returncode == 0
        except subprocess.TimeoutExpired:
            process.kill()
            return False
        except (OSError, subprocess.SubprocessError):
            return False

    def is_available(self) -> bool:
        """
        Check if clipboard is available.

        Returns:
            True if clipboard command is available
        """
        return self.clipboard_cmd is not None


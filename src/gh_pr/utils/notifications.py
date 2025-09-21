"""
Desktop notification support for gh-pr.

Provides cross-platform desktop notifications with fallback
to terminal notifications if desktop support is unavailable.
"""

import asyncio
import logging
import os
import sys
from typing import Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

logger = logging.getLogger(__name__)

# Platform-specific notification commands
NOTIFY_COMMANDS = {
    'darwin': [  # macOS
        'osascript', '-e',
        'display notification "{message}" with title "{title}" subtitle "{subtitle}"'
    ],
    'linux': {
        'notify-send': ['notify-send', '--urgency=normal', '{title}', '{message}'],
        'kdialog': ['kdialog', '--title', '{title}', '--passivepopup', '{message}', '5'],
        'zenity': ['zenity', '--notification', '--text="{title}\\n{message}"']
    }
}


@dataclass
class NotificationConfig:
    """Notification configuration."""

    enabled: bool = True
    sound: bool = False
    timeout: int = 5  # seconds
    urgency: str = 'normal'  # low, normal, critical
    icon_path: Optional[Path] = None
    fallback_to_terminal: bool = True


class NotificationManager:
    """
    Manages desktop notifications across platforms.

    Provides unified interface for sending notifications with
    automatic platform detection and fallback mechanisms.
    """

    def __init__(self, config: Optional[NotificationConfig] = None):
        """
        Initialize notification manager.

        Args:
            config: Notification configuration
        """
        self.config = config or NotificationConfig()
        self._platform = sys.platform
        self._notifier = None

        # Try to import plyer for cross-platform support
        try:
            from plyer import notification as plyer_notification
            self._plyer = plyer_notification
            self._use_plyer = True
            logger.debug("Using plyer for notifications")
        except ImportError:
            self._plyer = None
            self._use_plyer = False
            logger.debug("Plyer not available, using platform-specific commands")

        # Detect available notification command on Linux
        if self._platform == 'linux' and not self._use_plyer:
            self._detect_linux_notifier()

    def _detect_linux_notifier(self) -> None:
        """Detect available notification command on Linux."""
        for cmd_name in NOTIFY_COMMANDS.get('linux', {}).keys():
            if shutil.which(cmd_name):
                self._notifier = cmd_name
                logger.debug(f"Using {cmd_name} for Linux notifications")
                break

    async def notify(
        self,
        title: str,
        message: str,
        subtitle: str = "",
        icon: Optional[str] = None,
        urgency: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Send a desktop notification.

        Args:
            title: Notification title
            message: Notification message
            subtitle: Optional subtitle
            icon: Optional icon path
            urgency: Urgency level (low, normal, critical)
            **kwargs: Additional platform-specific parameters

        Returns:
            True if notification was sent successfully
        """
        if not self.config.enabled:
            return False

        try:
            # Try plyer first if available
            if self._use_plyer and self._plyer:
                return self._notify_with_plyer(title, message, icon)

            # Fall back to platform-specific commands
            if self._platform == 'darwin':
                return await self._notify_macos(title, message, subtitle)
            elif self._platform == 'linux':
                return await self._notify_linux(title, message, urgency or self.config.urgency)
            elif self._platform.startswith('win'):
                return await self._notify_windows(title, message, icon)
            else:
                logger.warning(f"Unsupported platform for notifications: {self._platform}")

                if self.config.fallback_to_terminal:
                    return self._notify_terminal(title, message)

                return False

        except Exception as e:
            logger.error(f"Notification error: {e}", exc_info=True)

            if self.config.fallback_to_terminal:
                return self._notify_terminal(title, message)

            return False

    def _notify_with_plyer(
        self,
        title: str,
        message: str,
        icon: Optional[str] = None
    ) -> bool:
        """
        Send notification using plyer library.

        Args:
            title: Notification title
            message: Notification message
            icon: Optional icon path

        Returns:
            True if successful
        """
        try:
            kwargs = {
                'title': title,
                'message': message,
                'timeout': self.config.timeout
            }

            if icon or self.config.icon_path:
                kwargs['app_icon'] = str(icon or self.config.icon_path)

            self._plyer.notify(**kwargs)
            return True

        except Exception as e:
            logger.debug(f"Plyer notification failed: {e}")
            return False

    def _as_quote(self, s: str) -> str:
        # Escape backslashes and double quotes for AppleScript string literals
        return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'

    async def _notify_macos(
        self,
        title: str,
        message: str,
        subtitle: str = ""
    ) -> bool:
        """
        Send notification on macOS using osascript.

        Args:
            title: Notification title
            message: Notification message
            subtitle: Optional subtitle

        Returns:
            True if successful
        """
        try:
            # Build AppleScript with proper quoting
            script = f'display notification {self._as_quote(message)} with title {self._as_quote(title)}'
            if subtitle:
                script += f' subtitle {self._as_quote(subtitle)}'

            if self.config.sound:
                script += ' sound name "default"'

            # Use async subprocess to avoid blocking the event loop
            process = await asyncio.create_subprocess_exec(
                'osascript', '-e', script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                # Wait for process with timeout
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=5.0
                )

                return process.returncode == 0

            except asyncio.TimeoutError:
                # Kill process if timeout
                process.kill()
                await process.wait()
                logger.debug("macOS notification timed out")
                return False

        except Exception as e:
            logger.debug(f"macOS notification failed: {e}")
            return False
    async def _notify_linux(
        self,
        title: str,
        message: str,
        urgency: str = 'normal'
    ) -> bool:
        """
        Send notification on Linux.

        Args:
            title: Notification title
            message: Notification message
            urgency: Urgency level

        Returns:
            True if successful
        """
        if not self._notifier:
            logger.debug("No Linux notifier available")
            return False

        try:
            # Security: Commands are from hardcoded NOTIFY_COMMANDS dictionary
            # Title and message are user input but used with shell=False (default)
            # This prevents shell injection as arguments are passed directly to the process
            commands = NOTIFY_COMMANDS['linux'][self._notifier]
            cmd = []

            # Replace placeholders with user input
            # Safe because we use subprocess with shell=False (default)
            for part in commands:
                if '{title}' in part:
                    cmd.append(part.format(title=title))
                elif '{message}' in part:
                    cmd.append(part.format(message=message))
                else:
                    cmd.append(part)

            # Add urgency for notify-send
            if self._notifier == 'notify-send':
                cmd[2] = f'--urgency={urgency}'

                # Add timeout
                cmd.extend(['-t', str(self.config.timeout * 1000)])

                # Add icon if available
                if self.config.icon_path and self.config.icon_path.exists():
                    cmd.extend(['-i', str(self.config.icon_path)])

            # Security: Using subprocess.run with shell=False (default) prevents injection
            result = subprocess.run(
                cmd,  # Safe: hardcoded command with user strings as arguments
                capture_output=True,
                text=True,
                timeout=5
            )

            return result.returncode == 0

        except Exception as e:
            logger.debug(f"Linux notification failed: {e}")
            return False

    async def _notify_windows(
        self,
        title: str,
        message: str,
        icon: Optional[str] = None
    ) -> bool:
        """
        Send notification on Windows.

        Args:
            title: Notification title
            message: Notification message
            icon: Optional icon path

        Returns:
            True if successful
        """
        try:
            # Try Windows 10 toast notifications
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(
                title,
                message,
                icon_path=icon,
                duration=self.config.timeout,
                threaded=True
            )
            return True

        except ImportError:
            logger.debug("win10toast not available")

            # Try Windows balloon tip as fallback
            try:
                import ctypes
                from ctypes import wintypes

                # This is a simplified version
                MessageBox = ctypes.windll.user32.MessageBoxW
                MessageBox(None, message, title, 0x40 | 0x1)
                return True

            except Exception as e:
                logger.debug(f"Windows notification failed: {e}")
                return False

    def _notify_terminal(self, title: str, message: str) -> bool:
        """
        Display notification in terminal as fallback.

        Args:
            title: Notification title
            message: Notification message

        Returns:
            Always returns True
        """
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.text import Text

            console = Console()

            # Create styled notification
            notification = Panel(
                Text(message, style="bright_white"),
                title=f"[bold yellow]🔔 {title}[/bold yellow]",
                border_style="bright_blue",
                padding=(1, 2),
            )

            console.print(notification)

        except ImportError:
            # Fallback to basic print
            print(f"\n{'=' * 60}")
            print(f"🔔 NOTIFICATION: {title}")
            print(f"   {message}")
            print(f"{'=' * 60}\n")

        return True

    def test_notification(self) -> bool:
        """
        Test notification system.

        Returns:
            True if test notification was sent
        """
        import asyncio
        return asyncio.run(
            self.notify(
                "gh-pr Test",
                "Notification system is working!",
                subtitle="Test notification"
            )
        )
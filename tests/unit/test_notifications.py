"""
Unit tests for notification system.

Tests cross-platform desktop notifications.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, call
import asyncio
import sys
import subprocess
from pathlib import Path

from gh_pr.utils.notifications import NotificationManager, NotificationConfig


class TestNotificationManager(unittest.TestCase):
    """Test notification manager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = NotificationConfig(
            enabled=True,
            sound=False,
            timeout=5,
            urgency='normal',
            fallback_to_terminal=True
        )
        self.manager = NotificationManager(self.config)

    @patch('sys.platform', 'darwin')
    @patch('subprocess.run')
    async def test_notify_macos(self, mock_run):
        """Test macOS notification."""
        mock_run.return_value = Mock(returncode=0)

        # Disable plyer for this test
        self.manager._use_plyer = False
        self.manager._platform = 'darwin'

        result = await self.manager.notify(
            "Test Title",
            "Test Message",
            subtitle="Test Subtitle"
        )

        self.assertTrue(result)
        mock_run.assert_called_once()

        # Check osascript command was called
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], 'osascript')
        self.assertEqual(call_args[1], '-e')
        self.assertIn('Test Title', call_args[2])
        self.assertIn('Test Message', call_args[2])

    @patch('sys.platform', 'linux')
    @patch('subprocess.run')
    @patch('shutil.which')
    async def test_notify_linux_notify_send(self, mock_which, mock_run):
        """Test Linux notification with notify-send."""
        mock_which.return_value = '/usr/bin/notify-send'
        mock_run.return_value = Mock(returncode=0)

        # Re-initialize to detect Linux notifier
        self.manager._use_plyer = False
        self.manager._platform = 'linux'
        self.manager._detect_linux_notifier()

        result = await self.manager.notify(
            "Test Title",
            "Test Message",
            urgency="critical"
        )

        self.assertTrue(result)
        mock_run.assert_called_once()

        # Check notify-send command
        call_args = mock_run.call_args[0][0]
        self.assertIn('notify-send', call_args[0])
        self.assertIn('Test Title', call_args)
        self.assertIn('Test Message', call_args)

    @patch('sys.platform', 'win32')
    async def test_notify_windows_fallback(self):
        """Test Windows notification fallback."""
        # Windows without win10toast should fall back to terminal
        self.manager._use_plyer = False
        self.manager._platform = 'win32'

        with patch.object(self.manager, '_notify_terminal') as mock_terminal:
            mock_terminal.return_value = True

            result = await self.manager.notify(
                "Test Title",
                "Test Message"
            )

            self.assertTrue(result)
            mock_terminal.assert_called_once_with("Test Title", "Test Message")

    def test_notify_with_plyer(self):
        """Test notification using plyer library."""
        mock_plyer = Mock()
        self.manager._plyer = mock_plyer
        self.manager._use_plyer = True

        result = self.manager._notify_with_plyer(
            "Test Title",
            "Test Message",
            icon="/path/to/icon.png"
        )

        self.assertTrue(result)
        mock_plyer.notify.assert_called_once_with(
            title="Test Title",
            message="Test Message",
            timeout=5,
            app_icon="/path/to/icon.png"
        )

    def test_notify_with_plyer_error(self):
        """Test plyer notification error handling."""
        mock_plyer = Mock()
        mock_plyer.notify.side_effect = Exception("Plyer error")
        self.manager._plyer = mock_plyer
        self.manager._use_plyer = True

        result = self.manager._notify_with_plyer(
            "Test Title",
            "Test Message"
        )

        self.assertFalse(result)

    async def test_notify_disabled(self):
        """Test notifications when disabled."""
        self.manager.config.enabled = False

        result = await self.manager.notify(
            "Test Title",
            "Test Message"
        )

        self.assertFalse(result)

    @patch('builtins.print')
    def test_terminal_notification_fallback(self, mock_print):
        """Test terminal notification fallback."""
        result = self.manager._notify_terminal(
            "Test Title",
            "Test Message"
        )

        self.assertTrue(result)
        mock_print.assert_called()

        # Check notification was printed
        call_args = mock_print.call_args_list
        printed = ' '.join(str(arg[0][0]) for arg in call_args)
        self.assertIn("Test Title", printed)
        self.assertIn("Test Message", printed)

    @patch('sys.platform', 'darwin')
    @patch('subprocess.run')
    async def test_notify_with_sound(self, mock_run):
        """Test notification with sound on macOS."""
        mock_run.return_value = Mock(returncode=0)

        self.manager._use_plyer = False
        self.manager._platform = 'darwin'
        self.manager.config.sound = True

        result = await self.manager.notify(
            "Test Title",
            "Test Message"
        )

        self.assertTrue(result)

        # Check sound was included in AppleScript
        call_args = mock_run.call_args[0][0]
        script = call_args[2]
        self.assertIn('sound name', script)

    @patch('sys.platform', 'linux')
    @patch('subprocess.run')
    @patch('shutil.which')
    async def test_linux_icon_support(self, mock_which, mock_run):
        """Test Linux notification with icon."""
        mock_which.return_value = '/usr/bin/notify-send'
        mock_run.return_value = Mock(returncode=0)

        # Set up icon path
        icon_path = Path("/tmp/test_icon.png")
        self.manager.config.icon_path = icon_path

        self.manager._use_plyer = False
        self.manager._platform = 'linux'
        self.manager._notifier = 'notify-send'

        # Mock icon path exists
        with patch.object(icon_path, 'exists', return_value=True):
            result = await self.manager.notify(
                "Test Title",
                "Test Message"
            )

        self.assertTrue(result)

        # Check icon was included
        call_args = mock_run.call_args[0][0]
        self.assertIn('-i', call_args)
        self.assertIn(str(icon_path), call_args)

    @patch('sys.platform', 'unsupported')
    def test_unsupported_platform(self):
        """Test unsupported platform handling."""
        self.manager._use_plyer = False
        self.manager._platform = 'unsupported'

        with patch.object(self.manager, '_notify_terminal') as mock_terminal:
            mock_terminal.return_value = True

            asyncio.run(self.manager.notify(
                "Test Title",
                "Test Message"
            ))

            # Should fall back to terminal
            mock_terminal.assert_called_once()

    def test_notification_config_defaults(self):
        """Test notification configuration defaults."""
        config = NotificationConfig()

        self.assertTrue(config.enabled)
        self.assertFalse(config.sound)
        self.assertEqual(config.timeout, 5)
        self.assertEqual(config.urgency, 'normal')
        self.assertTrue(config.fallback_to_terminal)
        self.assertIsNone(config.icon_path)

    @patch('subprocess.run')
    def test_test_notification(self, mock_run):
        """Test the test notification method."""
        mock_run.return_value = Mock(returncode=0)

        # Disable plyer for predictable testing
        self.manager._use_plyer = False
        self.manager._platform = 'darwin'

        result = self.manager.test_notification()

        # Should send test notification
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        script = call_args[2] if len(call_args) > 2 else ""
        self.assertIn("gh-pr Test", script)
        self.assertIn("working", script.lower())


if __name__ == '__main__':
    unittest.main()
"""
Unit tests for utils.clipboard module.

Tests clipboard management functionality with WSL2 support.
"""

import unittest
from unittest.mock import Mock, patch, mock_open

from gh_pr.utils.clipboard import ClipboardManager


class TestClipboardManager(unittest.TestCase):
    """Test ClipboardManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = ClipboardManager()

    @patch('gh_pr.utils.clipboard.shutil.which')
    @patch('builtins.open', new_callable=mock_open, read_data="Microsoft")
    def test_detect_clipboard_command_wsl_clip_exe(self, mock_file, mock_which):
        """Test WSL detection with clip.exe available."""
        # Mock WSL detection
        mock_which.side_effect = lambda cmd: "clip.exe" if cmd == "clip.exe" else None

        manager = ClipboardManager()
        self.assertEqual(manager.clipboard_cmd, ["clip.exe"])

    @patch('gh_pr.utils.clipboard.shutil.which')
    @patch('builtins.open', new_callable=mock_open, read_data="microsoft linux subsystem")
    def test_detect_clipboard_command_wsl_full_path(self, mock_file, mock_which):
        """Test WSL detection with full path to clip.exe."""
        # Mock WSL detection and clip.exe not in PATH but full path exists
        def which_side_effect(cmd):
            if cmd == "clip.exe":
                return None
            elif cmd == "/mnt/c/Windows/System32/clip.exe":
                return "/mnt/c/Windows/System32/clip.exe"
            return None

        mock_which.side_effect = which_side_effect

        manager = ClipboardManager()
        self.assertEqual(manager.clipboard_cmd, ["/mnt/c/Windows/System32/clip.exe"])

    @patch('gh_pr.utils.clipboard.shutil.which')
    @patch('builtins.open', side_effect=FileNotFoundError())
    def test_detect_clipboard_command_wayland(self, mock_file, mock_which):
        """Test Wayland clipboard detection."""
        mock_which.side_effect = lambda cmd: "wl-copy" if cmd == "wl-copy" else None

        manager = ClipboardManager()
        self.assertEqual(manager.clipboard_cmd, ["wl-copy"])

    @patch('gh_pr.utils.clipboard.shutil.which')
    @patch('builtins.open', side_effect=FileNotFoundError())
    def test_detect_clipboard_command_x11_xclip(self, mock_file, mock_which):
        """Test X11 clipboard detection with xclip."""
        mock_which.side_effect = lambda cmd: "xclip" if cmd == "xclip" else None

        manager = ClipboardManager()
        self.assertEqual(manager.clipboard_cmd, ["xclip", "-selection", "clipboard"])

    @patch('gh_pr.utils.clipboard.shutil.which')
    @patch('builtins.open', side_effect=FileNotFoundError())
    def test_detect_clipboard_command_x11_xsel(self, mock_file, mock_which):
        """Test X11 clipboard detection with xsel."""
        def which_side_effect(cmd):
            if cmd == "xsel":
                return "xsel"
            return None

        mock_which.side_effect = which_side_effect

        manager = ClipboardManager()
        self.assertEqual(manager.clipboard_cmd, ["xsel", "--clipboard", "--input"])

    @patch('gh_pr.utils.clipboard.shutil.which')
    @patch('builtins.open', side_effect=FileNotFoundError())
    def test_detect_clipboard_command_macos(self, mock_file, mock_which):
        """Test macOS clipboard detection."""
        mock_which.side_effect = lambda cmd: "pbcopy" if cmd == "pbcopy" else None

        manager = ClipboardManager()
        self.assertEqual(manager.clipboard_cmd, ["pbcopy"])

    @patch('gh_pr.utils.clipboard.shutil.which')
    @patch('builtins.open', side_effect=FileNotFoundError())
    def test_detect_clipboard_command_none_available(self, mock_file, mock_which):
        """Test when no clipboard command is available."""
        mock_which.return_value = None

        manager = ClipboardManager()
        self.assertIsNone(manager.clipboard_cmd)

    @patch('gh_pr.utils.clipboard.shutil.which')
    @patch('builtins.open', new_callable=mock_open, read_data="Not Microsoft")
    def test_detect_clipboard_command_not_wsl(self, mock_file, mock_which):
        """Test detection when /proc/version exists but not WSL."""
        mock_which.side_effect = lambda cmd: "wl-copy" if cmd == "wl-copy" else None

        manager = ClipboardManager()
        # Should detect Wayland instead of WSL
        self.assertEqual(manager.clipboard_cmd, ["wl-copy"])

    def test_is_available_true(self):
        """Test is_available when clipboard command exists."""
        self.manager.clipboard_cmd = ["echo"]
        self.assertTrue(self.manager.is_available())

    def test_is_available_false(self):
        """Test is_available when no clipboard command."""
        self.manager.clipboard_cmd = None
        self.assertFalse(self.manager.is_available())

    def test_copy_no_clipboard_command(self):
        """Test copy when no clipboard command is available."""
        self.manager.clipboard_cmd = None

        result = self.manager.copy("test text")
        self.assertFalse(result)

    @patch('gh_pr.utils.clipboard.subprocess.Popen')
    def test_copy_success(self, mock_popen):
        """Test successful copy operation."""
        # Mock successful subprocess
        mock_process = Mock()
        mock_process.communicate.return_value = (b"", b"")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        self.manager.clipboard_cmd = ["xclip", "-selection", "clipboard"]

        result = self.manager.copy("test text")
        self.assertTrue(result)

        # Verify subprocess was called correctly
        mock_popen.assert_called_once_with(
            ["xclip", "-selection", "clipboard"],
            stdin=mock_popen.call_args[1]['stdin'],
            stdout=mock_popen.call_args[1]['stdout'],
            stderr=mock_popen.call_args[1]['stderr'],
            shell=False,
            timeout=5
        )

        # Verify communicate was called with correct input
        mock_process.communicate.assert_called_once_with(
            input=b"test text",
            timeout=5
        )

    @patch('gh_pr.utils.clipboard.subprocess.Popen')
    def test_copy_process_failure(self, mock_popen):
        """Test copy when subprocess returns non-zero exit code."""
        # Mock failed subprocess
        mock_process = Mock()
        mock_process.communicate.return_value = (b"", b"error")
        mock_process.returncode = 1
        mock_popen.return_value = mock_process

        self.manager.clipboard_cmd = ["xclip", "-selection", "clipboard"]

        result = self.manager.copy("test text")
        self.assertFalse(result)

    @patch('gh_pr.utils.clipboard.subprocess.Popen')
    def test_copy_subprocess_error(self, mock_popen):
        """Test copy when subprocess raises an exception."""
        mock_popen.side_effect = OSError("Command not found")

        self.manager.clipboard_cmd = ["nonexistent_command"]

        result = self.manager.copy("test text")
        self.assertFalse(result)

    @patch('gh_pr.utils.clipboard.subprocess.Popen')
    def test_copy_timeout_error(self, mock_popen):
        """Test copy when subprocess times out."""
        import subprocess
        mock_popen.side_effect = subprocess.TimeoutExpired("cmd", 5)

        self.manager.clipboard_cmd = ["slow_command"]

        result = self.manager.copy("test text")
        self.assertFalse(result)

    @patch('gh_pr.utils.clipboard.subprocess.Popen')
    def test_copy_communicate_timeout(self, mock_popen):
        """Test copy when communicate times out."""
        import subprocess
        mock_process = Mock()
        mock_process.communicate.side_effect = subprocess.TimeoutExpired("cmd", 5)
        mock_popen.return_value = mock_process

        self.manager.clipboard_cmd = ["timeout_command"]

        result = self.manager.copy("test text")
        self.assertFalse(result)

    @patch('gh_pr.utils.clipboard.subprocess.Popen')
    def test_copy_unicode_text(self, mock_popen):
        """Test copy with Unicode text."""
        # Mock successful subprocess
        mock_process = Mock()
        mock_process.communicate.return_value = (b"", b"")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        self.manager.clipboard_cmd = ["pbcopy"]

        unicode_text = "Hello 世界 🌍"
        result = self.manager.copy(unicode_text)
        self.assertTrue(result)

        # Verify Unicode text was properly encoded
        expected_bytes = unicode_text.encode("utf-8")
        mock_process.communicate.assert_called_once_with(
            input=expected_bytes,
            timeout=5
        )

    @patch('gh_pr.utils.clipboard.subprocess.Popen')
    def test_copy_empty_text(self, mock_popen):
        """Test copy with empty text."""
        # Mock successful subprocess
        mock_process = Mock()
        mock_process.communicate.return_value = (b"", b"")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        self.manager.clipboard_cmd = ["pbcopy"]

        result = self.manager.copy("")
        self.assertTrue(result)

        mock_process.communicate.assert_called_once_with(
            input=b"",
            timeout=5
        )

    @patch('gh_pr.utils.clipboard.subprocess.Popen')
    def test_copy_large_text(self, mock_popen):
        """Test copy with large text."""
        # Mock successful subprocess
        mock_process = Mock()
        mock_process.communicate.return_value = (b"", b"")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        self.manager.clipboard_cmd = ["wl-copy"]

        # Create large text (10KB)
        large_text = "A" * 10240
        result = self.manager.copy(large_text)
        self.assertTrue(result)

        expected_bytes = large_text.encode("utf-8")
        mock_process.communicate.assert_called_once_with(
            input=expected_bytes,
            timeout=5
        )

    def test_copy_security_shell_false(self):
        """Test that copy always uses shell=False for security."""
        with patch('gh_pr.utils.clipboard.subprocess.Popen') as mock_popen:
            # Mock successful subprocess
            mock_process = Mock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_popen.return_value = mock_process

            self.manager.clipboard_cmd = ["echo"]

            self.manager.copy("test")

            # Verify shell=False is always used
            call_kwargs = mock_popen.call_args[1]
            self.assertFalse(call_kwargs['shell'])

    def test_copy_security_timeout_set(self):
        """Test that copy always sets a timeout for security."""
        with patch('gh_pr.utils.clipboard.subprocess.Popen') as mock_popen:
            # Mock successful subprocess
            mock_process = Mock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_popen.return_value = mock_process

            self.manager.clipboard_cmd = ["echo"]

            self.manager.copy("test")

            # Verify timeout is set in Popen
            call_kwargs = mock_popen.call_args[1]
            self.assertEqual(call_kwargs['timeout'], 5)

            # Verify timeout is set in communicate
            mock_process.communicate.assert_called_once()
            communicate_kwargs = mock_process.communicate.call_args[1]
            self.assertEqual(communicate_kwargs['timeout'], 5)

    @patch('gh_pr.utils.clipboard.shutil.which')
    @patch('builtins.open', side_effect=FileNotFoundError())
    def test_command_precedence(self, mock_file, mock_which):
        """Test that command detection follows correct precedence."""
        # Simulate multiple clipboard commands available
        available_commands = ["wl-copy", "xclip", "xsel", "pbcopy"]

        def which_side_effect(cmd):
            return cmd if cmd in available_commands else None

        mock_which.side_effect = which_side_effect

        manager = ClipboardManager()

        # Should prefer wl-copy (Wayland) first
        self.assertEqual(manager.clipboard_cmd, ["wl-copy"])

    @patch('gh_pr.utils.clipboard.shutil.which')
    @patch('builtins.open', side_effect=FileNotFoundError())
    def test_x11_command_precedence(self, mock_file, mock_which):
        """Test X11 command precedence (xclip over xsel)."""
        # Only X11 commands available
        available_commands = ["xclip", "xsel"]

        def which_side_effect(cmd):
            return cmd if cmd in available_commands else None

        mock_which.side_effect = which_side_effect

        manager = ClipboardManager()

        # Should prefer xclip over xsel
        self.assertEqual(manager.clipboard_cmd, ["xclip", "-selection", "clipboard"])


if __name__ == '__main__':
    unittest.main()
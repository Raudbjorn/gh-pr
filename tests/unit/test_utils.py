"""
Unit tests for utility modules.

Tests clipboard, config, and export functionality.
"""

import unittest
import tempfile
import json
import csv
import os
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
from io import StringIO

from gh_pr.utils.clipboard import ClipboardManager
from gh_pr.utils.config import ConfigManager
from gh_pr.utils.export import ExportManager


class TestClipboardManager(unittest.TestCase):
    """Test clipboard management functionality."""

    @patch('subprocess.Popen')
    def test_copy_to_clipboard(self, mock_popen):
        """Test copying text to clipboard."""
        clipboard = ClipboardManager()

        # Mock clipboard command availability
        clipboard.clipboard_cmd = ['pbcopy']

        # Mock successful subprocess execution
        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        text = "Test content for clipboard"
        result = clipboard.copy(text)

        self.assertTrue(result)
        mock_popen.assert_called_once()
        mock_process.communicate.assert_called_once_with(input=text.encode('utf-8'), timeout=5)

    def test_clipboard_availability(self):
        """Test clipboard availability check."""
        clipboard = ClipboardManager()

        # Test when clipboard command is available
        clipboard.clipboard_cmd = ['pbcopy']
        self.assertTrue(clipboard.is_available())

        # Test when clipboard command is not available
        clipboard.clipboard_cmd = None
        self.assertFalse(clipboard.is_available())

    @patch('subprocess.Popen')
    def test_clipboard_error_handling(self, mock_popen):
        """Test clipboard error handling."""
        clipboard = ClipboardManager()
        clipboard.clipboard_cmd = ['pbcopy']

        # Mock subprocess error
        mock_popen.side_effect = OSError("No clipboard")

        # Should handle error gracefully
        result = clipboard.copy("Test")
        self.assertFalse(result)

    @patch('subprocess.Popen')
    def test_copy_formatted_text(self, mock_popen):
        """Test copying formatted text."""
        clipboard = ClipboardManager()
        clipboard.clipboard_cmd = ['pbcopy']

        # Mock successful subprocess execution
        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        # Test copying formatted text
        text = "PR #123: Test PR\nURL: https://github.com/owner/repo/pull/123"
        result = clipboard.copy(text)

        self.assertTrue(result)
        mock_popen.assert_called_once()
        mock_process.communicate.assert_called_once()

    @patch('subprocess.Popen')
    def test_copy_multi_line_text(self, mock_popen):
        """Test copying multi-line text."""
        clipboard = ClipboardManager()
        clipboard.clipboard_cmd = ['pbcopy']

        # Mock successful subprocess execution
        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        # Test copying multi-line text
        text = """PR #1: PR 1
PR #2: PR 2
PR #3: PR 3"""
        result = clipboard.copy(text)

        self.assertTrue(result)
        mock_popen.assert_called_once()


class TestConfigManager(unittest.TestCase):
    """Test configuration management."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / 'config.json'

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_load_default_config(self):
        """Test loading default configuration."""
        manager = ConfigManager(str(self.config_path))

        # Config is loaded automatically in __init__
        config = manager.config

        self.assertIsInstance(config, dict)
        self.assertIn('github', config)
        self.assertIn('display', config)
        self.assertIn('cache', config)

    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        # Use home directory config which is allowed
        config_path = Path.home() / '.config' / 'gh-pr' / 'test_config.toml'
        config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            manager = ConfigManager(str(config_path))

            # Set configuration values
            manager.set('github.default_token', 'test_token')
            manager.set('display.context_lines', 20)
            manager.set('cache.ttl_minutes', 60)

            # Save configuration
            success = manager.save(str(config_path))
            self.assertTrue(success)

            # Create new manager to load saved config
            new_manager = ConfigManager(str(config_path))

            self.assertEqual(new_manager.get('github.default_token'), 'test_token')
            self.assertEqual(new_manager.get('display.context_lines'), 20)
            self.assertEqual(new_manager.get('cache.ttl_minutes'), 60)
        finally:
            # Cleanup
            if config_path.exists():
                config_path.unlink()

    def test_update_config(self):
        """Test updating configuration values."""
        manager = ConfigManager(str(self.config_path))

        # Set initial values
        manager.set('github.default_token', 'old_token')

        # Update config
        manager.set('github.default_token', 'new_token')
        manager.set('display.show_code', False)

        # Verify updates
        self.assertEqual(manager.get('github.default_token'), 'new_token')
        self.assertEqual(manager.get('display.show_code'), False)

    def test_get_config_value(self):
        """Test getting specific config values."""
        manager = ConfigManager()

        # Set nested values directly
        manager.set('github.api.timeout', 30)
        manager.set('features.webhooks', True)

        # Get nested value
        timeout = manager.get('github.api.timeout')
        self.assertEqual(timeout, 30)

        # Get with default
        missing = manager.get('nonexistent.key', default='default_value')
        self.assertEqual(missing, 'default_value')

    def test_config_defaults(self):
        """Test config defaults."""
        manager = ConfigManager()

        # Check default values
        self.assertIsNone(manager.get('github.default_token'))
        self.assertEqual(manager.get('display.default_filter'), 'unresolved')
        self.assertEqual(manager.get('display.context_lines'), 3)
        self.assertTrue(manager.get('display.show_code'))
        self.assertEqual(manager.get('cache.ttl_minutes'), 5)
        self.assertTrue(manager.get('cache.enabled'))
        self.assertTrue(manager.get('clipboard.auto_strip_ansi'))

    def test_config_merge(self):
        """Test config merging with defaults."""
        # Use home directory config which is allowed
        config_path = Path.home() / '.config' / 'gh-pr' / 'test_merge_config.toml'
        config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Save partial config
            import tomli_w
            partial_config = {
                'github': {'default_token': 'custom_token'},
                'display': {'context_lines': 5}
            }

            with open(config_path, 'wb') as f:
                tomli_w.dump(partial_config, f)

            # Load config - should merge with defaults
            manager = ConfigManager(str(config_path))

            # Check merged values
            self.assertEqual(manager.get('github.default_token'), 'custom_token')
            self.assertEqual(manager.get('display.context_lines'), 5)
            # Check defaults are preserved
            self.assertTrue(manager.get('display.show_code'))  # Default
            self.assertTrue(manager.get('cache.enabled'))  # Default
        finally:
            # Cleanup
            if config_path.exists():
                config_path.unlink()


class TestExportManager(unittest.TestCase):
    """Test export functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = ExportManager()

        # Create sample PRs
        self.prs = []
        for i in range(3):
            pr = Mock()
            pr.number = i + 1
            pr.title = f"PR Title {i + 1}"
            pr.state = "open" if i < 2 else "closed"
            pr.user.login = f"user{i}"
            pr.created_at = "2024-01-01T00:00:00Z"
            pr.html_url = f"https://github.com/owner/repo/pull/{i + 1}"
            pr.body = f"Description for PR {i + 1}"
            pr.labels = [Mock(name=f"label{j}") for j in range(2)]
            self.prs.append(pr)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_json_export(self):
        """Test exporting PRs to JSON."""
        output_path = Path(self.temp_dir) / 'export.json'

        # Create PR data dict from mock PR
        pr_data = {
            'number': self.prs[0].number,
            'title': self.prs[0].title,
            'state': self.prs[0].state,
            'author': self.prs[0].user.login,
            'body': self.prs[0].body
        }

        # Create comments list
        comments = []

        result = self.manager.export(pr_data, comments, format='json')

        # Should create a timestamped file
        self.assertTrue(Path(result).exists())

        # Read and verify
        with open(result) as f:
            data = json.load(f)

        self.assertIn('pr', data)
        self.assertEqual(data['pr']['number'], 1)
        self.assertIn('exported_at', data)

    def test_csv_export(self):
        """Test exporting PRs to CSV."""
        # Create PR data
        pr_data = {
            'number': 123,
            'title': 'Test PR',
            'state': 'open',
            'author': 'testuser'
        }

        # Create comments with thread structure
        comments = [
            {
                'path': 'file.py',
                'line': 10,
                'is_resolved': False,
                'is_outdated': False,
                'comments': [
                    {
                        'author': 'reviewer1',
                        'body': 'Comment 1',
                        'created_at': '2024-01-01'
                    }
                ]
            }
        ]

        result = self.manager.export(pr_data, comments, format='csv')

        # Should create a timestamped file
        self.assertTrue(Path(result).exists())

        # Read and verify
        with open(result) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['PR Number'], '123')

    def test_markdown_export(self):
        """Test exporting PRs to Markdown."""
        # Create PR data
        pr_data = {
            'number': 456,
            'title': 'Test PR for Markdown',
            'state': 'open',
            'author': 'testuser',
            'body': 'This is the PR description',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }

        # Create comments
        comments = [
            {
                'path': 'main.py',
                'line': 25,
                'is_resolved': True,
                'is_outdated': False,
                'comments': [
                    {
                        'author': 'reviewer1',
                        'body': 'Please fix this'
                    }
                ]
            }
        ]

        result = self.manager.export(pr_data, comments, format='markdown')

        # Read and verify
        content = Path(result).read_text()

        self.assertIn('# PR #456', content)
        self.assertIn('Test PR for Markdown', content)
        self.assertIn('@testuser', content)
        self.assertIn('## Review Comments', content)
        self.assertIn('main.py:25', content)

    def test_unsupported_format(self):
        """Test exporting to unsupported format."""
        pr_data = {'number': 1, 'title': 'Test'}
        comments = []

        with self.assertRaises(ValueError) as context:
            self.manager.export(pr_data, comments, format='html')

        self.assertIn('Unsupported format: html', str(context.exception))

    def test_batch_report_export(self):
        """Test exporting batch operation report."""
        batch_results = [
            {
                'pr_number': 1,
                'success': True,
                'result': 5,
                'duration': 1.23
            },
            {
                'pr_number': 2,
                'success': False,
                'result': 0,
                'errors': ['Connection timeout'],
                'duration': 0.5
            }
        ]

        result = self.manager.export_batch_report(batch_results, output_format='json')

        # Should create a timestamped file
        self.assertTrue(Path(result).exists())

        # Read and verify
        with open(result) as f:
            data = json.load(f)

        self.assertEqual(data['summary']['total_prs'], 2)
        self.assertEqual(data['summary']['successful'], 1)
        self.assertEqual(data['summary']['failed'], 1)

    def test_review_statistics_export(self):
        """Test exporting review statistics."""
        pr_data_list = [
            {
                'number': 1,
                'state': 'open',
                'author': 'user1',
                'comments': [
                    {
                        'path': 'file1.py',
                        'comments': [
                            {'author': 'reviewer1', 'body': 'Comment'}
                        ]
                    }
                ]
            },
            {
                'number': 2,
                'state': 'closed',
                'author': 'user2',
                'comments': []
            }
        ]

        result = self.manager.export_review_statistics(pr_data_list, output_format='json')

        # Should create a timestamped file
        self.assertTrue(Path(result).exists())

        # Read and verify
        with open(result) as f:
            data = json.load(f)

        self.assertEqual(data['total_prs'], 2)
        self.assertIn('pr_states', data)
        self.assertIn('comment_statistics', data)

    def test_enhanced_csv_export(self):
        """Test enhanced CSV export with all fields."""
        pr_data = {
            'number': 789,
            'title': 'Enhanced CSV Test',
            'state': 'open',
            'author': 'testuser'
        }

        comments = [
            {
                'path': 'test.py',
                'line': 42,
                'id': 'thread1',
                'is_resolved': False,
                'is_outdated': False,
                'comments': [
                    {
                        'id': 'comment1',
                        'author': 'reviewer',
                        'body': 'Test comment',
                        'type': 'review',
                        'created_at': '2024-01-01',
                        'updated_at': '2024-01-02',
                        'suggestions': [],
                        'reactions': [],
                        'author_association': 'COLLABORATOR'
                    }
                ]
            }
        ]

        result = self.manager.export_enhanced_csv(pr_data, comments, include_all_fields=True)

        # Should create a timestamped file
        self.assertTrue(Path(result).exists())

        # Read and verify headers
        with open(result) as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames

        self.assertIn('PR Number', headers)
        self.assertIn('Comment ID', headers)
        self.assertIn('Author Association', headers)

    def test_export_error_handling(self):
        """Test export error handling."""
        # Test with empty batch results
        with self.assertRaises(ValueError) as context:
            self.manager.export_batch_report([], output_format='json')

        self.assertIn('No batch results provided', str(context.exception))

        # Test with empty PR data list
        with self.assertRaises(ValueError) as context:
            self.manager.export_review_statistics([], output_format='json')

        self.assertIn('No PR data provided', str(context.exception))

    def test_export_empty_comments(self):
        """Test exporting with empty comments."""
        pr_data = {'number': 999, 'title': 'No Comments', 'state': 'open', 'author': 'user'}
        comments = []

        result = self.manager.export(pr_data, comments, format='json')

        # Should create a file even with no comments
        self.assertTrue(Path(result).exists())

        with open(result) as f:
            data = json.load(f)

        self.assertEqual(data['comments'], [])


if __name__ == '__main__':
    unittest.main()
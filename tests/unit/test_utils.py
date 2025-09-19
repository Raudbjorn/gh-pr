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
from gh_pr.utils.config import ConfigManager, validate_config
from gh_pr.utils.export import (
    ExportManager, JSONExporter, CSVExporter,
    MarkdownExporter, HTMLExporter
)


class TestClipboardManager(unittest.TestCase):
    """Test clipboard management functionality."""

    @patch('pyperclip.copy')
    def test_copy_to_clipboard(self, mock_copy):
        """Test copying text to clipboard."""
        clipboard = ClipboardManager()

        text = "Test content for clipboard"
        clipboard.copy(text)

        mock_copy.assert_called_once_with(text)

    @patch('pyperclip.paste')
    def test_paste_from_clipboard(self, mock_paste):
        """Test pasting text from clipboard."""
        clipboard = ClipboardManager()

        mock_paste.return_value = "Pasted content"

        result = clipboard.paste()

        self.assertEqual(result, "Pasted content")
        mock_paste.assert_called_once()

    @patch('pyperclip.copy', side_effect=Exception("No clipboard"))
    def test_clipboard_error_handling(self, mock_copy):
        """Test clipboard error handling."""
        clipboard = ClipboardManager()

        # Should handle error gracefully
        result = clipboard.copy("Test")
        self.assertFalse(result)

    @patch('pyperclip.copy')
    def test_copy_formatted_pr(self, mock_copy):
        """Test copying formatted PR information."""
        clipboard = ClipboardManager()

        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.title = "Test PR"
        mock_pr.html_url = "https://github.com/owner/repo/pull/123"
        mock_pr.body = "PR description"

        clipboard.copy_pr(mock_pr)

        # Check that formatted content was copied
        call_args = mock_copy.call_args[0][0]
        self.assertIn("#123", call_args)
        self.assertIn("Test PR", call_args)
        self.assertIn("https://github.com", call_args)

    @patch('pyperclip.copy')
    def test_copy_pr_list(self, mock_copy):
        """Test copying list of PRs."""
        clipboard = ClipboardManager()

        prs = []
        for i in range(3):
            pr = Mock()
            pr.number = i + 1
            pr.title = f"PR {i + 1}"
            pr.html_url = f"https://github.com/owner/repo/pull/{i + 1}"
            prs.append(pr)

        clipboard.copy_pr_list(prs)

        call_args = mock_copy.call_args[0][0]
        for pr in prs:
            self.assertIn(f"#{pr.number}", call_args)
            self.assertIn(pr.title, call_args)


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
        manager = ConfigManager(self.config_path)

        config = manager.load()

        self.assertIsInstance(config, dict)
        self.assertIn('github', config)
        self.assertIn('display', config)
        self.assertIn('cache', config)

    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        manager = ConfigManager(self.config_path)

        config = {
            'github': {'token': 'test_token'},
            'display': {'color': True, 'page_size': 20},
            'cache': {'ttl': 3600}
        }

        manager.save(config)
        loaded = manager.load()

        self.assertEqual(loaded['github']['token'], 'test_token')
        self.assertEqual(loaded['display']['color'], True)
        self.assertEqual(loaded['cache']['ttl'], 3600)

    def test_update_config(self):
        """Test updating configuration values."""
        manager = ConfigManager(self.config_path)

        # Save initial config
        initial = {'github': {'token': 'old_token'}}
        manager.save(initial)

        # Update config
        manager.update('github.token', 'new_token')
        manager.update('display.color', False)

        loaded = manager.load()

        self.assertEqual(loaded['github']['token'], 'new_token')
        self.assertEqual(loaded['display']['color'], False)

    def test_get_config_value(self):
        """Test getting specific config values."""
        manager = ConfigManager(self.config_path)

        config = {
            'github': {'api': {'timeout': 30}},
            'features': {'webhooks': True}
        }
        manager.save(config)

        # Get nested value
        timeout = manager.get('github.api.timeout')
        self.assertEqual(timeout, 30)

        # Get with default
        missing = manager.get('nonexistent.key', default='default_value')
        self.assertEqual(missing, 'default_value')

    def test_validate_config(self):
        """Test config validation."""
        # Valid config
        valid_config = {
            'github': {'token': 'ghp_valid_token'},
            'display': {'page_size': 25},
            'cache': {'ttl': 1800}
        }

        self.assertTrue(validate_config(valid_config))

        # Invalid config - missing required field
        invalid_config = {
            'display': {'page_size': 25}
        }

        self.assertFalse(validate_config(invalid_config))

        # Invalid config - wrong type
        invalid_type = {
            'github': {'token': 123},  # Should be string
            'display': {'page_size': '25'}  # Should be int
        }

        self.assertFalse(validate_config(invalid_type))

    def test_config_migration(self):
        """Test migrating old config format to new."""
        manager = ConfigManager(self.config_path)

        # Old format config
        old_config = {
            'token': 'old_token',
            'repo': 'owner/repo'
        }

        # Save old format
        with open(self.config_path, 'w') as f:
            json.dump(old_config, f)

        # Load should migrate
        config = manager.load()

        # Check migration
        self.assertIn('github', config)
        self.assertEqual(config['github'].get('token'), 'old_token')
        self.assertEqual(config['github'].get('repo'), 'owner/repo')


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
        exporter = JSONExporter()
        output_path = Path(self.temp_dir) / 'export.json'

        exporter.export(self.prs, output_path)

        # Read and verify
        with open(output_path) as f:
            data = json.load(f)

        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]['number'], 1)
        self.assertEqual(data[1]['title'], "PR Title 2")
        self.assertEqual(data[2]['state'], "closed")

    def test_csv_export(self):
        """Test exporting PRs to CSV."""
        exporter = CSVExporter()
        output_path = Path(self.temp_dir) / 'export.csv'

        exporter.export(self.prs, output_path)

        # Read and verify
        with open(output_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['number'], '1')
        self.assertEqual(rows[1]['title'], 'PR Title 2')
        self.assertEqual(rows[2]['state'], 'closed')

    def test_markdown_export(self):
        """Test exporting PRs to Markdown."""
        exporter = MarkdownExporter()
        output_path = Path(self.temp_dir) / 'export.md'

        exporter.export(self.prs, output_path)

        # Read and verify
        content = output_path.read_text()

        self.assertIn('# Pull Requests', content)
        self.assertIn('PR Title 1', content)
        self.assertIn('#2', content)
        self.assertIn('user0', content)
        self.assertIn('| Number | Title | State |', content)

    def test_html_export(self):
        """Test exporting PRs to HTML."""
        exporter = HTMLExporter()
        output_path = Path(self.temp_dir) / 'export.html'

        exporter.export(self.prs, output_path)

        # Read and verify
        content = output_path.read_text()

        self.assertIn('<html>', content)
        self.assertIn('<table>', content)
        self.assertIn('PR Title 1', content)
        self.assertIn('class="open"', content)
        self.assertIn('class="closed"', content)

    def test_export_with_custom_fields(self):
        """Test exporting with custom field selection."""
        exporter = JSONExporter()
        output_path = Path(self.temp_dir) / 'custom.json'

        # Export only specific fields
        fields = ['number', 'title', 'state']
        exporter.export(self.prs, output_path, fields=fields)

        with open(output_path) as f:
            data = json.load(f)

        # Should only have specified fields
        for item in data:
            self.assertIn('number', item)
            self.assertIn('title', item)
            self.assertIn('state', item)
            self.assertNotIn('body', item)
            self.assertNotIn('labels', item)

    def test_export_format_detection(self):
        """Test automatic format detection from file extension."""
        test_cases = [
            ('export.json', JSONExporter),
            ('export.csv', CSVExporter),
            ('export.md', MarkdownExporter),
            ('export.html', HTMLExporter)
        ]

        for filename, expected_class in test_cases:
            output_path = Path(self.temp_dir) / filename
            self.manager.export(self.prs, output_path)

            self.assertTrue(output_path.exists())

    def test_export_with_filter(self):
        """Test exporting with PR filter."""
        exporter = JSONExporter()
        output_path = Path(self.temp_dir) / 'filtered.json'

        # Filter only open PRs
        open_prs = [pr for pr in self.prs if pr.state == 'open']
        exporter.export(open_prs, output_path)

        with open(output_path) as f:
            data = json.load(f)

        self.assertEqual(len(data), 2)
        self.assertTrue(all(pr['state'] == 'open' for pr in data))

    def test_export_error_handling(self):
        """Test export error handling."""
        exporter = JSONExporter()

        # Invalid path
        invalid_path = Path('/invalid/path/export.json')

        with self.assertRaises(Exception):
            exporter.export(self.prs, invalid_path)

    def test_export_empty_list(self):
        """Test exporting empty PR list."""
        exporter = JSONExporter()
        output_path = Path(self.temp_dir) / 'empty.json'

        exporter.export([], output_path)

        with open(output_path) as f:
            data = json.load(f)

        self.assertEqual(data, [])


if __name__ == '__main__':
    unittest.main()
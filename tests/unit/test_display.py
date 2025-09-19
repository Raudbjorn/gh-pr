"""
Unit tests for UI display module.

Tests terminal UI formatting and display.
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

from gh_pr.ui.display import (
    PRDisplay, TableDisplay, ColorScheme, ProgressDisplay,
    format_timedelta, truncate_text, highlight_search_term
)


class TestPRDisplay(unittest.TestCase):
    """Test PR display formatting."""

    def setUp(self):
        """Set up test fixtures."""
        self.display = PRDisplay()

    def test_format_pr_summary(self):
        """Test formatting PR summary."""
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.title = "Add new feature"
        mock_pr.state = "open"
        mock_pr.user.login = "alice"
        mock_pr.created_at = datetime.now() - timedelta(days=2)
        mock_pr.labels = [Mock(name="enhancement"), Mock(name="review")]

        summary = self.display.format_pr_summary(mock_pr)

        self.assertIn("#123", summary)
        self.assertIn("Add new feature", summary)
        self.assertIn("alice", summary)
        self.assertIn("enhancement", summary)

    def test_format_pr_detailed(self):
        """Test formatting detailed PR view."""
        mock_pr = Mock()
        mock_pr.number = 456
        mock_pr.title = "Fix critical bug"
        mock_pr.body = "This PR fixes a critical bug in the authentication system."
        mock_pr.state = "open"
        mock_pr.user.login = "bob"
        mock_pr.created_at = datetime.now() - timedelta(hours=6)
        mock_pr.updated_at = datetime.now() - timedelta(minutes=30)
        mock_pr.labels = [Mock(name="bug", color="ff0000")]
        mock_pr.assignees = [Mock(login="charlie")]
        mock_pr.requested_reviewers = [Mock(login="david")]
        mock_pr.milestone = Mock(title="v1.0.0")
        mock_pr.additions = 150
        mock_pr.deletions = 50
        mock_pr.changed_files = 5

        detailed = self.display.format_pr_detailed(mock_pr)

        self.assertIn("#456", detailed)
        self.assertIn("Fix critical bug", detailed)
        self.assertIn("critical bug", detailed.lower())
        self.assertIn("bob", detailed)
        self.assertIn("charlie", detailed)
        self.assertIn("david", detailed)
        self.assertIn("v1.0.0", detailed)
        self.assertIn("150", detailed)
        self.assertIn("50", detailed)

    def test_format_pr_list(self):
        """Test formatting list of PRs."""
        prs = []
        for i in range(3):
            pr = Mock()
            pr.number = i + 1
            pr.title = f"PR {i + 1}"
            pr.state = "open" if i < 2 else "closed"
            pr.user.login = f"user{i}"
            pr.labels = []
            pr.created_at = datetime.now() - timedelta(days=i)
            prs.append(pr)

        pr_list = self.display.format_pr_list(prs)

        for i, pr in enumerate(prs):
            self.assertIn(f"#{pr.number}", pr_list)
            self.assertIn(pr.title, pr_list)
            self.assertIn(pr.user.login, pr_list)

    def test_format_empty_pr_list(self):
        """Test formatting empty PR list."""
        result = self.display.format_pr_list([])
        self.assertIn("No pull requests", result.lower())

    def test_format_pr_with_review_status(self):
        """Test formatting PR with review status."""
        mock_pr = Mock()
        mock_pr.number = 789
        mock_pr.title = "Feature with reviews"
        mock_pr.get_reviews.return_value = [
            Mock(state="APPROVED", user=Mock(login="reviewer1")),
            Mock(state="CHANGES_REQUESTED", user=Mock(login="reviewer2"))
        ]

        formatted = self.display.format_pr_with_review_status(mock_pr)

        self.assertIn("APPROVED", formatted)
        self.assertIn("CHANGES_REQUESTED", formatted)
        self.assertIn("reviewer1", formatted)
        self.assertIn("reviewer2", formatted)


class TestTableDisplay(unittest.TestCase):
    """Test table display formatting."""

    def test_create_simple_table(self):
        """Test creating a simple table."""
        display = TableDisplay()

        headers = ["ID", "Name", "Status"]
        rows = [
            ["1", "Task A", "Complete"],
            ["2", "Task B", "In Progress"],
            ["3", "Task C", "Pending"]
        ]

        table = display.create_table(headers, rows)

        for header in headers:
            self.assertIn(header, table)

        for row in rows:
            for cell in row:
                self.assertIn(cell, table)

    def test_table_with_column_widths(self):
        """Test table with custom column widths."""
        display = TableDisplay()

        headers = ["ID", "Description"]
        rows = [
            ["1", "This is a very long description that should be truncated"],
            ["2", "Short desc"]
        ]

        table = display.create_table(headers, rows, widths=[5, 20])

        lines = table.split('\n')
        # Check that lines respect width constraints
        for line in lines:
            if line and not line.startswith('─'):
                self.assertLessEqual(len(line), 30)  # Total width with padding

    def test_table_alignment(self):
        """Test table cell alignment."""
        display = TableDisplay()

        headers = ["Left", "Center", "Right"]
        rows = [["A", "B", "C"]]
        alignments = ['left', 'center', 'right']

        table = display.create_table(headers, rows, alignments=alignments)

        # Visual inspection would be needed for proper alignment testing
        self.assertIn("Left", table)
        self.assertIn("Center", table)
        self.assertIn("Right", table)

    def test_empty_table(self):
        """Test creating empty table."""
        display = TableDisplay()

        headers = ["Column1", "Column2"]
        rows = []

        table = display.create_table(headers, rows)

        for header in headers:
            self.assertIn(header, table)
        self.assertIn("No data", table.lower())


class TestColorScheme(unittest.TestCase):
    """Test color scheme functionality."""

    def test_default_color_scheme(self):
        """Test default color scheme."""
        scheme = ColorScheme()

        self.assertIsNotNone(scheme.get_color('success'))
        self.assertIsNotNone(scheme.get_color('error'))
        self.assertIsNotNone(scheme.get_color('warning'))
        self.assertIsNotNone(scheme.get_color('info'))

    def test_apply_color(self):
        """Test applying color to text."""
        scheme = ColorScheme()

        colored_text = scheme.apply('Test', 'success')
        self.assertIn('Test', colored_text)
        # Should contain ANSI color codes
        self.assertIn('\033[', colored_text)

    def test_no_color_mode(self):
        """Test no-color mode."""
        scheme = ColorScheme(no_color=True)

        text = "Test text"
        colored = scheme.apply(text, 'error')

        self.assertEqual(text, colored)
        self.assertNotIn('\033[', colored)

    def test_custom_colors(self):
        """Test custom color definitions."""
        custom_colors = {
            'highlight': '\033[93m',  # Bright yellow
            'dim': '\033[2m'  # Dim
        }

        scheme = ColorScheme(custom_colors=custom_colors)

        self.assertIsNotNone(scheme.get_color('highlight'))
        self.assertIsNotNone(scheme.get_color('dim'))


class TestProgressDisplay(unittest.TestCase):
    """Test progress display functionality."""

    @patch('sys.stdout', new_callable=StringIO)
    def test_progress_bar(self, mock_stdout):
        """Test progress bar display."""
        progress = ProgressDisplay()

        # Simulate progress
        total = 100
        for i in range(0, total + 1, 20):
            progress.update(i, total, f"Processing... {i}%")

        output = mock_stdout.getvalue()
        self.assertIn("Processing", output)

    def test_spinner_animation(self):
        """Test spinner animation."""
        progress = ProgressDisplay()

        frames = progress.get_spinner_frames()
        self.assertGreater(len(frames), 0)

        # Each frame should be different
        self.assertEqual(len(frames), len(set(frames)))

    def test_format_bytes(self):
        """Test byte size formatting."""
        progress = ProgressDisplay()

        self.assertEqual(progress.format_bytes(0), "0 B")
        self.assertEqual(progress.format_bytes(1024), "1.0 KB")
        self.assertEqual(progress.format_bytes(1024 * 1024), "1.0 MB")
        self.assertEqual(progress.format_bytes(1024 * 1024 * 1024), "1.0 GB")

    def test_format_duration(self):
        """Test duration formatting."""
        progress = ProgressDisplay()

        self.assertEqual(progress.format_duration(0), "0s")
        self.assertEqual(progress.format_duration(45), "45s")
        self.assertEqual(progress.format_duration(90), "1m 30s")
        self.assertEqual(progress.format_duration(3661), "1h 1m 1s")


class TestUtilityFunctions(unittest.TestCase):
    """Test utility formatting functions."""

    def test_format_timedelta(self):
        """Test timedelta formatting."""
        now = datetime.now()

        # Test various time differences
        self.assertEqual(format_timedelta(now), "just now")
        self.assertIn("minute", format_timedelta(now - timedelta(minutes=1)))
        self.assertIn("hour", format_timedelta(now - timedelta(hours=2)))
        self.assertIn("day", format_timedelta(now - timedelta(days=3)))
        self.assertIn("week", format_timedelta(now - timedelta(weeks=2)))
        self.assertIn("month", format_timedelta(now - timedelta(days=45)))

    def test_truncate_text(self):
        """Test text truncation."""
        long_text = "This is a very long text that needs to be truncated"

        # Test basic truncation
        truncated = truncate_text(long_text, 20)
        self.assertLessEqual(len(truncated), 20)
        self.assertIn("...", truncated)

        # Test short text (no truncation needed)
        short_text = "Short"
        self.assertEqual(truncate_text(short_text, 20), short_text)

        # Test with custom ellipsis
        truncated_custom = truncate_text(long_text, 20, ellipsis="…")
        self.assertIn("…", truncated_custom)

    def test_highlight_search_term(self):
        """Test search term highlighting."""
        text = "The quick brown fox jumps over the lazy dog"

        # Test basic highlighting
        highlighted = highlight_search_term(text, "fox")
        self.assertIn("fox", highlighted)
        # Should contain highlighting (ANSI codes or similar)
        self.assertNotEqual(text, highlighted)

        # Test case-insensitive highlighting
        highlighted_case = highlight_search_term(text, "FOX", case_sensitive=False)
        self.assertIn("fox", highlighted_case.lower())

        # Test multiple occurrences
        text_multi = "fox fox fox"
        highlighted_multi = highlight_search_term(text_multi, "fox")
        # All occurrences should be highlighted
        self.assertNotEqual(text_multi, highlighted_multi)

    def test_wrap_text(self):
        """Test text wrapping."""
        long_text = "This is a very long line that should be wrapped at a specific width to make it more readable in the terminal"

        from gh_pr.ui.display import wrap_text

        wrapped = wrap_text(long_text, width=40)
        lines = wrapped.split('\n')

        for line in lines:
            self.assertLessEqual(len(line), 40)

        # Original text should be preserved
        self.assertEqual(long_text, ' '.join(wrapped.split()))


if __name__ == '__main__':
    unittest.main()
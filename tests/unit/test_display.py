"""
Unit tests for UI display module.

Tests terminal UI formatting and display.
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from io import StringIO
import io

from rich.console import Console
from rich.table import Table
from gh_pr.ui.display import DisplayManager


class TestDisplayManager(unittest.TestCase):
    """Test DisplayManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a Console that writes to a capture buffer
        self.output_buffer = io.StringIO()
        self.console = Console(file=self.output_buffer, force_terminal=True, width=120, record=True)
        self.display = DisplayManager(self.console)

    def test_display_pr_header(self):
        """Test PR header display."""
        pr_data = {
            "number": 123,
            "title": "Add new feature",
            "author": "alice",
            "state": "open",
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-02T11:00:00Z",
            "labels": ["enhancement", "documentation"],
            "draft": False,
            "url": "https://github.com/owner/repo/pull/123"
        }

        self.display.display_pr_header(pr_data)

        # Capture output and check content
        output = self.output_buffer.getvalue()
        self.assertIn("123", output)
        self.assertIn("Add new feature", output)

    def test_display_pr_summary(self):
        """Test displaying PR summary."""
        pr_data = {
            "number": 456,
            "title": "Fix critical bug",
            "body": "This fixes a critical bug in the system.",
            "author": "alice",
            "state": "open"
        }

        # Just test that the method runs without error
        self.display.display_pr_summary(pr_data)

        # Check output was written
        output = self.output_buffer.getvalue()
        self.assertIn("456", output)
        self.assertIn("Fix critical bug", output)

    def test_display_error(self):
        """Test error message display."""
        error_msg = "This is an error message"
        self.display.display_error(error_msg)

        output = self.output_buffer.getvalue()
        self.assertIn(error_msg, output)

    def test_display_success(self):
        """Test success message display."""
        success_msg = "Operation completed successfully"
        self.display.display_success(success_msg)

        output = self.output_buffer.getvalue()
        self.assertIn(success_msg, output)

    def test_display_pr_reviews(self):
        """Test displaying PR reviews."""
        reviews = [
            {"state": "APPROVED", "author": "reviewer1"},
            {"state": "CHANGES_REQUESTED", "author": "reviewer2"}
        ]

        self.display.display_pr_reviews(reviews)

        output = self.output_buffer.getvalue()
        self.assertIn("APPROVED", output)
        self.assertIn("reviewer1", output)

    def test_display_comments(self):
        """Test displaying comments."""
        comments = [
            {
                "path": "src/main.py",
                "line": 42,
                "comments": [
                    {
                        "author": "reviewer1",
                        "body": "This needs refactoring",
                        "created_at": "2024-01-01T10:00:00Z"
                    }
                ],
                "is_resolved": False,
                "is_outdated": False
            }
        ]

        pr_data = {"number": 123}
        self.display.display_comments(comments, pr_data)

        output = self.output_buffer.getvalue()
        self.assertIn("src/main.py", output)
        self.assertIn("42", output)

    def test_display_summary(self):
        """Test displaying summary."""
        summary = {
            "total_threads": 10,
            "unresolved_active": 3,
            "unresolved_outdated": 2,
            "resolved_active": 4,
            "resolved_outdated": 1,
            "approvals": 2,
            "changes_requested": 1,
            "comments": 5
        }

        self.display.display_summary(summary)

        output = self.output_buffer.getvalue()
        self.assertIn("10", output)  # total threads
        self.assertIn("3", output)   # unresolved active

    def test_display_check_status(self):
        """Test displaying check status."""
        check_status = {
            "state": "success",
            "total": 5,
            "passed": 4,
            "failed": 1
        }

        self.display.display_check_status(check_status)

        output = self.output_buffer.getvalue()
        # Just verify it runs without error

    def test_format_timestamp(self):
        """Test timestamp formatting."""
        # Test ISO format
        ts = "2024-01-01T10:00:00Z"
        formatted = self.display.format_timestamp(ts)
        self.assertIsNotNone(formatted)

        # Test datetime object
        dt = datetime.now()
        formatted = self.display.format_timestamp(dt)
        self.assertIsNotNone(formatted)

        # Test None
        formatted = self.display.format_timestamp(None)
        self.assertEqual(formatted, "N/A")

    def test_truncate_text(self):
        """Test text truncation."""
        long_text = "This is a very long text that should be truncated"

        # Test truncation
        truncated = self.display.truncate_text(long_text, 20)
        self.assertLessEqual(len(truncated), 23)  # 20 + "..."

        # Test short text
        short_text = "Short"
        truncated = self.display.truncate_text(short_text, 20)
        self.assertEqual(truncated, short_text)

    def test_create_table(self):
        """Test table creation."""
        table = self.display.create_table("Test Table", ["Column 1", "Column 2"])
        self.assertIsInstance(table, Table)

    def test_display_pagination_info(self):
        """Test pagination info display."""
        self.display.display_pagination_info(1, 100, 20)

        output = self.output_buffer.getvalue()
        # Just verify it runs without error

    def test_display_suggestions(self):
        """Test displaying suggestions."""
        suggestions = [
            {
                "path": "src/main.py",
                "line": 10,
                "suggestion": "Use list comprehension",
                "diff": "-for x in range(10):\n-    result.append(x)\n+result = [x for x in range(10)]"
            }
        ]

        self.display.display_suggestions(suggestions)

        output = self.output_buffer.getvalue()
        self.assertIn("src/main.py", output)

    def test_display_pr_files(self):
        """Test displaying PR files."""
        files = [
            {
                "filename": "src/main.py",
                "additions": 10,
                "deletions": 5,
                "changes": 15,
                "status": "modified"
            }
        ]

        self.display.display_pr_files(files)

        output = self.output_buffer.getvalue()
        self.assertIn("src/main.py", output)

    def test_generate_plain_output(self):
        """Test plain output generation."""
        pr_data = {
            "number": 123,
            "title": "Test PR",
            "author": "user1",
            "state": "open"
        }

        comments = []
        summary = {
            "total_comments": 0,
            "unresolved_active": 0,
            "unresolved_outdated": 0,
            "resolved_active": 0,
            "resolved_outdated": 0
        }

        plain_output = self.display.generate_plain_output(pr_data, comments, summary)
        self.assertIn("123", plain_output)
        self.assertIn("Test PR", plain_output)

    def test_format_diff_hunk(self):
        """Test diff hunk formatting."""
        diff_hunk = "@@ -10,5 +10,7 @@ def test():"
        formatted = self.display.format_diff_hunk(diff_hunk)
        self.assertIsNotNone(formatted)

    def test_display_comment_thread(self):
        """Test displaying comment thread."""
        thread = {
            "path": "test.py",
            "line": 5,
            "comments": [
                {
                    "author": "user1",
                    "body": "Please fix this",
                    "created_at": "2024-01-01T10:00:00Z"
                }
            ]
        }

        self.display.display_comment_thread(thread)

        output = self.output_buffer.getvalue()
        self.assertIn("test.py", output)


if __name__ == '__main__':
    unittest.main()
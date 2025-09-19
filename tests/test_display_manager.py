"""Unit tests for DisplayManager class."""

from unittest.mock import Mock, patch

import pytest
from rich.console import Console
from rich.table import Table

from gh_pr.ui.display import DisplayManager


class TestDisplayManager:
    """Test DisplayManager class."""

    @pytest.fixture
    def display_manager(self):
        """Create a DisplayManager instance."""
        return DisplayManager()

    @pytest.fixture
    def mock_console(self):
        """Create a mock console."""
        with patch('gh_pr.ui.display.Console') as mock:
            yield mock.return_value

    @pytest.fixture
    def sample_pr_data(self):
        """Create sample PR data."""
        return {
            "number": 42,
            "title": "Test PR",
            "state": "open",
            "author": "testuser",
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
            "body": "This is a test PR description",
            "additions": 100,
            "deletions": 50,
            "changed_files": 5,
            "review_comments": 10,
            "comments": 3,
            "mergeable": True,
            "mergeable_state": "clean",
            "head": {"ref": "feature-branch", "sha": "abc123"},
            "base": {"ref": "main", "sha": "def456"},
        }

    @pytest.fixture
    def sample_comments(self):
        """Create sample comment threads."""
        return [
            {
                "id": "thread1",
                "path": "src/main.py",
                "line": 10,
                "is_resolved": False,
                "is_outdated": False,
                "diff_hunk": "@@ -10,5 +10,5 @@",
                "comments": [
                    {
                        "id": 1,
                        "body": "Please fix this issue",
                        "author": "reviewer1",
                        "created_at": "2024-01-01T10:00:00Z",
                    }
                ],
            },
            {
                "id": "thread2",
                "path": "src/utils.py",
                "line": 20,
                "is_resolved": True,
                "is_outdated": False,
                "comments": [
                    {
                        "id": 2,
                        "body": "Resolved comment",
                        "author": "reviewer2",
                        "created_at": "2024-01-01T11:00:00Z",
                    }
                ],
            },
        ]

    def test_display_pr_summary(self, display_manager, sample_pr_data, mock_console):
        """Test displaying PR summary."""
        display_manager.display_pr_summary(sample_pr_data)
        mock_console.print.assert_called()

    def test_display_pr_summary_handles_missing_fields(self, display_manager):
        """Test PR summary with missing fields."""
        minimal_pr = {
            "number": 1,
            "title": "Minimal PR",
            "state": "open",
        }
        # Should not raise exception
        display_manager.display_pr_summary(minimal_pr)

    def test_display_comments(self, display_manager, sample_comments, mock_console):
        """Test displaying comment threads."""
        display_manager.display_comments(sample_comments)
        mock_console.print.assert_called()

    def test_display_comments_empty_list(self, display_manager, mock_console):
        """Test displaying empty comment list."""
        display_manager.display_comments([])
        mock_console.print.assert_called()

    def test_display_comment_thread(self, display_manager, sample_comments, mock_console):
        """Test displaying a single comment thread."""
        display_manager.display_comment_thread(sample_comments[0])
        mock_console.print.assert_called()

    def test_display_check_status(self, display_manager, mock_console):
        """Test displaying check status."""
        checks_data = {
            "total": 5,
            "success": 3,
            "failure": 1,
            "pending": 1,
            "checks": [
                {"name": "Test", "status": "completed", "conclusion": "success"},
                {"name": "Build", "status": "completed", "conclusion": "failure"},
                {"name": "Deploy", "status": "in_progress", "conclusion": None},
            ],
        }
        display_manager.display_check_status(checks_data)
        mock_console.print.assert_called()

    def test_display_check_status_all_success(self, display_manager):
        """Test check status display when all checks pass."""
        checks_data = {
            "total": 3,
            "success": 3,
            "failure": 0,
            "pending": 0,
            "checks": [],
        }
        display_manager.display_check_status(checks_data)

    def test_display_pr_files(self, display_manager, mock_console):
        """Test displaying PR files."""
        files_data = [
            {
                "filename": "src/main.py",
                "status": "modified",
                "additions": 10,
                "deletions": 5,
                "changes": 15,
            },
            {
                "filename": "README.md",
                "status": "added",
                "additions": 50,
                "deletions": 0,
                "changes": 50,
            },
        ]
        display_manager.display_pr_files(files_data)
        mock_console.print.assert_called()

    def test_display_pr_files_empty(self, display_manager):
        """Test displaying empty file list."""
        display_manager.display_pr_files([])

    def test_display_summary(self, display_manager, mock_console):
        """Test displaying PR summary statistics."""
        summary_data = {
            "total_threads": 10,
            "unresolved_active": 5,
            "resolved_active": 3,
            "outdated": 2,
            "approvals": 2,
            "changes_requested": 1,
            "comments": 5,
        }
        display_manager.display_summary(summary_data)
        mock_console.print.assert_called()

    def test_display_error(self, display_manager, mock_console):
        """Test error message display."""
        display_manager.display_error("Test error message")
        mock_console.print.assert_called()

    def test_display_success(self, display_manager, mock_console):
        """Test success message display."""
        display_manager.display_success("Operation completed")
        mock_console.print.assert_called()

    def test_display_warning(self, display_manager, mock_console):
        """Test warning message display."""
        display_manager.display_warning("Warning message")
        mock_console.print.assert_called()

    def test_format_timestamp(self, display_manager):
        """Test timestamp formatting."""
        # Test ISO format
        formatted = display_manager.format_timestamp("2024-01-01T10:30:00Z")
        assert "2024-01-01" in formatted
        assert "10:30" in formatted

        # Test with None
        formatted = display_manager.format_timestamp(None)
        assert formatted == "N/A"

        # Test with invalid timestamp
        formatted = display_manager.format_timestamp("invalid")
        assert formatted == "invalid"  # Falls back to original

    def test_format_diff_hunk(self, display_manager):
        """Test diff hunk formatting."""
        diff_hunk = "@@ -10,5 +10,5 @@ def main():\n-    old_code\n+    new_code"
        formatted = display_manager.format_diff_hunk(diff_hunk)
        assert "old_code" in formatted
        assert "new_code" in formatted

    def test_truncate_text(self, display_manager):
        """Test text truncation."""
        long_text = "a" * 100
        truncated = display_manager.truncate_text(long_text, max_length=10)
        assert len(truncated) == 13  # 10 + "..."
        assert truncated.endswith("...")

        # Test short text
        short_text = "short"
        truncated = display_manager.truncate_text(short_text, max_length=10)
        assert truncated == short_text

    def test_create_table(self, display_manager):
        """Test table creation."""
        table = display_manager.create_table("Test Table", ["Col1", "Col2"])
        assert isinstance(table, Table)
        assert table.title == "Test Table"

    def test_display_pagination_info(self, display_manager, mock_console):
        """Test pagination info display."""
        display_manager.display_pagination_info(10, 50, 5)
        mock_console.print.assert_called()

    def test_display_pr_reviews(self, display_manager, mock_console):
        """Test displaying PR reviews."""
        reviews = [
            {"author": "user1", "state": "APPROVED", "body": "Looks good!"},
            {"author": "user2", "state": "CHANGES_REQUESTED", "body": "Please fix"},
        ]
        display_manager.display_pr_reviews(reviews)
        mock_console.print.assert_called()

    def test_display_suggestions(self, display_manager, mock_console):
        """Test displaying code suggestions."""
        suggestions = [
            {
                "comment_id": 1,
                "path": "src/main.py",
                "line": 10,
                "suggestion": "fixed_code()",
                "original": "broken_code()",
            }
        ]
        display_manager.display_suggestions(suggestions)
        mock_console.print.assert_called()

    def test_get_status_color(self, display_manager):
        """Test status color mapping."""
        assert display_manager.get_status_color("open") == "green"
        assert display_manager.get_status_color("closed") == "red"
        assert display_manager.get_status_color("merged") == "purple"
        assert display_manager.get_status_color("unknown") == "white"
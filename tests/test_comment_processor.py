"""Unit tests for CommentProcessor class."""

import datetime
import hashlib
from unittest.mock import Mock, patch

import pytest

from gh_pr.core.comments import CommentProcessor


class TestCommentProcessor:
    """Test CommentProcessor class."""

    @pytest.fixture
    def processor(self):
        """Create a CommentProcessor instance."""
        return CommentProcessor()

    @pytest.fixture
    def sample_comments(self):
        """Create sample comment data."""
        return [
            {
                "id": 1,
                "path": "src/main.py",
                "line": 10,
                "start_line": None,
                "body": "Please fix this",
                "author": "reviewer1",
                "created_at": "2024-01-01T10:00:00Z",
                "commit_id": "abc123",
                "position": 5,
                "original_position": 5,
                "diff_hunk": "@@ -5,7 +5,7 @@\n def main():\n-    pass\n+    print('hello')",
            },
            {
                "id": 2,
                "path": "src/main.py",
                "line": 10,
                "start_line": None,
                "body": "I agree",
                "author": "reviewer2",
                "created_at": "2024-01-01T11:00:00Z",
                "commit_id": "abc123",
                "position": 5,
                "original_position": 5,
            },
            {
                "id": 3,
                "path": "src/utils.py",
                "line": 20,
                "start_line": 18,
                "body": "Refactor needed",
                "author": "reviewer1",
                "created_at": "2024-01-01T10:30:00Z",
                "commit_id": "def456",
                "position": 10,
                "original_position": 10,
            },
        ]

    def test_organize_into_threads_same_location(self, processor, sample_comments):
        """Test that comments on the same location are grouped into one thread."""
        # First two comments are on the same location
        threads = processor.organize_into_threads(sample_comments[:2])

        assert len(threads) == 1
        assert len(threads[0]["comments"]) == 2
        assert threads[0]["path"] == "src/main.py"
        assert threads[0]["line"] == 10

    def test_organize_into_threads_different_locations(self, processor, sample_comments):
        """Test that comments on different locations create separate threads."""
        threads = processor.organize_into_threads(sample_comments)

        assert len(threads) == 2
        # First thread has two comments (same location)
        assert len(threads[0]["comments"]) == 2
        # Second thread has one comment (different location)
        assert len(threads[1]["comments"]) == 1
        assert threads[1]["path"] == "src/utils.py"

    def test_organize_into_threads_unique_ids(self, processor):
        """Test that thread IDs are unique even for similar locations."""
        comments = [
            {
                "id": 1,
                "path": "file.py",
                "line": 10,
                "body": "Comment 1",
                "author": "user1",
                "created_at": "2024-01-01T10:00:00Z",
            },
            {
                "id": 2,
                "path": "file.py",
                "line": 10,
                "body": "Comment 2",
                "author": "user2",
                "created_at": "2024-01-01T11:00:00Z",
                "commit_id": "different_commit",
            },
        ]

        threads = processor.organize_into_threads(comments)

        # Check that thread IDs are generated consistently
        thread_ids = [thread["id"] for thread in threads]
        assert len(thread_ids) == len(set(thread_ids))  # All unique

    def test_organize_into_threads_sorting(self, processor):
        """Test that comments within threads are sorted by creation time."""
        comments = [
            {
                "id": 1,
                "path": "file.py",
                "line": 10,
                "body": "Second comment",
                "author": "user1",
                "created_at": "2024-01-01T11:00:00Z",
            },
            {
                "id": 2,
                "path": "file.py",
                "line": 10,
                "body": "First comment",
                "author": "user2",
                "created_at": "2024-01-01T10:00:00Z",
            },
            {
                "id": 3,
                "path": "file.py",
                "line": 10,
                "body": "Third comment",
                "author": "user3",
                "created_at": "2024-01-01T12:00:00Z",
            },
        ]

        threads = processor.organize_into_threads(comments)

        assert len(threads) == 1
        thread_comments = threads[0]["comments"]
        assert thread_comments[0]["body"] == "First comment"
        assert thread_comments[1]["body"] == "Second comment"
        assert thread_comments[2]["body"] == "Third comment"

    def test_organize_into_threads_invalid_dates(self, processor):
        """Test handling of invalid or missing created_at dates."""
        comments = [
            {
                "id": 1,
                "path": "file.py",
                "line": 10,
                "body": "Valid date",
                "author": "user1",
                "created_at": "2024-01-01T10:00:00Z",
            },
            {
                "id": 2,
                "path": "file.py",
                "line": 10,
                "body": "Invalid date",
                "author": "user2",
                "created_at": "invalid-date",
            },
            {
                "id": 3,
                "path": "file.py",
                "line": 10,
                "body": "Missing date",
                "author": "user3",
                # No created_at field
            },
        ]

        threads = processor.organize_into_threads(comments)

        assert len(threads) == 1
        assert len(threads[0]["comments"]) == 3
        # Comments with invalid/missing dates should be placed last
        assert threads[0]["comments"][0]["body"] == "Valid date"

    def test_organize_into_threads_empty(self, processor):
        """Test organizing empty comment list."""
        threads = processor.organize_into_threads([])
        assert threads == []

    def test_is_comment_outdated_with_positions(self, processor):
        """Test outdated detection when positions differ."""
        comment = {
            "position": 10,
            "original_position": 5,
        }
        assert processor._is_comment_outdated(comment) is True

        comment = {
            "position": 10,
            "original_position": 10,
        }
        assert processor._is_comment_outdated(comment) is False

    def test_is_comment_outdated_with_none_values(self, processor):
        """Test outdated detection with None values."""
        # Both None - cannot determine
        comment = {
            "position": None,
            "original_position": None,
        }
        assert processor._is_comment_outdated(comment) is False

        # One None - consider outdated
        comment = {
            "position": 10,
            "original_position": None,
        }
        assert processor._is_comment_outdated(comment) is True

        comment = {
            "position": None,
            "original_position": 10,
        }
        assert processor._is_comment_outdated(comment) is True

    def test_is_comment_outdated_missing_fields(self, processor):
        """Test outdated detection with missing fields."""
        comment = {}
        # Missing fields should return False (cannot determine)
        assert processor._is_comment_outdated(comment) is False

    def test_extract_suggestions(self, processor):
        """Test extracting suggestions from comments."""
        comments = [
            {
                "id": 1,
                "path": "file.py",
                "line": 10,
                "author": "reviewer",
                "body": "Please use this:\n```suggestion\nprint('hello world')\n```",
            },
            {
                "id": 2,
                "path": "file.py",
                "line": 20,
                "author": "reviewer",
                "body": "No suggestion here",
            },
        ]

        suggestions = processor.extract_suggestions(comments)

        assert len(suggestions) == 1
        assert suggestions[0]["comment_id"] == 1
        assert suggestions[0]["suggestion"] == "print('hello world')"
        assert suggestions[0]["path"] == "file.py"

    def test_extract_suggestions_multiple(self, processor):
        """Test extracting multiple suggestions from one comment."""
        comments = [
            {
                "id": 1,
                "path": "file.py",
                "line": 10,
                "author": "reviewer",
                "body": (
                    "Two suggestions:\n"
                    "```suggestion\nfix1()\n```\n"
                    "And also:\n"
                    "```suggestion\nfix2()\n```"
                ),
            }
        ]

        suggestions = processor.extract_suggestions(comments)

        assert len(suggestions) == 2
        assert suggestions[0]["suggestion"] == "fix1()"
        assert suggestions[1]["suggestion"] == "fix2()"

    def test_extract_suggestions_malformed(self, processor):
        """Test handling malformed suggestion blocks."""
        comments = [
            {
                "id": 1,
                "path": "file.py",
                "author": "reviewer",
                "body": "```suggestion",  # Unclosed block
            },
            {
                "id": 2,
                "path": "file.py",
                "author": "reviewer",
                "body": "suggestion\nsome code\n```",  # Missing opening
            },
        ]

        suggestions = processor.extract_suggestions(comments)
        assert len(suggestions) == 0  # No valid suggestions found

    def test_extract_original_code(self, processor):
        """Test extracting original code from diff hunk."""
        comment = {
            "diff_hunk": "@@ -5,7 +5,7 @@\n def main():\n-    pass\n+    print('hello')\n     return"
        }

        original = processor._extract_original_code(comment)
        assert original == "pass"  # First line starting with - or +

    def test_extract_original_code_empty_diff(self, processor):
        """Test extracting from empty or missing diff hunk."""
        comment = {"diff_hunk": ""}
        assert processor._extract_original_code(comment) is None

        comment = {}  # Missing diff_hunk
        assert processor._extract_original_code(comment) is None

    def test_extract_original_code_no_changes(self, processor):
        """Test extracting from diff with no changed lines."""
        comment = {
            "diff_hunk": "@@ -5,7 +5,7 @@\n def main():\n     unchanged line\n     another unchanged"
        }

        original = processor._extract_original_code(comment)
        assert original is None  # No lines starting with + or -

    def test_thread_fields(self, processor):
        """Test that threads have all expected fields."""
        comments = [
            {
                "id": 1,
                "path": "file.py",
                "line": 10,
                "start_line": 8,
                "body": "Comment",
                "author": "user",
                "diff_hunk": "@@ diff @@",
                "position": 5,
                "original_position": 5,
            }
        ]

        threads = processor.organize_into_threads(comments)

        assert len(threads) == 1
        thread = threads[0]
        assert "id" in thread
        assert thread["path"] == "file.py"
        assert thread["line"] == 10
        assert thread["start_line"] == 8
        assert thread["is_resolved"] is False  # Default
        assert thread["is_outdated"] is False  # Same positions
        assert thread["diff_hunk"] == "@@ diff @@"
        assert len(thread["comments"]) == 1
"""
Unit tests for comment filtering functionality.

Tests comment filter behavior for various modes.
"""

import unittest
from gh_pr.core.filters import CommentFilter


class TestCommentFilter(unittest.TestCase):
    """Test comment filtering functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.filter = CommentFilter()
        self.sample_threads = [
            {
                "id": 1,
                "is_resolved": False,
                "is_outdated": False,
                "comments": [{"author": "user1", "body": "Comment 1"}]
            },
            {
                "id": 2,
                "is_resolved": True,
                "is_outdated": False,
                "comments": [{"author": "user2", "body": "Comment 2"}]
            },
            {
                "id": 3,
                "is_resolved": False,
                "is_outdated": True,
                "comments": [{"author": "user3", "body": "Comment 3"}]
            }
        ]

    def test_filter_comments_all_mode(self):
        """Test filtering with 'all' mode."""
        result = self.filter.filter_comments(self.sample_threads, "all")
        self.assertEqual(len(result), 3)

    def test_filter_comments_unresolved_mode(self):
        """Test filtering with 'unresolved' mode."""
        result = self.filter.filter_comments(self.sample_threads, "unresolved")
        self.assertEqual(len(result), 2)  # Thread 1 and 3
        self.assertFalse(result[0]["is_resolved"])
        self.assertFalse(result[1]["is_resolved"])

    def test_filter_comments_resolved_active_mode(self):
        """Test filtering with 'resolved_active' mode."""
        result = self.filter.filter_comments(self.sample_threads, "resolved_active")
        self.assertEqual(len(result), 1)  # Thread 2
        self.assertTrue(result[0]["is_resolved"])
        self.assertFalse(result[0]["is_outdated"])

    def test_filter_comments_invalid_mode(self):
        """Test filtering with invalid mode defaults to 'all'."""
        result = self.filter.filter_comments(self.sample_threads, "invalid_mode")
        self.assertEqual(len(result), 3)  # Should return all threads
        self.assertEqual(result, self.sample_threads)

    def test_filter_by_author(self):
        """Test filtering threads by author."""
        result = self.filter.filter_by_author(self.sample_threads, "user1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], 1)

    def test_filter_by_path(self):
        """Test filtering threads by file path pattern."""
        threads_with_paths = [
            {"id": 1, "path": "src/main.py"},
            {"id": 2, "path": "tests/test_main.py"},
            {"id": 3, "path": "docs/readme.md"}
        ]

        result = self.filter.filter_by_path(threads_with_paths, "*.py")
        self.assertEqual(len(result), 2)

        result = self.filter.filter_by_path(threads_with_paths, "src/*")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["path"], "src/main.py")


if __name__ == '__main__':
    unittest.main()
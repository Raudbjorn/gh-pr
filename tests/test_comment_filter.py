"""Unit tests for CommentFilter class."""

from unittest.mock import Mock

import pytest

from gh_pr.core.filters import CommentFilter


class TestCommentFilter:
    """Test CommentFilter class."""

    @pytest.fixture
    def filter(self):
        """Create a CommentFilter instance."""
        return CommentFilter()

    @pytest.fixture
    def sample_threads(self):
        """Create sample thread data."""
        return [
            {
                "id": "thread1",
                "path": "src/main.py",
                "line": 10,
                "is_resolved": False,
                "is_outdated": False,
                "comments": [
                    {
                        "id": 1,
                        "body": "Please fix this",
                        "author": "reviewer1",
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
                        "body": "Fixed",
                        "author": "reviewer2",
                    }
                ],
            },
            {
                "id": "thread3",
                "path": "src/main.py",
                "line": 30,
                "is_resolved": False,
                "is_outdated": True,
                "comments": [
                    {
                        "id": 3,
                        "body": "Outdated comment",
                        "author": "reviewer1",
                    }
                ],
            },
        ]

    def test_filter_all(self, filter, sample_threads):
        """Test filtering with 'all' filter."""
        result = filter.filter_comments(sample_threads, "all")
        assert len(result) == 3
        assert result == sample_threads

    def test_filter_unresolved(self, filter, sample_threads):
        """Test filtering unresolved comments."""
        result = filter.filter_comments(sample_threads, "unresolved")
        assert len(result) == 2
        assert all(not thread["is_resolved"] for thread in result)
        assert result[0]["id"] == "thread1"
        assert result[1]["id"] == "thread3"

    def test_filter_current_unresolved(self, filter, sample_threads):
        """Test filtering current unresolved comments."""
        result = filter.filter_comments(sample_threads, "current_unresolved")
        assert len(result) == 1  # Only thread1 is unresolved and not outdated
        assert result[0]["id"] == "thread1"
        assert not result[0]["is_resolved"]
        assert not result[0]["is_outdated"]
    def test_filter_unresolved_outdated(self, filter, sample_threads):
        """Test filtering unresolved outdated comments."""
        result = filter.filter_comments(sample_threads, "unresolved_outdated")
        assert len(result) == 1
        assert result[0]["id"] == "thread3"
        assert not result[0]["is_resolved"]
        assert result[0]["is_outdated"]
    def test_filter_by_path(self, filter, sample_threads):
        """Test filtering by file path."""
        result = filter.filter_comments(sample_threads, "all", path="src/main.py")
        assert len(result) == 2
        assert all(thread["path"] == "src/main.py" for thread in result)

    def test_filter_by_author(self, filter, sample_threads):
        """Test filtering by author."""
        result = filter.filter_comments(sample_threads, "all", author="reviewer1")
        assert len(result) == 2
        for thread in result:
            assert any(
                comment["author"] == "reviewer1" for comment in thread["comments"]
            )

    def test_filter_by_keyword(self, filter, sample_threads):
        """Test filtering by keyword in comment body."""
        result = filter.filter_comments(sample_threads, "all", keyword="fix")
        assert len(result) == 2
        for thread in result:
            assert any(
                "fix" in comment["body"].lower() for comment in thread["comments"]
            )

    def test_filter_combined_filters(self, filter, sample_threads):
        """Test combining multiple filters."""
        result = filter.filter_comments(
            sample_threads, "unresolved", path="src/main.py"
        )
        assert len(result) == 1
        assert result[0]["id"] == "thread1"
        assert not result[0]["is_resolved"]
        assert result[0]["path"] == "src/main.py"

    def test_filter_case_insensitive_keyword(self, filter, sample_threads):
        """Test that keyword filtering is case-insensitive."""
        result = filter.filter_comments(sample_threads, "all", keyword="FIX")
        assert len(result) == 2
        # Should find both "fix" and "Fixed"

    def test_filter_empty_threads(self, filter):
        """Test filtering empty thread list."""
        result = filter.filter_comments([], "unresolved")
        assert result == []

    def test_filter_invalid_filter_type(self, filter, sample_threads):
        """Test with invalid filter type defaults to 'all'."""
        result = filter.filter_comments(sample_threads, "invalid")
        assert len(result) == 3  # Should return all threads

    def test_filter_by_nonexistent_author(self, filter, sample_threads):
        """Test filtering by author that doesn't exist."""
        result = filter.filter_comments(sample_threads, "all", author="nonexistent")
        assert len(result) == 0

    def test_filter_by_nonexistent_path(self, filter, sample_threads):
        """Test filtering by path that doesn't exist."""
        result = filter.filter_comments(sample_threads, "all", path="nonexistent.py")
        assert len(result) == 0

    def test_get_filter_stats(self, filter, sample_threads):
        """Test getting statistics for filtered comments."""
        stats = filter.get_filter_stats(sample_threads)
        assert stats["total"] == 3
        assert stats["unresolved"] == 2
        assert stats["resolved"] == 1
        assert stats["active"] == 2
        assert stats["outdated"] == 1

    def test_get_filter_stats_empty(self, filter):
        """Test statistics for empty thread list."""
        stats = filter.get_filter_stats([])
        assert stats["total"] == 0
        assert stats["unresolved"] == 0
        assert stats["resolved"] == 0
        assert stats["active"] == 0
        assert stats["outdated"] == 0

    def test_filter_threads_without_comments(self, filter):
        """Test filtering threads that have no comments."""
        threads = [
            {
                "id": "thread1",
                "path": "file.py",
                "is_resolved": False,
                "is_outdated": False,
                "comments": [],
            }
        ]
        result = filter.filter_comments(threads, "unresolved")
        assert len(result) == 1  # Thread still included even with no comments

    def test_filter_by_multiple_authors(self, filter):
        """Test that threads with multiple authors are handled correctly."""
        threads = [
            {
                "id": "thread1",
                "path": "file.py",
                "is_resolved": False,
                "is_outdated": False,
                "comments": [
                    {"id": 1, "body": "Comment 1", "author": "author1"},
                    {"id": 2, "body": "Comment 2", "author": "author2"},
                ],
            }
        ]

        result = filter.filter_by_author(threads, "author1")
        assert len(result) == 1

        result = filter.filter_by_author(threads, "author2")
        assert len(result) == 1

        result = filter.filter_by_author(threads, "author3")
        assert len(result) == 0
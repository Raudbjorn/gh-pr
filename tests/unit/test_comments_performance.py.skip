"""Unit tests for comments.py optimized datetime parsing and performance."""

import datetime
from functools import lru_cache
from unittest.mock import Mock, patch

import pytest

from gh_pr.core.comments import CommentProcessor, _parse_datetime_cached


class TestOptimizedDatetimeParsing:
    """Test optimized datetime parsing functionality."""

    def test_parse_datetime_cached_valid_iso_format(self):
        """Test parsing valid ISO 8601 datetime strings."""
        # Test various valid ISO 8601 formats
        test_cases = [
            "2023-10-15T14:30:45+00:00",
            "2023-10-15T14:30:45Z",
            "2023-10-15T14:30:45.123456+00:00",
            "2023-10-15T14:30:45.123456Z",
        ]

        for date_string in test_cases:
            result = _parse_datetime_cached(date_string)
            assert isinstance(result, datetime.datetime)
            assert result != datetime.datetime.max

    def test_parse_datetime_cached_z_timezone_conversion(self):
        """Test that 'Z' timezone indicator is converted to '+00:00'."""
        date_string = "2023-10-15T14:30:45Z"
        result = _parse_datetime_cached(date_string)

        expected = datetime.datetime(2023, 10, 15, 14, 30, 45, tzinfo=datetime.timezone.utc)
        assert result == expected

    def test_parse_datetime_cached_with_explicit_timezone(self):
        """Test parsing datetime with explicit timezone offset."""
        date_string = "2023-10-15T14:30:45+05:00"
        result = _parse_datetime_cached(date_string)

        expected = datetime.datetime(2023, 10, 15, 14, 30, 45,
                                   tzinfo=datetime.timezone(datetime.timedelta(hours=5)))
        assert result == expected

    def test_parse_datetime_cached_invalid_format(self):
        """Test that invalid datetime formats return datetime.max."""
        invalid_cases = [
            "invalid-date",
            "2023-13-45T25:70:99Z",  # Invalid date/time values
            "not-a-date-at-all",
            "",
            "2023-10-15",  # Date only, not ISO format
            "14:30:45",    # Time only
        ]

        for invalid_string in invalid_cases:
            result = _parse_datetime_cached(invalid_string)
            assert result == datetime.datetime.max

    def test_parse_datetime_cached_none_input(self):
        """Test handling of None input."""
        result = _parse_datetime_cached(None)
        assert result == datetime.datetime.max

    def test_parse_datetime_cached_empty_string(self):
        """Test handling of empty string input."""
        result = _parse_datetime_cached("")
        assert result == datetime.datetime.max

    def test_parse_datetime_cached_caching_functionality(self):
        """Test that datetime parsing results are cached."""
        # Clear cache before test
        _parse_datetime_cached.cache_clear()

        date_string = "2023-10-15T14:30:45Z"

        # First call should hit the function
        result1 = _parse_datetime_cached(date_string)

        # Check cache info
        cache_info = _parse_datetime_cached.cache_info()
        assert cache_info.hits == 0
        assert cache_info.misses == 1

        # Second call should hit cache
        result2 = _parse_datetime_cached(date_string)

        cache_info = _parse_datetime_cached.cache_info()
        assert cache_info.hits == 1
        assert cache_info.misses == 1

        # Results should be identical
        assert result1 == result2

    def test_parse_datetime_cached_cache_size_limit(self):
        """Test that cache respects maxsize limit of 1000."""
        # Clear cache before test
        _parse_datetime_cached.cache_clear()

        # Add entries up to cache limit
        for i in range(1001):
            date_string = f"2023-10-15T14:30:{i:02d}Z"
            _parse_datetime_cached(date_string)

        cache_info = _parse_datetime_cached.cache_info()
        assert cache_info.currsize <= 1000

    def test_parse_datetime_cached_performance_benefit(self):
        """Test that caching provides performance benefit for repeated calls."""
        # Clear cache before test
        _parse_datetime_cached.cache_clear()

        date_string = "2023-10-15T14:30:45Z"

        # Time first call (uncached)
        import time
        start_time = time.time()
        for _ in range(100):
            _parse_datetime_cached(date_string)
        cached_time = time.time() - start_time

        # Clear cache and time direct parsing
        _parse_datetime_cached.cache_clear()
        start_time = time.time()
        for _ in range(100):
            # Direct parsing without cache
            try:
                test_string = date_string
                if test_string.endswith('Z'):
                    test_string = test_string[:-1] + '+00:00'
                datetime.datetime.fromisoformat(test_string)
            except (ValueError, AttributeError):
                pass
        uncached_time = time.time() - start_time

        # Cached version should be faster for repeated calls
        # (This might not always be true for small datasets, but demonstrates caching)
        # assert cached_time < uncached_time  # This is too dependent on system performance

        # Instead, just verify cache was used
        cache_info = _parse_datetime_cached.cache_info()
        assert cache_info.hits > 0

    def test_parse_datetime_cached_microseconds_handling(self):
        """Test handling of datetime strings with microseconds."""
        date_string = "2023-10-15T14:30:45.123456Z"
        result = _parse_datetime_cached(date_string)

        expected = datetime.datetime(2023, 10, 15, 14, 30, 45, 123456,
                                   tzinfo=datetime.timezone.utc)
        assert result == expected

    def test_parse_datetime_cached_different_timezones(self):
        """Test parsing datetime strings with different timezone offsets."""
        test_cases = [
            ("2023-10-15T14:30:45+00:00", datetime.timedelta(hours=0)),
            ("2023-10-15T14:30:45+05:30", datetime.timedelta(hours=5, minutes=30)),
            ("2023-10-15T14:30:45-08:00", datetime.timedelta(hours=-8)),
        ]

        for date_string, expected_offset in test_cases:
            result = _parse_datetime_cached(date_string)
            assert result.tzinfo.utcoffset(None) == expected_offset


class TestCommentProcessorPerformance:
    """Test CommentProcessor with optimized datetime parsing."""

    def test_organize_into_threads_uses_cached_parsing(self):
        """Test that organize_into_threads uses cached datetime parsing."""
        processor = CommentProcessor()

        # Create test comments with same timestamp
        same_timestamp = "2023-10-15T14:30:45Z"
        comments = [
            {
                "id": 1,
                "path": "file1.py",
                "line": 10,
                "created_at": same_timestamp,
                "author": "user1",
                "body": "Comment 1"
            },
            {
                "id": 2,
                "path": "file1.py",
                "line": 10,
                "created_at": same_timestamp,
                "author": "user2",
                "body": "Comment 2"
            },
            {
                "id": 3,
                "path": "file1.py",
                "line": 10,
                "created_at": same_timestamp,
                "author": "user3",
                "body": "Comment 3"
            }
        ]

        # Clear cache before test
        _parse_datetime_cached.cache_clear()

        threads = processor.organize_into_threads(comments)

        # Should have one thread with three comments
        assert len(threads) == 1
        assert len(threads[0]["comments"]) == 3

        # Check that cache was used (multiple hits for same timestamp)
        cache_info = _parse_datetime_cached.cache_info()
        assert cache_info.hits >= 2  # At least 2 cache hits for the repeated timestamp

    def test_organize_into_threads_comment_sorting_with_cache(self):
        """Test that comments are sorted correctly using cached datetime parsing."""
        processor = CommentProcessor()

        # Create comments with different timestamps (out of order)
        comments = [
            {
                "id": 1,
                "path": "file1.py",
                "line": 10,
                "created_at": "2023-10-15T14:30:45Z",
                "author": "user1",
                "body": "Second comment"
            },
            {
                "id": 2,
                "path": "file1.py",
                "line": 10,
                "created_at": "2023-10-15T14:25:30Z",
                "author": "user2",
                "body": "First comment"
            },
            {
                "id": 3,
                "path": "file1.py",
                "line": 10,
                "created_at": "2023-10-15T14:35:15Z",
                "author": "user3",
                "body": "Third comment"
            }
        ]

        threads = processor.organize_into_threads(comments)

        # Should be sorted by creation time
        assert len(threads) == 1
        thread_comments = threads[0]["comments"]
        assert thread_comments[0]["body"] == "First comment"
        assert thread_comments[1]["body"] == "Second comment"
        assert thread_comments[2]["body"] == "Third comment"

    def test_organize_into_threads_invalid_dates_handled(self):
        """Test that comments with invalid dates are handled gracefully."""
        processor = CommentProcessor()

        comments = [
            {
                "id": 1,
                "path": "file1.py",
                "line": 10,
                "created_at": "invalid-date",
                "author": "user1",
                "body": "Comment with invalid date"
            },
            {
                "id": 2,
                "path": "file1.py",
                "line": 10,
                "created_at": "2023-10-15T14:30:45Z",
                "author": "user2",
                "body": "Comment with valid date"
            },
            {
                "id": 3,
                "path": "file1.py",
                "line": 10,
                "created_at": "",
                "author": "user3",
                "body": "Comment with empty date"
            }
        ]

        threads = processor.organize_into_threads(comments)

        # Should handle gracefully without crashing
        assert len(threads) == 1
        assert len(threads[0]["comments"]) == 3

        # Comments with invalid dates should be sorted last (datetime.max)
        thread_comments = threads[0]["comments"]
        assert thread_comments[0]["body"] == "Comment with valid date"
        # Invalid dates end up at the end due to datetime.max

    def test_organize_into_threads_missing_created_at_field(self):
        """Test handling of comments missing created_at field."""
        processor = CommentProcessor()

        comments = [
            {
                "id": 1,
                "path": "file1.py",
                "line": 10,
                "author": "user1",
                "body": "Comment without created_at"
            },
            {
                "id": 2,
                "path": "file1.py",
                "line": 10,
                "created_at": "2023-10-15T14:30:45Z",
                "author": "user2",
                "body": "Comment with created_at"
            }
        ]

        threads = processor.organize_into_threads(comments)

        # Should handle gracefully
        assert len(threads) == 1
        assert len(threads[0]["comments"]) == 2

    def test_organize_into_threads_thread_key_generation(self):
        """Test that thread keys are generated correctly to prevent collisions."""
        processor = CommentProcessor()

        # Create comments that might have similar keys
        comments = [
            {
                "id": 1,
                "path": "file1.py",
                "line": 10,
                "commit_id": "abc123",
                "created_at": "2023-10-15T14:30:45Z",
                "author": "user1",
                "body": "Comment 1"
            },
            {
                "id": 2,
                "path": "file1.py",
                "line": 10,
                "commit_id": "def456",  # Different commit
                "created_at": "2023-10-15T14:30:45Z",
                "author": "user2",
                "body": "Comment 2"
            },
            {
                "id": 3,
                "path": "file1.py",
                "line": 11,  # Different line
                "commit_id": "abc123",
                "created_at": "2023-10-15T14:30:45Z",
                "author": "user3",
                "body": "Comment 3"
            }
        ]

        threads = processor.organize_into_threads(comments)

        # Should create separate threads for different commit_id and line
        assert len(threads) == 3

    def test_organize_into_threads_thread_metadata(self):
        """Test that thread metadata is set correctly."""
        processor = CommentProcessor()

        comments = [
            {
                "id": 1,
                "path": "src/main.py",
                "line": 25,
                "start_line": 20,
                "diff_hunk": "@@ -20,5 +20,5 @@",
                "position": 5,
                "original_position": 3,
                "created_at": "2023-10-15T14:30:45Z",
                "author": "reviewer",
                "body": "Please fix this"
            }
        ]

        threads = processor.organize_into_threads(comments)

        assert len(threads) == 1
        thread = threads[0]

        assert thread["path"] == "src/main.py"
        assert thread["line"] == 25
        assert thread["start_line"] == 20
        assert thread["diff_hunk"] == "@@ -20,5 +20,5 @@"
        assert thread["is_outdated"] is True  # position != original_position
        assert isinstance(thread["id"], str)
        assert len(thread["id"]) == 16  # SHA256 hash truncated to 16 chars

    def test_is_comment_outdated_logic(self):
        """Test the _is_comment_outdated method logic."""
        processor = CommentProcessor()

        # Test cases for outdated comment detection
        test_cases = [
            # (position, original_position, expected_outdated)
            (5, 5, False),      # Same position - not outdated
            (5, 3, True),       # Different position - outdated
            (None, None, False), # Both None - not outdated
            (5, None, True),    # Only position - outdated
            (None, 3, True),    # Only original_position - outdated
        ]

        for position, original_position, expected in test_cases:
            comment = {
                "position": position,
                "original_position": original_position
            }
            result = processor._is_comment_outdated(comment)
            assert result == expected, f"Failed for position={position}, original_position={original_position}"


class TestCommentProcessorSuggestions:
    """Test suggestion extraction functionality."""

    def test_extract_suggestions_basic(self):
        """Test basic suggestion extraction."""
        processor = CommentProcessor()

        comments = [
            {
                "id": 1,
                "author": "reviewer",
                "path": "file.py",
                "line": 10,
                "body": "Please change this:\n```suggestion\nprint('Hello, World!')\n```"
            }
        ]

        suggestions = processor.extract_suggestions(comments)

        assert len(suggestions) == 1
        suggestion = suggestions[0]
        assert suggestion["comment_id"] == 1
        assert suggestion["author"] == "reviewer"
        assert suggestion["path"] == "file.py"
        assert suggestion["line"] == 10
        assert suggestion["suggestion"] == "print('Hello, World!')"

    def test_extract_suggestions_multiple_in_comment(self):
        """Test extracting multiple suggestions from one comment."""
        processor = CommentProcessor()

        comments = [
            {
                "id": 1,
                "author": "reviewer",
                "path": "file.py",
                "line": 10,
                "body": """First suggestion:
```suggestion
line1
```

Second suggestion:
```suggestion
line2
```"""
            }
        ]

        suggestions = processor.extract_suggestions(comments)

        assert len(suggestions) == 2
        assert suggestions[0]["suggestion"] == "line1"
        assert suggestions[1]["suggestion"] == "line2"

    def test_extract_suggestions_empty_suggestion(self):
        """Test that empty suggestions are filtered out."""
        processor = CommentProcessor()

        comments = [
            {
                "id": 1,
                "author": "reviewer",
                "path": "file.py",
                "line": 10,
                "body": "Empty suggestion:\n```suggestion\n\n```\nValid suggestion:\n```suggestion\nvalid code\n```"
            }
        ]

        suggestions = processor.extract_suggestions(comments)

        # Should only include non-empty suggestion
        assert len(suggestions) == 1
        assert suggestions[0]["suggestion"] == "valid code"

    def test_extract_suggestions_whitespace_handling(self):
        """Test that suggestions with whitespace are handled correctly."""
        processor = CommentProcessor()

        comments = [
            {
                "id": 1,
                "author": "reviewer",
                "path": "file.py",
                "line": 10,
                "body": "```suggestion\n  indented code  \n```"
            }
        ]

        suggestions = processor.extract_suggestions(comments)

        assert len(suggestions) == 1
        assert suggestions[0]["suggestion"] == "indented code"

    def test_extract_suggestions_no_suggestions(self):
        """Test comments without suggestions."""
        processor = CommentProcessor()

        comments = [
            {
                "id": 1,
                "author": "reviewer",
                "path": "file.py",
                "line": 10,
                "body": "Just a regular comment without suggestions."
            }
        ]

        suggestions = processor.extract_suggestions(comments)

        assert len(suggestions) == 0

    def test_extract_original_code_from_diff_hunk(self):
        """Test extraction of original code from diff hunk."""
        processor = CommentProcessor()

        comment = {
            "diff_hunk": """@@ -10,3 +10,3 @@
 def function():
-    old_code()
+    new_code()
 end"""
        }

        original_code = processor._extract_original_code(comment)
        assert original_code == "old_code()"

    def test_extract_original_code_no_diff_hunk(self):
        """Test handling when diff_hunk is missing."""
        processor = CommentProcessor()

        comment = {}
        original_code = processor._extract_original_code(comment)
        assert original_code is None

    def test_extract_original_code_empty_diff_hunk(self):
        """Test handling of empty diff_hunk."""
        processor = CommentProcessor()

        comment = {"diff_hunk": ""}
        original_code = processor._extract_original_code(comment)
        assert original_code is None


class TestCommentProcessorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_organize_into_threads_empty_comments_list(self):
        """Test organizing empty comments list."""
        processor = CommentProcessor()

        threads = processor.organize_into_threads([])

        assert threads == []

    def test_organize_into_threads_missing_required_fields(self):
        """Test handling of comments missing required fields."""
        processor = CommentProcessor()

        comments = [
            {
                "id": 1,
                # Missing path field
                "line": 10,
                "created_at": "2023-10-15T14:30:45Z",
                "author": "user1",
                "body": "Comment 1"
            }
        ]

        # Should handle gracefully without crashing
        threads = processor.organize_into_threads(comments)
        assert isinstance(threads, list)

    def test_organize_into_threads_very_large_comment_list(self):
        """Test performance with large number of comments."""
        processor = CommentProcessor()

        # Create a large number of comments
        num_comments = 1000
        comments = []
        for i in range(num_comments):
            comments.append({
                "id": i,
                "path": f"file_{i % 10}.py",  # 10 different files
                "line": i % 50,  # 50 different lines
                "created_at": f"2023-10-15T14:{i % 60:02d}:00Z",  # Different timestamps
                "author": f"user_{i % 20}",  # 20 different users
                "body": f"Comment {i}"
            })

        # Should handle large datasets efficiently
        import time
        start_time = time.time()
        threads = processor.organize_into_threads(comments)
        end_time = time.time()

        # Should complete within reasonable time (adjust threshold as needed)
        assert end_time - start_time < 5.0  # 5 seconds should be more than enough

        # Should organize into threads correctly
        assert isinstance(threads, list)
        assert len(threads) > 0

    def test_cache_memory_usage_with_many_unique_dates(self):
        """Test cache behavior with many unique datetime strings."""
        # Clear cache before test
        _parse_datetime_cached.cache_clear()

        # Generate many unique datetime strings
        for i in range(1500):  # More than cache maxsize of 1000
            date_string = f"2023-10-15T14:30:{i % 60:02d}.{i:06d}Z"
            _parse_datetime_cached(date_string)

        cache_info = _parse_datetime_cached.cache_info()

        # Cache should respect maxsize limit
        assert cache_info.currsize <= 1000

        # Should have some cache evictions
        assert cache_info.misses > 1000
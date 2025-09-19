"""Unit tests for CacheManager class."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from gh_pr.utils.cache import CacheManager


class TestCacheManager:
    """Test CacheManager class."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cache_manager(self, temp_cache_dir):
        """Create a CacheManager instance with temp directory."""
        return CacheManager(cache_dir=temp_cache_dir, ttl_seconds=3600)

    def test_init_default(self):
        """Test CacheManager initialization with defaults."""
        manager = CacheManager()
        assert manager.enabled is True
        assert manager.ttl == timedelta(seconds=3600)
        assert manager.cache_dir.name == ".gh-pr-cache"

    def test_init_custom(self, temp_cache_dir):
        """Test CacheManager initialization with custom values."""
        manager = CacheManager(
            cache_dir=temp_cache_dir, ttl_seconds=7200, enabled=False
        )
        assert manager.enabled is False
        assert manager.ttl == timedelta(seconds=7200)
        assert manager.cache_dir == temp_cache_dir

    def test_init_creates_cache_dir(self, temp_cache_dir):
        """Test that initialization creates cache directory."""
        cache_path = temp_cache_dir / "cache"
        assert not cache_path.exists()
        CacheManager(cache_dir=cache_path)
        assert cache_path.exists()

    def test_get_cache_key(self, cache_manager):
        """Test cache key generation."""
        key = cache_manager._get_cache_key("owner", "repo", 42, "data")
        assert key == "owner_repo_42_data"

        # Test with special characters
        key = cache_manager._get_cache_key("my-org", "my.repo", 123, "pr-data")
        assert key == "my-org_my.repo_123_pr-data"

    def test_get_cache_path(self, cache_manager):
        """Test cache path generation."""
        path = cache_manager._get_cache_path("test_key")
        assert path.parent == cache_manager.cache_dir
        assert path.name == "test_key.json"

    def test_set_and_get(self, cache_manager):
        """Test setting and getting cached data."""
        data = {"test": "data", "number": 42}
        cache_manager.set("owner", "repo", 42, "test", data)

        retrieved = cache_manager.get("owner", "repo", 42, "test")
        assert retrieved == data

    def test_get_nonexistent(self, cache_manager):
        """Test getting non-existent cache entry."""
        result = cache_manager.get("owner", "repo", 999, "missing")
        assert result is None

    def test_get_expired(self, cache_manager):
        """Test getting expired cache entry."""
        data = {"test": "data"}
        cache_manager.set("owner", "repo", 42, "test", data)

        # Modify the cache file to have old timestamp
        key = cache_manager._get_cache_key("owner", "repo", 42, "test")
        cache_path = cache_manager._get_cache_path(key)

        old_time = datetime.now() - timedelta(seconds=7200)
        cache_data = {
            "timestamp": old_time.isoformat(),
            "data": data,
        }
        cache_path.write_text(json.dumps(cache_data))

        # Should return None for expired data
        result = cache_manager.get("owner", "repo", 42, "test")
        assert result is None

    def test_get_disabled(self, temp_cache_dir):
        """Test that get returns None when cache is disabled."""
        manager = CacheManager(cache_dir=temp_cache_dir, enabled=False)
        manager.set("owner", "repo", 42, "test", {"data": "value"})
        result = manager.get("owner", "repo", 42, "test")
        assert result is None

    def test_set_disabled(self, temp_cache_dir):
        """Test that set does nothing when cache is disabled."""
        manager = CacheManager(cache_dir=temp_cache_dir, enabled=False)
        manager.set("owner", "repo", 42, "test", {"data": "value"})

        # Check that no cache file was created
        key = manager._get_cache_key("owner", "repo", 42, "test")
        cache_path = manager._get_cache_path(key)
        assert not cache_path.exists()

    def test_invalidate(self, cache_manager):
        """Test cache invalidation."""
        data = {"test": "data"}
        cache_manager.set("owner", "repo", 42, "test", data)

        # Verify data is cached
        assert cache_manager.get("owner", "repo", 42, "test") == data

        # Invalidate
        cache_manager.invalidate("owner", "repo", 42, "test")

        # Verify data is gone
        assert cache_manager.get("owner", "repo", 42, "test") is None

    def test_invalidate_nonexistent(self, cache_manager):
        """Test invalidating non-existent cache entry."""
        # Should not raise exception
        cache_manager.invalidate("owner", "repo", 999, "missing")

    def test_clear_all(self, cache_manager):
        """Test clearing all cache entries."""
        # Set multiple cache entries
        cache_manager.set("owner1", "repo1", 1, "data", {"value": 1})
        cache_manager.set("owner2", "repo2", 2, "data", {"value": 2})

        # Clear all
        cache_manager.clear_all()

        # Verify all entries are gone
        assert cache_manager.get("owner1", "repo1", 1, "data") is None
        assert cache_manager.get("owner2", "repo2", 2, "data") is None

    def test_clear_all_empty_cache(self, cache_manager):
        """Test clearing empty cache directory."""
        # Should not raise exception
        cache_manager.clear_all()

    def test_get_cache_size(self, cache_manager):
        """Test getting cache size."""
        initial_size = cache_manager.get_cache_size()
        assert initial_size >= 0

        # Add some data
        large_data = {"data": "x" * 1000}
        cache_manager.set("owner", "repo", 42, "test", large_data)

        new_size = cache_manager.get_cache_size()
        assert new_size > initial_size

    def test_get_cache_stats(self, cache_manager):
        """Test getting cache statistics."""
        # Add some cache entries
        cache_manager.set("owner1", "repo1", 1, "data", {"value": 1})
        cache_manager.set("owner2", "repo2", 2, "data", {"value": 2})

        stats = cache_manager.get_cache_stats()
        assert stats["total_files"] == 2
        assert stats["total_size"] > 0
        assert "oldest_entry" in stats
        assert "newest_entry" in stats

    def test_cleanup_expired(self, cache_manager):
        """Test cleaning up expired entries."""
        # Set data
        cache_manager.set("owner", "repo", 42, "test", {"data": "value"})

        # Manually create an expired entry
        expired_key = "expired_entry"
        expired_path = cache_manager._get_cache_path(expired_key)
        old_time = datetime.now() - timedelta(seconds=7200)
        expired_data = {
            "timestamp": old_time.isoformat(),
            "data": {"expired": "data"},
        }
        expired_path.write_text(json.dumps(expired_data))

        # Run cleanup
        removed = cache_manager.cleanup_expired()
        assert removed == 1

        # Verify expired entry is gone but valid one remains
        assert not expired_path.exists()
        assert cache_manager.get("owner", "repo", 42, "test") is not None

    def test_corrupt_cache_file(self, cache_manager):
        """Test handling of corrupted cache files."""
        key = cache_manager._get_cache_key("owner", "repo", 42, "test")
        cache_path = cache_manager._get_cache_path(key)

        # Write invalid JSON
        cache_path.write_text("not valid json{]")

        # Should return None and not raise exception
        result = cache_manager.get("owner", "repo", 42, "test")
        assert result is None

    def test_missing_timestamp_in_cache(self, cache_manager):
        """Test handling cache file without timestamp."""
        key = cache_manager._get_cache_key("owner", "repo", 42, "test")
        cache_path = cache_manager._get_cache_path(key)

        # Write cache without timestamp
        cache_data = {"data": {"test": "value"}}
        cache_path.write_text(json.dumps(cache_data))

        # Should return None
        result = cache_manager.get("owner", "repo", 42, "test")
        assert result is None

    def test_write_error_handling(self, cache_manager):
        """Test handling of write errors."""
        with patch("pathlib.Path.write_text", side_effect=OSError("Write error")):
            # Should not raise exception
            cache_manager.set("owner", "repo", 42, "test", {"data": "value"})

    def test_read_error_handling(self, cache_manager):
        """Test handling of read errors."""
        # Set data first
        cache_manager.set("owner", "repo", 42, "test", {"data": "value"})

        with patch("pathlib.Path.read_text", side_effect=OSError("Read error")):
            # Should return None and not raise exception
            result = cache_manager.get("owner", "repo", 42, "test")
            assert result is None

    def test_cache_pr_specific_data(self, cache_manager):
        """Test caching PR-specific data types."""
        # Cache PR data
        pr_data = {
            "number": 42,
            "title": "Test PR",
            "author": "testuser",
            "state": "open",
        }
        cache_manager.set("owner", "repo", 42, "pr", pr_data)
        assert cache_manager.get("owner", "repo", 42, "pr") == pr_data

        # Cache comments
        comments = [{"id": 1, "body": "Comment", "author": "user1"}]
        cache_manager.set("owner", "repo", 42, "comments", comments)
        assert cache_manager.get("owner", "repo", 42, "comments") == comments

        # Cache reviews
        reviews = [{"state": "APPROVED", "author": "reviewer1"}]
        cache_manager.set("owner", "repo", 42, "reviews", reviews)
        assert cache_manager.get("owner", "repo", 42, "reviews") == reviews
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
        return CacheManager(enabled=True, location=str(temp_cache_dir))

    def test_init_default(self):
        """Test CacheManager initialization with defaults."""
        manager = CacheManager()
        assert manager.enabled is True
        assert manager.location.name == "gh-pr"  # default location ends with gh-pr

    def test_init_custom(self, temp_cache_dir):
        """Test CacheManager initialization with custom values."""
        manager = CacheManager(
            enabled=False, location=str(temp_cache_dir)
        )
        assert manager.enabled is False
        assert manager.location == temp_cache_dir

    def test_init_creates_cache_dir(self, temp_cache_dir):
        """Test that initialization creates cache directory."""
        cache_path = temp_cache_dir / "cache"
        assert not cache_path.exists()
        CacheManager(enabled=True, location=str(cache_path))
        assert cache_path.exists()

    def test_generate_key(self, cache_manager):
        """Test cache key generation."""
        key = cache_manager.generate_key("owner", "repo", 42, "data")
        assert isinstance(key, str)
        assert len(key) == 16  # SHA256 truncated to 16 chars

        # Test with special characters
        key = cache_manager.generate_key("my-org", "my.repo", 123, "pr-data")
        assert isinstance(key, str)
        assert len(key) == 16

    def test_set_and_get(self, cache_manager):
        """Test setting and getting cached data."""
        key = cache_manager.generate_key("test")
        data = {"test": "data", "number": 42}
        result = cache_manager.set(key, data, ttl=300)
        assert result is True

        retrieved = cache_manager.get(key)
        assert retrieved == data

    def test_get_nonexistent(self, cache_manager):
        """Test getting non-existent cache entry."""
        key = cache_manager.generate_key("missing")
        result = cache_manager.get(key)
        assert result is None

    def test_delete(self, cache_manager):
        """Test cache deletion."""
        key = cache_manager.generate_key("to_delete")
        data = {"test": "data"}
        cache_manager.set(key, data, ttl=300)

        # Verify data is cached
        assert cache_manager.get(key) == data

        # Delete
        result = cache_manager.delete(key)
        assert result is True

        # Verify data is gone
        assert cache_manager.get(key) is None

    def test_get_expired(self, cache_manager):
        """Test getting expired cache entry."""
        import time
        key = cache_manager.generate_key("expired")
        data = {"test": "data"}
        # Set with very short TTL
        cache_manager.set(key, data, ttl=1)

        # Wait for expiration
        time.sleep(2)

        # Should return None for expired data
        result = cache_manager.get(key)
        assert result is None

    def test_get_disabled(self, temp_cache_dir):
        """Test that get returns None when cache is disabled."""
        manager = CacheManager(enabled=False, location=str(temp_cache_dir))
        key = manager.generate_key("test")
        manager.set(key, {"data": "value"}, ttl=300)
        result = manager.get(key)
        assert result is None

    def test_set_disabled(self, temp_cache_dir):
        """Test that set returns False when cache is disabled."""
        manager = CacheManager(enabled=False, location=str(temp_cache_dir))
        key = manager.generate_key("test")
        result = manager.set(key, {"data": "value"}, ttl=300)
        assert result is False

    def test_clear(self, cache_manager):
        """Test clearing all cache entries."""
        # Set multiple cache entries
        key1 = cache_manager.generate_key("entry1")
        key2 = cache_manager.generate_key("entry2")
        cache_manager.set(key1, {"value": 1}, ttl=300)
        cache_manager.set(key2, {"value": 2}, ttl=300)

        # Clear all
        result = cache_manager.clear()
        assert result is True

        # Verify all entries are gone
        assert cache_manager.get(key1) is None
        assert cache_manager.get(key2) is None

    def test_delete_nonexistent(self, cache_manager):
        """Test deleting non-existent cache entry."""
        # Should not raise exception, just return False
        key = cache_manager.generate_key("nonexistent")
        result = cache_manager.delete(key)
        # delete returns False when key doesn't exist
        assert result is False

    def test_clear_empty_cache(self, cache_manager):
        """Test clearing empty cache directory."""
        # Should not raise exception
        result = cache_manager.clear()
        assert result is True

    def test_cache_pr_specific_data(self, cache_manager):
        """Test caching PR-specific data types."""
        # Cache PR data
        pr_data = {
            "number": 42,
            "title": "Test PR",
            "author": "testuser",
            "state": "open",
        }
        key = cache_manager.generate_key("pr", 42)
        cache_manager.set(key, pr_data, ttl=300)
        assert cache_manager.get(key) == pr_data

        # Cache comments
        comments = [{"id": 1, "body": "Comment", "author": "user1"}]
        key = cache_manager.generate_key("comments", 42)
        cache_manager.set(key, comments, ttl=300)
        assert cache_manager.get(key) == comments

        # Cache reviews
        reviews = [{"state": "APPROVED", "author": "reviewer1"}]
        key = cache_manager.generate_key("reviews", 42)
        cache_manager.set(key, reviews, ttl=300)
        assert cache_manager.get(key) == reviews
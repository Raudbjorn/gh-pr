"""
Integration tests for caching flow.

Tests complete caching workflows including cache persistence, invalidation, and performance.
"""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from gh_pr.utils.cache import CacheManager
from gh_pr.core.pr_manager import PRManager
from gh_pr.core.github import GitHubClient


class TestCachingFlow(unittest.TestCase):
    """Test complete caching workflows."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.cache_dir = self.temp_dir / "test_cache"

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cache_manager_initialization_and_persistence(self):
        """Test cache manager initialization and data persistence."""
        # Test cache creation
        cache_manager = CacheManager(enabled=True, location=str(self.cache_dir))

        if not cache_manager.enabled:
            self.skipTest("Cache initialization failed - likely missing diskcache")

        # Test basic operations
        success = cache_manager.set("test_key", {"data": "test_value"}, ttl=60)
        self.assertTrue(success)

        # Verify data persists
        retrieved_value = cache_manager.get("test_key")
        self.assertEqual(retrieved_value, {"data": "test_value"})

        # Test cache directory was created
        self.assertTrue(self.cache_dir.exists())

        # Test new cache manager instance can read existing data
        cache_manager2 = CacheManager(enabled=True, location=str(self.cache_dir))
        if cache_manager2.enabled:
            retrieved_value2 = cache_manager2.get("test_key")
            self.assertEqual(retrieved_value2, {"data": "test_value"})

    def test_cache_manager_ttl_and_expiration(self):
        """Test cache TTL and expiration behavior."""
        cache_manager = CacheManager(enabled=True, location=str(self.cache_dir))

        if not cache_manager.enabled:
            self.skipTest("Cache initialization failed")

        # Set data with short TTL
        success = cache_manager.set("short_ttl_key", "expires_soon", ttl=1)
        self.assertTrue(success)

        # Should be available immediately
        value = cache_manager.get("short_ttl_key")
        self.assertEqual(value, "expires_soon")

        # Wait for expiration
        time.sleep(2)

        # Should be expired
        value = cache_manager.get("short_ttl_key")
        self.assertIsNone(value)

from datetime import datetime

    def test_cache_manager_with_pr_data_integration(self):
        """Test cache manager integration with PR data workflow."""
        # Mock GitHub client and PR manager
        mock_github = Mock(spec=GitHubClient)
        cache_manager = CacheManager(enabled=True, location=str(self.cache_dir))

        if not cache_manager.enabled:
            self.skipTest("Cache initialization failed")

        pr_manager = PRManager(mock_github, cache_manager)

        # Mock PR data
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.title = "Test PR"
        mock_pr.state = "open"
        mock_pr.user.login = "testuser"
        mock_pr.created_at = datetime.now()
        mock_pr.updated_at = datetime.now()
        mock_pr.merged = False
        mock_pr.merged_at = None
        mock_pr.mergeable = True
        mock_pr.mergeable_state = "clean"
        mock_pr.head.ref = "feature"
        mock_pr.head.sha = "abc123"
        mock_pr.base.ref = "main"
        mock_pr.base.sha = "def456"
        mock_pr.body = "Test PR body"
        mock_pr.additions = 10
        mock_pr.deletions = 5
        mock_pr.changed_files = 2
        mock_pr.review_comments = 0
        mock_pr.comments = 0
        mock_pr.commits = 1
        mock_pr.labels = []

        mock_github.get_pull_request.return_value = mock_pr

        # Verify cache key is being used correctly
        expected_cache_key = "pr_data_owner_repo_123"
        
        # First call should fetch from API and cache
        pr_data1 = pr_manager.fetch_pr_data("owner", "repo", 123)
        mock_github.get_pull_request.assert_called_once()
        
        # Verify data was cached
        cached_value = cache_manager.get(expected_cache_key)
        self.assertIsNotNone(cached_value)
        self.assertEqual(cached_value["number"], 123)

        # Second call should use cache
        pr_data2 = pr_manager.fetch_pr_data("owner", "repo", 123)
        # Should still only be called once (cached)
        mock_github.get_pull_request.assert_called_once()

        # Data should be identical
        self.assertEqual(pr_data1, pr_data2)
        self.assertEqual(pr_data1["number"], 123)
        self.assertEqual(pr_data1["title"], "Test PR")
    def test_cache_manager_key_generation_consistency(self):
        """Test cache key generation consistency and collision avoidance."""
        cache_manager = CacheManager(enabled=True, location=str(self.cache_dir))

        if not cache_manager.enabled:
            self.skipTest("Cache initialization failed")

        # Test key generation consistency
        key1 = cache_manager.generate_key("owner", "repo", "123")
        key2 = cache_manager.generate_key("owner", "repo", "123")
        self.assertEqual(key1, key2)

        # Test collision avoidance
        key3 = cache_manager.generate_key("owner", "repo", "124")
        self.assertNotEqual(key1, key3)

        # Test different order produces different keys
        key4 = cache_manager.generate_key("repo", "owner", "123")
        self.assertNotEqual(key1, key4)

        # Use generated keys for caching
        cache_manager.set(key1, "data_for_pr_123")
        cache_manager.set(key3, "data_for_pr_124")

        # Verify correct data retrieval
        self.assertEqual(cache_manager.get(key1), "data_for_pr_123")
        self.assertEqual(cache_manager.get(key3), "data_for_pr_124")

    def test_cache_manager_bulk_operations(self):
        """Test cache manager with bulk operations."""
        cache_manager = CacheManager(enabled=True, location=str(self.cache_dir))

        if not cache_manager.enabled:
            self.skipTest("Cache initialization failed")

        # Store multiple items
        test_data = {}
        for i in range(100):
            key = f"bulk_key_{i}"
            value = {"pr_number": i, "title": f"PR {i}", "data": "x" * 100}
            success = cache_manager.set(key, value, ttl=300)
            self.assertTrue(success)
            test_data[key] = value

        # Retrieve all items
        for key, expected_value in test_data.items():
            retrieved_value = cache_manager.get(key)
            self.assertEqual(retrieved_value, expected_value)

        # Test cache clear
        success = cache_manager.clear()
        self.assertTrue(success)

        # Verify all items are gone
        for key in test_data:
            retrieved_value = cache_manager.get(key)
            self.assertIsNone(retrieved_value)

    def test_cache_manager_error_handling_and_fallback(self):
        """Test cache manager error handling and fallback behavior."""
        # Test with insufficient permissions
        readonly_dir = self.temp_dir / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # Read-only

        try:
            cache_manager = CacheManager(enabled=True, location=str(readonly_dir / "cache"))

            # Should disable cache on permission error
            self.assertFalse(cache_manager.enabled)

            # Operations should fail gracefully
            self.assertFalse(cache_manager.set("key", "value"))
            self.assertIsNone(cache_manager.get("key"))
            self.assertFalse(cache_manager.delete("key"))
            self.assertFalse(cache_manager.clear())

        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(0o755)

    def test_cache_manager_concurrent_access(self):
        """Test cache manager behavior with concurrent access simulation."""
        cache_manager = CacheManager(enabled=True, location=str(self.cache_dir))

        if not cache_manager.enabled:
            self.skipTest("Cache initialization failed")

        # Simulate concurrent writes
        keys_written = []
        for i in range(50):
            key = f"concurrent_key_{i}"
            value = {"thread_id": i, "data": f"concurrent_data_{i}"}
            success = cache_manager.set(key, value)
            if success:
                keys_written.append((key, value))

        # Verify all writes were successful
        for key, expected_value in keys_written:
            retrieved_value = cache_manager.get(key)
            self.assertEqual(retrieved_value, expected_value)

        # Simulate concurrent reads and writes
        for i in range(len(keys_written)):
            key, _ = keys_written[i]
            # Update existing key
            new_value = {"thread_id": i, "data": f"updated_data_{i}"}
            cache_manager.set(key, new_value)

            # Read updated value
            retrieved_value = cache_manager.get(key)
            self.assertEqual(retrieved_value, new_value)

    def test_pr_manager_cache_invalidation_workflow(self):
        """Test PR manager cache invalidation workflow."""
        mock_github = Mock(spec=GitHubClient)
        cache_manager = CacheManager(enabled=True, location=str(self.cache_dir))

        if not cache_manager.enabled:
            self.skipTest("Cache initialization failed")

        pr_manager = PRManager(mock_github, cache_manager)

        # Mock different PR states
        mock_pr_v1 = Mock()
        mock_pr_v1.number = 123
        mock_pr_v1.title = "Original Title"
        mock_pr_v1.state = "open"
        mock_pr_v1.user.login = "author"
        mock_pr_v1.created_at = Mock()
        mock_pr_v1.updated_at = Mock()
        mock_pr_v1.merged = False
        mock_pr_v1.merged_at = None
        mock_pr_v1.mergeable = True
        mock_pr_v1.mergeable_state = "clean"
        mock_pr_v1.head.ref = "feature"
        mock_pr_v1.head.sha = "abc123"
        mock_pr_v1.base.ref = "main"
        mock_pr_v1.base.sha = "def456"
        mock_pr_v1.body = "Original body"
        mock_pr_v1.additions = 10
        mock_pr_v1.deletions = 5
        mock_pr_v1.changed_files = 2
        mock_pr_v1.review_comments = 0
        mock_pr_v1.comments = 0
        mock_pr_v1.commits = 1
        mock_pr_v1.labels = []

        mock_github.get_pull_request.return_value = mock_pr_v1

        # Fetch PR data (will cache)
        pr_data_v1 = pr_manager.fetch_pr_data("owner", "repo", 123)
        self.assertEqual(pr_data_v1["title"], "Original Title")

        # Simulate PR update with cache disabled
        cache_manager.enabled = False
        mock_pr_v2 = Mock()
        mock_pr_v2.number = 123
        mock_pr_v2.title = "Updated Title"
        mock_pr_v2.state = "open"
        mock_pr_v2.user.login = "author"
        mock_pr_v2.created_at = Mock()
        mock_pr_v2.updated_at = Mock()
        mock_pr_v2.merged = False
        mock_pr_v2.merged_at = None
        mock_pr_v2.mergeable = True
        mock_pr_v2.mergeable_state = "clean"
        mock_pr_v2.head.ref = "feature"
        mock_pr_v2.head.sha = "abc123"
        mock_pr_v2.base.ref = "main"
        mock_pr_v2.base.sha = "def456"
        mock_pr_v2.body = "Updated body"
        mock_pr_v2.additions = 15
        mock_pr_v2.deletions = 3
        mock_pr_v2.changed_files = 3
        mock_pr_v2.review_comments = 2
        mock_pr_v2.comments = 1
        mock_pr_v2.commits = 2
        mock_pr_v2.labels = [Mock(name="bug")]

        mock_github.get_pull_request.return_value = mock_pr_v2

        # Fetch updated data (bypasses cache)
        pr_data_v2 = pr_manager.fetch_pr_data("owner", "repo", 123)
        self.assertEqual(pr_data_v2["title"], "Updated Title")
        self.assertEqual(pr_data_v2["additions"], 15)

    def test_cache_manager_memory_usage_and_cleanup(self):
        """Test cache manager memory usage and cleanup behavior."""
        cache_manager = CacheManager(enabled=True, location=str(self.cache_dir))

        if not cache_manager.enabled:
            self.skipTest("Cache initialization failed")

        # Store large amount of data
        large_data = "x" * 10000  # 10KB strings
        keys = []

        for i in range(100):  # 1MB total
            key = f"large_key_{i}"
            cache_manager.set(key, large_data, ttl=60)
            keys.append(key)

        # Verify data is stored
        for key in keys[:10]:  # Check first 10
            value = cache_manager.get(key)
            self.assertEqual(value, large_data)

        # Test selective deletion
        for i in range(0, 50, 2):  # Delete every other key
            key = keys[i]
            success = cache_manager.delete(key)
            self.assertTrue(success)

        # Verify deletion
        for i in range(0, 50, 2):
            key = keys[i]
            value = cache_manager.get(key)
            self.assertIsNone(value)

        # Verify remaining keys still exist
        for i in range(1, 50, 2):
            key = keys[i]
            value = cache_manager.get(key)
            self.assertEqual(value, large_data)

        # Clear all
        success = cache_manager.clear()
        self.assertTrue(success)

        # Verify all data is gone
        for key in keys:
            value = cache_manager.get(key)
            self.assertIsNone(value)

    def test_cache_performance_comparison(self):
        """Test cache performance vs non-cached operations."""
        cache_manager = CacheManager(enabled=True, location=str(self.cache_dir))

        if not cache_manager.enabled:
            self.skipTest("Cache initialization failed")

        # Simulate expensive operation with caching
        def expensive_operation(param):
            # Simulate network delay
            time.sleep(0.01)
            return {"result": f"processed_{param}", "timestamp": time.time()}

        # Test with cache
        start_time = time.time()
        for i in range(10):
            key = f"perf_key_{i}"
            cached_result = cache_manager.get(key)
            if cached_result is None:
                result = expensive_operation(i)
                cache_manager.set(key, result, ttl=60)
            else:
                result = cached_result

        cached_time = time.time() - start_time

        # Clear cache and test without cache
        cache_manager.clear()

        start_time = time.time()
        for i in range(10):
            result = expensive_operation(i)

        uncached_time = time.time() - start_time

        # First run (populating cache) should be similar to uncached
        # But second run should be much faster
        start_time = time.time()
        for i in range(10):
            key = f"perf_key_{i}"
            result = cache_manager.get(key)

        cache_hit_time = time.time() - start_time

        # Cache hits should be significantly faster
        self.assertLess(cache_hit_time, uncached_time / 2)

    def test_cache_integration_with_error_conditions(self):
        """Test cache behavior during error conditions."""
        cache_manager = CacheManager(enabled=True, location=str(self.cache_dir))

        if not cache_manager.enabled:
            self.skipTest("Cache initialization failed")

        # Test with disk full simulation (mock)
        with patch.object(cache_manager.cache, 'set') as mock_set:
            mock_set.side_effect = OSError("No space left on device")

            # Should handle error gracefully
            success = cache_manager.set("error_key", "error_value")
            self.assertFalse(success)

        # Cache should still work for other operations
        success = cache_manager.set("normal_key", "normal_value")
        self.assertTrue(success)

        value = cache_manager.get("normal_key")
        self.assertEqual(value, "normal_value")


if __name__ == '__main__':
    unittest.main()
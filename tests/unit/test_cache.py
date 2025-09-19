"""
Unit tests for utils.cache module.

Tests caching functionality for PR data.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import diskcache

from gh_pr.utils.cache import CacheManager


class TestCacheManager(unittest.TestCase):
    """Test CacheManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up test fixtures."""
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_enabled_default_location(self):
        """Test initialization with caching enabled and default location."""
        with patch('gh_pr.utils.cache.diskcache.Cache') as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance

            manager = CacheManager(enabled=True)

            self.assertTrue(manager.enabled)
            self.assertEqual(manager.location, Path.home() / ".cache" / "gh-pr")
            self.assertEqual(manager.cache, mock_cache_instance)

    def test_init_enabled_custom_location(self):
        """Test initialization with custom cache location."""
        custom_location = str(self.temp_dir / "custom_cache")

        with patch('gh_pr.utils.cache.diskcache.Cache') as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance

            manager = CacheManager(enabled=True, location=custom_location)

            self.assertTrue(manager.enabled)
            self.assertEqual(manager.location, Path(custom_location).expanduser())
            self.assertEqual(manager.cache, mock_cache_instance)

    def test_init_disabled(self):
        """Test initialization with caching disabled."""
        manager = CacheManager(enabled=False)

        self.assertFalse(manager.enabled)
        self.assertIsNone(manager.cache)

    @patch('gh_pr.utils.cache.os.access')
    @patch('gh_pr.utils.cache.diskcache.Cache')
    def test_init_cache_location_not_writable(self, mock_cache_class, mock_access):
        """Test initialization when cache location is not writable."""
        mock_access.return_value = False

        with patch('gh_pr.utils.cache.logger') as mock_logger:
            manager = CacheManager(enabled=True, location=str(self.temp_dir))

            self.assertFalse(manager.enabled)
            self.assertIsNone(manager.cache)
            mock_logger.warning.assert_called_once()
            self.assertIn("not writable", mock_logger.warning.call_args[0][0])

    @patch('gh_pr.utils.cache.os.statvfs')
    @patch('gh_pr.utils.cache.os.access')
    @patch('gh_pr.utils.cache.diskcache.Cache')
    def test_init_insufficient_disk_space(self, mock_cache_class, mock_access, mock_statvfs):
        """Test initialization when insufficient disk space."""
        mock_access.return_value = True

        # Mock statvfs to return insufficient space (less than 10MB)
        mock_stat = Mock()
        mock_stat.f_bavail = 1000  # 1000 blocks
        mock_stat.f_frsize = 1024  # 1KB block size = 1MB total
        mock_statvfs.return_value = mock_stat

        with patch('gh_pr.utils.cache.logger') as mock_logger:
            manager = CacheManager(enabled=True, location=str(self.temp_dir))

            self.assertFalse(manager.enabled)
            self.assertIsNone(manager.cache)
            mock_logger.warning.assert_called_once()
            self.assertIn("Insufficient disk space", mock_logger.warning.call_args[0][0])

    @patch('gh_pr.utils.cache.os.statvfs')
    @patch('gh_pr.utils.cache.os.access')
    @patch('gh_pr.utils.cache.diskcache.Cache')
    def test_init_sufficient_disk_space(self, mock_cache_class, mock_access, mock_statvfs):
        """Test initialization with sufficient disk space."""
        mock_access.return_value = True

        # Mock statvfs to return sufficient space (20MB)
        mock_stat = Mock()
        mock_stat.f_bavail = 20 * 1024  # 20K blocks
        mock_stat.f_frsize = 1024  # 1KB block size = 20MB total
        mock_statvfs.return_value = mock_stat

        mock_cache_instance = Mock()
        mock_cache_class.return_value = mock_cache_instance

        manager = CacheManager(enabled=True, location=str(self.temp_dir))

        self.assertTrue(manager.enabled)
        self.assertEqual(manager.cache, mock_cache_instance)

    @patch('gh_pr.utils.cache.os.statvfs')
    @patch('gh_pr.utils.cache.os.access')
    @patch('gh_pr.utils.cache.diskcache.Cache')
    def test_init_statvfs_not_available(self, mock_cache_class, mock_access, mock_statvfs):
        """Test initialization when statvfs is not available (e.g., Windows)."""
        mock_access.return_value = True
        mock_statvfs.side_effect = AttributeError("statvfs not available")

        mock_cache_instance = Mock()
        mock_cache_class.return_value = mock_cache_instance

        manager = CacheManager(enabled=True, location=str(self.temp_dir))

        # Should continue without checking disk space
        self.assertTrue(manager.enabled)
        self.assertEqual(manager.cache, mock_cache_instance)

    @patch('gh_pr.utils.cache.diskcache.Cache')
    def test_init_cache_creation_fails(self, mock_cache_class):
        """Test initialization when cache creation fails."""
        mock_cache_class.side_effect = OSError("Permission denied")

        with patch('gh_pr.utils.cache.logger') as mock_logger:
            manager = CacheManager(enabled=True, location=str(self.temp_dir))

            self.assertFalse(manager.enabled)
            self.assertIsNone(manager.cache)
            mock_logger.warning.assert_called_once()
            self.assertIn("Failed to initialize cache", mock_logger.warning.call_args[0][0])

    def test_get_cache_disabled(self):
        """Test get method when cache is disabled."""
        manager = CacheManager(enabled=False)

        result = manager.get("test_key")
        self.assertIsNone(result)

    def test_get_success(self):
        """Test successful cache get operation."""
        mock_cache = Mock()
        mock_cache.get.return_value = "test_value"

        manager = CacheManager(enabled=True)
        manager.cache = mock_cache

        result = manager.get("test_key")
        self.assertEqual(result, "test_value")
        mock_cache.get.assert_called_once_with("test_key")

    def test_get_exception_handling(self):
        """Test get method handling exceptions."""
        mock_cache = Mock()
        mock_cache.get.side_effect = Exception("Cache error")

        manager = CacheManager(enabled=True)
        manager.cache = mock_cache

        with patch('gh_pr.utils.cache.logger') as mock_logger:
            result = manager.get("test_key")

            self.assertIsNone(result)
            mock_logger.warning.assert_called_once()
            self.assertIn("Cache get failed", mock_logger.warning.call_args[0][0])

    def test_set_cache_disabled(self):
        """Test set method when cache is disabled."""
        manager = CacheManager(enabled=False)

        result = manager.set("test_key", "test_value")
        self.assertFalse(result)

    def test_set_success(self):
        """Test successful cache set operation."""
        mock_cache = Mock()

        manager = CacheManager(enabled=True)
        manager.cache = mock_cache

        result = manager.set("test_key", "test_value", ttl=600)
        self.assertTrue(result)
        mock_cache.set.assert_called_once_with("test_key", "test_value", expire=600)

    def test_set_exception_handling(self):
        """Test set method handling exceptions."""
        mock_cache = Mock()
        mock_cache.set.side_effect = OSError("Disk full")

        manager = CacheManager(enabled=True)
        manager.cache = mock_cache

        with patch('gh_pr.utils.cache.logger') as mock_logger:
            result = manager.set("test_key", "test_value")

            self.assertFalse(result)
            mock_logger.warning.assert_called_once()
            self.assertIn("Cache set failed", mock_logger.warning.call_args[0][0])

    def test_delete_cache_disabled(self):
        """Test delete method when cache is disabled."""
        manager = CacheManager(enabled=False)

        result = manager.delete("test_key")
        self.assertFalse(result)

    def test_delete_success(self):
        """Test successful cache delete operation."""
        mock_cache = Mock()

        manager = CacheManager(enabled=True)
        manager.cache = mock_cache

        result = manager.delete("test_key")
        self.assertTrue(result)
        # Should use __delitem__ method
        mock_cache.__delitem__.assert_called_once_with("test_key")

    def test_delete_key_not_found(self):
        """Test delete method when key doesn't exist."""
        mock_cache = Mock()
        mock_cache.__delitem__.side_effect = KeyError("Key not found")

        manager = CacheManager(enabled=True)
        manager.cache = mock_cache

        with patch('gh_pr.utils.cache.logger') as mock_logger:
            result = manager.delete("nonexistent_key")

            self.assertFalse(result)
            mock_logger.warning.assert_called_once()
            self.assertIn("Cache delete failed", mock_logger.warning.call_args[0][0])

    def test_delete_exception_handling(self):
        """Test delete method handling other exceptions."""
        mock_cache = Mock()
        mock_cache.__delitem__.side_effect = OSError("Cache error")

        manager = CacheManager(enabled=True)
        manager.cache = mock_cache

        with patch('gh_pr.utils.cache.logger') as mock_logger:
            result = manager.delete("test_key")

            self.assertFalse(result)
            mock_logger.warning.assert_called_once()

    def test_clear_cache_disabled(self):
        """Test clear method when cache is disabled."""
        manager = CacheManager(enabled=False)

        result = manager.clear()
        self.assertFalse(result)

    def test_clear_success(self):
        """Test successful cache clear operation."""
        mock_cache = Mock()

        manager = CacheManager(enabled=True)
        manager.cache = mock_cache

        result = manager.clear()
        self.assertTrue(result)
        mock_cache.clear.assert_called_once()

    def test_clear_exception_handling(self):
        """Test clear method handling exceptions."""
        mock_cache = Mock()
        mock_cache.clear.side_effect = OSError("Cache error")

        manager = CacheManager(enabled=True)
        manager.cache = mock_cache

        with patch('gh_pr.utils.cache.logger') as mock_logger:
            result = manager.clear()

            self.assertFalse(result)
            mock_logger.warning.assert_called_once()
            self.assertIn("Cache clear failed", mock_logger.warning.call_args[0][0])

    def test_generate_key_single_part(self):
        """Test generate_key with single part."""
        manager = CacheManager(enabled=False)

        key = manager.generate_key("test")
        self.assertIsInstance(key, str)
        self.assertEqual(len(key), 16)  # SHA256 truncated to 16 chars

    def test_generate_key_multiple_parts(self):
        """Test generate_key with multiple parts."""
        manager = CacheManager(enabled=False)

        key = manager.generate_key("owner", "repo", "123")
        self.assertIsInstance(key, str)
        self.assertEqual(len(key), 16)

        # Same inputs should produce same key
        key2 = manager.generate_key("owner", "repo", "123")
        self.assertEqual(key, key2)

        # Different inputs should produce different keys
        key3 = manager.generate_key("owner", "repo", "124")
        self.assertNotEqual(key, key3)

    def test_generate_key_with_numbers(self):
        """Test generate_key with numeric parts."""
        manager = CacheManager(enabled=False)

        key = manager.generate_key("test", 123, 45.6)
        self.assertIsInstance(key, str)
        self.assertEqual(len(key), 16)

    def test_generate_key_empty_parts(self):
        """Test generate_key with empty parts."""
        manager = CacheManager(enabled=False)

        key = manager.generate_key("", "test", "")
        self.assertIsInstance(key, str)
        self.assertEqual(len(key), 16)

    def test_real_cache_integration(self):
        """Test with real diskcache instance for integration testing."""
        cache_dir = self.temp_dir / "real_cache"

        # Test with real cache
        manager = CacheManager(enabled=True, location=str(cache_dir))

        if manager.enabled:  # Only run if cache initialization succeeded
            # Test set and get
            success = manager.set("test_key", {"data": "test_value"}, ttl=60)
            self.assertTrue(success)

            value = manager.get("test_key")
            self.assertEqual(value, {"data": "test_value"})

            # Test delete
            success = manager.delete("test_key")
            self.assertTrue(success)

            value = manager.get("test_key")
            self.assertIsNone(value)

    def test_cache_key_generation_consistency(self):
        """Test that cache key generation is consistent."""
        manager = CacheManager(enabled=False)

        # Test same inputs produce same keys
        key1 = manager.generate_key("owner", "repo", "pr_123")
        key2 = manager.generate_key("owner", "repo", "pr_123")
        self.assertEqual(key1, key2)

        # Test different order produces different keys
        key3 = manager.generate_key("repo", "owner", "pr_123")
        self.assertNotEqual(key1, key3)

    def test_location_path_expansion(self):
        """Test that location paths are properly expanded."""
        with patch('gh_pr.utils.cache.diskcache.Cache'):
            manager = CacheManager(enabled=True, location="~/test_cache")

            expected_path = Path.home() / "test_cache"
            self.assertEqual(manager.location, expected_path)


if __name__ == '__main__':
    unittest.main()
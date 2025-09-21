"""Unit tests for cache.py failure logging and reliability."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from gh_pr.utils.cache import CacheManager


class TestCacheManagerFailureLogging:
    """Test cache failure logging and error handling."""

    @patch('gh_pr.utils.cache.logger')
    def test_cache_init_permission_error_logging(self, mock_logger):
        """Test that permission errors during cache initialization are logged."""
        with patch('pathlib.Path.mkdir', side_effect=PermissionError("Access denied")):
            cache_manager = CacheManager(enabled=True, location="/restricted/cache")

            assert cache_manager.enabled is False
            mock_logger.warning.assert_called()
            log_message = mock_logger.warning.call_args[0][0]
            assert "Failed to initialize cache" in log_message
            assert "PermissionError" in str(mock_logger.warning.call_args)

    @patch('gh_pr.utils.cache.logger')
    def test_cache_init_os_error_logging(self, mock_logger):
        """Test that OS errors during cache initialization are logged."""
        with patch('pathlib.Path.mkdir', side_effect=OSError("Disk full")):
            cache_manager = CacheManager(enabled=True, location="/tmp/test_cache")

            assert cache_manager.enabled is False
            mock_logger.warning.assert_called()
            log_message = mock_logger.warning.call_args[0][0]
            assert "Failed to initialize cache" in log_message

    @patch('gh_pr.utils.cache.logger')
    @patch('os.access')
    def test_cache_init_write_permission_check_logging(self, mock_access, mock_logger):
        """Test that write permission check failures are logged."""
        mock_access.return_value = False  # Simulate no write permission

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(enabled=True, location=temp_dir)

            assert cache_manager.enabled is False
            mock_logger.warning.assert_called()
            log_message = mock_logger.warning.call_args[0][0]
            assert "not writable" in log_message
            assert "Disabling cache" in log_message

    @patch('gh_pr.utils.cache.logger')
    @patch('os.statvfs')
    def test_cache_init_disk_space_check_logging(self, mock_statvfs, mock_logger):
        """Test that insufficient disk space is logged."""
        # Mock insufficient disk space (less than 10MB)
        mock_stat = Mock()
        mock_stat.f_bavail = 100  # 100 blocks
        mock_stat.f_frsize = 1024  # 1KB per block = 100KB total (< 10MB)
        mock_statvfs.return_value = mock_stat

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(enabled=True, location=temp_dir)

            assert cache_manager.enabled is False
            mock_logger.warning.assert_called()
            log_message = mock_logger.warning.call_args[0][0]
            assert "Insufficient disk space" in log_message
            assert "10MB" in log_message

    @patch('gh_pr.utils.cache.logger')
    def test_cache_get_failure_logging(self, mock_logger):
        """Test that cache get failures are logged."""
        cache_manager = CacheManager(enabled=True)

        # Mock the cache to raise an exception
        with patch.object(cache_manager, 'cache') as mock_cache:
            mock_cache.get.side_effect = RuntimeError("Cache corruption")

            result = cache_manager.get("test_key")

            assert result is None
            mock_logger.warning.assert_called()
            log_message = mock_logger.warning.call_args[0][0]
            assert "Cache get failed" in log_message
            assert "test_key" in log_message

    @patch('gh_pr.utils.cache.logger')
    def test_cache_set_failure_logging(self, mock_logger):
        """Test that cache set failures are logged."""
        cache_manager = CacheManager(enabled=True)

        # Mock the cache to raise an exception
        with patch.object(cache_manager, 'cache') as mock_cache:
            mock_cache.set.side_effect = OSError("Disk full")

            result = cache_manager.set("test_key", "test_value")

            assert result is False
            mock_logger.warning.assert_called()
            log_message = mock_logger.warning.call_args[0][0]
            assert "Cache set failed" in log_message
            assert "test_key" in log_message

    @patch('gh_pr.utils.cache.logger')
    def test_cache_delete_failure_logging(self, mock_logger):
        """Test that cache delete failures are logged."""
        cache_manager = CacheManager(enabled=True)

        # Mock the cache to raise an exception
        with patch.object(cache_manager, 'cache') as mock_cache:
            mock_cache.__delitem__.side_effect = OSError("Permission denied")

            result = cache_manager.delete("test_key")

            assert result is False
            mock_logger.warning.assert_called()
            log_message = mock_logger.warning.call_args[0][0]
            assert "Cache delete failed" in log_message
            assert "test_key" in log_message

    @patch('gh_pr.utils.cache.logger')
    def test_cache_clear_failure_logging(self, mock_logger):
        """Test that cache clear failures are logged."""
        cache_manager = CacheManager(enabled=True)

        # Mock the cache to raise an exception
        with patch.object(cache_manager, 'cache') as mock_cache:
            mock_cache.clear.side_effect = AttributeError("Method not available")

            result = cache_manager.clear()

            assert result is False
            mock_logger.warning.assert_called()
            log_message = mock_logger.warning.call_args[0][0]
            assert "Cache clear failed" in log_message

    @patch('gh_pr.utils.cache.logger')
    def test_cache_keyerror_delete_logging(self, mock_logger):
        """Test that KeyError during delete is logged appropriately."""
        cache_manager = CacheManager(enabled=True)

        # Mock the cache to raise KeyError (key doesn't exist)
        with patch.object(cache_manager, 'cache') as mock_cache:
            mock_cache.__delitem__.side_effect = KeyError("Key not found")

            result = cache_manager.delete("nonexistent_key")

            assert result is False
            mock_logger.warning.assert_called()
            log_message = mock_logger.warning.call_args[0][0]
            assert "Cache delete failed" in log_message
            assert "nonexistent_key" in log_message

    @patch('gh_pr.utils.cache.logger')
    def test_cache_type_error_set_logging(self, mock_logger):
        """Test that TypeError during set is logged appropriately."""
        cache_manager = CacheManager(enabled=True)

        # Mock the cache to raise TypeError (value not serializable)
        with patch.object(cache_manager, 'cache') as mock_cache:
            mock_cache.set.side_effect = TypeError("Object not serializable")

            result = cache_manager.set("test_key", object())

            assert result is False
            mock_logger.warning.assert_called()
            log_message = mock_logger.warning.call_args[0][0]
            assert "Cache set failed" in log_message

    @patch('gh_pr.utils.cache.diskcache.Cache')
    @patch('gh_pr.utils.cache.logger')
    def test_cache_diskcache_import_failure_handling(self, mock_logger, mock_diskcache):
        """Test handling when diskcache operations fail."""
        mock_diskcache.side_effect = ImportError("diskcache not available")

        cache_manager = CacheManager(enabled=True)

        # Cache should be disabled
        assert cache_manager.enabled is False
        mock_logger.warning.assert_called()


class TestCacheManagerReliability:
    """Test cache reliability and robustness features."""

    def test_cache_disabled_operations_safe(self):
        """Test that cache operations are safe when cache is disabled."""
        cache_manager = CacheManager(enabled=False)

        # All operations should return safe defaults
        assert cache_manager.get("any_key") is None
        assert cache_manager.set("any_key", "any_value") is False
        assert cache_manager.delete("any_key") is False
        assert cache_manager.clear() is False

    def test_cache_location_expansion(self):
        """Test that cache location with ~ is properly expanded."""
        cache_manager = CacheManager(location="~/test_cache")

        expected_location = Path.home() / "test_cache"
        assert cache_manager.location == expected_location

    def test_cache_location_absolute_path(self):
        """Test that absolute cache location is handled correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(location=temp_dir)
            assert cache_manager.location == Path(temp_dir)

    @patch('os.statvfs')
    def test_cache_statvfs_not_available(self, mock_statvfs):
        """Test cache initialization when statvfs is not available (e.g., Windows)."""
        mock_statvfs.side_effect = AttributeError("statvfs not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(enabled=True, location=temp_dir)

            # Should continue initialization despite statvfs failure
            # (assuming other checks pass)
            assert cache_manager.location == Path(temp_dir)

    @patch('os.statvfs')
    def test_cache_statvfs_os_error(self, mock_statvfs):
        """Test cache initialization when statvfs raises OSError."""
        mock_statvfs.side_effect = OSError("Operation not supported")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(enabled=True, location=temp_dir)

            # Should continue initialization despite statvfs failure
            assert cache_manager.location == Path(temp_dir)

    def test_cache_generate_key_consistent(self):
        """Test that key generation is consistent."""
        cache_manager = CacheManager(enabled=False)

        key1 = cache_manager.generate_key("part1", "part2", "part3")
        key2 = cache_manager.generate_key("part1", "part2", "part3")

        assert key1 == key2
        assert len(key1) == 16  # SHA256 truncated to 16 chars

    def test_cache_generate_key_different_inputs(self):
        """Test that different inputs generate different keys."""
        cache_manager = CacheManager(enabled=False)

        key1 = cache_manager.generate_key("part1", "part2")
        key2 = cache_manager.generate_key("part1", "part3")
        key3 = cache_manager.generate_key("different", "parts")

        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    def test_cache_generate_key_special_characters(self):
        """Test key generation with special characters."""
        cache_manager = CacheManager(enabled=False)

        key = cache_manager.generate_key("special!@#$%", "unicode: éñ", "emoji: 🎯")

        assert isinstance(key, str)
        assert len(key) == 16

    def test_cache_generate_key_empty_parts(self):
        """Test key generation with empty parts."""
        cache_manager = CacheManager(enabled=False)

        key = cache_manager.generate_key("", "part2", "")

        assert isinstance(key, str)
        assert len(key) == 16

    def test_cache_generate_key_numeric_parts(self):
        """Test key generation with numeric parts."""
        cache_manager = CacheManager(enabled=False)

        key = cache_manager.generate_key(123, 456.789, True)

        assert isinstance(key, str)
        assert len(key) == 16

    def test_cache_ttl_parameter_handling(self):
        """Test that TTL parameters are handled correctly."""
        cache_manager = CacheManager(enabled=True)

        with patch.object(cache_manager, 'cache') as mock_cache:
            cache_manager.set("test_key", "test_value", ttl=600)

            mock_cache.set.assert_called_once_with("test_key", "test_value", expire=600)

    def test_cache_default_ttl(self):
        """Test that default TTL is used when not specified."""
        cache_manager = CacheManager(enabled=True)

        with patch.object(cache_manager, 'cache') as mock_cache:
            cache_manager.set("test_key", "test_value")

            mock_cache.set.assert_called_once_with("test_key", "test_value", expire=300)

    @patch('gh_pr.utils.cache.diskcache.Cache')
    def test_cache_creation_with_string_location(self, mock_diskcache):
        """Test that cache is created with string location path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(enabled=True, location=temp_dir)

            if cache_manager.enabled:  # Only check if cache init succeeded
                mock_diskcache.assert_called_once_with(str(Path(temp_dir)))


class TestCacheManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_cache_none_cache_object(self):
        """Test operations when cache object is None."""
        cache_manager = CacheManager(enabled=True)
        cache_manager.cache = None  # Simulate failed initialization

        assert cache_manager.get("test_key") is None
        assert cache_manager.set("test_key", "value") is False
        assert cache_manager.delete("test_key") is False
        assert cache_manager.clear() is False

    def test_cache_very_long_key(self):
        """Test cache operations with very long keys."""
        cache_manager = CacheManager(enabled=True)
        long_key = "x" * 1000

        with patch.object(cache_manager, 'cache') as mock_cache:
            cache_manager.get(long_key)
            mock_cache.get.assert_called_once_with(long_key)

    def test_cache_special_characters_in_key(self):
        """Test cache operations with special characters in keys."""
        cache_manager = CacheManager(enabled=True)
        special_key = "key!@#$%^&*()_+{}|:<>?[]\\;'\",./"

        with patch.object(cache_manager, 'cache') as mock_cache:
            cache_manager.get(special_key)
            mock_cache.get.assert_called_once_with(special_key)

    def test_cache_unicode_key(self):
        """Test cache operations with Unicode keys."""
        cache_manager = CacheManager(enabled=True)
        unicode_key = "测试键🎯éñ"

        with patch.object(cache_manager, 'cache') as mock_cache:
            cache_manager.get(unicode_key)
            mock_cache.get.assert_called_once_with(unicode_key)

    def test_cache_none_value(self):
        """Test caching None values."""
        cache_manager = CacheManager(enabled=True)

        with patch.object(cache_manager, 'cache') as mock_cache:
            cache_manager.set("test_key", None)
            mock_cache.set.assert_called_once_with("test_key", None, expire=300)

    def test_cache_complex_value_types(self):
        """Test caching complex value types."""
        cache_manager = CacheManager(enabled=True)

        complex_value = {
            "list": [1, 2, 3],
            "dict": {"nested": True},
            "tuple": (4, 5, 6),
            "none": None,
            "bool": True,
            "float": 3.14
        }

        with patch.object(cache_manager, 'cache') as mock_cache:
            cache_manager.set("complex_key", complex_value)
            mock_cache.set.assert_called_once_with("complex_key", complex_value, expire=300)

    def test_cache_zero_ttl(self):
        """Test cache with zero TTL."""
        cache_manager = CacheManager(enabled=True)

        with patch.object(cache_manager, 'cache') as mock_cache:
            cache_manager.set("test_key", "test_value", ttl=0)
            mock_cache.set.assert_called_once_with("test_key", "test_value", expire=0)

    def test_cache_negative_ttl(self):
        """Test cache with negative TTL."""
        cache_manager = CacheManager(enabled=True)

        with patch.object(cache_manager, 'cache') as mock_cache:
            cache_manager.set("test_key", "test_value", ttl=-100)
            mock_cache.set.assert_called_once_with("test_key", "test_value", expire=-100)

    def test_cache_very_large_ttl(self):
        """Test cache with very large TTL."""
        cache_manager = CacheManager(enabled=True)
        large_ttl = 365 * 24 * 3600  # One year in seconds

        with patch.object(cache_manager, 'cache') as mock_cache:
            cache_manager.set("test_key", "test_value", ttl=large_ttl)
            mock_cache.set.assert_called_once_with("test_key", "test_value", expire=large_ttl)

    @patch('gh_pr.utils.cache.logger')
    def test_cache_concurrent_failure_logging(self, mock_logger):
        """Test that concurrent cache failures are logged correctly."""
        cache_manager = CacheManager(enabled=True)

        # Mock multiple concurrent failures
        with patch.object(cache_manager, 'cache') as mock_cache:
            mock_cache.get.side_effect = RuntimeError("Concurrent access error")

            # Multiple operations should each log separately
            cache_manager.get("key1")
            cache_manager.get("key2")
            cache_manager.get("key3")

            assert mock_logger.warning.call_count == 3

    def test_cache_disabled_after_init_failure(self):
        """Test that cache remains disabled after initialization failure."""
        with patch('pathlib.Path.mkdir', side_effect=PermissionError()):
            cache_manager = CacheManager(enabled=True)

            # Cache should be disabled
            assert cache_manager.enabled is False

            # All subsequent operations should be no-ops
            assert cache_manager.get("test") is None
            assert cache_manager.set("test", "value") is False
            assert cache_manager.delete("test") is False
            assert cache_manager.clear() is False
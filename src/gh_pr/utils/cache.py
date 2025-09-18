"""Caching functionality for gh-pr."""

import os
import hashlib
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Optional

import diskcache

logger = logging.getLogger(__name__)


class CacheManager:
    """Manage caching for PR data."""

    def __init__(self, enabled: bool = True, location: str = "~/.cache/gh-pr"):
        """
        Initialize CacheManager.

        Args:
            enabled: Whether caching is enabled
            location: Cache directory location
        """
        self.enabled = enabled
        self.location = Path(location).expanduser()
        self.cache = None

        if self.enabled:
            try:
                # Create directory
                self.location.mkdir(parents=True, exist_ok=True)

                # Check write permissions
                if not os.access(self.location, os.W_OK):
                    logger.warning(f"Cache location '{self.location}' is not writable. Disabling cache.")
                    self.enabled = False
                    return

                # Check available disk space (require at least 10MB)
                try:
                    stat = os.statvfs(str(self.location))
                    free_bytes = stat.f_bavail * stat.f_frsize
                    if free_bytes < 10 * 1024 * 1024:
                        logger.warning(f"Insufficient disk space at cache location '{self.location}'. "
                                     f"Required: 10MB, Available: {free_bytes // (1024 * 1024)}MB. Disabling cache.")
                        self.enabled = False
                        return
                except (OSError, AttributeError):
                    # statvfs not available on all systems
                    pass

                self.cache = diskcache.Cache(str(self.location))
            except (OSError, PermissionError) as e:
                logger.warning(f"Failed to initialize cache at '{self.location}': {e}. Disabling cache.")
                self.enabled = False

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if not self.enabled or not self.cache:
            return None

        try:
            return self.cache.get(key)
        except Exception as e:
            logger.debug(f"Cache get failed for key '{key}': {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        if not self.enabled:
            return False

        try:
            self.cache.set(key, value, expire=ttl)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if successful
        """
        if not self.enabled:
            return False

        try:
            del self.cache[key]
            return True
        except Exception:
            return False

    def clear(self) -> bool:
        """
        Clear all cache.

        Returns:
            True if successful
        """
        if not self.enabled:
            return False

        try:
            self.cache.clear()
            return True
        except Exception:
            return False

    def generate_key(self, *parts: str) -> str:
        """
        Generate a cache key from parts.

        Args:
            *parts: Key components

        Returns:
            Cache key string
        """
        combined = "_".join(str(p) for p in parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
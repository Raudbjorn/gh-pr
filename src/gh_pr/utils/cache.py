"""Caching functionality for gh-pr."""

import os
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Optional

import diskcache


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

        if self.enabled:
            self.location.mkdir(parents=True, exist_ok=True)
            self.cache = diskcache.Cache(str(self.location))

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if not self.enabled:
            return None

        try:
            return self.cache.get(key)
        except Exception:
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
"""Configuration management for gh-pr."""

import logging
import os
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib

import tomli_w

logger = logging.getLogger(__name__)

# Constants for allowed config directories
ALLOWED_CONFIG_DIRS = [
    Path.cwd(),  # Current working directory
    Path.home() / ".config" / "gh-pr",  # User config directory
    Path.home(),  # User home directory
]


def _validate_config_path(config_path: Path) -> bool:
    """
    Validate that config path is within allowed directories.

    Args:
        config_path: Path to validate

    Returns:
        True if path is safe, False otherwise
    """
    try:
        # Resolve the path to handle symlinks and relative paths
        resolved_path = config_path.resolve()

        # Check if the path is within any allowed directory
        for allowed_dir in ALLOWED_CONFIG_DIRS:
            try:
                allowed_resolved = allowed_dir.resolve()
                # Check if config path is relative to allowed directory
                resolved_path.relative_to(allowed_resolved)
                return True
            except ValueError:
                # Path is not relative to this allowed directory, continue checking
                continue

        logger.warning(f"Config path not in allowed directories: {resolved_path}")
        return False

    except (OSError, RuntimeError) as e:
        logger.warning(f"Failed to validate config path {config_path}: {e}")
        return False


class ConfigManager:
    """Manage configuration for gh-pr."""

    DEFAULT_CONFIG = {
        "github": {
            "default_token": None,
            "check_token_expiry": True,
        },
        "display": {
            "default_filter": "unresolved",
            "context_lines": 3,
            "show_code": True,
            "color_theme": "monokai",
        },
        "cache": {
            "enabled": True,
            "ttl_minutes": 5,
            "location": "~/.cache/gh-pr",
        },
        "clipboard": {
            "auto_strip_ansi": True,
        },
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize ConfigManager.

        Args:
            config_path: Path to config file
        """
        self.config = self.DEFAULT_CONFIG.copy()
        self.config_path = self._find_config_file(config_path)

        if self.config_path and self.config_path.exists():
            self._load_config()

    def _find_config_file(self, config_path: Optional[str] = None) -> Optional[Path]:
        """
        Find configuration file.

        Args:
            config_path: Explicit config path

        Returns:
            Path object or None
        """
        if config_path:
            config_path_obj = Path(config_path)
            if not _validate_config_path(config_path_obj):
                logger.warning(f"Invalid config path provided: {config_path}")
                return None
            return config_path_obj

        # Check locations in order of precedence
        locations = [
            Path(".gh-pr.toml"),  # Project-specific
            Path.home() / ".config" / "gh-pr" / "config.toml",  # User config
            Path.home() / ".gh-pr.toml",  # Legacy user config
        ]

        for location in locations:
            if location.exists() and _validate_config_path(location):
                return location

        return None

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            with open(self.config_path, "rb") as f:
                loaded_config = tomllib.load(f)

            # Merge with defaults
            self._merge_config(self.config, loaded_config)
        except (FileNotFoundError, PermissionError, tomllib.TOMLDecodeError) as e:
            # If config loading fails, use defaults
            logger.debug(f"Failed to load config from {self.config_path}: {e}")
            pass

    def _merge_config(self, base: dict[str, Any], update: dict[str, Any]) -> None:
        """
        Recursively merge configuration dictionaries.

        Args:
            base: Base configuration
            update: Update configuration
        """
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Args:
            key: Configuration key (dot-separated)
            default: Default value

        Returns:
            Configuration value
        """
        keys = key.split(".")
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value.

        Args:
            key: Configuration key (dot-separated)
            value: Value to set
        """
        keys = key.split(".")
        config = self.config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save(self, path: Optional[str] = None) -> bool:
        """
        Save configuration to file.

        Args:
            path: Path to save to

        Returns:
            True if successful
        """
        save_path = (Path(path) if path else self.config_path) or Path.home() / ".config" / "gh-pr" / "config.toml"

        # Validate the save path
        if not _validate_config_path(save_path):
            logger.error(f"Invalid save path: {save_path}")
            return False

        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, "wb") as f:
                tomli_w.dump(self.config, f)

            return True
        except (OSError, PermissionError, TypeError) as e:
            logger.debug(f"Failed to save config to {save_path}: {e}")
            return False

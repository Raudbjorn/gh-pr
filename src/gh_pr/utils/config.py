"""Configuration management for gh-pr."""

from pathlib import Path
from typing import Any, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib

import tomli_w


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
            "timeout_seconds": 5.0,
        },
        "logging": {
            "level": "INFO",
            "console_output": True,
            "file_output": True,
            "log_file": None,  # Auto-generated if None
            "timezone": "Atlantic/Reykjavik",
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
            return Path(config_path)

        # Check locations in order of precedence
        locations = [
            Path(".gh-pr.toml"),  # Project-specific
            Path.home() / ".config" / "gh-pr" / "config.toml",  # User config
            Path.home() / ".gh-pr.toml",  # Legacy user config
        ]

        for location in locations:
            if location.exists():
                return location

        return None

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            with open(self.config_path, "rb") as f:
                loaded_config = tomllib.load(f)

            # Merge with defaults
            self._merge_config(self.config, loaded_config)
        except Exception:
            # If config loading fails, use defaults
            pass

    def _merge_config(self, base: dict[str, Any], update: dict[str, Any]) -> None:
        """
        Recursively merge configuration dictionaries.

        Algorithm:
            1. Iterate through each key-value pair in the update dictionary
            2. If key exists in base AND both values are dictionaries: recurse
            3. Otherwise: overwrite base[key] with update[key]

        This preserves the deep structure while allowing selective overwrites.

        Args:
            base: Base configuration dictionary (modified in place)
            update: Update configuration dictionary (values to merge in)
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

    def delete(self, key: str) -> None:
        """
        Delete configuration value.

        Args:
            key: Configuration key (dot-separated)
        """
        keys = key.split(".")

        # Handle single key (top-level)
        if len(keys) == 1:
            if keys[0] in self.config:
                del self.config[keys[0]]
            return

        # Navigate to parent of the key to delete
        config = self.config
        for k in keys[:-1]:
            if not isinstance(config, dict) or k not in config:
                # Key doesn't exist, nothing to delete
                return
            config = config[k]

        # Delete the final key if it exists
        if isinstance(config, dict) and keys[-1] in config:
            del config[keys[-1]]

    def save(self, path: Optional[str] = None) -> bool:
        """
        Save configuration to file.

        Args:
            path: Path to save to

        Returns:
            True if successful
        """
        save_path = (Path(path) if path else self.config_path) or Path.home() / ".config" / "gh-pr" / "config.toml"

        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, "wb") as f:
                tomli_w.dump(self.config, f)

            return True
        except Exception:
            return False

    def get_all(self) -> dict[str, Any]:
        """
        Get entire configuration.

        Returns:
            Configuration dictionary
        """
        return self.config.copy()

    def update_section(self, section: str, values: dict[str, Any]) -> None:
        """
        Update entire configuration section.

        Args:
            section: Section name
            values: New section values
        """
        self.config[section] = values

    def has(self, key: str) -> bool:
        """
        Check if configuration key exists.

        Args:
            key: Configuration key (dot-separated)

        Returns:
            True if key exists
        """
        keys = key.split(".")
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return False

        return True

    def reset_to_defaults(self, defaults: dict[str, Any]) -> None:
        """
        Reset configuration to provided defaults.

        Args:
            defaults: Default configuration
        """
        self.config = defaults.copy()

    def merge(self, additional_config: dict[str, Any]) -> None:
        """
        Merge additional configuration into the current configuration.

        This method performs a deep merge of configuration dictionaries:
        - For nested dictionaries: Merges recursively, preserving existing keys
        - For scalar values: New values completely replace existing values
        - For new keys: Adds them to the configuration
        - Modifies the existing configuration in place

        Merge Behavior Examples:
            Base config: {"github": {"token": "old", "check_expiry": True}}
            Additional: {"github": {"token": "new"}, "cache": {"enabled": False}}
            Result: {"github": {"token": "new", "check_expiry": True}, "cache": {"enabled": False}}

            Base config: {"display": {"theme": "dark", "lines": 5}}
            Additional: {"display": {"theme": "light"}}
            Result: {"display": {"theme": "light", "lines": 5}}

        Use Cases:
            - Runtime configuration overrides from CLI arguments
            - User-specific configuration layered over defaults
            - Dynamic configuration updates during execution
            - Token metadata storage (adds new token entries without affecting others)

        Note:
            This method modifies the existing configuration in place.
            The merge is recursive for nested dictionaries. Values from
            additional_config will override existing values with the same key.

        Args:
            additional_config: Configuration dictionary to merge into current config.
                              Must be a valid dictionary structure matching config schema.

        Raises:
            TypeError: If additional_config is not a dictionary or contains invalid types
        """
        if not isinstance(additional_config, dict):
            raise TypeError("additional_config must be a dictionary")
        self._merge_config(self.config, additional_config)

    def get_logging_config(self) -> dict[str, Any]:
        """
        Get logging configuration.

        Returns:
            Dictionary containing logging configuration
        """
        return self.get("logging", self.DEFAULT_CONFIG["logging"])

    def setup_logging(self) -> None:
        """
        Setup application logging using the configured settings.

        This method initializes the RichLogger with the configuration
        settings and makes it available throughout the application.
        """
        from .rich_logger import setup_logging
        import logging

        log_config = self.get_logging_config()

        # Convert string log level to int
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        level = level_map.get(log_config["level"].upper(), logging.INFO)

        # Setup logging with configuration
        setup_logging(
            level=level,
            log_file=log_config.get("log_file"),
            console_output=log_config.get("console_output", True),
            file_output=log_config.get("file_output", True)
        )

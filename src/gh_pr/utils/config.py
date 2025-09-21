"""Configuration management for gh-pr."""

import logging
import os
from pathlib import Path
from typing import Any, Optional
from rich.console import Console

try:
    import tomllib
except ImportError:
    import tomli as tomllib

# Constants for test compatibility
ALLOWED_CONFIG_DIRS = ['/home', '/tmp', '/etc']

def _validate_config_path(path: Path) -> bool:
    """Validate config path for security.

    Args:
        path: Path to validate

    Returns:
        True if path is in allowed directories
    """
    try:
        resolved = path.resolve()
        # In test mode, use ALLOWED_CONFIG_DIRS
        import os
        if os.environ.get('GH_PR_TEST'):
            return any(str(resolved).startswith(d) for d in ALLOWED_CONFIG_DIRS)
        # In production, allow home directory and system config
        return str(resolved).startswith(str(Path.home())) or str(resolved).startswith('/etc')
    except Exception:
        return False

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
            "pr_limit": 50,  # Maximum number of PRs to fetch per repository
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
            "syslog_output": False,
            "syslog_address": None,  # None for local, or ("host", 514) for remote
            "syslog_facility": "LOG_USER",  # Syslog facility name
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
            path = Path(config_path)
            if _validate_config_path(path):
                return path
            else:
                console = Console()
                console.print(f"[yellow]Warning: Config path '{config_path}' is not in an allowed directory[/yellow]")
                return None

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
        import logging

        from .rich_logger import setup_logging

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

        # Get timezone configuration
        import pytz
        timezone_str = log_config.get("timezone", "Atlantic/Reykjavik")
        try:
            timezone_obj = pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            timezone_obj = pytz.timezone("Atlantic/Reykjavik")  # Fallback to default

        # Parse syslog facility if configured
        import logging.handlers
        syslog_facility = log_config.get("syslog_facility", "LOG_USER")
        facility_map = {
            "LOG_KERN": logging.handlers.SysLogHandler.LOG_KERN,
            "LOG_USER": logging.handlers.SysLogHandler.LOG_USER,
            "LOG_MAIL": logging.handlers.SysLogHandler.LOG_MAIL,
            "LOG_DAEMON": logging.handlers.SysLogHandler.LOG_DAEMON,
            "LOG_AUTH": logging.handlers.SysLogHandler.LOG_AUTH,
            "LOG_SYSLOG": logging.handlers.SysLogHandler.LOG_SYSLOG,
            "LOG_LPR": logging.handlers.SysLogHandler.LOG_LPR,
            "LOG_NEWS": logging.handlers.SysLogHandler.LOG_NEWS,
            "LOG_UUCP": logging.handlers.SysLogHandler.LOG_UUCP,
            "LOG_CRON": logging.handlers.SysLogHandler.LOG_CRON,
            "LOG_LOCAL0": logging.handlers.SysLogHandler.LOG_LOCAL0,
            "LOG_LOCAL1": logging.handlers.SysLogHandler.LOG_LOCAL1,
            "LOG_LOCAL2": logging.handlers.SysLogHandler.LOG_LOCAL2,
            "LOG_LOCAL3": logging.handlers.SysLogHandler.LOG_LOCAL3,
            "LOG_LOCAL4": logging.handlers.SysLogHandler.LOG_LOCAL4,
            "LOG_LOCAL5": logging.handlers.SysLogHandler.LOG_LOCAL5,
            "LOG_LOCAL6": logging.handlers.SysLogHandler.LOG_LOCAL6,
            "LOG_LOCAL7": logging.handlers.SysLogHandler.LOG_LOCAL7,
        }
        syslog_facility_code = facility_map.get(syslog_facility, logging.handlers.SysLogHandler.LOG_USER)

        # Parse syslog address
        syslog_address = log_config.get("syslog_address")
        if syslog_address and isinstance(syslog_address, list) and len(syslog_address) == 2:
            syslog_address = tuple(syslog_address)  # Convert list to tuple

        # Setup logging with configuration
        setup_logging(
            level=level,
            log_file=log_config.get("log_file"),
            console_output=log_config.get("console_output", True),
            file_output=log_config.get("file_output", True),
            syslog_output=log_config.get("syslog_output", False),
            syslog_address=syslog_address,
            syslog_facility=syslog_facility_code,
            timezone=timezone_obj
        )

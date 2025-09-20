"""
Base plugin interface and metadata.

Defines the plugin contract and metadata structure for
gh-pr plugins.
"""

import importlib
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

logger = logging.getLogger(__name__)


class PluginCapability(Enum):
    """Plugin capability types."""

    # Event handlers
    PR_EVENT = "pr_event"
    COMMENT_FILTER = "comment_filter"
    WEBHOOK_HANDLER = "webhook_handler"

    # Display extensions
    DISPLAY_FORMATTER = "display_formatter"
    EXPORT_FORMAT = "export_format"

    # Data processors
    DATA_PROCESSOR = "data_processor"
    CACHE_PROVIDER = "cache_provider"

    # Actions
    AUTOMATION = "automation"
    NOTIFICATION = "notification"


@dataclass
class PluginMetadata:
    """
    Plugin metadata and configuration.

    Attributes:
        name: Unique plugin identifier
        version: Plugin version string
        description: Human-readable description
        author: Plugin author
        capabilities: Set of capabilities provided
        dependencies: Required Python packages
        config_schema: JSON schema for configuration
    """

    name: str
    version: str
    description: str
    author: str = "Unknown"
    capabilities: Set[PluginCapability] = field(default_factory=set)
    dependencies: List[str] = field(default_factory=list)
    config_schema: Optional[Dict[str, Any]] = None
    homepage: Optional[str] = None
    license: str = "MIT"

    def validate(self) -> bool:
        """
        Validate metadata requirements.

        Returns:
            True if metadata is valid
        """
        if not self.name or not self.version:
            return False

        # Validate name format (alphanumeric, dash, underscore)
        pass  # re imported at top
        if not re.match(r'^[a-zA-Z0-9_-]+$', self.name):
            logger.warning(f"Invalid plugin name format: {self.name}")
            return False

        return True


@dataclass
class PluginContext:
    """
    Runtime context provided to plugins.

    Provides access to application services and configuration.
    """

    config: Dict[str, Any]
    cache_manager: Optional[Any] = None
    github_client: Optional[Any] = None
    display_manager: Optional[Any] = None
    notification_manager: Optional[Any] = None
    plugin_dir: Optional[Path] = None
    data_dir: Optional[Path] = None


class Plugin(ABC):
    """
    Abstract base class for gh-pr plugins.

    All plugins must inherit from this class and implement
    the required methods.
    """

    def __init__(self, context: PluginContext):
        """
        Initialize plugin with runtime context.

        Args:
            context: Plugin runtime context
        """
        self.context = context
        self._enabled = True

    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata object
        """
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize plugin.

        Perform any setup required before the plugin can be used.
        This may include checking dependencies, setting up resources, etc.

        Returns:
            True if initialization successful
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Shutdown plugin.

        Clean up any resources used by the plugin.
        """
        pass

    def is_enabled(self) -> bool:
        """Check if plugin is enabled."""
        return self._enabled

    def enable(self) -> None:
        """Enable the plugin."""
        self._enabled = True
        logger.info(f"Plugin {self.get_metadata().name} enabled")

    def disable(self) -> None:
        """Disable the plugin."""
        self._enabled = False
        logger.info(f"Plugin {self.get_metadata().name} disabled")

    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get plugin configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value
        """
        plugin_config = self.context.config.get('plugins', {}).get(
            self.get_metadata().name, {}
        )
        return plugin_config.get(key, default)

    async def validate_dependencies(self) -> bool:
        """
        Validate that required dependencies are available.

        Returns:
            True if all dependencies are satisfied
        """
        metadata = self.get_metadata()

        for dep in metadata.dependencies:
            try:
                # Try to import the dependency
                pass  # importlib imported at top
                importlib.import_module(dep.split('>=')[0].strip())
            except ImportError:
                logger.error(f"Plugin {metadata.name} missing dependency: {dep}")
                return False

        return True

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform plugin health check.

        Returns:
            Health status dictionary
        """
        return {
            'name': self.get_metadata().name,
            'enabled': self._enabled,
            'healthy': True,
            'version': self.get_metadata().version
        }


class PREventPlugin(Plugin):
    """Base class for PR event handling plugins."""

    @abstractmethod
    async def handle_pr_event(self, event: Dict[str, Any]) -> Any:
        """Handle a PR event."""
        pass


class CommentFilterPlugin(Plugin):
    """Base class for comment filter plugins."""

    @abstractmethod
    async def filter_comments(
        self,
        comments: List[Dict[str, Any]],
        criteria: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Filter comments based on criteria."""
        pass


class DisplayFormatterPlugin(Plugin):
    """Base class for display formatter plugins."""

    @abstractmethod
    async def format_output(
        self,
        data: Dict[str, Any],
        format_options: Dict[str, Any]
    ) -> str:
        """Format data for display."""
        pass


class NotificationPlugin(Plugin):
    """Base class for notification plugins."""

    @abstractmethod
    async def send_notification(
        self,
        title: str,
        message: str,
        **kwargs
    ) -> bool:
        """Send a notification."""
        pass
"""
Plugin manager for coordinating plugin operations.

Provides high-level plugin management including lifecycle,
event routing, and capability dispatch.
"""

import logging
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
import asyncio

from .base import Plugin, PluginCapability, PluginContext
from .loader import PluginLoader

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Central manager for plugin operations.

    Coordinates plugin loading, initialization, event routing,
    and capability dispatch.
    """

    def __init__(
        self,
        context: PluginContext,
        plugin_paths: Optional[List[Path]] = None,
        auto_discover: bool = True
    ):
        """
        Initialize plugin manager.

        Args:
            context: Plugin runtime context
            plugin_paths: Additional plugin search paths
            auto_discover: Automatically discover and load plugins
        """
        self.context = context
        self.loader = PluginLoader(plugin_paths, context)
        self._initialized = False
        self._capability_registry: Dict[PluginCapability, List[Plugin]] = {}

        if auto_discover:
            self.discover_and_load()

    def discover_and_load(self) -> Dict[str, Plugin]:
        """
        Discover and load all available plugins.

        Returns:
            Dictionary of loaded plugins
        """
        logger.info("Discovering plugins...")
        plugins = self.loader.load_all_plugins()
        logger.info(f"Loaded {len(plugins)} plugins")

        # Build capability registry
        self._rebuild_capability_registry()

        return plugins

    def _rebuild_capability_registry(self) -> None:
        """Rebuild the capability registry from loaded plugins."""
        self._capability_registry.clear()

        for plugin in self.loader.get_loaded_plugins().values():
            if not plugin.is_enabled():
                continue

            metadata = plugin.get_metadata()
            for capability in metadata.capabilities:
                if capability not in self._capability_registry:
                    self._capability_registry[capability] = []
                self._capability_registry[capability].append(plugin)

    async def initialize(self) -> bool:
        """
        Initialize all plugins.

        Returns:
            True if all enabled plugins initialized successfully
        """
        if self._initialized:
            logger.debug("Plugin manager already initialized")
            return True

        logger.info("Initializing plugins...")
        results = await self.loader.initialize_plugins()

        # Check if all enabled plugins initialized
        success = all(
            status for name, status in results.items()
            if self.loader.get_plugin(name) and
            self.loader.get_plugin(name).is_enabled()
        )

        if success:
            self._initialized = True
            logger.info("All plugins initialized successfully")
        else:
            failed = [name for name, status in results.items() if not status]
            logger.warning(f"Some plugins failed to initialize: {failed}")

        return success

    async def shutdown(self) -> None:
        """Shutdown all plugins."""
        logger.info("Shutting down plugins...")
        await self.loader.shutdown_plugins()
        self._initialized = False

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """
        Get a specific plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None
        """
        return self.loader.get_plugin(name)

    def get_plugins_with_capability(
        self,
        capability: PluginCapability
    ) -> List[Plugin]:
        """
        Get all plugins with a specific capability.

        Args:
            capability: Capability to filter by

        Returns:
            List of plugins with the capability
        """
        return self._capability_registry.get(capability, [])

    async def dispatch_pr_event(
        self,
        event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Dispatch a PR event to all PR event handlers.

        Args:
            event: PR event data

        Returns:
            Results from all handlers
        """
        handlers = self.get_plugins_with_capability(PluginCapability.PR_EVENT)
        results = {}

        for plugin in handlers:
            if not plugin.is_enabled():
                continue

            try:
                # Import here to avoid circular dependency
                from .base import PREventPlugin
                if isinstance(plugin, PREventPlugin):
                    result = await plugin.handle_pr_event(event)
                    results[plugin.get_metadata().name] = result
            except Exception as e:
                logger.error(f"Plugin {plugin.get_metadata().name} error handling PR event: {e}")
                results[plugin.get_metadata().name] = {'error': str(e)}

        return results

    async def filter_comments(
        self,
        comments: List[Dict[str, Any]],
        criteria: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Filter comments through all comment filter plugins.

        Args:
            comments: Comments to filter
            criteria: Filter criteria

        Returns:
            Filtered comments
        """
        filters = self.get_plugins_with_capability(PluginCapability.COMMENT_FILTER)

        filtered = comments
        for plugin in filters:
            if not plugin.is_enabled():
                continue

            try:
                from .base import CommentFilterPlugin
                if isinstance(plugin, CommentFilterPlugin):
                    filtered = await plugin.filter_comments(filtered, criteria)
            except Exception as e:
                logger.error(f"Plugin {plugin.get_metadata().name} error filtering comments: {e}")

        return filtered

    async def send_notification(
        self,
        title: str,
        message: str,
        **kwargs
    ) -> Dict[str, bool]:
        """
        Send notification through all notification plugins.

        Args:
            title: Notification title
            message: Notification message
            **kwargs: Additional notification parameters

        Returns:
            Results from all notification plugins
        """
        notifiers = self.get_plugins_with_capability(PluginCapability.NOTIFICATION)
        results = {}

        # Run notifications in parallel
        tasks = []
        for plugin in notifiers:
            if not plugin.is_enabled():
                continue

            from .base import NotificationPlugin
            if isinstance(plugin, NotificationPlugin):
                task = asyncio.create_task(
                    plugin.send_notification(title, message, **kwargs)
                )
                tasks.append((plugin.get_metadata().name, task))

        for name, task in tasks:
            try:
                result = await task
                results[name] = result
            except Exception as e:
                logger.error(f"Plugin {name} notification error: {e}")
                results[name] = False

        return results

    def enable_plugin(self, name: str) -> bool:
        """
        Enable a specific plugin.

        Args:
            name: Plugin name

        Returns:
            True if plugin was enabled
        """
        plugin = self.get_plugin(name)
        if plugin:
            plugin.enable()
            self._rebuild_capability_registry()
            return True
        return False

    def disable_plugin(self, name: str) -> bool:
        """
        Disable a specific plugin.

        Args:
            name: Plugin name

        Returns:
            True if plugin was disabled
        """
        plugin = self.get_plugin(name)
        if plugin:
            plugin.disable()
            self._rebuild_capability_registry()
            return True
        return False

    async def get_plugin_health(self) -> Dict[str, Dict[str, Any]]:
        """
        Get health status of all plugins.

        Returns:
            Health status for each plugin
        """
        health_status = {}

        for name, plugin in self.loader.get_loaded_plugins().items():
            try:
                health = await plugin.health_check()
                health_status[name] = health
            except Exception as e:
                health_status[name] = {
                    'name': name,
                    'healthy': False,
                    'error': str(e)
                }

        return health_status

    def get_plugin_info(self) -> List[Dict[str, Any]]:
        """
        Get information about all loaded plugins.

        Returns:
            List of plugin information dictionaries
        """
        info = []

        for plugin in self.loader.get_loaded_plugins().values():
            metadata = plugin.get_metadata()
            info.append({
                'name': metadata.name,
                'version': metadata.version,
                'description': metadata.description,
                'author': metadata.author,
                'capabilities': [cap.value for cap in metadata.capabilities],
                'enabled': plugin.is_enabled()
            })

        return info
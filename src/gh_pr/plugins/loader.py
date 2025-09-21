"""
Plugin loader for dynamic plugin discovery and loading.

Handles plugin discovery from various sources and safe loading
with dependency validation.
"""

import importlib
import importlib.util
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

import tomllib

from .base import Plugin, PluginContext

logger = logging.getLogger(__name__)

# Plugin loader namespace to prevent collisions with stdlib/third-party packages
PLUGIN_NAMESPACE = "gh_pr_plugins"


def sanitize_module_name(name: str) -> str:
    """
    Sanitize plugin name for use as a Python module name.

    Replaces hyphens with underscores and removes other invalid characters.

    Args:
        name: Original plugin name

    Returns:
        Sanitized module name safe for Python imports
    """
    # Replace hyphens with underscores and remove non-alphanumeric chars
    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    # Ensure it doesn't start with a digit
    if safe_name and safe_name[0].isdigit():
        safe_name = '_' + safe_name
    return safe_name

# Default plugin search paths
DEFAULT_PLUGIN_PATHS = [
    Path.home() / '.config' / 'gh-pr' / 'plugins',
    Path.home() / '.gh-pr' / 'plugins',
]

# Only include CWD if explicitly enabled via environment variable (security measure)
if os.getenv('GH_PR_ALLOW_CWD_PLUGINS', '').lower() == 'true':
    DEFAULT_PLUGIN_PATHS.append(Path.cwd() / '.gh-pr' / 'plugins')


class PluginLoader:
    """
    Loads and manages plugin modules.

    Handles discovery, validation, and instantiation of plugins
    from various sources.
    """

    def __init__(
        self,
        plugin_paths: Optional[List[Path]] = None,
        context: Optional[PluginContext] = None
    ):
        """
        Initialize plugin loader.

        Args:
            plugin_paths: Additional paths to search for plugins
            context: Plugin context to provide to loaded plugins
        """
        self.plugin_paths = DEFAULT_PLUGIN_PATHS.copy()
        if plugin_paths:
            self.plugin_paths.extend(plugin_paths)

        self.context = context or PluginContext(config={})
        self._loaded_plugins: Dict[str, Plugin] = {}
        self._plugin_errors: Dict[str, str] = {}

    def discover_plugins(self) -> Dict[str, Path]:
        """
        Discover available plugins.

        Searches configured paths for plugin modules and manifests.

        Returns:
            Dictionary mapping plugin names to their paths
        """
        discovered = {}

        for plugin_dir in self.plugin_paths:
            if not plugin_dir.exists():
                continue

            # Look for plugin manifests (plugin.toml or plugin.json)
            for manifest_file in plugin_dir.glob('*/plugin.toml'):
                try:
                    with open(manifest_file, 'rb') as f:
                        manifest = tomllib.load(f)

                    plugin_name = manifest.get('plugin', {}).get('name')
                    if plugin_name:
                        discovered[plugin_name] = manifest_file.parent
                        logger.debug(f"Discovered plugin: {plugin_name} at {manifest_file.parent}")
                except Exception:
                    logger.exception(f"Failed to read manifest {manifest_file}")

            # Also check for JSON manifests
            for manifest_file in plugin_dir.glob('*/plugin.json'):
                try:
                    with open(manifest_file) as f:
                        manifest = json.load(f)

                    plugin_name = manifest.get('name')
                    if plugin_name:
                        discovered[plugin_name] = manifest_file.parent
                        logger.debug(f"Discovered plugin: {plugin_name} at {manifest_file.parent}")
                except Exception:
                    logger.exception(f"Failed to read JSON manifest {manifest_file}")

            # Look for Python plugin modules
            for py_file in plugin_dir.glob('*.py'):
                if py_file.stem.startswith('_'):
                    continue

                module_name = f"ghpr_plugin_{py_file.stem}"
                discovered[module_name] = py_file
                logger.debug(f"Discovered Python plugin: {module_name} at {py_file}")

        return discovered

    def load_plugin(self, name: str, path: Path) -> Optional[Plugin]:
        """
        Load a specific plugin.

        Args:
            name: Plugin name
            path: Path to plugin module or directory

        Returns:
            Loaded plugin instance or None if failed
        """
        if name in self._loaded_plugins:
            logger.debug(f"Plugin {name} already loaded")
            return self._loaded_plugins[name]

        try:
            if path.is_file() and path.suffix == '.py':
                # Load Python module directly
                plugin = self._load_python_plugin(name, path)
            elif path.is_dir():
                # Load plugin from directory
                plugin = self._load_plugin_directory(name, path)
            else:
                msg = f"Invalid plugin path: {path}"
                raise ValueError(msg)

            if plugin:
                self._loaded_plugins[name] = plugin
                logger.info(f"Loaded plugin: {name}")

            return plugin

        except Exception as e:
            error_msg = f"Failed to load plugin {name}: {e}"
            logger.error(error_msg, exc_info=True)
            self._plugin_errors[name] = str(e)
            return None

    def _load_python_plugin(self, name: str, path: Path) -> Optional[Plugin]:
        """
        Load a Python plugin module.

        Args:
            name: Plugin name
            path: Path to Python file

        Returns:
            Plugin instance or None
        """
        # Load module dynamically with proper package handling
        # Use the parent directory as the package location for relative imports
        if path.parent != Path('.'):
            spec = importlib.util.spec_from_file_location(
                name,
                path,
                submodule_search_locations=[str(path.parent)]
            )
        else:
            spec = importlib.util.spec_from_file_location(name, path)

        if not spec or not spec.loader:
            msg = f"Cannot load module from {path}"
            raise ImportError(msg)

        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module

        # Set up proper package structure for relative imports
        if '.' in name:
            parent_name = name.rsplit('.', 1)[0]
            if parent_name not in sys.modules:
                # Create proper namespace package with correct name and spec
                parent_spec = importlib.util.spec_from_file_location(
                    parent_name,
                    None,
                    submodule_search_locations=[str(path.parent)]
                )
                parent_module = importlib.util.module_from_spec(parent_spec)
                parent_module.__path__ = [str(path.parent)]
                sys.modules[parent_name] = parent_module

        spec.loader.exec_module(module)

        # Find Plugin subclass in module
        # Skip base plugin classes that may be imported
        from .base import (
            CommentFilterPlugin,
            DisplayFormatterPlugin,
            NotificationPlugin,
            Plugin,
            PREventPlugin,
        )
        base_classes = {Plugin, PREventPlugin, NotificationPlugin,
                       CommentFilterPlugin, DisplayFormatterPlugin}

        candidates = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, Plugin) and attr not in base_classes:
                candidates.append(attr)

        if not candidates:
            msg = f"No Plugin subclass found in {path}"
            raise ValueError(msg)
        if len(candidates) > 1:
            msg = f"Multiple Plugin subclasses found in {path}: {[c.__name__ for c in candidates]}"
            raise ValueError(msg)

        # Instantiate and validate metadata
        plugin = candidates[0](self.context)
        metadata = plugin.get_metadata()
        if not metadata or not metadata.validate():
            msg = f"Invalid plugin metadata for {getattr(metadata, 'name', '<unknown>')}"
            raise ValueError(msg)
        return plugin

    def _load_plugin_directory(self, name: str, path: Path) -> Optional[Plugin]:
        """
        Load a plugin from a directory.

        Args:
            name: Plugin name
            path: Plugin directory path

        Returns:
            Plugin instance or None
        """
        # Look for main plugin module
        main_file = path / 'plugin.py'
        if not main_file.exists():
            main_file = path / '__init__.py'

        if not main_file.exists():
            raise FileNotFoundError(f"No plugin.py or __init__.py found in {path}")

        # Sanitize the plugin name for use as a module name
        safe_module_name = sanitize_module_name(name)
        # Place all plugins under the isolated namespace to prevent collisions
        if main_file.name == 'plugin.py':
            package_name = f"{PLUGIN_NAMESPACE}.{safe_module_name}.{main_file.stem}"
        else:
            package_name = f"{PLUGIN_NAMESPACE}.{safe_module_name}"
        return self._load_python_plugin(package_name, main_file)

    def load_all_plugins(self) -> Dict[str, Plugin]:
        """
        Load all discovered plugins.

        Returns:
            Dictionary of loaded plugins
        """
        discovered = self.discover_plugins()

        for name, path in discovered.items():
            if name not in self._loaded_plugins:
                self.load_plugin(name, path)

        return self._loaded_plugins.copy()

    async def initialize_plugins(self) -> Dict[str, bool]:
        """
        Initialize all loaded plugins.

        Returns:
            Dictionary mapping plugin names to initialization status
        """
        results = {}

        for name, plugin in self._loaded_plugins.items():
            try:
                # Validate dependencies first
                if not await plugin.validate_dependencies():
                    logger.warning(f"Plugin {name} has unsatisfied dependencies")
                    results[name] = False
                    continue

                # Initialize plugin
                success = await plugin.initialize()
                results[name] = success

                if not success:
                    logger.warning(f"Plugin {name} initialization failed")

            except Exception as e:
                logger.error(f"Plugin {name} initialization error: {e}", exc_info=True)
                results[name] = False
                self._plugin_errors[name] = f"Initialization error: {e}"

        return results

    async def shutdown_plugins(self) -> None:
        """Shutdown all loaded plugins."""
        for name, plugin in self._loaded_plugins.items():
            try:
                await plugin.shutdown()
                logger.debug(f"Plugin {name} shutdown complete")
            except Exception as e:
                logger.error(f"Plugin {name} shutdown error: {e}", exc_info=True)

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """
        Get a loaded plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None
        """
        return self._loaded_plugins.get(name)

    def get_plugins_by_capability(
        self,
        capability: str
    ) -> List[Plugin]:
        """
        Get plugins that provide a specific capability.

        Args:
            capability: Capability name (string or PluginCapability enum)

        Returns:
            List of plugins with the capability
        """
        # Normalize the capability to a string value
        if hasattr(capability, "value"):
            # It's an enum member, get its value
            capability = capability.value
        else:
            # Ensure it's a string
            capability = str(capability)

        plugins = []

        for plugin in self._loaded_plugins.values():
            metadata = plugin.get_metadata()
            if capability in [cap.value for cap in metadata.capabilities]:
                plugins.append(plugin)

        return plugins

    def get_loaded_plugins(self) -> Dict[str, Plugin]:
        """Get all loaded plugins."""
        return self._loaded_plugins.copy()

    def get_plugin_errors(self) -> Dict[str, str]:
        """Get plugin loading errors."""
        return self._plugin_errors.copy()

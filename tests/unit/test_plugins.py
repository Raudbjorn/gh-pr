"""
Unit tests for plugin system.

Tests plugin loading, management, and dispatch.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import tempfile
import shutil
from pathlib import Path
import json
import asyncio

from gh_pr.plugins.base import (
    Plugin, PluginMetadata, PluginContext, PluginCapability,
    PREventPlugin, CommentFilterPlugin, NotificationPlugin
)
from gh_pr.plugins.loader import PluginLoader
from gh_pr.plugins.manager import PluginManager


class TestPluginBase(unittest.TestCase):
    """Test base plugin functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.context = PluginContext(config={})

    def test_plugin_metadata_validation(self):
        """Test plugin metadata validation."""
        # Valid metadata
        metadata = PluginMetadata(
            name="test-plugin",
            version="1.0.0",
            description="Test plugin",
            capabilities={PluginCapability.PR_EVENT}
        )
        self.assertTrue(metadata.validate())

        # Invalid name format
        metadata_invalid = PluginMetadata(
            name="test plugin!",  # Invalid characters
            version="1.0.0",
            description="Test plugin"
        )
        self.assertFalse(metadata_invalid.validate())

        # Missing required fields
        metadata_empty = PluginMetadata(
            name="",
            version="",
            description="Test"
        )
        self.assertFalse(metadata_empty.validate())

    def test_plugin_enable_disable(self):
        """Test plugin enable/disable functionality."""
        class TestPlugin(Plugin):
            def get_metadata(self):
                return PluginMetadata(
                    name="test",
                    version="1.0.0",
                    description="Test"
                )

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        plugin = TestPlugin(self.context)

        # Should be enabled by default
        self.assertTrue(plugin.is_enabled())

        # Disable
        plugin.disable()
        self.assertFalse(plugin.is_enabled())

        # Re-enable
        plugin.enable()
        self.assertTrue(plugin.is_enabled())

    def test_plugin_config_access(self):
        """Test plugin configuration access."""
        context = PluginContext(
            config={
                'plugins': {
                    'test-plugin': {
                        'api_key': 'secret123',
                        'timeout': 30
                    }
                }
            }
        )

        class TestPlugin(Plugin):
            def get_metadata(self):
                return PluginMetadata(name="test-plugin", version="1.0.0", description="Test")

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        plugin = TestPlugin(context)

        # Access existing config
        self.assertEqual(plugin.get_config('api_key'), 'secret123')
        self.assertEqual(plugin.get_config('timeout'), 30)

        # Access with default
        self.assertEqual(plugin.get_config('missing', 'default'), 'default')


class TestPluginLoader(unittest.TestCase):
    """Test plugin loader functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.plugin_dir = Path(self.temp_dir) / 'plugins'
        self.plugin_dir.mkdir()
        self.context = PluginContext(config={})
        self.loader = PluginLoader([self.plugin_dir], self.context)

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)

    def test_discover_plugins_with_toml(self):
        """Test plugin discovery with TOML manifest."""
        # Create plugin directory with manifest
        plugin_path = self.plugin_dir / 'test_plugin'
        plugin_path.mkdir()

        manifest = plugin_path / 'plugin.toml'
        manifest.write_text("""
[plugin]
name = "test-plugin"
version = "1.0.0"
""")

        discovered = self.loader.discover_plugins()
        self.assertIn('test-plugin', discovered)
        self.assertEqual(discovered['test-plugin'], plugin_path)

    def test_discover_plugins_with_json(self):
        """Test plugin discovery with JSON manifest."""
        plugin_path = self.plugin_dir / 'json_plugin'
        plugin_path.mkdir()

        manifest = plugin_path / 'plugin.json'
        manifest.write_text(json.dumps({
            'name': 'json-plugin',
            'version': '1.0.0'
        }))

        discovered = self.loader.discover_plugins()
        self.assertIn('json-plugin', discovered)

    def test_discover_python_plugins(self):
        """Test discovery of Python plugin files."""
        plugin_file = self.plugin_dir / 'simple_plugin.py'
        plugin_file.write_text("# Plugin module")

        discovered = self.loader.discover_plugins()
        self.assertIn('ghpr_plugin_simple_plugin', discovered)

    def test_load_python_plugin(self):
        """Test loading a Python plugin module."""
        # Create a simple plugin file
        plugin_file = self.plugin_dir / 'test.py'
        plugin_file.write_text("""
from gh_pr.plugins.base import Plugin, PluginMetadata

class TestPlugin(Plugin):
    def get_metadata(self):
        return PluginMetadata(
            name="loaded-test",
            version="1.0.0",
            description="Loaded test plugin"
        )

    async def initialize(self):
        return True

    async def shutdown(self):
        pass
""")

        plugin = self.loader.load_plugin('test', plugin_file)
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.get_metadata().name, 'loaded-test')

    def test_load_plugin_directory(self):
        """Test loading plugin from directory."""
        plugin_path = self.plugin_dir / 'dir_plugin'
        plugin_path.mkdir()

        # Create plugin.py
        (plugin_path / 'plugin.py').write_text("""
from gh_pr.plugins.base import Plugin, PluginMetadata

class DirPlugin(Plugin):
    def get_metadata(self):
        return PluginMetadata(name="dir-plugin", version="1.0.0", description="Dir plugin")

    async def initialize(self):
        return True

    async def shutdown(self):
        pass
""")

        plugin = self.loader.load_plugin('dir-plugin', plugin_path)
        self.assertIsNotNone(plugin)

    @patch('importlib.util.spec_from_file_location')
    def test_load_plugin_error_handling(self, mock_spec):
        """Test plugin loading error handling."""
        mock_spec.return_value = None

        plugin_file = self.plugin_dir / 'bad.py'
        plugin_file.write_text("# Bad plugin")

        plugin = self.loader.load_plugin('bad', plugin_file)
        self.assertIsNone(plugin)
        self.assertIn('bad', self.loader._plugin_errors)


class TestPluginManager(unittest.TestCase):
    """Test plugin manager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.context = PluginContext(config={})
        self.manager = PluginManager(self.context, auto_discover=False)

    def test_capability_registry(self):
        """Test capability registry building."""
        # Create mock plugins
        plugin1 = Mock()
        plugin1.is_enabled.return_value = True
        plugin1.get_metadata.return_value = PluginMetadata(
            name="plugin1",
            version="1.0.0",
            description="Test",
            capabilities={PluginCapability.PR_EVENT}
        )

        plugin2 = Mock()
        plugin2.is_enabled.return_value = True
        plugin2.get_metadata.return_value = PluginMetadata(
            name="plugin2",
            version="1.0.0",
            description="Test",
            capabilities={PluginCapability.NOTIFICATION, PluginCapability.PR_EVENT}
        )

        # Add plugins to loader
        self.manager.loader._loaded_plugins = {
            'plugin1': plugin1,
            'plugin2': plugin2
        }

        # Rebuild registry
        self.manager._rebuild_capability_registry()

        # Check registry
        pr_plugins = self.manager.get_plugins_with_capability(PluginCapability.PR_EVENT)
        self.assertEqual(len(pr_plugins), 2)

        notif_plugins = self.manager.get_plugins_with_capability(PluginCapability.NOTIFICATION)
        self.assertEqual(len(notif_plugins), 1)
        self.assertEqual(notif_plugins[0], plugin2)

    async def test_dispatch_pr_event(self):
        """Test PR event dispatch to plugins."""
        # Create mock PR event plugin
        plugin = Mock(spec=PREventPlugin)
        plugin.is_enabled.return_value = True
        plugin.get_metadata.return_value = PluginMetadata(
            name="pr-handler",
            version="1.0.0",
            description="Test",
            capabilities={PluginCapability.PR_EVENT}
        )
        plugin.handle_pr_event = AsyncMock(return_value={'handled': True})

        self.manager._capability_registry[PluginCapability.PR_EVENT] = [plugin]

        # Dispatch event
        event = {'type': 'pull_request', 'action': 'opened'}
        results = await self.manager.dispatch_pr_event(event)

        plugin.handle_pr_event.assert_called_once_with(event)
        self.assertEqual(results['pr-handler'], {'handled': True})

    async def test_send_notification(self):
        """Test notification dispatch to plugins."""
        # Create mock notification plugin
        plugin = Mock(spec=NotificationPlugin)
        plugin.is_enabled.return_value = True
        plugin.get_metadata.return_value = PluginMetadata(
            name="notifier",
            version="1.0.0",
            description="Test",
            capabilities={PluginCapability.NOTIFICATION}
        )
        plugin.send_notification = AsyncMock(return_value=True)

        self.manager._capability_registry[PluginCapability.NOTIFICATION] = [plugin]

        # Send notification
        results = await self.manager.send_notification(
            "Test Title",
            "Test Message",
            urgency="high"
        )

        plugin.send_notification.assert_called_once()
        self.assertEqual(results['notifier'], True)

    def test_enable_disable_plugin(self):
        """Test plugin enable/disable through manager."""
        plugin = Mock()
        plugin.enable = Mock()
        plugin.disable = Mock()

        self.manager.loader._loaded_plugins['test'] = plugin

        # Enable plugin
        result = self.manager.enable_plugin('test')
        self.assertTrue(result)
        plugin.enable.assert_called_once()

        # Disable plugin
        result = self.manager.disable_plugin('test')
        self.assertTrue(result)
        plugin.disable.assert_called_once()

        # Non-existent plugin
        result = self.manager.enable_plugin('nonexistent')
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
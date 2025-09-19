"""
Integration tests for plugin system.

Tests complete plugin lifecycle and interaction.
"""

import unittest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock

from gh_pr.plugins.base import (
    Plugin, PluginMetadata, PluginContext, PluginCapability,
    PREventPlugin, NotificationPlugin, CommentFilterPlugin
)
from gh_pr.plugins.loader import PluginLoader
from gh_pr.plugins.manager import PluginManager


class TestPluginIntegration(unittest.TestCase):
    """Integration tests for plugin system."""

    def setUp(self):
        """Set up test environment."""
        # Create temporary plugin directory
        self.temp_dir = tempfile.mkdtemp()
        self.plugin_dir = Path(self.temp_dir) / 'plugins'
        self.plugin_dir.mkdir()

        # Create context
        self.context = PluginContext(
            config={
                'plugins': {
                    'test-pr-handler': {'enabled': True},
                    'test-notifier': {'enabled': True}
                }
            },
            github_client=Mock(),
            cache_manager=Mock()
        )

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir)

    def create_test_plugin(self, name: str, plugin_type: str) -> Path:
        """Create a test plugin file."""
        plugin_path = self.plugin_dir / f"{name}.py"

        if plugin_type == 'pr_event':
            plugin_code = f"""
from gh_pr.plugins.base import PREventPlugin, PluginMetadata, PluginCapability

class {name.title()}Plugin(PREventPlugin):
    def get_metadata(self):
        return PluginMetadata(
            name="{name}",
            version="1.0.0",
            description="Test PR event plugin",
            capabilities={{PluginCapability.PR_EVENT}}
        )

    async def initialize(self):
        return True

    async def shutdown(self):
        pass

    async def handle_pr_event(self, event):
        return {{'plugin': '{name}', 'handled': True, 'pr_id': event.get('pull_request', {{}}).get('id')}}
"""
        elif plugin_type == 'notification':
            plugin_code = f"""
from gh_pr.plugins.base import NotificationPlugin, PluginMetadata, PluginCapability

class {name.title()}Plugin(NotificationPlugin):
    def get_metadata(self):
        return PluginMetadata(
            name="{name}",
            version="1.0.0",
            description="Test notification plugin",
            capabilities={{PluginCapability.NOTIFICATION}}
        )

    async def initialize(self):
        return True

    async def shutdown(self):
        pass

    async def send_notification(self, title, message, **kwargs):
        print(f"[{name}] {{title}}: {{message}}")
        return True
"""
        elif plugin_type == 'filter':
            plugin_code = f"""
from gh_pr.plugins.base import CommentFilterPlugin, PluginMetadata, PluginCapability

class {name.title()}Plugin(CommentFilterPlugin):
    def get_metadata(self):
        return PluginMetadata(
            name="{name}",
            version="1.0.0",
            description="Test comment filter plugin",
            capabilities={{PluginCapability.COMMENT_FILTER}}
        )

    async def initialize(self):
        return True

    async def shutdown(self):
        pass

    async def filter_comments(self, comments, criteria):
        # Simple filter: keep only comments with 'important' in body
        return [c for c in comments if 'important' in c.get('body', '').lower()]
"""

        plugin_path.write_text(plugin_code)
        return plugin_path

    async def test_complete_plugin_lifecycle(self):
        """Test complete plugin lifecycle from loading to shutdown."""
        # Create test plugins
        self.create_test_plugin('pr_handler', 'pr_event')
        self.create_test_plugin('notifier', 'notification')
        self.create_test_plugin('filter', 'filter')

        # Create plugin manager
        manager = PluginManager(
            self.context,
            plugin_paths=[self.plugin_dir],
            auto_discover=True
        )

        # Initialize plugins
        init_results = await manager.initialize()
        self.assertTrue(all(init_results.values()))

        # Test PR event dispatch
        pr_event = {
            'type': 'pull_request',
            'action': 'opened',
            'pull_request': {'id': 123, 'title': 'Test PR'}
        }

        pr_results = await manager.dispatch_pr_event(pr_event)
        self.assertIn('ghpr_plugin_pr_handler', pr_results)
        self.assertEqual(pr_results['ghpr_plugin_pr_handler']['pr_id'], 123)

        # Test notification dispatch
        notif_results = await manager.send_notification(
            "Test Title",
            "Test Message"
        )
        self.assertIn('ghpr_plugin_notifier', notif_results)
        self.assertTrue(notif_results['ghpr_plugin_notifier'])

        # Test comment filtering
        comments = [
            {'id': 1, 'body': 'This is important'},
            {'id': 2, 'body': 'Regular comment'},
            {'id': 3, 'body': 'Another important note'}
        ]

        filtered = await manager.filter_comments(comments, {})
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0]['id'], 1)
        self.assertEqual(filtered[1]['id'], 3)

        # Shutdown plugins
        await manager.shutdown()

    async def test_plugin_dependency_validation(self):
        """Test plugin dependency validation."""
        # Create plugin with dependencies
        plugin_path = self.plugin_dir / 'dep_plugin.py'
        plugin_path.write_text("""
from gh_pr.plugins.base import Plugin, PluginMetadata

class DepPlugin(Plugin):
    def get_metadata(self):
        return PluginMetadata(
            name="dep-plugin",
            version="1.0.0",
            description="Plugin with dependencies",
            dependencies=["nonexistent_package>=1.0.0"]
        )

    async def initialize(self):
        return True

    async def shutdown(self):
        pass
""")

        loader = PluginLoader([self.plugin_dir], self.context)
        plugins = loader.load_all_plugins()

        # Initialize should fail due to missing dependency
        init_results = await loader.initialize_plugins()
        self.assertFalse(init_results.get('ghpr_plugin_dep_plugin', True))

    async def test_plugin_error_recovery(self):
        """Test plugin system error recovery."""
        # Create plugin that fails initialization
        plugin_path = self.plugin_dir / 'failing.py'
        plugin_path.write_text("""
from gh_pr.plugins.base import Plugin, PluginMetadata

class FailingPlugin(Plugin):
    def get_metadata(self):
        return PluginMetadata(
            name="failing",
            version="1.0.0",
            description="Plugin that fails"
        )

    async def initialize(self):
        raise Exception("Initialization failed")

    async def shutdown(self):
        pass
""")

        # Create working plugin
        self.create_test_plugin('working', 'notification')

        manager = PluginManager(
            self.context,
            plugin_paths=[self.plugin_dir],
            auto_discover=True
        )

        # Initialize - should partially succeed
        init_results = await manager.initialize()
        self.assertFalse(init_results.get('ghpr_plugin_failing', True))
        self.assertTrue(init_results.get('ghpr_plugin_working', False))

        # Working plugin should still function
        notif_results = await manager.send_notification("Test", "Message")
        self.assertIn('ghpr_plugin_working', notif_results)
        self.assertTrue(notif_results['ghpr_plugin_working'])

    async def test_plugin_health_monitoring(self):
        """Test plugin health check functionality."""
        # Create healthy and unhealthy plugins
        healthy_path = self.plugin_dir / 'healthy.py'
        healthy_path.write_text("""
from gh_pr.plugins.base import Plugin, PluginMetadata

class HealthyPlugin(Plugin):
    def get_metadata(self):
        return PluginMetadata(name="healthy", version="1.0.0", description="Healthy")

    async def initialize(self):
        return True

    async def shutdown(self):
        pass

    async def health_check(self):
        return {
            'name': 'healthy',
            'healthy': True,
            'enabled': True,
            'version': '1.0.0',
            'metrics': {'requests': 100, 'errors': 0}
        }
""")

        unhealthy_path = self.plugin_dir / 'unhealthy.py'
        unhealthy_path.write_text("""
from gh_pr.plugins.base import Plugin, PluginMetadata

class UnhealthyPlugin(Plugin):
    def get_metadata(self):
        return PluginMetadata(name="unhealthy", version="1.0.0", description="Unhealthy")

    async def initialize(self):
        return True

    async def shutdown(self):
        pass

    async def health_check(self):
        raise Exception("Health check failed")
""")

        manager = PluginManager(
            self.context,
            plugin_paths=[self.plugin_dir],
            auto_discover=True
        )

        await manager.initialize()

        # Get health status
        health = await manager.get_plugin_health()

        # Check healthy plugin
        self.assertIn('ghpr_plugin_healthy', health)
        self.assertTrue(health['ghpr_plugin_healthy']['healthy'])
        self.assertIn('metrics', health['ghpr_plugin_healthy'])

        # Check unhealthy plugin
        self.assertIn('ghpr_plugin_unhealthy', health)
        self.assertFalse(health['ghpr_plugin_unhealthy']['healthy'])
        self.assertIn('error', health['ghpr_plugin_unhealthy'])

    def test_plugin_info_retrieval(self):
        """Test plugin information retrieval."""
        # Create plugins with different capabilities
        self.create_test_plugin('multi_cap', 'pr_event')

        # Modify to add multiple capabilities
        plugin_path = self.plugin_dir / 'multi_cap.py'
        plugin_path.write_text("""
from gh_pr.plugins.base import Plugin, PluginMetadata, PluginCapability

class Multi_CapPlugin(Plugin):
    def get_metadata(self):
        return PluginMetadata(
            name="multi-cap",
            version="2.0.0",
            description="Multi-capability plugin",
            author="Test Author",
            capabilities={
                PluginCapability.PR_EVENT,
                PluginCapability.NOTIFICATION,
                PluginCapability.WEBHOOK_HANDLER
            }
        )

    async def initialize(self):
        return True

    async def shutdown(self):
        pass
""")

        manager = PluginManager(
            self.context,
            plugin_paths=[self.plugin_dir],
            auto_discover=True
        )

        # Get plugin info
        info = manager.get_plugin_info()

        # Find multi-cap plugin
        multi_cap_info = next(
            (p for p in info if p['name'] == 'multi-cap'),
            None
        )

        self.assertIsNotNone(multi_cap_info)
        self.assertEqual(multi_cap_info['version'], '2.0.0')
        self.assertEqual(multi_cap_info['author'], 'Test Author')
        self.assertIn('pr_event', multi_cap_info['capabilities'])
        self.assertIn('notification', multi_cap_info['capabilities'])
        self.assertIn('webhook_handler', multi_cap_info['capabilities'])


if __name__ == '__main__':
    unittest.main()
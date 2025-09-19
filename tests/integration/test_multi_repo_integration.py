"""
Integration tests for multi-repository and notification systems.

Tests complete workflows involving multiple repos and notifications.
"""

import unittest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from gh_pr.core.multi_repo import (
    RepoConfig, CrossRepoPR, MultiRepoManager
)
from gh_pr.utils.notifications import (
    NotificationManager, NotificationConfig
)


class TestMultiRepoIntegration(unittest.TestCase):
    """Integration tests for multi-repo operations."""

    def setUp(self):
        """Set up test environment."""
        # Mock GitHub client
        self.mock_github = Mock()
        self.mock_github._github = Mock()

        # Mock cache manager
        self.mock_cache = Mock()
        self.mock_cache.get.return_value = None  # No cache hits

        # Create multi-repo manager
        self.manager = MultiRepoManager(
            self.mock_github,
            self.mock_cache
        )

        # Add test repositories
        self.repo1 = RepoConfig(
            owner="org1",
            name="repo1",
            aliases=["r1"],
            pr_limit=10
        )
        self.repo2 = RepoConfig(
            owner="org2",
            name="repo2",
            aliases=["r2"],
            pr_limit=5
        )
        self.repo3 = RepoConfig(
            owner="org3",
            name="repo3",
            default_branch="master"
        )

        self.manager.add_repository(self.repo1)
        self.manager.add_repository(self.repo2)
        self.manager.add_repository(self.repo3)

    async def test_cross_repo_pr_discovery(self):
        """Test discovering PRs with cross-repository references."""
        # Mock PRs with cross-references
        pr1 = Mock()
        pr1.number = 100
        pr1.title = "Feature A"
        pr1.body = "Implements feature A. Fixes org2/repo2#200"
        pr1.user.login = "user1"
        pr1.state = "open"

        pr2 = Mock()
        pr2.number = 200
        pr2.title = "Bug fix"
        pr2.body = "Fixes bug mentioned in org1/repo1#100"
        pr2.user.login = "user2"
        pr2.state = "open"

        # Mock repository clients
        repo1_client = Mock()
        repo1_client.get_pulls.return_value = [pr1]
        repo2_client = Mock()
        repo2_client.get_pulls.return_value = [pr2]

        def mock_get_client(repo_config):
            if repo_config.full_name == "org1/repo1":
                return repo1_client
            elif repo_config.full_name == "org2/repo2":
                return repo2_client
            return Mock()

        self.manager._get_repo_client = mock_get_client

        # Get all PRs
        all_prs = await self.manager.get_all_prs()

        self.assertIn("org1/repo1", all_prs)
        self.assertIn("org2/repo2", all_prs)

        # Build PR graph from pr1
        repo1_client.get_pull.return_value = pr1
        repo2_client.get_pull.return_value = pr2

        graph = await self.manager.get_pr_graph(("org1/repo1", 100), max_depth=2)

        # Verify graph structure
        self.assertEqual(graph['root'], "org1/repo1#100")
        self.assertTrue(len(graph['nodes']) > 0)

        # Check if cross-reference was detected
        node = next((n for n in graph['nodes'] if n['id'] == "org1/repo1#100"), None)
        self.assertIsNotNone(node)
        self.assertEqual(node['title'], "Feature A")

    async def test_search_across_repositories(self):
        """Test searching PRs across multiple repositories."""
        # Mock search results
        mock_issue1 = Mock()
        mock_issue1.pull_request = True
        mock_issue1.repository.full_name = "org1/repo1"
        mock_issue1.as_pull_request.return_value = Mock(
            title="Search Result 1",
            body="Contains search term"
        )

        mock_issue2 = Mock()
        mock_issue2.pull_request = True
        mock_issue2.repository.full_name = "org2/repo2"
        mock_issue2.as_pull_request.return_value = Mock(
            title="Search Result 2",
            body="Also contains search term"
        )

        self.mock_github._github.search_issues.return_value = [
            mock_issue1, mock_issue2
        ]

        # Search across specific repos
        results = await self.manager.search_prs(
            "search term",
            repos=["r1", "r2"]  # Using aliases
        )

        self.assertEqual(len(results), 2)
        self.mock_github._github.search_issues.assert_called_once()

        # Verify search query includes repos
        call_kwargs = self.mock_github._github.search_issues.call_args[1]
        search_query = call_kwargs['query']
        self.assertIn("repo:org1/repo1", search_query)
        self.assertIn("repo:org2/repo2", search_query)

    async def test_label_sync_workflow(self):
        """Test syncing labels across repositories."""
        # Mock source repo labels
        label1 = Mock(name="bug", color="ff0000", description="Bug reports")
        label2 = Mock(name="enhancement", color="00ff00", description="New features")
        label3 = Mock(name="documentation", color="0000ff", description="Docs")

        source_client = Mock()
        source_client.get_labels.return_value = [label1, label2, label3]

        # Mock target repos
        target1_client = Mock()
        target2_client = Mock()

        # One label already exists in target1
        target1_client.create_label.side_effect = [
            None,  # bug created
            Exception("Label already exists"),  # enhancement exists
            None   # documentation created
        ]

        # All labels created successfully in target2
        target2_client.create_label.return_value = None

        def mock_get_client(repo_config):
            if repo_config.full_name == "org1/repo1":
                return source_client
            elif repo_config.full_name == "org2/repo2":
                return target1_client
            elif repo_config.full_name == "org3/repo3":
                return target2_client
            return Mock()

        self.manager._get_repo_client = mock_get_client

        # Sync labels from repo1 to others
        results = await self.manager.sync_labels("r1")  # Using alias

        # Check results
        self.assertIn("org2/repo2", results)
        self.assertIn("org3/repo3", results)

        # Target1 should have bug and documentation (enhancement existed)
        self.assertIn("bug", results["org2/repo2"])
        self.assertIn("documentation", results["org2/repo2"])

        # Target2 should have all three
        self.assertIn("bug", results["org3/repo3"])
        self.assertIn("enhancement", results["org3/repo3"])
        self.assertIn("documentation", results["org3/repo3"])


class TestNotificationIntegration(unittest.TestCase):
    """Integration tests for notification system."""

    def setUp(self):
        """Set up test environment."""
        self.config = NotificationConfig(
            enabled=True,
            timeout=3,
            fallback_to_terminal=True
        )

    @patch('sys.platform', 'darwin')
    @patch('subprocess.run')
    async def test_pr_notification_workflow(self, mock_run):
        """Test notification workflow for PR events."""
        mock_run.return_value = Mock(returncode=0)

        # Create notification manager
        manager = NotificationManager(self.config)
        manager._use_plyer = False
        manager._platform = 'darwin'

        # Simulate PR opened event
        result = await manager.notify(
            title="New PR: Feature Implementation",
            message="User opened PR #123: Add new authentication system",
            subtitle="Repository: org/repo"
        )

        self.assertTrue(result)
        mock_run.assert_called_once()

        # Verify notification content
        call_args = mock_run.call_args[0][0]
        script = call_args[2]
        self.assertIn("New PR", script)
        self.assertIn("#123", script)

    @patch('sys.platform', 'linux')
    @patch('subprocess.run')
    @patch('shutil.which')
    async def test_review_notification_workflow(self, mock_which, mock_run):
        """Test notification for PR review events."""
        mock_which.return_value = '/usr/bin/notify-send'
        mock_run.return_value = Mock(returncode=0)

        manager = NotificationManager(self.config)
        manager._use_plyer = False
        manager._platform = 'linux'
        manager._notifier = 'notify-send'

        # Simulate review requested
        result = await manager.notify(
            title="Review Requested",
            message="You were requested to review PR #456",
            urgency="high"
        )

        self.assertTrue(result)

        # Check high urgency was set
        call_args = mock_run.call_args[0][0]
        self.assertIn('--urgency=high', call_args)

    async def test_notification_with_multi_repo_events(self):
        """Test notifications for multi-repo events."""
        # Create mock multi-repo manager
        mock_github = Mock()
        mock_cache = Mock()
        repo_manager = MultiRepoManager(mock_github, mock_cache)

        # Create notification manager
        notif_manager = NotificationManager(NotificationConfig(enabled=True))

        # Mock terminal notification for testing
        with patch.object(notif_manager, '_notify_terminal') as mock_terminal:
            mock_terminal.return_value = True

            # Simulate cross-repo PR detection
            await notif_manager.notify(
                title="Cross-Repository PR Detected",
                message="PR #100 in org1/repo1 references PR #200 in org2/repo2"
            )

            mock_terminal.assert_called_once()
            args = mock_terminal.call_args[0]
            self.assertIn("Cross-Repository", args[0])
            self.assertIn("#100", args[1])
            self.assertIn("#200", args[1])

    @patch('builtins.print')
    async def test_fallback_notification_chain(self, mock_print):
        """Test notification fallback chain."""
        manager = NotificationManager(self.config)

        # Disable all native notifications
        manager._use_plyer = False
        manager._platform = 'unsupported_platform'

        # Should fall back to terminal
        result = await manager.notify(
            title="Fallback Test",
            message="This should appear in terminal"
        )

        self.assertTrue(result)
        mock_print.assert_called()

        # Verify content was printed
        printed_content = ' '.join(
            str(call[0][0]) for call in mock_print.call_args_list
        )
        self.assertIn("Fallback Test", printed_content)
        self.assertIn("terminal", printed_content.lower())


class TestCompleteWorkflow(unittest.TestCase):
    """Test complete Phase 5 workflow integration."""

    async def test_pr_event_to_notification_workflow(self):
        """Test complete workflow from PR event to notification."""
        from gh_pr.webhooks.events import WebhookEvent, EventType
        from gh_pr.webhooks.handler import WebhookHandler

        # Create components
        webhook_handler = WebhookHandler()
        notif_config = NotificationConfig(enabled=True, fallback_to_terminal=True)
        notif_manager = NotificationManager(notif_config)

        # Track workflow execution
        workflow_executed = False

        async def pr_handler(event):
            nonlocal workflow_executed
            workflow_executed = True

            # Process PR event
            pr_data = event.payload.get('pull_request', {})
            pr_number = pr_data.get('number', 'unknown')
            pr_title = pr_data.get('title', 'Untitled')

            # Send notification
            with patch.object(notif_manager, '_notify_terminal') as mock_terminal:
                mock_terminal.return_value = True

                await notif_manager.notify(
                    title=f"PR #{pr_number} {event.action}",
                    message=pr_title
                )

                mock_terminal.assert_called_once()

            return {'status': 'handled', 'notified': True}

        # Register handler
        webhook_handler.register_handler(EventType.PULL_REQUEST, pr_handler)

        # Create PR event
        pr_event = WebhookEvent(
            type=EventType.PULL_REQUEST,
            action='opened',
            payload={
                'pull_request': {
                    'number': 789,
                    'title': 'Add new feature',
                    'user': {'login': 'testuser'}
                }
            }
        )

        # Process event
        results = await webhook_handler.handle_event(pr_event)

        self.assertTrue(workflow_executed)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['status'], 'handled')
        self.assertTrue(results[0]['notified'])


if __name__ == '__main__':
    unittest.main()
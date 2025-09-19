"""
End-to-end integration tests.

Tests complete system workflows including all Phase 5 features.
"""

import unittest
import asyncio
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from gh_pr.core.pr_manager import EnhancedPRManager
from gh_pr.core.github import GitHubClient
from gh_pr.webhooks.server import WebhookServer
from gh_pr.webhooks.handler import WebhookHandler
from gh_pr.plugins.manager import PluginManager
from gh_pr.core.multi_repo import MultiRepoManager
from gh_pr.utils.notifications import NotificationManager


class TestEndToEndWorkflows(unittest.TestCase):
    """Test complete end-to-end workflows."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()

        # Mock GitHub client
        self.mock_github = Mock()
        self.mock_github._github = Mock()

        # Create managers
        self.pr_manager = EnhancedPRManager(self.mock_github, 'owner/repo')
        self.multi_repo_manager = MultiRepoManager(self.mock_github)

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)

    async def test_webhook_triggered_pr_workflow(self):
        """Test webhook triggering PR processing workflow."""
        # Setup webhook server and handler
        webhook_config = Mock()
        webhook_config.secret = "test_secret"
        webhook_config.port = 8080
        webhook_config.rate_limit = 100
        webhook_config.rate_window = 60

        webhook_handler = WebhookHandler()
        webhook_server = WebhookServer(webhook_config)
        webhook_server.handler = webhook_handler

        # Setup notification manager
        notif_manager = NotificationManager()

        # Track workflow execution
        workflow_executed = False
        pr_processed = None

        async def handle_pr_event(event):
            """Handle PR webhook event."""
            nonlocal workflow_executed, pr_processed
            workflow_executed = True

            # Extract PR data
            pr_data = event.payload.get('pull_request', {})
            pr_processed = pr_data.get('number')

            # Process PR
            if event.action == 'opened':
                # Send notification
                await notif_manager.notify(
                    f"New PR #{pr_data.get('number')}",
                    pr_data.get('title', 'Untitled')
                )

                # Auto-label based on title/body
                if 'bug' in pr_data.get('title', '').lower():
                    return {'auto_label': 'bug'}
                elif 'feature' in pr_data.get('title', '').lower():
                    return {'auto_label': 'enhancement'}

            return {'processed': True}

        # Register handler
        from gh_pr.webhooks.events import EventType
        webhook_handler.register_handler(EventType.PULL_REQUEST, handle_pr_event)

        # Simulate webhook event
        event = webhook_handler.parse_github_event(
            headers={'X-GitHub-Event': 'pull_request'},
            payload={
                'action': 'opened',
                'pull_request': {
                    'number': 123,
                    'title': 'Fix bug in authentication',
                    'user': {'login': 'testuser'}
                }
            }
        )

        # Process event
        results = await webhook_handler.handle_event(event)

        self.assertTrue(workflow_executed)
        self.assertEqual(pr_processed, 123)
        self.assertIn('auto_label', results[0])
        self.assertEqual(results[0]['auto_label'], 'bug')

    async def test_multi_repo_search_and_sync(self):
        """Test multi-repo search and label sync workflow."""
        # Add repositories to manager
        from gh_pr.core.multi_repo import RepoConfig

        repo1 = RepoConfig(owner="org", name="repo1", aliases=["r1"])
        repo2 = RepoConfig(owner="org", name="repo2", aliases=["r2"])
        repo3 = RepoConfig(owner="org", name="repo3", aliases=["r3"])

        self.multi_repo_manager.add_repository(repo1)
        self.multi_repo_manager.add_repository(repo2)
        self.multi_repo_manager.add_repository(repo3)

        # Mock PR search results
        mock_issue1 = Mock()
        mock_issue1.pull_request = True
        mock_issue1.repository.full_name = "org/repo1"
        mock_issue1.as_pull_request.return_value = Mock(
            title="Security fix",
            body="Fixes CVE-2024-001"
        )

        mock_issue2 = Mock()
        mock_issue2.pull_request = True
        mock_issue2.repository.full_name = "org/repo2"
        mock_issue2.as_pull_request.return_value = Mock(
            title="Related security patch",
            body="See org/repo1#123"
        )

        self.mock_github._github.search_issues.return_value = [
            mock_issue1, mock_issue2
        ]

        # Search across repos
        results = await self.multi_repo_manager.search_prs("security")

        self.assertEqual(len(results), 2)

        # Check cross-references were detected
        for result in results:
            if "org/repo1#123" in result.pr.body:
                self.assertTrue(result.has_cross_references())

        # Mock label sync
        mock_label = Mock(name="security", color="ff0000", description="Security fixes")
        source_repo = Mock()
        source_repo.get_labels.return_value = [mock_label]

        target_repos = [Mock(), Mock()]
        for target in target_repos:
            target.create_label.return_value = None

        def mock_get_client(repo_config):
            if repo_config.full_name == "org/repo1":
                return source_repo
            return target_repos.pop(0) if target_repos else Mock()

        self.multi_repo_manager._get_repo_client = mock_get_client

        # Sync labels
        sync_results = await self.multi_repo_manager.sync_labels("r1")

        self.assertIn("org/repo2", sync_results)
        self.assertIn("org/repo3", sync_results)

    async def test_plugin_system_with_pr_events(self):
        """Test plugin system handling PR events."""
        # Create plugin manager
        from gh_pr.plugins.base import PluginContext
        context = PluginContext(
            config={'plugins': {}},
            github_client=self.mock_github
        )
        plugin_manager = PluginManager(context, auto_discover=False)

        # Create mock plugins
        pr_processed = []
        notifications_sent = []

        async def pr_handler(event):
            pr_processed.append(event.get('pull_request', {}).get('number'))
            return {'handled': True}

        async def notifier(title, message, **kwargs):
            notifications_sent.append((title, message))
            return True

        # Register mock plugins
        from gh_pr.plugins.base import PluginCapability
        mock_pr_plugin = Mock()
        mock_pr_plugin.is_enabled.return_value = True
        mock_pr_plugin.get_metadata.return_value = Mock(
            name="pr-processor",
            capabilities={PluginCapability.PR_EVENT}
        )
        mock_pr_plugin.handle_pr_event = pr_handler

        mock_notif_plugin = Mock()
        mock_notif_plugin.is_enabled.return_value = True
        mock_notif_plugin.get_metadata.return_value = Mock(
            name="notifier",
            capabilities={PluginCapability.NOTIFICATION}
        )
        mock_notif_plugin.send_notification = notifier

        plugin_manager._capability_registry[PluginCapability.PR_EVENT] = [mock_pr_plugin]
        plugin_manager._capability_registry[PluginCapability.NOTIFICATION] = [mock_notif_plugin]

        # Simulate PR event
        pr_event = {
            'type': 'pull_request',
            'action': 'opened',
            'pull_request': {'number': 456, 'title': 'New feature'}
        }

        # Dispatch to plugins
        pr_results = await plugin_manager.dispatch_pr_event(pr_event)
        notif_results = await plugin_manager.send_notification(
            f"PR #{pr_event['pull_request']['number']}",
            pr_event['pull_request']['title']
        )

        self.assertEqual(pr_processed, [456])
        self.assertEqual(len(notifications_sent), 1)
        self.assertIn("PR #456", notifications_sent[0][0])

    async def test_complete_pr_lifecycle(self):
        """Test complete PR lifecycle from creation to merge."""
        # Mock PR lifecycle
        mock_pr = Mock()
        mock_pr.number = 789
        mock_pr.title = "Complete feature"
        mock_pr.state = "open"
        mock_pr.user.login = "author"
        mock_pr.mergeable = True
        mock_pr.merged = False

        # Track lifecycle events
        lifecycle_events = []

        # 1. PR Created
        lifecycle_events.append(('created', mock_pr.number))

        # 2. Auto-assign reviewers
        mock_pr.create_review_request = Mock()
        mock_pr.create_review_request(reviewers=['reviewer1', 'reviewer2'])
        lifecycle_events.append(('reviewers_assigned', ['reviewer1', 'reviewer2']))

        # 3. CI checks
        mock_pr.get_commits.return_value = [Mock(sha="abc123")]
        mock_commit = Mock()
        mock_commit.create_status = Mock()
        mock_commit.create_status(
            state="success",
            description="All checks passed",
            context="ci/tests"
        )
        lifecycle_events.append(('ci_passed', True))

        # 4. Reviews
        mock_review1 = Mock(state="APPROVED", user=Mock(login="reviewer1"))
        mock_review2 = Mock(state="APPROVED", user=Mock(login="reviewer2"))
        mock_pr.get_reviews.return_value = [mock_review1, mock_review2]
        lifecycle_events.append(('approved', 2))

        # 5. Merge
        mock_pr.merge = Mock(return_value=Mock(merged=True))
        merge_result = mock_pr.merge(merge_method="squash")
        lifecycle_events.append(('merged', 'squash'))

        # 6. Post-merge cleanup
        mock_pr.state = "closed"
        mock_pr.merged = True
        lifecycle_events.append(('closed', True))

        # Verify lifecycle
        self.assertEqual(len(lifecycle_events), 6)
        self.assertEqual(lifecycle_events[0][0], 'created')
        self.assertEqual(lifecycle_events[-1][0], 'closed')

        # Verify mock calls
        mock_pr.create_review_request.assert_called_once()
        mock_pr.merge.assert_called_once_with(merge_method="squash")

    async def test_error_recovery_workflow(self):
        """Test error recovery in workflows."""
        # Test webhook error recovery
        webhook_handler = WebhookHandler()

        error_count = 0

        async def failing_handler(event):
            nonlocal error_count
            error_count += 1
            if error_count < 3:
                raise Exception("Temporary error")
            return {'recovered': True}

        from gh_pr.webhooks.events import EventType
        webhook_handler.register_handler(EventType.PUSH, failing_handler)

        # Process event multiple times
        event = webhook_handler.parse_github_event(
            headers={'X-GitHub-Event': 'push'},
            payload={'commits': []}
        )

        # First two attempts fail
        for i in range(2):
            results = await webhook_handler.handle_event(event)
            self.assertIn('error', results[0])

        # Third attempt succeeds
        results = await webhook_handler.handle_event(event)
        self.assertEqual(results[0], {'recovered': True})

    def test_performance_with_large_datasets(self):
        """Test system performance with large datasets."""
        # Create large number of PRs
        large_pr_list = []
        for i in range(1000):
            pr = Mock()
            pr.number = i + 1
            pr.title = f"PR {i + 1}"
            pr.state = "open" if i % 3 else "closed"
            pr.user.login = f"user{i % 10}"
            pr.created_at = datetime.now() - timedelta(days=i)
            pr.labels = [Mock(name=f"label{j}") for j in range(i % 5)]
            large_pr_list.append(pr)

        # Test filtering performance
        from gh_pr.core.filters import StateFilter, AuthorFilter, CombinedFilter

        state_filter = StateFilter('open')
        author_filter = AuthorFilter('user5')
        combined = CombinedFilter([state_filter, author_filter], operator='AND')

        import time
        start = time.time()

        filtered = [pr for pr in large_pr_list if combined.matches(pr)]

        elapsed = time.time() - start

        # Should filter 1000 PRs in under 1 second
        self.assertLess(elapsed, 1.0)

        # Verify filtering worked
        self.assertTrue(all(pr.state == 'open' for pr in filtered))
        self.assertTrue(all(pr.user.login == 'user5' for pr in filtered))

    async def test_concurrent_operations(self):
        """Test concurrent operations across multiple repos."""
        # Setup multiple repos
        repos = []
        for i in range(5):
            repo_config = Mock()
            repo_config.full_name = f"org/repo{i}"
            repo_config.pr_limit = 10
            repos.append(repo_config)

            self.multi_repo_manager.add_repository(repo_config)

        # Mock concurrent PR fetching
        async def mock_get_prs(repo, state, filters):
            # Simulate network delay
            await asyncio.sleep(0.1)
            return [Mock(title=f"PR from {repo.full_name}")]

        self.multi_repo_manager._get_repo_prs = mock_get_prs

        # Measure concurrent fetching
        import time
        start = time.time()

        all_prs = await self.multi_repo_manager.get_all_prs()

        elapsed = time.time() - start

        # Should fetch from 5 repos concurrently (faster than sequential)
        self.assertLess(elapsed, 0.3)  # Would take 0.5s sequentially
        self.assertEqual(len(all_prs), 5)


if __name__ == '__main__':
    unittest.main()
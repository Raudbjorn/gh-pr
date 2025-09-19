"""
Integration tests for CLI interface.

Tests complete CLI workflows and command interactions.
"""

import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner

from gh_pr.cli import cli, list_prs, show_pr, review_pr, comment_on_pr


class TestCLIIntegration(unittest.TestCase):
    """Integration tests for CLI commands."""

    def setUp(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()

        # Mock GitHub client
        self.mock_github = Mock()
        self.mock_repo = Mock()
        self.mock_github.get_repo.return_value = self.mock_repo

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)

    @patch('gh_pr.cli.GitHubClient')
    def test_list_command(self, mock_client_class):
        """Test list command."""
        # Setup mocks
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_pr1 = Mock()
        mock_pr1.number = 1
        mock_pr1.title = "First PR"
        mock_pr1.state = "open"
        mock_pr1.user.login = "user1"

        mock_pr2 = Mock()
        mock_pr2.number = 2
        mock_pr2.title = "Second PR"
        mock_pr2.state = "open"
        mock_pr2.user.login = "user2"

        mock_repo.get_pulls.return_value = [mock_pr1, mock_pr2]
        mock_client.get_repo.return_value = mock_repo

        # Run command
        result = self.runner.invoke(cli, ['list', 'owner/repo'])

        self.assertEqual(result.exit_code, 0)
        self.assertIn('#1', result.output)
        self.assertIn('First PR', result.output)
        self.assertIn('#2', result.output)

    @patch('gh_pr.cli.GitHubClient')
    def test_list_with_filters(self, mock_client_class):
        """Test list command with filters."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_pr = Mock()
        mock_pr.number = 1
        mock_pr.title = "Filtered PR"
        mock_pr.state = "open"
        mock_pr.user.login = "alice"
        mock_pr.labels = [Mock(name="bug")]

        mock_repo.get_pulls.return_value = [mock_pr]
        mock_client.get_repo.return_value = mock_repo

        # Test with state filter
        result = self.runner.invoke(cli, [
            'list', 'owner/repo',
            '--state', 'open'
        ])

        self.assertEqual(result.exit_code, 0)
        self.assertIn('Filtered PR', result.output)

        # Test with author filter
        result = self.runner.invoke(cli, [
            'list', 'owner/repo',
            '--author', 'alice'
        ])

        self.assertEqual(result.exit_code, 0)

        # Test with label filter
        result = self.runner.invoke(cli, [
            'list', 'owner/repo',
            '--label', 'bug'
        ])

        self.assertEqual(result.exit_code, 0)

    @patch('gh_pr.cli.GitHubClient')
    def test_show_command(self, mock_client_class):
        """Test show command."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.title = "Test PR"
        mock_pr.body = "This is a test PR"
        mock_pr.state = "open"
        mock_pr.user.login = "testuser"
        mock_pr.created_at = "2024-01-01T00:00:00Z"
        mock_pr.labels = []
        mock_pr.assignees = []
        mock_pr.requested_reviewers = []
        mock_pr.milestone = None
        mock_pr.get_reviews.return_value = []
        mock_pr.get_commits.return_value = []

        mock_repo.get_pull.return_value = mock_pr
        mock_client.get_repo.return_value = mock_repo

        result = self.runner.invoke(cli, ['show', 'owner/repo', '123'])

        self.assertEqual(result.exit_code, 0)
        self.assertIn('#123', result.output)
        self.assertIn('Test PR', result.output)
        self.assertIn('test PR', result.output)

    @patch('gh_pr.cli.GitHubClient')
    def test_review_command(self, mock_client_class):
        """Test review command."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_pr = Mock()
        mock_pr.number = 456
        mock_pr.create_review = Mock(return_value=Mock(id=1))

        mock_repo.get_pull.return_value = mock_pr
        mock_client.get_repo.return_value = mock_repo

        # Approve PR
        result = self.runner.invoke(cli, [
            'review', 'owner/repo', '456',
            '--approve',
            '--comment', 'LGTM!'
        ])

        self.assertEqual(result.exit_code, 0)
        mock_pr.create_review.assert_called_once()

        # Check review was created with approval
        call_args = mock_pr.create_review.call_args[1]
        self.assertEqual(call_args['event'], 'APPROVE')
        self.assertEqual(call_args['body'], 'LGTM!')

    @patch('gh_pr.cli.GitHubClient')
    def test_comment_command(self, mock_client_class):
        """Test comment command."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_pr = Mock()
        mock_pr.number = 789
        mock_comment = Mock(id=1, body="Test comment")
        mock_pr.create_issue_comment.return_value = mock_comment

        mock_repo.get_pull.return_value = mock_pr
        mock_client.get_repo.return_value = mock_repo

        result = self.runner.invoke(cli, [
            'comment', 'owner/repo', '789',
            '--body', 'Test comment'
        ])

        self.assertEqual(result.exit_code, 0)
        mock_pr.create_issue_comment.assert_called_once_with('Test comment')

    @patch('gh_pr.cli.GitHubClient')
    @patch('gh_pr.cli.click.edit')
    def test_comment_with_editor(self, mock_edit, mock_client_class):
        """Test comment command with editor."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_pr = Mock()
        mock_pr.number = 999
        mock_pr.create_issue_comment.return_value = Mock(id=2)

        mock_repo.get_pull.return_value = mock_pr
        mock_client.get_repo.return_value = mock_repo

        # Simulate editor input
        mock_edit.return_value = "Comment from editor"

        result = self.runner.invoke(cli, [
            'comment', 'owner/repo', '999',
            '--edit'
        ])

        self.assertEqual(result.exit_code, 0)
        mock_pr.create_issue_comment.assert_called_once_with("Comment from editor")

    @patch('gh_pr.cli.GitHubClient')
    def test_export_command(self, mock_client_class):
        """Test export command."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_pr = Mock()
        mock_pr.number = 1
        mock_pr.title = "Export test"
        mock_pr.state = "open"
        mock_pr.user.login = "user1"
        mock_pr.created_at = "2024-01-01T00:00:00Z"
        mock_pr.html_url = "https://github.com/owner/repo/pull/1"
        mock_pr.body = "Test body"
        mock_pr.labels = []

        mock_repo.get_pulls.return_value = [mock_pr]
        mock_client.get_repo.return_value = mock_repo

        # Test JSON export
        output_path = Path(self.temp_dir) / 'export.json'
        result = self.runner.invoke(cli, [
            'list', 'owner/repo',
            '--export', str(output_path)
        ])

        self.assertEqual(result.exit_code, 0)
        self.assertTrue(output_path.exists())

        with open(output_path) as f:
            data = json.load(f)

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['number'], 1)

    @patch('gh_pr.cli.GitHubClient')
    def test_batch_operations(self, mock_client_class):
        """Test batch operations on multiple PRs."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Create multiple PRs
        prs = []
        for i in range(3):
            pr = Mock()
            pr.number = i + 1
            pr.add_to_labels = Mock()
            pr.remove_from_labels = Mock()
            prs.append(pr)

        def get_pull(number):
            return prs[number - 1]

        mock_repo.get_pull = get_pull
        mock_client.get_repo.return_value = mock_repo

        # Test batch label addition
        result = self.runner.invoke(cli, [
            'batch', 'owner/repo',
            '--pr-numbers', '1,2,3',
            '--add-label', 'ready-for-review'
        ])

        self.assertEqual(result.exit_code, 0)
        for pr in prs:
            pr.add_to_labels.assert_called()

    @patch('gh_pr.cli.GitHubClient')
    def test_webhook_setup(self, mock_client_class):
        """Test webhook setup command."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_repo.create_hook.return_value = Mock(id=1)
        mock_client.get_repo.return_value = mock_repo

        result = self.runner.invoke(cli, [
            'webhook', 'setup', 'owner/repo',
            '--url', 'https://example.com/webhook',
            '--secret', 'webhook_secret'
        ])

        self.assertEqual(result.exit_code, 0)
        mock_repo.create_hook.assert_called_once()

    def test_config_command(self):
        """Test config command."""
        config_path = Path(self.temp_dir) / 'config.json'

        # Set config value
        result = self.runner.invoke(cli, [
            'config', 'set',
            'github.token', 'test_token',
            '--config', str(config_path)
        ])

        self.assertEqual(result.exit_code, 0)
        self.assertTrue(config_path.exists())

        # Get config value
        result = self.runner.invoke(cli, [
            'config', 'get',
            'github.token',
            '--config', str(config_path)
        ])

        self.assertEqual(result.exit_code, 0)
        self.assertIn('test_token', result.output)

        # List all config
        result = self.runner.invoke(cli, [
            'config', 'list',
            '--config', str(config_path)
        ])

        self.assertEqual(result.exit_code, 0)
        self.assertIn('github.token', result.output)

    def test_version_command(self):
        """Test version command."""
        result = self.runner.invoke(cli, ['version'])

        self.assertEqual(result.exit_code, 0)
        self.assertIn('gh-pr', result.output.lower())

    def test_help_command(self):
        """Test help command."""
        result = self.runner.invoke(cli, ['--help'])

        self.assertEqual(result.exit_code, 0)
        self.assertIn('Usage:', result.output)
        self.assertIn('Commands:', result.output)

    @patch('gh_pr.cli.GitHubClient')
    def test_error_handling(self, mock_client_class):
        """Test error handling in CLI."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Simulate GitHub API error
        mock_client.get_repo.side_effect = Exception("API Error")

        result = self.runner.invoke(cli, ['list', 'owner/repo'])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('Error', result.output)

    @patch('gh_pr.cli.GitHubClient')
    def test_pagination(self, mock_client_class):
        """Test pagination in list command."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Create many PRs
        prs = []
        for i in range(50):
            pr = Mock()
            pr.number = i + 1
            pr.title = f"PR {i + 1}"
            pr.state = "open"
            pr.user.login = "user"
            prs.append(pr)

        mock_repo.get_pulls.return_value = prs
        mock_client.get_repo.return_value = mock_repo

        # Test with limit
        result = self.runner.invoke(cli, [
            'list', 'owner/repo',
            '--limit', '10'
        ])

        self.assertEqual(result.exit_code, 0)
        # Should only show 10 PRs
        pr_count = result.output.count('#')
        self.assertLessEqual(pr_count, 10)


class TestCompleteWorkflow(unittest.TestCase):
    """Test complete CLI workflows."""

    def setUp(self):
        """Set up test environment."""
        self.runner = CliRunner()

    @patch('gh_pr.cli.GitHubClient')
    def test_pr_review_workflow(self, mock_client_class):
        """Test complete PR review workflow."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Setup PR
        mock_pr = Mock()
        mock_pr.number = 100
        mock_pr.title = "Feature PR"
        mock_pr.body = "Implements new feature"
        mock_pr.diff_url = "https://github.com/owner/repo/pull/100.diff"
        mock_pr.get_reviews.return_value = []
        mock_pr.get_commits.return_value = [Mock(sha="abc123")]
        mock_pr.create_review = Mock(return_value=Mock(id=1))
        mock_pr.create_issue_comment = Mock(return_value=Mock(id=2))

        mock_repo = Mock()
        mock_repo.get_pull.return_value = mock_pr
        mock_client.get_repo.return_value = mock_repo

        # 1. View PR details
        result = self.runner.invoke(cli, ['show', 'owner/repo', '100'])
        self.assertEqual(result.exit_code, 0)

        # 2. Add comment
        result = self.runner.invoke(cli, [
            'comment', 'owner/repo', '100',
            '--body', 'Starting review'
        ])
        self.assertEqual(result.exit_code, 0)

        # 3. Approve PR
        result = self.runner.invoke(cli, [
            'review', 'owner/repo', '100',
            '--approve',
            '--comment', 'LGTM, great work!'
        ])
        self.assertEqual(result.exit_code, 0)

        # Verify workflow
        mock_pr.create_issue_comment.assert_called_with('Starting review')
        mock_pr.create_review.assert_called()


if __name__ == '__main__':
    unittest.main()
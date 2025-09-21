"""
Unit tests for auth.token module.

Tests token management functionality with focus on security and error handling.
"""

import os
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime, timezone, timedelta

from github import GithubException
from github.Auth import Token as GithubToken

from gh_pr.auth.token import TokenManager


class TestTokenManager(unittest.TestCase):
    """Test TokenManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Clear environment variables
        self.env_patcher = patch.dict(os.environ, {}, clear=True)
        self.env_patcher.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.env_patcher.stop()

    def test_init_with_token_parameter(self):
        """Test initialization with explicit token parameter."""
        token = "ghp_test_token_123"
        manager = TokenManager(token=token)
        self.assertEqual(manager.token, token)

    @patch.dict(os.environ, {'GH_TOKEN': 'env_token_gh'})
    def test_get_token_from_gh_token_env(self):
        """Test getting token from GH_TOKEN environment variable."""
        manager = TokenManager()
        self.assertEqual(manager.token, 'env_token_gh')

    @patch.dict(os.environ, {'GITHUB_TOKEN': 'env_token_github'})
    def test_get_token_from_github_token_env(self):
        """Test getting token from GITHUB_TOKEN environment variable."""
        manager = TokenManager()
        self.assertEqual(manager.token, 'env_token_github')

    @patch.dict(os.environ, {'GH_TOKEN': 'gh_token', 'GITHUB_TOKEN': 'github_token'})
    def test_token_precedence_gh_token_first(self):
        """Test that GH_TOKEN takes precedence over GITHUB_TOKEN."""
        manager = TokenManager()
        self.assertEqual(manager.token, 'gh_token')

    @patch('gh_pr.auth.token.subprocess.run')
    def test_get_token_from_gh_cli_auth_status(self, mock_run):
        """Test getting token from gh CLI auth status command."""
        # Mock successful gh auth status command
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "✓ github.com\n  ✓ Git operations\n  ✓ Token: ghp_cli_token_456\n"
        mock_run.return_value = mock_result

        manager = TokenManager()
        self.assertEqual(manager.token, 'ghp_cli_token_456')

    @patch('gh_pr.auth.token.subprocess.run')
    def test_get_token_from_gh_cli_auth_token(self, mock_run):
        """Test getting token from gh CLI auth token command."""
        # Mock auth status failing, auth token succeeding
        mock_result_status = Mock()
        mock_result_status.returncode = 1
        mock_result_status.stdout = ""

        mock_result_token = Mock()
        mock_result_token.returncode = 0
        mock_result_token.stdout = "ghp_cli_token_789\n"

        mock_run.side_effect = [mock_result_status, mock_result_token]

        manager = TokenManager()
        self.assertEqual(manager.token, 'ghp_cli_token_789')

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_timeout_handling(self, mock_run):
        """Test handling of subprocess timeout for gh CLI commands."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            ['gh', 'auth', 'status'], timeout=5
        )

        with self.assertRaises(ValueError) as context:
            TokenManager()

        self.assertIn("No GitHub token found", str(context.exception))

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_file_not_found(self, mock_run):
        """Test handling when gh CLI is not installed."""
        mock_run.side_effect = FileNotFoundError("gh command not found")

        with self.assertRaises(ValueError) as context:
            TokenManager()

        self.assertIn("No GitHub token found", str(context.exception))

    def test_no_token_found_raises_error(self):
        """Test that ValueError is raised when no token is found."""
        with self.assertRaises(ValueError) as context:
            TokenManager()

        self.assertIn("No GitHub token found", str(context.exception))

    def test_get_token_method(self):
        """Test the get_token method."""
        token = "ghp_test_token"
        manager = TokenManager(token=token)
        self.assertEqual(manager.get_token(), token)

    @patch('gh_pr.auth.token.Github')
    def test_get_github_client(self, mock_github_class):
        """Test getting GitHub client instance."""
        token = "ghp_test_token"
        manager = TokenManager(token=token)

        # Mock Github instance
        mock_github = Mock()
        mock_github_class.return_value = mock_github

        client = manager.get_github_client()

        # Should cache the client
        self.assertEqual(client, mock_github)
        self.assertEqual(manager.get_github_client(), mock_github)

        # Should be called with GithubToken auth
        mock_github_class.assert_called_once()
        call_args = mock_github_class.call_args
        self.assertIsInstance(call_args[1]['auth'], GithubToken)

    @patch('gh_pr.auth.token.Github')
    def test_validate_token_success(self, mock_github_class):
        """Test successful token validation."""
        token = "ghp_valid_token"
        manager = TokenManager(token=token)

        # Mock successful API call
        mock_github = Mock()
        mock_user = Mock()
        mock_user.login = "testuser"
        mock_github.get_user.return_value = mock_user
        mock_github_class.return_value = mock_github

        result = manager.validate_token()
        self.assertTrue(result)

    @patch('gh_pr.auth.token.Github')
    def test_validate_token_failure(self, mock_github_class):
        """Test token validation failure."""
        token = "ghp_invalid_token"
        manager = TokenManager(token=token)

        # Mock failed API call
        mock_github = Mock()
        mock_github.get_user.side_effect = GithubException(401, "Bad credentials")
        mock_github_class.return_value = mock_github

        result = manager.validate_token()
        self.assertFalse(result)

    @patch('gh_pr.auth.token.Github')
    def test_get_token_info_classic_pat(self, mock_github_class):
        """Test getting token info for classic personal access token."""
        token = "ghp_classic_token_123"
        manager = TokenManager(token=token)

        # Mock GitHub client and rate limit
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4500
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        info = manager.get_token_info()

        self.assertIsNotNone(info)
        self.assertEqual(info["type"], "Classic Personal Access Token")
        self.assertEqual(info["rate_limit"]["limit"], 5000)
        self.assertEqual(info["rate_limit"]["remaining"], 4500)

    @patch('gh_pr.auth.token.Github')
    def test_get_token_info_fine_grained_pat(self, mock_github_class):
        """Test getting token info for fine-grained personal access token."""
        token = "github_pat_fine_grained_123"
        manager = TokenManager(token=token)

        # Mock GitHub client
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 1000
        mock_rate_limit.core.remaining = 800
        mock_rate_limit.core.reset = None
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        info = manager.get_token_info()

        self.assertIsNotNone(info)
        self.assertEqual(info["type"], "Fine-grained Personal Access Token")
        self.assertEqual(info["rate_limit"]["limit"], 1000)

    @patch('gh_pr.auth.token.Github')
    def test_get_token_info_app_installation(self, mock_github_class):
        """Test getting token info for GitHub App installation token."""
        token = "ghs_app_installation_123"
        manager = TokenManager(token=token)

        # Mock GitHub client
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 5000
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        info = manager.get_token_info()

        self.assertIsNotNone(info)
        self.assertEqual(info["type"], "GitHub App Installation Token")

    @patch('gh_pr.auth.token.Github')
    def test_get_token_info_unknown_type(self, mock_github_class):
        """Test getting token info for unknown token type."""
        token = "unknown_token_format"
        manager = TokenManager(token=token)

        # Mock GitHub client
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 60
        mock_rate_limit.core.remaining = 60
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        info = manager.get_token_info()

        self.assertIsNotNone(info)
        self.assertEqual(info["type"], "Unknown")

    @patch('gh_pr.auth.token.Github')
    def test_get_token_info_api_failure(self, mock_github_class):
        """Test token info when API call fails."""
        token = "ghp_failing_token"
        manager = TokenManager(token=token)

        # Mock failed API call
        mock_github = Mock()
        mock_github.get_rate_limit.side_effect = GithubException(401, "Bad credentials")
        mock_github_class.return_value = mock_github

        info = manager.get_token_info()
        self.assertIsNone(info)

    @patch('gh_pr.auth.token.Github')
    def test_get_token_info_caching(self, mock_github_class):
        """Test that token info is cached."""
        token = "ghp_cached_token"
        manager = TokenManager(token=token)

        # Mock GitHub client
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        # First call
        info1 = manager.get_token_info()
        # Second call should return cached value
        info2 = manager.get_token_info()

        self.assertEqual(info1, info2)
        # API should only be called once
        mock_github.get_rate_limit.assert_called_once()

    def test_has_permissions_no_token_info(self):
        """Test has_permissions when token info is unavailable."""
        token = "ghp_invalid_token"
        manager = TokenManager(token=token)
        manager._token_info = None

        with patch.object(manager, 'get_token_info', return_value=None):
            result = manager.has_permissions(["repo"])
            self.assertFalse(result)

    def test_has_permissions_classic_token_with_scopes(self):
        """Test has_permissions for classic token with scope info."""
        token = "ghp_classic_token"
        manager = TokenManager(token=token)

        # Mock token info with scopes
        mock_info = {
            "type": "Classic Personal Access Token",
            "scopes": ["repo", "read:org"]
        }

        with patch.object(manager, 'get_token_info', return_value=mock_info):
            self.assertTrue(manager.has_permissions(["repo"]))
            self.assertTrue(manager.has_permissions(["read:org"]))
            self.assertFalse(manager.has_permissions(["admin:org"]))
            self.assertTrue(manager.has_permissions(["repo", "read:org"]))
            self.assertFalse(manager.has_permissions(["repo", "admin:org"]))

    @patch('gh_pr.auth.token.Github')
    def test_check_fine_grained_permissions_success(self, mock_github_class):
        """Test checking fine-grained token permissions successfully."""
        token = "github_pat_fine_grained"
        manager = TokenManager(token=token)

        # Mock GitHub client and API responses
        mock_github = Mock()
        mock_user = Mock()

        # Mock repos
        mock_repo = Mock()
        mock_repos = Mock()
        mock_repos.totalCount = 1
        mock_repos.__getitem__ = Mock(return_value=mock_repo)
        mock_user.get_repos.return_value = mock_repos
        mock_repo.get_pulls.return_value = [Mock()]
        mock_repo.get_issues.return_value = [Mock()]
        mock_repo.get_discussions.return_value = [Mock()]
        mock_user.get_orgs.return_value = [Mock()]

        mock_github.get_user.return_value = mock_user
        mock_github_class.return_value = mock_github

        result = manager._check_fine_grained_permissions(["repo"])
        self.assertTrue(result)

    @patch('gh_pr.auth.token.Github')
    def test_check_fine_grained_permissions_failure(self, mock_github_class):
        """Test checking fine-grained token permissions failure."""
        token = "github_pat_fine_grained"
        manager = TokenManager(token=token)

        # Mock GitHub client with failing API calls
        mock_github = Mock()
        mock_user = Mock()
        mock_user.get_repos.side_effect = GithubException(403, "Forbidden")
        mock_github.get_user.return_value = mock_user
        mock_github_class.return_value = mock_github

        result = manager._check_fine_grained_permissions(["repo"])
        self.assertFalse(result)

    def test_check_expiration_no_expiration_info(self):
        """Test check_expiration when no expiration info is available."""
        token = "ghp_token_no_expiry"
        manager = TokenManager(token=token)

        mock_info = {
            "type": "Classic Personal Access Token",
            "expires_at": None
        }

        with patch.object(manager, 'get_token_info', return_value=mock_info):
            result = manager.check_expiration()
            self.assertIsNone(result)

    def test_check_expiration_with_valid_token(self):
        """Test check_expiration with a valid, non-expired token."""
        token = "github_pat_valid"
        manager = TokenManager(token=token)

        # Mock future expiration date (add 30 days safely)
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        mock_info = {
            "type": "Fine-grained Personal Access Token",
            "expires_at": future_date.isoformat()
        }

        with patch.object(manager, 'get_token_info', return_value=mock_info):
            result = manager.check_expiration()

            self.assertIsNotNone(result)
            self.assertFalse(result["expired"])
            self.assertGreater(result["days_remaining"], 25)
            self.assertFalse(result["warning"])

    def test_check_expiration_with_expiring_token(self):
        """Test check_expiration with a token expiring soon."""
        token = "github_pat_expiring"
        manager = TokenManager(token=token)

        # Mock expiration date in 3 days (should trigger warning)
        future_date = datetime.now(timezone.utc) + timedelta(days=3)
        mock_info = {
            "type": "Fine-grained Personal Access Token",
            "expires_at": future_date.isoformat()
        }

        with patch.object(manager, 'get_token_info', return_value=mock_info):
            result = manager.check_expiration()

            self.assertIsNotNone(result)
            self.assertFalse(result["expired"])
            self.assertLessEqual(result["days_remaining"], 7)
            self.assertTrue(result["warning"])

    def test_security_subprocess_timeout_constants(self):
        """Test that security-critical constants are properly defined."""
        from gh_pr.auth.token import SUBPROCESS_TIMEOUT, GH_CLI_AUTH_STATUS_CMD, GH_CLI_AUTH_TOKEN_CMD

        # Verify timeout is reasonable (not too long)
        self.assertLessEqual(SUBPROCESS_TIMEOUT, 10)
        self.assertGreaterEqual(SUBPROCESS_TIMEOUT, 1)

        # Verify commands are static lists (not constructed from user input)
        self.assertIsInstance(GH_CLI_AUTH_STATUS_CMD, list)
        self.assertIsInstance(GH_CLI_AUTH_TOKEN_CMD, list)
        self.assertEqual(GH_CLI_AUTH_STATUS_CMD[0], "gh")
        self.assertEqual(GH_CLI_AUTH_TOKEN_CMD[0], "gh")

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_token_fallback_from_auth_token_command(self, mock_run):
        """Test fallback to gh auth token command when auth status fails."""
        # Mock auth status failing
        mock_result_status = Mock()
        mock_result_status.returncode = 1
        mock_result_status.stdout = "Not logged in"

        # Mock auth token succeeding
        mock_result_token = Mock()
        mock_result_token.returncode = 0
        mock_result_token.stdout = "ghp_fallback_token_123\n"

        mock_run.side_effect = [mock_result_status, mock_result_token]

        manager = TokenManager()
        self.assertEqual(manager.token, 'ghp_fallback_token_123')

        # Verify both commands were called
        self.assertEqual(mock_run.call_count, 2)

    def test_missing_token_error_message_details(self):
        """Test that missing token error provides helpful guidance."""
        with self.assertRaises(ValueError) as context:
            TokenManager()

        error_message = str(context.exception)

        # Verify the error message contains helpful information
        self.assertIn("No GitHub token found", error_message)
        self.assertIn("--token", error_message)
        self.assertIn("GH_TOKEN", error_message)
        self.assertIn("GITHUB_TOKEN", error_message)
        self.assertIn("gh CLI", error_message)

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_both_commands_fail_gracefully(self, mock_run):
        """Test that when both gh CLI commands fail, we get appropriate error."""
        # Mock both commands failing
        mock_result_status = Mock()
        mock_result_status.returncode = 1
        mock_result_status.stdout = ""

        mock_result_token = Mock()
        mock_result_token.returncode = 1
        mock_result_token.stdout = ""

        mock_run.side_effect = [mock_result_status, mock_result_token]

        with self.assertRaises(ValueError) as context:
            TokenManager()

        error_message = str(context.exception)
        self.assertIn("No GitHub token found", error_message)


if __name__ == '__main__':
    unittest.main()
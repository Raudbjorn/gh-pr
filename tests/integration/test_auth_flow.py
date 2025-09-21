"""
Integration tests for authentication flow.

Tests complete authentication workflows from token management to permissions checking.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from github import Github, GithubException
from github.Auth import Token as GithubToken

from gh_pr.auth.token import TokenManager
from gh_pr.auth.permissions import PermissionChecker
from gh_pr.core.github import GitHubClient


class TestAuthenticationFlow(unittest.TestCase):
    """Test complete authentication workflows."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch.dict(os.environ, {'GH_TOKEN': 'test_token_env'})
    @patch('gh_pr.auth.token.Github')
    def test_complete_auth_flow_environment_token(self, mock_github_class):
        """Test complete authentication flow using environment token."""
        # Mock GitHub API responses
        mock_github = Mock(spec=Github)
        mock_user = Mock()
        mock_user.login = "testuser"
        mock_github.get_user.return_value = mock_user

        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = None
        mock_github.get_rate_limit.return_value = mock_rate_limit

        mock_github_class.return_value = mock_github

        # Step 1: Initialize token manager
        token_manager = TokenManager()
        self.assertEqual(token_manager.get_token(), "test_token_env")

        # Step 2: Validate token
        is_valid = token_manager.validate_token()
        self.assertTrue(is_valid)

        # Step 3: Get token info
        token_info = token_manager.get_token_info()
        self.assertIsNotNone(token_info)
        self.assertEqual(token_info["type"], "Classic Personal Access Token")
        self.assertEqual(token_info["rate_limit"]["limit"], 5000)

        # Step 4: Check permissions
        has_perms = token_manager.has_permissions(["repo"])
        # With no scopes info, should defer to fine-grained check
        self.assertTrue(has_perms)

        # Step 5: Initialize GitHub client
        github_client = token_manager.get_github_client()
        self.assertEqual(github_client, mock_github)

        # Step 6: Initialize permission checker
        permission_checker = PermissionChecker(github_client)

        # Mock repository for permission checking
        mock_repo = Mock()
        mock_repo.get_collaborator_permission.return_value = "write"
        mock_github.get_repo.return_value = mock_repo

        # Step 7: Check operation permissions
        result = permission_checker.can_perform_operation("resolve_comments", "owner", "repo")
        self.assertTrue(result["allowed"])
        self.assertEqual(result["reason"], "Write access to repository")

    @patch('gh_pr.auth.token.subprocess.run')
    @patch('gh_pr.auth.token.Github')
    def test_complete_auth_flow_gh_cli_token(self, mock_github_class, mock_subprocess):
        """Test complete authentication flow using gh CLI token."""
        # Clear environment variables
        with patch.dict(os.environ, {}, clear=True):
            # Mock gh CLI response
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "✓ github.com\n  ✓ Token: ghp_FAKE_TEST_TOKEN_REPLACED\n"
            mock_subprocess.return_value = mock_result

            # Mock GitHub API
            mock_github = Mock(spec=Github)
            mock_user = Mock()
            mock_user.login = "cliuser"
            mock_github.get_user.return_value = mock_user
            mock_github_class.return_value = mock_github

            # Initialize token manager
            token_manager = TokenManager()
            self.assertEqual(token_manager.get_token(), "ghp_FAKE_TEST_TOKEN_REPLACED")

            # Validate token works
            self.assertTrue(token_manager.validate_token())

    def test_auth_flow_token_not_found(self):
        """Test authentication flow when no token is found."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('gh_pr.auth.token.subprocess.run') as mock_subprocess:
                # Mock gh CLI not available
                mock_subprocess.side_effect = FileNotFoundError("gh command not found")

                # Should raise ValueError
                with self.assertRaises(ValueError) as context:
                    TokenManager()

                self.assertIn("No GitHub token found", str(context.exception))

    @patch('gh_pr.auth.token.Github')
    def test_auth_flow_invalid_token(self, mock_github_class):
        """Test authentication flow with invalid token."""
        # Mock GitHub API to reject token
        mock_github = Mock(spec=Github)
        mock_github.get_user.side_effect = GithubException(401, "Bad credentials")
        mock_github_class.return_value = mock_github

        token_manager = TokenManager(token="invalid_token")

        # Token validation should fail
        is_valid = token_manager.validate_token()
        self.assertFalse(is_valid)

        # Token info should be None
        token_info = token_manager.get_token_info()
        self.assertIsNone(token_info)

    @patch('gh_pr.auth.token.Github')
    def test_permission_flow_with_pr_context(self, mock_github_class):
        """Test permission checking flow in PR context."""
        # Mock GitHub API
        mock_github = Mock(spec=Github)
        mock_user = Mock()
        mock_user.login = "reviewer"
        mock_github.get_user.return_value = mock_user

        # Mock repository and PR
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.user.login = "author"
        mock_pr.base.ref = "main"

        mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_collaborator_permission.return_value = "write"
        mock_repo.has_in_collaborators.return_value = True

        # Mock reviews
        mock_pr.get_reviews.return_value = []

        # Mock branch (unprotected)
        mock_branch = Mock()
        mock_branch.protected = False
        mock_repo.get_branch.return_value = mock_branch

        mock_github_class.return_value = mock_github

        # Initialize auth components
        token_manager = TokenManager(token="test_token")
        permission_checker = PermissionChecker(mock_github)

        # Check PR-specific permissions
        permissions = permission_checker.check_pr_permissions("owner", "repo", 123)

        # Verify expected permissions for collaborator with write access
        self.assertFalse(permissions["is_author"])
        self.assertTrue(permissions["is_collaborator"])
        self.assertTrue(permissions["can_comment"])
        self.assertTrue(permissions["can_review"])
        self.assertTrue(permissions["can_approve"])
        self.assertTrue(permissions["can_close"])
        self.assertTrue(permissions["can_edit"])
        self.assertTrue(permissions["can_resolve_comments"])
        self.assertTrue(permissions["can_accept_suggestions"])
        self.assertTrue(permissions["can_merge"])  # Unprotected branch

    @patch('gh_pr.auth.token.Github')
    def test_permission_flow_protected_branch(self, mock_github_class):
        """Test permission checking flow with protected branch."""
        # Mock GitHub API
        mock_github = Mock(spec=Github)
        mock_user = Mock()
        mock_user.login = "maintainer"
        mock_github.get_user.return_value = mock_user

        # Mock repository and PR
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.user.login = "author"
        mock_pr.base.ref = "main"

        mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_collaborator_permission.return_value = "maintain"

        # Mock protected branch with admin enforcement
        mock_branch = Mock()
        mock_branch.protected = True
        mock_protection = Mock()
        mock_protection.enforce_admins = True
        mock_branch.get_protection.return_value = mock_protection
        mock_repo.get_branch.return_value = mock_branch

        mock_github_class.return_value = mock_github

        # Initialize permission checker
        permission_checker = PermissionChecker(mock_github)

        # Check PR permissions
        permissions = permission_checker.check_pr_permissions("owner", "repo", 123)

        # Should not be able to merge due to admin enforcement
        self.assertFalse(permissions["can_merge"])
        # But should have other write permissions
        self.assertTrue(permissions["can_approve"])
        self.assertTrue(permissions["can_close"])

    def test_integration_github_client_with_auth(self):
        """Test GitHubClient integration with authentication."""
        token = "test_integration_token"

        with patch('gh_pr.core.github.Github') as mock_github_class:
            mock_github = Mock(spec=Github)
            mock_github_class.return_value = mock_github

            # Initialize GitHub client
            github_client = GitHubClient(token)

            # Verify Github was initialized with correct token
            mock_github_class.assert_called_once_with(token, timeout=30)

            # Test user property access
            mock_user = Mock()
            mock_user.login = "integration_user"
            mock_github.get_user.return_value = mock_user

            user = github_client.user
            self.assertEqual(user.login, "integration_user")

            # Test get_current_user_login
            login = github_client.get_current_user_login()
            self.assertEqual(login, "integration_user")

    @patch('gh_pr.auth.token.Github')
    def test_auth_flow_with_expiring_token(self, mock_github_class):
        """Test authentication flow with expiring token."""
        from datetime import datetime, timezone

        # Mock GitHub API
        mock_github = Mock(spec=Github)
        mock_user = Mock()
        mock_user.login = "testuser"
        mock_github.get_user.return_value = mock_user

        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 1000
        mock_rate_limit.core.remaining = 999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit

        mock_github_class.return_value = mock_github

        # Initialize with fine-grained token
        token_manager = TokenManager(token="github_pat_expiring_token")

        # Get token info
        token_info = token_manager.get_token_info()
        self.assertEqual(token_info["type"], "Fine-grained Personal Access Token")

        # Mock expiration check
        with patch.object(token_manager, 'get_token_info') as mock_get_info:
            # Mock token expiring in 3 days
            future_date = datetime.now(timezone.utc).replace(day=datetime.now().day + 3)
            mock_info = {
                "type": "Fine-grained Personal Access Token",
                "expires_at": future_date.isoformat()
            }
            mock_get_info.return_value = mock_info

            # Check expiration
            expiration_info = token_manager.check_expiration()
            self.assertIsNotNone(expiration_info)
            self.assertFalse(expiration_info["expired"])
            self.assertTrue(expiration_info["warning"])  # Should warn when < 7 days

    @patch('gh_pr.auth.token.Github')
    def test_auth_flow_permission_escalation_check(self, mock_github_class):
        """Test authentication flow checks for permission escalation."""
        # Mock GitHub API
        mock_github = Mock(spec=Github)
        mock_user = Mock()
        mock_user.login = "limiteduser"
        mock_github.get_user.return_value = mock_user

        mock_github_class.return_value = mock_github

        token_manager = TokenManager(token="limited_token")
        permission_checker = PermissionChecker(mock_github)

        # Mock repository with read-only access
        mock_repo = Mock()
        mock_repo.get_collaborator_permission.return_value = "read"
        mock_github.get_repo.return_value = mock_repo

        # Try to perform operation requiring write access
        result = permission_checker.can_perform_operation("resolve_comments", "owner", "repo")

        # Should be denied
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "Read-only access to repository")
        self.assertEqual(result["missing_permissions"], ["write"])

        # Try operation requiring admin access
        result = permission_checker.can_perform_operation("dismiss_review", "owner", "repo")

        # Should be denied
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "Read-only access to repository")

    def test_auth_flow_error_recovery(self):
        """Test authentication flow error recovery mechanisms."""
        # Test graceful handling of network errors
        with patch('gh_pr.auth.token.Github') as mock_github_class:
            mock_github = Mock(spec=Github)

            # First call succeeds (token validation)
            mock_user = Mock()
            mock_user.login = "testuser"
            mock_github.get_user.return_value = mock_user

            # Second call fails (rate limit check)
            mock_github.get_rate_limit.side_effect = GithubException(500, "Server Error")

            mock_github_class.return_value = mock_github

            token_manager = TokenManager(token="test_token")

            # Token validation should still work
            self.assertTrue(token_manager.validate_token())

            # Token info should handle error gracefully
            token_info = token_manager.get_token_info()
            self.assertIsNotNone(token_info)  # Should return partial info even on rate limit error
            self.assertEqual(token_info["rate_limit"]["limit"], "N/A")  # Rate limit should show fallback

    @patch('gh_pr.auth.token.Github')
    def test_permission_flow_fallback_mechanisms(self, mock_github_class):
        """Test permission checking fallback mechanisms."""
        # Mock GitHub API with partial failures
        mock_github = Mock(spec=Github)
        mock_user = Mock()
        mock_user.login = "fallbackuser"
        mock_github.get_user.return_value = mock_user

        # Mock repository
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.user.login = "author"

        mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr

        # Collaborator permission check fails
        mock_repo.get_collaborator_permission.side_effect = GithubException(403, "Forbidden")
        # Collaborator check fails
        mock_repo.has_in_collaborators.side_effect = GithubException(404, "Not Found")

        mock_github_class.return_value = mock_github

        permission_checker = PermissionChecker(mock_github)

        # Should still allow basic commenting despite permission check failures
        permissions = permission_checker.check_pr_permissions("owner", "repo", 123)

        self.assertTrue(permissions["can_comment"])  # Fallback permission
        self.assertFalse(permissions["is_collaborator"])  # Failed check handled gracefully


if __name__ == '__main__':
    unittest.main()
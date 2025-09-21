"""
Unit tests for auth.permissions module.

Tests permission checking functionality for GitHub operations.
"""

import unittest
from unittest.mock import Mock, patch
import contextlib

from github import Github, GithubException

from gh_pr.auth.permissions import PermissionChecker


class TestPermissionChecker(unittest.TestCase):
    """Test PermissionChecker functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_github = Mock(spec=Github)
        self.checker = PermissionChecker(self.mock_github)

    def test_init(self):
        """Test PermissionChecker initialization."""
        self.assertEqual(self.checker.github, self.mock_github)
        self.assertIsInstance(self.checker.OPERATION_PERMISSIONS, dict)

    def test_operation_permissions_mapping(self):
        """Test that operation permissions mapping is correctly defined."""
        required_operations = [
            "resolve_comments", "accept_suggestions", "create_commit",
            "approve_pr", "merge_pr", "close_pr", "reopen_pr",
            "add_labels", "remove_labels", "assign_users",
            "request_review", "dismiss_review"
        ]

        for operation in required_operations:
            self.assertIn(operation, self.checker.OPERATION_PERMISSIONS)
            self.assertIsInstance(self.checker.OPERATION_PERMISSIONS[operation], list)

    def test_can_perform_operation_no_permissions_required(self):
        """Test operations that don't require special permissions."""
        # Mock an operation not in the mapping
        result = self.checker.can_perform_operation("unknown_operation", "owner", "repo")

        self.assertTrue(result["allowed"])
        self.assertEqual(result["reason"], "No special permissions required")
        self.assertEqual(result["required_permissions"], [])

    def test_can_perform_operation_admin_access(self):
        """Test operation with admin access."""
        # Mock repository and user
        mock_repo = Mock()
        mock_user = Mock()
        mock_user.login = "testuser"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_collaborator_permission.return_value = "admin"

        result = self.checker.can_perform_operation("resolve_comments", "owner", "repo")

        self.assertTrue(result["allowed"])
        self.assertEqual(result["reason"], "Admin access to repository")
        self.assertEqual(result["has_permissions"], ["admin", "write", "read"])

    def test_can_perform_operation_write_access(self):
        """Test operation with write access."""
        # Mock repository and user
        mock_repo = Mock()
        mock_user = Mock()
        mock_user.login = "testuser"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_collaborator_permission.return_value = "write"

        result = self.checker.can_perform_operation("resolve_comments", "owner", "repo")

        self.assertTrue(result["allowed"])
        self.assertEqual(result["reason"], "Write access to repository")
        self.assertEqual(result["has_permissions"], ["write", "read"])

    def test_can_perform_operation_maintain_access(self):
        """Test operation with maintain access."""
        # Mock repository and user
        mock_repo = Mock()
        mock_user = Mock()
        mock_user.login = "testuser"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_collaborator_permission.return_value = "maintain"

        result = self.checker.can_perform_operation("accept_suggestions", "owner", "repo")

        self.assertTrue(result["allowed"])
        self.assertEqual(result["reason"], "Maintain access to repository")
        self.assertEqual(result["has_permissions"], ["write", "read"])

    def test_can_perform_operation_admin_required_insufficient_perms(self):
        """Test operation requiring admin access with insufficient permissions."""
        # Mock repository and user
        mock_repo = Mock()
        mock_user = Mock()
        mock_user.login = "testuser"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_collaborator_permission.return_value = "write"

        result = self.checker.can_perform_operation("dismiss_review", "owner", "repo")

        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "Operation requires admin access")
        self.assertEqual(result["missing_permissions"], ["admin"])

    def test_can_perform_operation_read_only_access(self):
        """Test operation with read-only access."""
        # Mock repository and user
        mock_repo = Mock()
        mock_user = Mock()
        mock_user.login = "testuser"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_collaborator_permission.return_value = "read"

        result = self.checker.can_perform_operation("resolve_comments", "owner", "repo")

        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "Read-only access to repository")
        self.assertEqual(result["has_permissions"], ["read"])
        self.assertEqual(result["missing_permissions"], ["write"])

    def test_can_perform_operation_no_access(self):
        """Test operation with no repository access."""
        # Mock repository and user
        mock_repo = Mock()
        mock_user = Mock()
        mock_user.login = "testuser"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_collaborator_permission.return_value = "none"

        result = self.checker.can_perform_operation("resolve_comments", "owner", "repo")

        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "No access to repository")
        self.assertEqual(result["required_permissions"], ["repo", "write:discussion"])
        self.assertEqual(result["missing_permissions"], ["repo", "write:discussion"])

    def test_can_perform_operation_github_exception(self):
        """Test handling of GitHub API exceptions."""
        # Mock GitHub exception
        self.mock_github.get_repo.side_effect = GithubException(404, "Not Found")

        result = self.checker.can_perform_operation("resolve_comments", "owner", "repo")

        self.assertFalse(result["allowed"])
        self.assertIn("Error checking permissions", result["reason"])

    def test_check_pr_permissions_pr_author(self):
        """Test PR permissions for PR author."""
        # Mock repository, PR, and user
        mock_repo = Mock()
        mock_pr = Mock()
        mock_user = Mock()

        mock_pr.user.login = "prauthor"
        mock_user.login = "prauthor"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_collaborator_permission.return_value = "write"

        permissions = self.checker.check_pr_permissions("owner", "repo", 123)

        self.assertTrue(permissions["is_author"])
        self.assertTrue(permissions["can_comment"])
        self.assertFalse(permissions["can_approve"])  # Author can't approve own PR

    def test_check_pr_permissions_collaborator_with_write_access(self):
        """Test PR permissions for collaborator with write access."""
        # Mock repository, PR, and user
        mock_repo = Mock()
        mock_pr = Mock()
        mock_user = Mock()

        mock_pr.user.login = "prauthor"
        mock_user.login = "reviewer"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_collaborator_permission.return_value = "write"
        mock_repo.has_in_collaborators.return_value = True

        permissions = self.checker.check_pr_permissions("owner", "repo", 123)

        self.assertFalse(permissions["is_author"])
        self.assertTrue(permissions["is_collaborator"])
        self.assertTrue(permissions["can_comment"])
        self.assertTrue(permissions["can_review"])
        self.assertTrue(permissions["can_approve"])
        self.assertTrue(permissions["can_close"])
        self.assertTrue(permissions["can_edit"])
        self.assertTrue(permissions["can_resolve_comments"])
        self.assertTrue(permissions["can_accept_suggestions"])

    def test_check_pr_permissions_admin_access(self):
        """Test PR permissions for admin access."""
        # Mock repository, PR, and user
        mock_repo = Mock()
        mock_pr = Mock()
        mock_user = Mock()

        mock_pr.user.login = "prauthor"
        mock_user.login = "admin"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_collaborator_permission.return_value = "admin"

        permissions = self.checker.check_pr_permissions("owner", "repo", 123)

        self.assertTrue(permissions["can_merge"])

    def test_check_pr_permissions_is_reviewer(self):
        """Test PR permissions when user is a reviewer."""
        # Mock repository, PR, user, and reviews
        mock_repo = Mock()
        mock_pr = Mock()
        mock_user = Mock()
        mock_review = Mock()

        mock_pr.user.login = "prauthor"
        mock_user.login = "reviewer"
        mock_review.user.login = "reviewer"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_pull.return_value = mock_pr
        mock_pr.get_reviews.return_value = [mock_review]
        mock_repo.get_collaborator_permission.return_value = "read"

        permissions = self.checker.check_pr_permissions("owner", "repo", 123)

        self.assertTrue(permissions["is_reviewer"])

    def test_check_pr_permissions_read_only_access(self):
        """Test PR permissions for read-only access."""
        # Mock repository, PR, and user
        mock_repo = Mock()
        mock_pr = Mock()
        mock_user = Mock()

        mock_pr.user.login = "prauthor"
        mock_user.login = "readonly"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_collaborator_permission.return_value = "read"

        permissions = self.checker.check_pr_permissions("owner", "repo", 123)

        self.assertTrue(permissions["can_comment"])
        self.assertFalse(permissions["can_review"])

    def test_check_pr_permissions_protected_branch_admin_enforcement(self):
        """Test PR permissions with protected branch and admin enforcement."""
        # Mock repository, PR, user, and protected branch
        mock_repo = Mock()
        mock_pr = Mock()
        mock_user = Mock()
        mock_branch = Mock()
        mock_protection = Mock()

        mock_pr.user.login = "prauthor"
        mock_pr.base.ref = "main"
        mock_user.login = "maintainer"
        mock_branch.protected = True
        mock_protection.enforce_admins = True

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_collaborator_permission.return_value = "maintain"
        mock_repo.get_branch.return_value = mock_branch
        mock_branch.get_protection.return_value = mock_protection

        permissions = self.checker.check_pr_permissions("owner", "repo", 123)

        self.assertFalse(permissions["can_merge"])  # Admin enforcement blocks merge

    def test_check_pr_permissions_protected_branch_no_admin_enforcement(self):
        """Test PR permissions with protected branch without admin enforcement."""
        # Mock repository, PR, user, and protected branch
        mock_repo = Mock()
        mock_pr = Mock()
        mock_user = Mock()
        mock_branch = Mock()
        mock_protection = Mock()

        mock_pr.user.login = "prauthor"
        mock_pr.base.ref = "main"
        mock_user.login = "maintainer"
        mock_branch.protected = True
        mock_protection.enforce_admins = False

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_collaborator_permission.return_value = "maintain"
        mock_repo.get_branch.return_value = mock_branch
        mock_branch.get_protection.return_value = mock_protection

        permissions = self.checker.check_pr_permissions("owner", "repo", 123)

        self.assertTrue(permissions["can_merge"])  # Maintainer can merge

    def test_check_pr_permissions_unprotected_branch(self):
        """Test PR permissions with unprotected branch."""
        # Mock repository, PR, user, and unprotected branch
        mock_repo = Mock()
        mock_pr = Mock()
        mock_user = Mock()
        mock_branch = Mock()

        mock_pr.user.login = "prauthor"
        mock_pr.base.ref = "feature"
        mock_user.login = "contributor"
        mock_branch.protected = False

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_collaborator_permission.return_value = "write"
        mock_repo.get_branch.return_value = mock_branch

        permissions = self.checker.check_pr_permissions("owner", "repo", 123)

        self.assertTrue(permissions["can_merge"])

    def test_check_pr_permissions_github_exception_fallback(self):
        """Test PR permissions handling GitHub exceptions gracefully."""
        # Mock repository and PR, but make collaborator check fail
        mock_repo = Mock()
        mock_pr = Mock()
        mock_user = Mock()

        mock_pr.user.login = "prauthor"
        mock_user.login = "external"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_collaborator_permission.side_effect = GithubException(403, "Forbidden")

        permissions = self.checker.check_pr_permissions("owner", "repo", 123)

        # Should still allow commenting for external users
        self.assertTrue(permissions["can_comment"])
        self.assertFalse(permissions["is_collaborator"])

    def test_check_pr_permissions_exception_handling(self):
        """Test PR permissions with general exception handling."""
        # Mock exception during PR retrieval
        self.mock_github.get_repo.side_effect = Exception("Network error")

        permissions = self.checker.check_pr_permissions("owner", "repo", 123)

        self.assertIn("error", permissions)
        self.assertEqual(permissions["error"], "Network error")

    def test_get_required_permissions_summary(self):
        """Test getting required permissions summary."""
        operations = ["resolve_comments", "accept_suggestions", "unknown_operation"]

        summary = self.checker.get_required_permissions_summary(operations)

        self.assertIn("resolve_comments", summary)
        self.assertIn("accept_suggestions", summary)
        self.assertNotIn("unknown_operation", summary)

        self.assertEqual(summary["resolve_comments"], ["repo", "write:discussion"])
        self.assertEqual(summary["accept_suggestions"], ["repo"])

    def test_contextlib_suppress_usage(self):
        """Test that contextlib.suppress is used correctly for optional operations."""
        # This tests the implementation detail of using contextlib.suppress
        # for the has_in_collaborators check
        mock_repo = Mock()
        mock_pr = Mock()
        mock_user = Mock()

        mock_pr.user.login = "prauthor"
        mock_user.login = "testuser"

        self.mock_github.get_repo.return_value = mock_repo
        self.mock_github.get_user.return_value = mock_user
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_collaborator_permission.return_value = "read"

        # Make has_in_collaborators raise an exception
        mock_repo.has_in_collaborators.side_effect = GithubException(404, "Not Found")

        # Should not raise an exception due to contextlib.suppress
        permissions = self.checker.check_pr_permissions("owner", "repo", 123)

        # Should have default value for is_collaborator
        self.assertFalse(permissions["is_collaborator"])


if __name__ == '__main__':
    unittest.main()
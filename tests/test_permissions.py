"""Unit tests for permission checking system."""

from unittest.mock import Mock, patch

import pytest
from github import GithubException

from gh_pr.auth.permissions import PermissionChecker


class TestPermissionChecker:
    """Test PermissionChecker class."""

    @pytest.fixture
    def mock_github(self):
        """Create a mock GitHub client."""
        mock = Mock()
        mock_user = Mock()
        mock_user.login = "testuser"
        mock.get_user.return_value = mock_user
        return mock

    def test_init(self, mock_github):
        """Test PermissionChecker initialization."""
        checker = PermissionChecker(mock_github)
        assert checker.github is mock_github
        assert checker._cache == {}

    def test_get_required_permissions(self):
        """Test getting required permissions for operations."""
        checker = PermissionChecker(Mock())

        # Test known operations
        perms = checker.get_required_permissions("resolve_comments")
        assert "repo" in perms
        assert "write:discussion" in perms

        perms = checker.get_required_permissions("accept_suggestions")
        assert "repo" in perms

        perms = checker.get_required_permissions("merge_pr")
        assert "repo" in perms

        # Test unknown operation
        perms = checker.get_required_permissions("unknown_operation")
        assert perms == []

    def test_can_perform_operation_with_permissions(self, mock_github):
        """Test checking if user can perform operation with permissions."""
        checker = PermissionChecker(mock_github)

        # Mock repository access
        mock_repo = Mock()
        mock_repo.permissions.push = True
        mock_repo.permissions.pull = True
        mock_repo.permissions.admin = False
        mock_github.get_repo.return_value = mock_repo

        result = checker.can_perform_operation("accept_suggestions", "owner", "repo")

        assert result["can_perform"] is True
        assert result["has_permissions"] is True
        assert result["missing_permissions"] == []

    def test_can_perform_operation_without_permissions(self, mock_github):
        """Test checking if user can perform operation without permissions."""
        checker = PermissionChecker(mock_github)

        # Mock repository with limited access
        mock_repo = Mock()
        mock_repo.permissions.push = False
        mock_repo.permissions.pull = True
        mock_repo.permissions.admin = False
        mock_github.get_repo.return_value = mock_repo

        result = checker.can_perform_operation("accept_suggestions", "owner", "repo")

        assert result["can_perform"] is False
        assert result["has_permissions"] is False
        assert "repo" in result["missing_permissions"]

    def test_can_perform_operation_api_error(self, mock_github):
        """Test handling API errors when checking permissions."""
        checker = PermissionChecker(mock_github)

        # Mock API error
        mock_github.get_repo.side_effect = GithubException(404, {"message": "Not found"})

        result = checker.can_perform_operation("resolve_comments", "owner", "repo")

        assert result["can_perform"] is False
        assert result["error"] is not None
        assert "404" in result["error"]

    def test_check_pr_permissions_as_author(self, mock_github):
        """Test checking PR permissions as the PR author."""
        checker = PermissionChecker(mock_github)

        # Mock PR and repository
        mock_pr = Mock()
        mock_pr.user.login = "testuser"  # Same as authenticated user
        mock_pr.base.repo.permissions.push = False  # Not a collaborator

        mock_repo = Mock()
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.has_in_collaborators.return_value = False

        mock_github.get_repo.return_value = mock_repo
        mock_github.get_user().login = "testuser"

        result = checker.check_pr_permissions("owner", "repo", 1)

        assert result["is_author"] is True
        assert result["is_collaborator"] is False
        assert result["can_modify_pr"] is True  # Authors can modify their own PRs

    def test_check_pr_permissions_as_collaborator(self, mock_github):
        """Test checking PR permissions as a repository collaborator."""
        checker = PermissionChecker(mock_github)

        # Mock PR and repository
        mock_pr = Mock()
        mock_pr.user.login = "otheruser"  # Different from authenticated user

        mock_repo = Mock()
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.permissions.push = True  # Has push access
        mock_repo.has_in_collaborators.return_value = True

        mock_github.get_repo.return_value = mock_repo
        mock_github.get_user().login = "testuser"

        result = checker.check_pr_permissions("owner", "repo", 1)

        assert result["is_author"] is False
        assert result["is_collaborator"] is True
        assert result["can_modify_pr"] is True  # Collaborators can modify PRs

    def test_check_pr_permissions_as_reviewer(self, mock_github):
        """Test checking PR permissions as a PR reviewer."""
        checker = PermissionChecker(mock_github)

        # Mock PR with review requests
        mock_pr = Mock()
        mock_pr.user.login = "otheruser"

        # Mock requested reviewer
        mock_reviewer = Mock()
        mock_reviewer.login = "testuser"
        mock_pr.requested_reviewers = [mock_reviewer]

        mock_repo = Mock()
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.permissions.push = False
        mock_repo.has_in_collaborators.return_value = False

        mock_github.get_repo.return_value = mock_repo
        mock_github.get_user().login = "testuser"

        result = checker.check_pr_permissions("owner", "repo", 1)

        assert result["is_author"] is False
        assert result["is_collaborator"] is False
        assert result["is_reviewer"] is True
        assert result["can_modify_pr"] is False  # Reviewers can't modify without push access

    def test_check_pr_permissions_no_access(self, mock_github):
        """Test checking PR permissions with no special access."""
        checker = PermissionChecker(mock_github)

        # Mock PR and repository
        mock_pr = Mock()
        mock_pr.user.login = "otheruser"
        mock_pr.requested_reviewers = []

        mock_repo = Mock()
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.permissions.push = False
        mock_repo.permissions.pull = True
        mock_repo.has_in_collaborators.return_value = False

        mock_github.get_repo.return_value = mock_repo
        mock_github.get_user().login = "testuser"

        result = checker.check_pr_permissions("owner", "repo", 1)

        assert result["is_author"] is False
        assert result["is_collaborator"] is False
        assert result["is_reviewer"] is False
        assert result["can_modify_pr"] is False
        assert result["can_comment"] is True  # Anyone with read access can comment

    def test_check_repository_permissions_admin(self, mock_github):
        """Test checking repository permissions with admin access."""
        checker = PermissionChecker(mock_github)

        mock_repo = Mock()
        mock_repo.permissions.admin = True
        mock_repo.permissions.push = True
        mock_repo.permissions.pull = True

        mock_github.get_repo.return_value = mock_repo

        result = checker.check_repository_permissions("owner", "repo")

        assert result["access_level"] == "admin"
        assert result["can_push"] is True
        assert result["can_merge"] is True
        assert result["can_manage_issues"] is True

    def test_check_repository_permissions_write(self, mock_github):
        """Test checking repository permissions with write access."""
        checker = PermissionChecker(mock_github)

        mock_repo = Mock()
        mock_repo.permissions.admin = False
        mock_repo.permissions.push = True
        mock_repo.permissions.pull = True

        mock_github.get_repo.return_value = mock_repo

        result = checker.check_repository_permissions("owner", "repo")

        assert result["access_level"] == "write"
        assert result["can_push"] is True
        assert result["can_merge"] is True
        assert result["can_manage_issues"] is False

    def test_check_repository_permissions_read(self, mock_github):
        """Test checking repository permissions with read-only access."""
        checker = PermissionChecker(mock_github)

        mock_repo = Mock()
        mock_repo.permissions.admin = False
        mock_repo.permissions.push = False
        mock_repo.permissions.pull = True

        mock_github.get_repo.return_value = mock_repo

        result = checker.check_repository_permissions("owner", "repo")

        assert result["access_level"] == "read"
        assert result["can_push"] is False
        assert result["can_merge"] is False
        assert result["can_manage_issues"] is False

    def test_get_required_permissions_summary(self):
        """Test getting summary of required permissions for multiple operations."""
        checker = PermissionChecker(Mock())

        operations = ["resolve_comments", "accept_suggestions", "merge_pr"]
        summary = checker.get_required_permissions_summary(operations)

        assert "resolve_comments" in summary
        assert "accept_suggestions" in summary
        assert "merge_pr" in summary

        # Check that permissions are correctly mapped
        assert "repo" in summary["resolve_comments"]
        assert "write:discussion" in summary["resolve_comments"]
        assert "repo" in summary["accept_suggestions"]

    def test_caching(self, mock_github):
        """Test that permission checks are cached."""
        checker = PermissionChecker(mock_github)

        mock_repo = Mock()
        mock_repo.permissions.push = True
        mock_repo.permissions.pull = True
        mock_repo.permissions.admin = False
        mock_github.get_repo.return_value = mock_repo

        # First call
        result1 = checker.can_perform_operation("accept_suggestions", "owner", "repo")
        # Second call with same parameters
        result2 = checker.can_perform_operation("accept_suggestions", "owner", "repo")

        # Should return same result
        assert result1 == result2
        # But should only call API once
        mock_github.get_repo.assert_called_once()

    def test_cache_different_operations(self, mock_github):
        """Test that different operations create different cache entries."""
        checker = PermissionChecker(mock_github)

        mock_repo = Mock()
        mock_repo.permissions.push = True
        mock_repo.permissions.pull = True
        mock_repo.permissions.admin = True
        mock_github.get_repo.return_value = mock_repo

        # Call with different operations
        checker.can_perform_operation("accept_suggestions", "owner", "repo")
        checker.can_perform_operation("resolve_comments", "owner", "repo")

        # Should have two cache entries
        assert len(checker._cache) == 2

    def test_handle_api_rate_limit(self, mock_github):
        """Test handling of API rate limit errors."""
        checker = PermissionChecker(mock_github)

        # Mock rate limit error
        mock_github.get_repo.side_effect = GithubException(
            403, {"message": "API rate limit exceeded"}
        )

        result = checker.can_perform_operation("resolve_comments", "owner", "repo")

        assert result["can_perform"] is False
        assert "rate limit" in result["error"].lower()
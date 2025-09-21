"""Permission checking for GitHub operations."""

import contextlib
from typing import Any

from github import Github, GithubException

from ..utils.rich_logger import get_logger

logger = get_logger(__name__)


class PermissionChecker:
    """Check permissions for GitHub operations."""

    # Map of operations to required scopes/permissions
    OPERATION_PERMISSIONS = {
        "resolve_comments": ["repo", "write:discussion"],
        "accept_suggestions": ["repo"],
        "create_commit": ["repo"],
        "approve_pr": ["repo"],
        "merge_pr": ["repo"],
        "close_pr": ["repo"],
        "reopen_pr": ["repo"],
        "add_labels": ["repo"],
        "remove_labels": ["repo"],
        "assign_users": ["repo"],
        "request_review": ["repo"],
        "dismiss_review": ["repo"],
    }

    def __init__(self, token_manager):
        """
        Initialize PermissionChecker.

        Args:
            token_manager: TokenManager instance with GitHub token
        """
        self.github = Github(token_manager.get_token())

    def can_perform_operation(
        self, operation: str, owner: str, repo: str
    ) -> dict[str, Any]:
        """
        Check if current user can perform an operation on a repository.

        Args:
            operation: Operation name
            owner: Repository owner
            repo: Repository name

        Returns:
            Dictionary with permission status and details
        """
        logger.debug("Checking operation permissions",
                    operation=operation,
                    repo=f"{owner}/{repo}")

        result = {
            "allowed": False,
            "reason": None,
            "required_permissions": [],
            "has_permissions": [],
            "missing_permissions": [],
        }

        # Get required permissions for operation
        required = self.OPERATION_PERMISSIONS.get(operation, [])
        result["required_permissions"] = required

        if not required:
            result["allowed"] = True
            result["reason"] = "No special permissions required"
            return result

        try:
            # Get repository
            repository = self.github.get_repo(f"{owner}/{repo}")

            # Check if user has push access (indicates write permissions)
            user = self.github.get_user()

            # Check repository permissions
            permissions = repository.get_collaborator_permission(user.login)

            # Map permission level to allowed operations
            if permissions == "admin":
                result["has_permissions"] = ["admin", "write", "read"]
                result["allowed"] = True
                result["reason"] = "Admin access to repository"
            elif permissions in {"write", "maintain"}:
                result["has_permissions"] = ["write", "read"]
                # Check if operation requires admin
                if operation in {"dismiss_review"}:
                    result["allowed"] = False
                    result["reason"] = "Operation requires admin access"
                    result["missing_permissions"] = ["admin"]
                else:
                    result["allowed"] = True
                    result["reason"] = f"{permissions.capitalize()} access to repository"
            elif permissions == "read":
                result["has_permissions"] = ["read"]
                result["allowed"] = False
                result["reason"] = "Read-only access to repository"
                result["missing_permissions"] = ["write"]
            else:
                result["allowed"] = False
                result["reason"] = "No access to repository"
                result["missing_permissions"] = required

        except GithubException as e:
            logger.warning("Error checking permissions",
                         operation=operation,
                         repo=f"{owner}/{repo}",
                         error=str(e),
                         error_type=e.__class__.__name__)
            result["allowed"] = False
            result["reason"] = f"Error checking permissions: {str(e)}"

        logger.info("Permission check completed",
                   operation=operation,
                   repo=f"{owner}/{repo}",
                   allowed=result["allowed"],
                   reason=result["reason"])
        return result

    def check_pr_permissions(
        self, owner: str, repo: str, pr_number: int
    ) -> dict[str, Any]:
        """
        Check permissions for a specific PR.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number

        Returns:
            Dictionary with PR-specific permissions
        """
        permissions = {
            "can_comment": False,
            "can_review": False,
            "can_approve": False,
            "can_merge": False,
            "can_close": False,
            "can_edit": False,
            "can_resolve_comments": False,
            "can_accept_suggestions": False,
            "is_author": False,
            "is_collaborator": False,
            "is_reviewer": False,
        }

        try:
            repository = self.github.get_repo(f"{owner}/{repo}")
            pr = repository.get_pull(pr_number)
            user = self.github.get_user()

            # Check if user is PR author
            permissions["is_author"] = pr.user.login == user.login

            # Check if user is a collaborator
            with contextlib.suppress(GithubException):
                permissions["is_collaborator"] = repository.has_in_collaborators(
                    user.login
                )

            # Check if user is a reviewer
            for review in pr.get_reviews():
                if review.user.login == user.login:
                    permissions["is_reviewer"] = True
                    break

            # Check repository permissions
            try:
                perm_level = repository.get_collaborator_permission(user.login)

                if perm_level in {"admin", "write", "maintain"}:
                    permissions["can_comment"] = True
                    permissions["can_review"] = True
                    permissions["can_approve"] = not permissions["is_author"]
                    permissions["can_close"] = True
                    permissions["can_edit"] = True
                    permissions["can_resolve_comments"] = True
                    permissions["can_accept_suggestions"] = True

                    # Check merge permissions
                    if perm_level == "admin":
                        permissions["can_merge"] = True
                    elif perm_level in {"write", "maintain"}:
                        # Check branch protection rules
                        try:
                            branch = repository.get_branch(pr.base.ref)
                            if branch.protected:
                                # Need to check protection rules
                                protection = branch.get_protection()
                                if protection.enforce_admins:
                                    permissions["can_merge"] = False
                                else:
                                    permissions["can_merge"] = perm_level == "maintain"
                            else:
                                permissions["can_merge"] = True
                        except GithubException:
                            permissions["can_merge"] = perm_level in {"write", "maintain"}
                elif perm_level == "read":
                    permissions["can_comment"] = True
                    permissions["can_review"] = False

            except GithubException:
                # User might not be a collaborator but can still comment
                permissions["can_comment"] = True

        except Exception as e:
            # Return minimal permissions on error
            permissions["error"] = str(e)

        return permissions

    def get_required_permissions_summary(
        self, operations: list[str]
    ) -> dict[str, list[str]]:
        """
        Get a summary of required permissions for multiple operations.

        Args:
            operations: List of operation names

        Returns:
            Dictionary mapping operations to required permissions
        """
        return {
            operation: self.OPERATION_PERMISSIONS[operation]
            for operation in operations
            if operation in self.OPERATION_PERMISSIONS
        }

    def has_pr_permissions(
        self, owner: str, repo: str, operations: list[str]
    ) -> bool:
        """
        Check if user has permissions for PR operations.

        Args:
            owner: Repository owner
            repo: Repository name
            operations: List of operations to check

        Returns:
            True if user has permissions for all operations
        """
        for operation in operations:
            result = self.can_perform_operation(operation, owner, repo)
            if not result["allowed"]:
                return False
        return True

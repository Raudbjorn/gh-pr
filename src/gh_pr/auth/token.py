"""GitHub token management and validation."""

import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Any, Optional

from github import Github, GithubException
from github.Auth import Token as GithubToken

logger = logging.getLogger(__name__)

# Constants
SUBPROCESS_TIMEOUT = 5  # seconds
GH_CLI_AUTH_STATUS_CMD = ["gh", "auth", "status", "--show-token"]
GH_CLI_AUTH_TOKEN_CMD = ["gh", "auth", "token"]


class TokenManager:
    """Manages GitHub authentication tokens."""

    def __init__(self, token: Optional[str] = None):
        """
        Initialize TokenManager.

        Args:
            token: GitHub token. If not provided, will try to get from environment.
        """
        self.token = self._get_token(token)
        self._github: Optional[Github] = None
        self._token_info: Optional[dict[str, Any]] = None

    def _get_token(self, token: Optional[str] = None) -> str:
        """
        Get GitHub token from various sources.

        Priority:
        1. Provided token parameter
        2. GH_TOKEN environment variable
        3. GITHUB_TOKEN environment variable
        4. gh CLI configuration

        Args:
            token: Optional token string

        Returns:
            GitHub token string

        Raises:
            ValueError: If no token is found
        """
        if token:
            return token

        # Try environment variables
        for env_var in ["GH_TOKEN", "GITHUB_TOKEN"]:
            if env_token := os.environ.get(env_var):
                return env_token

        if gh_token := self._get_gh_cli_token():
            return gh_token

        raise ValueError(
            "No GitHub token found. Please provide a token via --token, "
            "GH_TOKEN/GITHUB_TOKEN environment variable, or configure gh CLI"
        )

    def _get_gh_cli_token(self) -> Optional[str]:
        """
        Try to get token from gh CLI configuration.

        Returns:
            Token string if found, None otherwise
        """
        try:
            # Try to get auth status from gh CLI
            # Security: GH_CLI_AUTH_STATUS_CMD is a hardcoded constant list, not user input
            result = subprocess.run(
                GH_CLI_AUTH_STATUS_CMD,  # Static constant: ["gh", "auth", "status", "--show-token"]
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT
            )

            # Parse token from output
            for line in result.stdout.split('\n'):
                if "Token:" in line:
                    return line.split("Token:")[-1].strip()

            # Alternative: try to get token from gh config
            # Security: GH_CLI_AUTH_TOKEN_CMD is a hardcoded constant list, not user input
            result = subprocess.run(
                GH_CLI_AUTH_TOKEN_CMD,  # Static constant: ["gh", "auth", "token"]
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT
            )

            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()

        except subprocess.TimeoutExpired:
            logger.debug(f"Timeout expired while getting gh CLI token (timeout: {SUBPROCESS_TIMEOUT}s)")
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.debug(f"Failed to get gh CLI token: {e}")
        except Exception as e:
            logger.debug(f"Unexpected error getting gh CLI token: {e}")

        return None

    def get_token(self) -> str:
        """Get the current token."""
        return self.token

    def get_github_client(self) -> Github:
        """Get an authenticated GitHub client."""
        if not self._github:
            auth = GithubToken(self.token)
            self._github = Github(auth=auth)
        return self._github

    def validate_token(self) -> bool:
        """
        Validate the current token.

        Returns:
            True if token is valid, False otherwise
        """
        try:
            github = self.get_github_client()
            # Try to get the authenticated user
            user = github.get_user()
            _ = user.login  # Force API call
            return True
        except GithubException:
            return False

    def get_token_info(self) -> Optional[dict[str, Any]]:
        """
        Get information about the current token.

        Returns:
            Dictionary with token information or None if invalid
        """
        if self._token_info:
            return self._token_info

        try:
            github = self.get_github_client()

            # Check if it's a classic token or fine-grained token
            if self.token.startswith("ghp_"):
                token_type = "Classic Personal Access Token"
            elif self.token.startswith("github_pat_"):
                token_type = "Fine-grained Personal Access Token"
            elif self.token.startswith("ghs_"):
                token_type = "GitHub App Installation Token"
            else:
                token_type = "Unknown"

            info: dict[str, Any] = {
                "type": token_type,
                "scopes": [],
                "expires_at": None,
                "days_remaining": None,
            }

            # Try to get rate limit info (works for all valid tokens)
            rate_limit = github.get_rate_limit()
            info["rate_limit"] = {
                "limit": rate_limit.core.limit,
                "remaining": rate_limit.core.remaining,
                "reset": rate_limit.core.reset.isoformat() if rate_limit.core.reset else None,
            }

            # Try to get scopes (only for OAuth/PAT tokens)
            # Note: PyGithub doesn't provide a public API for token scopes.
            # For now, we'll skip scope detection to avoid accessing private attributes.
            # Future improvement: Make a direct API request to get scope information.
            info["scopes"] = []  # Unable to determine scopes without private attribute access

            # Check token expiration for fine-grained tokens
            if token_type == "Fine-grained Personal Access Token":
                # Fine-grained tokens have expiration
                # GitHub API doesn't directly expose token expiry
                # In real implementation, you might store this when token is created
                pass

            self._token_info = info
            return info

        except (GithubException, ValueError, KeyError) as e:
            logger.debug(f"Failed to get token info: {e}")
            return None

    def has_permissions(self, required_scopes: list[str]) -> bool:
        """
        Check if token has required permissions.

        Args:
            required_scopes: List of required OAuth scopes

        Returns:
            True if token has all required scopes
        """
        info = self.get_token_info()
        if not info:
            return False

        token_scopes = info.get("scopes", [])

        # If no scopes info (e.g., fine-grained token), try to check permissions
        if not token_scopes and info.get("type") == "Fine-grained Personal Access Token":
            # For fine-grained tokens, we need to check specific permissions
            # This would require testing actual API calls
            return self._check_fine_grained_permissions(required_scopes)

        # For classic tokens, check scopes
        return all(scope in token_scopes for scope in required_scopes)

    def _check_fine_grained_permissions(self, required_scopes: list[str]) -> bool:
        """
        Check permissions for fine-grained tokens.

        Args:
            required_scopes: List of required scopes

        Returns:
            True if token has required permissions
        """
        try:
            github = self.get_github_client()

            # Map classic scopes to fine-grained permissions
            permission_map = {
                "repo": ["contents", "pull_requests", "issues"],
                "write:discussion": ["discussions"],
                "read:org": ["organization"],
            }

            # Test permissions by trying relevant API calls for each mapped permission
            user = github.get_user()
            for scope in required_scopes:
                mapped_permissions = permission_map.get(scope, [])
                for perm in mapped_permissions:
                    if perm == "contents":
                        # Try to list repos (contents access)
                        try:
                            user.get_repos(type="all")[0]
                        except (GithubException, IndexError, AttributeError):
                            return False
                    elif perm == "pull_requests":
                        # Try to list pull requests for a repo
                        try:
                            repos = user.get_repos(type="all")
                            if repos.totalCount > 0:
                                repo = repos[0]
                                repo.get_pulls()[0]
                        except (GithubException, IndexError, AttributeError):
                            return False
                    elif perm == "issues":
                        # Try to list issues for a repo
                        try:
                            repos = user.get_repos(type="all")
                            if repos.totalCount > 0:
                                repo = repos[0]
                                repo.get_issues()[0]
                        except (GithubException, IndexError, AttributeError):
                            return False
                    elif perm == "discussions":
                        # Try to list discussions for a repo
                        try:
                            repos = user.get_repos(type="all")
                            if repos.totalCount > 0:
                                repo = repos[0]
                                repo.get_discussions()[0]
                        except (GithubException, IndexError, AttributeError):
                            return False
                    elif perm == "organization":
                        # Try to get organizations
                        try:
                            user.get_orgs()[0]
                        except (GithubException, IndexError, AttributeError):
                            return False
            return True

        except GithubException:
            return False

    def check_expiration(self) -> Optional[dict[str, Any]]:
        """
        Check token expiration status.

        Returns:
            Dictionary with expiration info or None
        """
        info = self.get_token_info()
        if not info or not info.get("expires_at"):
            return None

        expires_at = datetime.fromisoformat(info["expires_at"])
        now = datetime.now(timezone.utc)
        days_remaining = (expires_at - now).days

        return {
            "expired": days_remaining <= 0,
            "expires_at": expires_at.isoformat(),
            "days_remaining": days_remaining,
            "warning": days_remaining <= 7,  # Warn if expiring within a week
        }

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

    def __init__(self, token: Optional[str] = None, config_manager=None):
        """
        Initialize TokenManager.

        Args:
            token: GitHub token. If not provided, will try to get from environment.
            config_manager: Optional config manager for token storage.
        """
        self.config_manager = config_manager
        self.token = self._get_token(token)
        self._github: Optional[Github] = None
        self._token_info: Optional[dict[str, Any]] = None
        self._expiration_info: Optional[dict[str, Any]] = None

    def _get_token(self, token: Optional[str] = None) -> str:
        """
        Get GitHub token from various sources.

        Priority:
        1. Provided token parameter
        2. GH_TOKEN environment variable
        3. GITHUB_TOKEN environment variable
        4. Configuration file
        5. gh CLI configuration

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

        # Try configuration file
        if self.config_manager:
            if config_token := self.config_manager.get("github.token"):
                return config_token

        # Try gh CLI
        if gh_token := self._get_gh_cli_token():
            return gh_token

        raise ValueError(
            "No GitHub token found. Please provide a token via --token, "
            "GH_TOKEN/GITHUB_TOKEN environment variable, config file, or configure gh CLI"
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

        except (subprocess.SubprocessError, FileNotFoundError):
            pass

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
            try:
                rate_limit = github.get_rate_limit()
                core = rate_limit.core
                info["rate_limit"] = {
                    "limit": getattr(core, "limit", "N/A"),
                    "remaining": getattr(core, "remaining", "N/A"),
                    "reset": datetime.fromtimestamp(core.reset.timestamp(), timezone.utc).isoformat() if getattr(core, "reset", None) else None,
                }
            except (GithubException, KeyError, AttributeError) as e:
                # Fallback if rate limit API changes or data is missing
                logger.warning(f"Could not retrieve rate limit info: {e}")
                info["rate_limit"] = {
                    "limit": "N/A",
                    "remaining": "N/A",
                    "reset": None,
                }

            # Try to get scopes (only for OAuth/PAT tokens)
            # Note: PyGithub doesn't provide a public API for token scopes.
            # For now, we'll skip scope detection to avoid accessing private attributes.
            # Future improvement: Make a direct API request to get scope information.
            info["scopes"] = []  # Unable to determine scopes without private attribute access

            # Check token expiration for fine-grained tokens
            if token_type == "Fine-grained Personal Access Token":
                # Fine-grained tokens have expiration (typically 60-365 days)
                # Try to get from stored metadata if available
                if self.config_manager:
                    stored_expiry = self.config_manager.get(f"tokens.{self.token[:10]}.expires_at")
                    if stored_expiry:
                        info["expires_at"] = stored_expiry
                        from datetime import datetime
                        expires_dt = datetime.fromisoformat(stored_expiry)
                        now = datetime.now(timezone.utc)
                        days_remaining = (expires_dt - now).days
                        info["days_remaining"] = days_remaining

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
                        except Exception:
                            return False
                    elif perm == "pull_requests":
                        # Try to list pull requests for a repo
                        try:
                            repos = user.get_repos(type="all")
                            if repos.totalCount > 0:
                                repo = repos[0]
                                repo.get_pulls()[0]
                        except Exception:
                            return False
                    elif perm == "issues":
                        # Try to list issues for a repo
                        try:
                            repos = user.get_repos(type="all")
                            if repos.totalCount > 0:
                                repo = repos[0]
                                repo.get_issues()[0]
                        except Exception:
                            return False
                    elif perm == "discussions":
                        # Try to list discussions for a repo
                        try:
                            repos = user.get_repos(type="all")
                            if repos.totalCount > 0:
                                repo = repos[0]
                                repo.get_discussions()[0]
                        except Exception:
                            return False
                    elif perm == "organization":
                        # Try to get organizations
                        try:
                            user.get_orgs()[0]
                        except Exception:
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
        # Return cached expiration info if available
        if self._expiration_info:
            return self._expiration_info

        info = self.get_token_info()
        if not info:
            return None

        # Check for stored expiration or estimated expiration
        expires_at_str = info.get("expires_at")

        # For GitHub App tokens, they typically expire after 1 hour
        if info.get("type") == "GitHub App Installation Token":
            # Estimate 1 hour from now (conservative estimate)
            from datetime import datetime, timedelta
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            expires_at_str = expires_at.isoformat()

        if not expires_at_str:
            return None

        from datetime import datetime
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        days_remaining = (expires_at - now).days
        hours_remaining = int((expires_at - now).total_seconds() / 3600)

        self._expiration_info = {
            "expired": expires_at <= now,
            "expires_at": expires_at.isoformat(),
            "days_remaining": days_remaining,
            "hours_remaining": hours_remaining,
            "warning": days_remaining <= 7,  # Warn if expiring within a week
        }

        return self._expiration_info

    def store_token_metadata(self, expires_at: Optional[str] = None) -> bool:
        """
        Store token metadata in configuration.

        Args:
            expires_at: Optional expiration date in ISO format

        Returns:
            True if stored successfully
        """
        if not self.config_manager:
            return False

        try:
            # Store token metadata using first 10 chars as key
            token_key = self.token[:10] if len(self.token) > 10 else self.token

            metadata = {
                "type": self.get_token_info().get("type", "Unknown"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            if expires_at:
                metadata["expires_at"] = expires_at

            self.config_manager.set(f"tokens.{token_key}", metadata)
            return True
        except Exception as e:
            logger.debug(f"Failed to store token metadata: {e}")
            return False

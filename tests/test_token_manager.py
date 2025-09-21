"""Unit tests for TokenManager class."""

import os
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from github import Github, GithubException

from gh_pr.auth.token import TokenManager
from gh_pr.utils.config import ConfigManager


class TestTokenManagerInitialization:
    """Test TokenManager initialization and token discovery."""

    def test_init_with_provided_token(self):
        """Test initialization with explicitly provided token."""
        token = "ghp_FAKE_TOKEN_FOR_TESTING_ONLY"  # noqa: S105
        manager = TokenManager(token=token)
        assert manager.token == token
        assert manager._github is None

    @patch.dict(os.environ, {"GH_TOKEN": "ghp_FAKE_ENV_TOKEN"}, clear=True)  # noqa: S106
    def test_init_with_gh_token_env(self):
        """Test token discovery from GH_TOKEN environment variable."""
        manager = TokenManager()
        assert manager.token == "ghp_FAKE_ENV_TOKEN"  # noqa: S105

    @patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_FAKE_GITHUB_ENV_TOKEN"}, clear=True)  # noqa: S106
    def test_init_with_github_token_env(self):
        """Test token discovery from GITHUB_TOKEN environment variable."""
        manager = TokenManager()
        assert manager.token == "ghp_FAKE_GITHUB_ENV_TOKEN"  # noqa: S105

    @patch.dict(os.environ, {}, clear=True)
    @patch("subprocess.run")
    def test_init_with_gh_cli_token(self, mock_run):
        """Test token discovery from gh CLI."""
        # Mock gh CLI response
        mock_result = Mock()
        mock_result.stdout = "Token: ghp_FAKE_CLI_TOKEN"  # noqa: S105
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        manager = TokenManager()
        assert manager.token == "ghp_FAKE_CLI_TOKEN"  # noqa: S105

    @patch.dict(os.environ, {}, clear=True)
    def test_init_with_config_token(self):
        """Test token discovery from configuration file."""
        config = ConfigManager()
        config.set("github.token", "ghp_FAKE_CONFIG_TOKEN")  # noqa: S105

        manager = TokenManager(config_manager=config)
        assert manager.token == "ghp_FAKE_CONFIG_TOKEN"  # noqa: S105

    @patch.dict(os.environ, {}, clear=True)
    @patch("subprocess.run")
    def test_init_no_token_found(self, mock_run):
        """Test initialization when no token is found."""
        mock_run.side_effect = subprocess.SubprocessError()

        with pytest.raises(ValueError) as exc_info:
            TokenManager()
        assert "No GitHub token found" in str(exc_info.value)

    def test_priority_order(self):
        """Test token discovery priority order."""
        # Direct token has highest priority
        with patch.dict(os.environ, {"GH_TOKEN": "env_token"}):
            manager = TokenManager(token="direct_token")
            assert manager.token == "direct_token"

        # Environment variables have priority over config
        config = ConfigManager()
        config.set("github.token", "config_token")
        with patch.dict(os.environ, {"GH_TOKEN": "env_token"}):
            manager = TokenManager(config_manager=config)
            assert manager.token == "env_token"


class TestTokenValidation:
    """Test token validation functionality."""

    @patch("gh_pr.auth.token.Github")
    def test_validate_token_network_error(self, mock_github_class):
        """Test validation of a token when a network error occurs."""
        mock_github = Mock()
        # Simulate a network error (e.g., requests.exceptions.ConnectionError)
        import requests
        mock_github.get_user.side_effect = requests.exceptions.ConnectionError("Network failure")
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="ghp_network_error_token")  # noqa: S106
        assert manager.validate_token() is False

    @patch("gh_pr.auth.token.Github")
    def test_validate_token_unexpected_exception(self, mock_github_class):
        """Test validation of a token when an unexpected exception occurs."""
        mock_github = Mock()
        mock_github.get_user.side_effect = Exception("Unexpected error")
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="ghp_unexpected_error_token")  # noqa: S106
        assert manager.validate_token() is False

    @patch("gh_pr.auth.token.Github")
    def test_validate_token_valid(self, mock_github_class):
        """Test validation of a valid token."""
        # Setup mock
        mock_github = Mock()
        mock_user = Mock()
        mock_user.login = "testuser"
        mock_github.get_user.return_value = mock_user
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="ghp_valid_token")  # noqa: S106
        assert manager.validate_token() is True

    @patch("gh_pr.auth.token.Github")
    def test_validate_token_invalid(self, mock_github_class):
        """Test validation of an invalid token."""
        # Setup mock to raise GithubException
        mock_github = Mock()
        mock_github.get_user.side_effect = GithubException(401, {"message": "Bad credentials"})
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="ghp_invalid_token")  # noqa: S106
        assert manager.validate_token() is False


class TestTokenInfo:
    """Test token information retrieval."""

    @patch("gh_pr.auth.token.Github")
    def test_get_token_info_classic_pat(self, mock_github_class):
        """Test getting info for classic personal access token."""
        # Setup mock
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="ghp_FAKE_TEST_TOKEN_REPLACED")  # noqa: S106
        info = manager.get_token_info()

        assert info is not None
        assert info["type"] == "Classic Personal Access Token"
        assert info["rate_limit"]["limit"] == 5000
        assert info["rate_limit"]["remaining"] == 4999

    @patch("gh_pr.auth.token.Github")
    def test_get_token_info_fine_grained_pat(self, mock_github_class):
        """Test getting info for fine-grained personal access token."""
        # Setup mock
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="github_pat_fine_grained_token")  # noqa: S106
        info = manager.get_token_info()

        assert info is not None
        assert info["type"] == "Fine-grained Personal Access Token"

    @patch("gh_pr.auth.token.Github")
    def test_get_token_info_github_app(self, mock_github_class):
        """Test getting info for GitHub App installation token."""
        # Setup mock
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="ghs_app_token_12345")  # noqa: S106
        info = manager.get_token_info()

        assert info is not None
        assert info["type"] == "GitHub App Installation Token"

    @patch("gh_pr.auth.token.Github")
    def test_get_token_info_caching(self, mock_github_class):
        """Test that token info is cached."""
        # Setup mock
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="ghp_test_token")  # noqa: S106

        # First call
        info1 = manager.get_token_info()
        # Second call should use cache
        info2 = manager.get_token_info()

        assert info1 is info2  # Same object reference
        mock_github.get_rate_limit.assert_called_once()  # Only called once


class TestTokenExpiration:
    """Test token expiration checking."""

    @patch("gh_pr.auth.token.Github")
    def test_check_expiration_no_expiry(self, mock_github_class):
        """Test expiration check for token without expiry."""
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="ghp_classic_token")  # noqa: S106
        expiration = manager.check_expiration()

        assert expiration is None  # Classic tokens don't expire

    @patch("gh_pr.auth.token.Github")
    def test_check_expiration_fine_grained_with_metadata(self, mock_github_class):
        """Test expiration check for fine-grained token with stored metadata."""
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        # Setup config with expiration metadata
        config = ConfigManager()
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        # Use proper token key (first 16 chars of SHA256 hash)
        import hashlib
        token_key = hashlib.sha256("github_pat_fine_grained".encode()).hexdigest()[:16]
        config.set(f"tokens.{token_key}.expires_at", future_date.isoformat())

        manager = TokenManager(token="github_pat_fine_grained", config_manager=config)  # noqa: S106
        expiration = manager.check_expiration()

        assert expiration is not None
        assert expiration["expired"] is False
        assert expiration["days_remaining"] in [29, 30]
        assert expiration["warning"] is False

    @patch("gh_pr.auth.token.Github")
    def test_check_expiration_warning(self, mock_github_class):
        """Test expiration warning when token expires within 7 days."""
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        config = ConfigManager()
        near_future = datetime.now(timezone.utc) + timedelta(days=5)
        # Use proper token key (first 16 chars of SHA256 hash)
        import hashlib
        token_key = hashlib.sha256("github_pat_fine_grained".encode()).hexdigest()[:16]
        config.set(f"tokens.{token_key}.expires_at", near_future.isoformat())

        manager = TokenManager(token="github_pat_fine_grained", config_manager=config)  # noqa: S106
        expiration = manager.check_expiration()

        assert expiration is not None
        assert expiration["expired"] is False
        assert expiration["warning"] is True
        assert expiration["days_remaining"] <= 5

    @patch("gh_pr.auth.token.Github")
    def test_check_expiration_expired(self, mock_github_class):
        """Test expiration check for expired token."""
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        config = ConfigManager()
        past_date = datetime.now(timezone.utc) - timedelta(days=1)
        # Use proper token key (first 16 chars of SHA256 hash)
        import hashlib
        token_key = hashlib.sha256("github_pat_fine_grained".encode()).hexdigest()[:16]
        config.set(f"tokens.{token_key}.expires_at", past_date.isoformat())

        manager = TokenManager(token="github_pat_fine_grained", config_manager=config)  # noqa: S106
        expiration = manager.check_expiration()

        assert expiration is not None
        assert expiration["expired"] is True
        assert expiration["days_remaining"] <= 0

    @patch("gh_pr.auth.token.Github")
    def test_check_expiration_github_app_token(self, mock_github_class):
        """Test expiration check for GitHub App token."""
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="ghs_app_token")  # noqa: S106
        expiration = manager.check_expiration()

        assert expiration is not None
        # App tokens have estimated 1-hour expiry
        assert expiration["hours_remaining"] <= 1
        assert expiration["expired"] is False


class TestPermissions:
    """Test permission checking functionality."""

    @pytest.mark.xfail(reason="Scope detection for classic tokens is not yet implemented")
    @patch("gh_pr.auth.token.Github")
    def test_has_permissions_classic_token_with_scopes(self, mock_github_class):
        """Test permission checking for classic token with scopes.

        NOTE: This test is marked as expected failure because scope detection
        for classic tokens is not yet implemented. The get_token_info method
        currently hardcodes info["scopes"] = [] with a comment that this is
        a future improvement.
        """
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="ghp_classic_token")
        # Note: In real implementation, scopes would be set from API
        # For testing, we'd need to mock the scope retrieval
        with patch.object(manager, "get_token_info", return_value={
            "type": "Classic Personal Access Token",
            "scopes": ["repo", "write:discussion"],
        }):
            assert manager.has_permissions(["repo"]) is True
            assert manager.has_permissions(["repo", "write:discussion"]) is True
            assert manager.has_permissions(["admin:org"]) is False
    @patch("gh_pr.auth.token.Github")
    def test_has_permissions_fine_grained_token_success(self, mock_github_class):
        """Test permission checking for fine-grained token succeeds."""
        mock_github = Mock()
        mock_user = Mock()
        mock_repos = Mock()
        mock_repos.totalCount = 1
        mock_repo = Mock()

        # Setup mock responses for permission tests
        mock_repos.__getitem__ = Mock(return_value=mock_repo)
        mock_user.get_repos.return_value = mock_repos
        # Make the return values subscriptable to avoid TypeError
        mock_pulls = MagicMock()
        mock_pulls.__getitem__ = Mock(return_value=Mock())
        mock_repo.get_pulls.return_value = mock_pulls
        mock_issues = MagicMock()
        mock_issues.__getitem__ = Mock(return_value=Mock())
        mock_repo.get_issues.return_value = mock_issues

        mock_github.get_user.return_value = mock_user
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="github_pat_fine_grained")  # noqa: S106

        # Should successfully check permissions
        result = manager.has_permissions(["repo"])
        assert result is True

    @patch("gh_pr.auth.token.Github")
    def test_has_permissions_fine_grained_token_failure(self, mock_github_class):
        """Test permission checking for fine-grained token fails."""
        mock_github = Mock()

        # Setup mock to raise GithubException for permission denied
        mock_github.get_user.side_effect = GithubException(403, "Insufficient permissions")

        # Mock rate limit to avoid TypeError
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit

        mock_github_class.return_value = mock_github

        manager = TokenManager(token="github_pat_fine_grained")  # noqa: S106

        # Should fail permission check when API calls are denied
        result = manager.has_permissions(["repo"])
        assert result is False


class TestTokenMetadata:
    """Test token metadata storage functionality."""

    def test_store_token_metadata_with_expiration(self):
        """Test storing token metadata with expiration date."""
        config = ConfigManager()
        manager = TokenManager(token="github_pat_test_token", config_manager=config)  # noqa: S106

        expires_at = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        result = manager.store_token_metadata(expires_at=expires_at)

        assert result is True
        # Token key is first 16 chars of SHA256 hash
        import hashlib
        token_key = hashlib.sha256("github_pat_test_token".encode()).hexdigest()[:16]
        stored_value = config.get(f"tokens.{token_key}")
        assert stored_value is not None
        assert stored_value.get("expires_at") == expires_at

    def test_store_token_metadata_without_config(self):
        """Test storing metadata fails gracefully without config manager."""
        manager = TokenManager(token="ghp_test_token")  # noqa: S106
        result = manager.store_token_metadata()

        assert result is False  # Should return False when no config manager

    @patch("gh_pr.auth.token.Github")
    def test_store_token_metadata_with_type(self, mock_github_class):
        """Test storing token metadata includes token type."""
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        config = ConfigManager()
        manager = TokenManager(token="ghp_classic_token", config_manager=config)  # noqa: S106

        # Get token info to populate type
        manager.get_token_info()
        result = manager.store_token_metadata()

        assert result is True
        # Token key is first 16 chars of SHA256 hash
        import hashlib
        token_key = hashlib.sha256("ghp_FAKE_TEST_TOKEN_REPLACED".encode()).hexdigest()[:16]
        stored_value = config.get(f"tokens.{token_key}")
        assert stored_value is not None
        assert stored_value.get("type") == "Classic Personal Access Token"


class TestGitHubClient:
    """Test GitHub client creation."""

    @patch("gh_pr.auth.token.Github")
    def test_get_github_client(self, mock_github_class):
        """Test getting authenticated GitHub client."""
        mock_github = Mock()
        mock_github_class.return_value = mock_github

        manager = TokenManager(token="ghp_test_token")  # noqa: S106
        client1 = manager.get_github_client()
        client2 = manager.get_github_client()

        # Should return same cached instance
        assert client1 is client2
        assert client1 is mock_github
        # Should only create one instance
        assert mock_github_class.call_count == 1

    def test_get_token(self):
        """Test getting the current token."""
        token = "ghp_FAKE_TEST_TOKEN_REPLACED"  # noqa: S105
        manager = TokenManager(token=token)
        assert manager.get_token() == token
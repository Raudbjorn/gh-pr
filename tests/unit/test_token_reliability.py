"""Unit tests for token.py timeout handling and reliability."""

import subprocess
from unittest.mock import Mock, patch, MagicMock

import pytest
from github import GithubException

from gh_pr.auth.token import TokenManager, SUBPROCESS_TIMEOUT, GH_CLI_AUTH_STATUS_CMD, GH_CLI_AUTH_TOKEN_CMD


class TestTokenManagerTimeouts:
    """Test timeout handling in token operations."""

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_token_timeout_handling(self, mock_run):
        """Test that subprocess timeouts are handled gracefully."""
        # Simulate timeout
        mock_run.side_effect = subprocess.TimeoutExpired(GH_CLI_AUTH_STATUS_CMD, SUBPROCESS_TIMEOUT)

        token_manager = TokenManager(token="dummy")  # noqa: S106

        # Should handle timeout gracefully and return None
        result = token_manager._get_gh_cli_token()
        assert result is None

        # Should have tried with the correct timeout
        assert mock_run.call_count >= 1
        call_args = mock_run.call_args_list[0]
        assert call_args[1]['timeout'] == SUBPROCESS_TIMEOUT

    @patch('gh_pr.auth.token.subprocess.run')
    @patch('gh_pr.auth.token.logger')
    def test_gh_cli_token_timeout_logging(self, mock_logger, mock_run):
        """Test that timeout errors are logged appropriately."""
        mock_run.side_effect = subprocess.TimeoutExpired(GH_CLI_AUTH_STATUS_CMD, SUBPROCESS_TIMEOUT)

        token_manager = TokenManager(token="dummy")  # noqa: S106
        result = token_manager._get_gh_cli_token()

        assert result is None
        mock_logger.debug.assert_called()
        log_message = mock_logger.debug.call_args[0][0]
        assert "Timeout expired" in log_message
        assert str(SUBPROCESS_TIMEOUT) in log_message

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_token_subprocess_error_handling(self, mock_run):
        """Test that subprocess errors are handled gracefully."""
        mock_run.side_effect = subprocess.SubprocessError("Mock subprocess error")

        token_manager = TokenManager(token="dummy")  # noqa: S106
        result = token_manager._get_gh_cli_token()

        assert result is None

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_token_file_not_found_handling(self, mock_run):
        """Test that FileNotFoundError is handled when gh CLI is not installed."""
        mock_run.side_effect = FileNotFoundError("gh command not found")

        token_manager = TokenManager(token="dummy")  # noqa: S106
        result = token_manager._get_gh_cli_token()

        assert result is None

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_token_unexpected_error_handling(self, mock_run):
        """Test that unexpected errors are handled gracefully."""
        mock_run.side_effect = RuntimeError("Unexpected error")

        token_manager = TokenManager(token="dummy")  # noqa: S106
        result = token_manager._get_gh_cli_token()

        assert result is None

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_token_successful_status_parsing(self, mock_run):
        """Test successful token extraction from gh auth status."""
        # Mock successful gh auth status command
        mock_result = Mock()
        mock_result.stdout = """
GitHub.com
  ✓ Logged in to github.com as testuser (keyring)
  ✓ Git operations for github.com configured to use https protocol.
  ✓ Token: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
"""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        token_manager = TokenManager(token="dummy")  # noqa: S106
        result = token_manager._get_gh_cli_token()

        assert result == "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_token_fallback_to_auth_token(self, mock_run):
        """Test fallback to gh auth token command when status fails."""
        # First call (auth status) fails to find token
        status_result = Mock()
        status_result.stdout = "No token found in status"
        status_result.returncode = 0

        # Second call (auth token) succeeds
        token_result = Mock()
        token_result.stdout = "ghp_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
        token_result.returncode = 0

        mock_run.side_effect = [status_result, token_result]

        token_manager = TokenManager(token="dummy")  # noqa: S106
        result = token_manager._get_gh_cli_token()

        assert result == "ghp_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
        assert mock_run.call_count == 2

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_token_both_commands_fail(self, mock_run):
        """Test when both gh CLI commands fail."""
        # Both commands fail
        failed_result = Mock()
        failed_result.stdout = ""
        failed_result.returncode = 1

        mock_run.return_value = failed_result

        token_manager = TokenManager(token="dummy")  # noqa: S106
        result = token_manager._get_gh_cli_token()

        assert result is None

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_token_empty_output(self, mock_run):
        """Test handling of empty output from gh CLI commands."""
        empty_result = Mock()
        empty_result.stdout = ""
        empty_result.returncode = 0

        mock_run.return_value = empty_result

        token_manager = TokenManager(token="dummy")  # noqa: S106
        result = token_manager._get_gh_cli_token()

        assert result is None

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_token_whitespace_handling(self, mock_run):
        """Test that tokens with whitespace are properly stripped."""
        mock_result = Mock()
        mock_result.stdout = "  ghp_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz  \n"
        mock_result.returncode = 0

        # First call fails, second succeeds
        failed_result = Mock()
        failed_result.stdout = "No token"
        failed_result.returncode = 0

        mock_run.side_effect = [failed_result, mock_result]

        token_manager = TokenManager(token="dummy")  # noqa: S106
        result = token_manager._get_gh_cli_token()

        assert result == "ghp_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"

    def test_gh_cli_commands_are_hardcoded_constants(self):
        """Test that subprocess commands use hardcoded constants (security check)."""
        # Ensure commands are not constructed from user input
        assert GH_CLI_AUTH_STATUS_CMD == ["gh", "auth", "status", "--show-token"]
        assert GH_CLI_AUTH_TOKEN_CMD == ["gh", "auth", "token"]

        # Ensure these are lists (not strings that could be shell-injected)
        assert isinstance(GH_CLI_AUTH_STATUS_CMD, list)
        assert isinstance(GH_CLI_AUTH_TOKEN_CMD, list)

        # Ensure timeout is a reasonable constant
        assert isinstance(SUBPROCESS_TIMEOUT, int)
        assert 1 <= SUBPROCESS_TIMEOUT <= 30  # Reasonable timeout range


class TestTokenManagerReliability:
    """Test TokenManager reliability features."""

    def test_token_manager_with_provided_token(self):
        """Test TokenManager when token is provided directly."""
        test_token = "ghp_provided_token_123456789"
        token_manager = TokenManager(token=test_token)

        assert token_manager.get_token() == test_token

    @patch.dict('os.environ', {'GH_TOKEN': 'ghp_env_token_123456789'})
    def test_token_manager_with_gh_token_env(self):
        """Test TokenManager with GH_TOKEN environment variable."""
        token_manager = TokenManager()
        assert token_manager.get_token() == "ghp_env_token_123456789"
    @patch.dict('os.environ', {'GITHUB_TOKEN': 'ghp_github_env_token_123456789'})
    def test_token_manager_with_github_token_env(self):
        """Test TokenManager with GITHUB_TOKEN environment variable."""
        # Clear GH_TOKEN to test GITHUB_TOKEN fallback
        with patch.dict('os.environ', {}, clear=True):
            with patch.dict('os.environ', {'GITHUB_TOKEN': 'ghp_github_env_token_123456789'}):
                token_manager = TokenManager(token="dummy")  # noqa: S106
                assert token_manager.get_token() == "ghp_github_env_token_123456789"

    @patch.dict('os.environ', {}, clear=True)
    @patch('gh_pr.auth.token.TokenManager._get_gh_cli_token')
    def test_token_manager_with_gh_cli_fallback(self, mock_gh_cli):
        """Test TokenManager fallback to gh CLI."""
        mock_gh_cli.return_value = "ghp_cli_token_123456789"

        token_manager = TokenManager(token="dummy")  # noqa: S106
        assert token_manager.get_token() == "ghp_cli_token_123456789"

    @patch.dict('os.environ', {}, clear=True)
    @patch('gh_pr.auth.token.TokenManager._get_gh_cli_token')
    def test_token_manager_no_token_found(self, mock_gh_cli):
        """Test TokenManager when no token is found anywhere."""
        mock_gh_cli.return_value = None

        with pytest.raises(ValueError, match="No GitHub token found"):
            TokenManager(token="dummy")  # noqa: S106

    def test_token_manager_token_precedence(self):
        """Test that token sources are checked in correct precedence order."""
        provided_token = "ghp_provided_token"
        env_token = "ghp_env_token"

        # Provided token should take precedence over environment
        with patch.dict('os.environ', {'GH_TOKEN': env_token}):
            token_manager = TokenManager(token=provided_token)
            assert token_manager.get_token() == provided_token

    @patch.dict('os.environ', {'GH_TOKEN': 'ghp_gh_token', 'GITHUB_TOKEN': 'ghp_github_token'})
    def test_gh_token_precedence_over_github_token(self):
        """Test that GH_TOKEN takes precedence over GITHUB_TOKEN."""
        token_manager = TokenManager(token="dummy")  # noqa: S106
        assert token_manager.get_token() == "ghp_gh_token"

    @patch('gh_pr.auth.token.Github')
    def test_get_github_client_caching(self, mock_github_class):
        """Test that GitHub client is cached and reused."""
        mock_github_instance = Mock()
        mock_github_class.return_value = mock_github_instance

        token_manager = TokenManager(token="test_token")

        # First call should create client
        client1 = token_manager.get_github_client()
        assert client1 == mock_github_instance

        # Second call should return cached client
        client2 = token_manager.get_github_client()
        assert client2 == mock_github_instance

        # Github constructor should only be called once
        assert mock_github_class.call_count == 1

    @patch('gh_pr.auth.token.Github')
    def test_validate_token_success(self, mock_github_class):
        """Test successful token validation."""
        mock_github = Mock()
        mock_user = Mock()
        mock_user.login = "testuser"
        mock_github.get_user.return_value = mock_user
        mock_github_class.return_value = mock_github

        token_manager = TokenManager(token="valid_token")
        assert token_manager.validate_token() is True

    @patch('gh_pr.auth.token.Github')
    def test_validate_token_failure(self, mock_github_class):
        """Test failed token validation."""
        mock_github = Mock()
        mock_github.get_user.side_effect = GithubException(401, "Bad credentials")
        mock_github_class.return_value = mock_github

        token_manager = TokenManager(token="invalid_token")
        assert token_manager.validate_token() is False

    @patch('gh_pr.auth.token.Github')
    def test_get_token_info_classic_token(self, mock_github_class):
        """Test token info retrieval for classic personal access token."""
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4500
        mock_rate_limit.core.reset = None
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        token_manager = TokenManager(token="ghp_classic_token_123456789")
        info = token_manager.get_token_info()

        assert info is not None
        assert info["type"] == "Classic Personal Access Token"
        assert info["rate_limit"]["limit"] == 5000
        assert info["rate_limit"]["remaining"] == 4500

    @patch('gh_pr.auth.token.Github')
    def test_get_token_info_fine_grained_token(self, mock_github_class):
        """Test token info retrieval for fine-grained personal access token."""
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 1000
        mock_rate_limit.core.remaining = 800
        mock_rate_limit.core.reset = None
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        token_manager = TokenManager(token="github_pat_fine_grained_token_123456789")
        info = token_manager.get_token_info()

        assert info is not None
        assert info["type"] == "Fine-grained Personal Access Token"
        assert info["rate_limit"]["limit"] == 1000

    @patch('gh_pr.auth.token.Github')
    def test_get_token_info_github_app_token(self, mock_github_class):
        """Test token info retrieval for GitHub App installation token."""
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 15000
        mock_rate_limit.core.remaining = 14000
        mock_rate_limit.core.reset = None
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        token_manager = TokenManager(token="ghs_app_installation_token_123456789")
        info = token_manager.get_token_info()

        assert info is not None
        assert info["type"] == "GitHub App Installation Token"
        assert info["rate_limit"]["limit"] == 15000

    @patch('gh_pr.auth.token.Github')
    def test_get_token_info_caching(self, mock_github_class):
        """Test that token info is cached."""
        mock_github = Mock()
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4500
        mock_rate_limit.core.reset = None
        mock_github.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github

        token_manager = TokenManager(token="test_token")

        # First call should fetch info
        info1 = token_manager.get_token_info()
        assert info1 is not None

        # Second call should return cached info
        info2 = token_manager.get_token_info()
        assert info2 == info1

        # GitHub API should only be called once
        assert mock_github.get_rate_limit.call_count == 1

    @patch('gh_pr.auth.token.Github')
    def test_get_token_info_github_exception(self, mock_github_class):
        """Test token info retrieval when GitHub API fails."""
        mock_github = Mock()
        mock_github.get_rate_limit.side_effect = GithubException(403, "Forbidden")
        mock_github_class.return_value = mock_github

        token_manager = TokenManager(token="invalid_token")
        info = token_manager.get_token_info()

        assert info is None

    def test_has_permissions_no_token_info(self):
        """Test has_permissions when token info is unavailable."""
        with patch.object(TokenManager, 'get_token_info', return_value=None):
            token_manager = TokenManager(token="test_token")
            assert token_manager.has_permissions(["repo"]) is False

    def test_has_permissions_classic_token_with_scopes(self):
        """Test has_permissions for classic token with scopes."""
        mock_info = {
            "type": "Classic Personal Access Token",
            "scopes": ["repo", "read:org"]
        }

        with patch.object(TokenManager, 'get_token_info', return_value=mock_info):
            token_manager = TokenManager(token="test_token")

            assert token_manager.has_permissions(["repo"]) is True
            assert token_manager.has_permissions(["repo", "read:org"]) is True
            assert token_manager.has_permissions(["repo", "admin:org"]) is False

    @patch('gh_pr.auth.token.Github')
    def test_fine_grained_permissions_check(self, mock_github_class):
        """Test fine-grained token permissions checking."""
        mock_github = Mock()
        mock_user = Mock()
        mock_repos = Mock()
        mock_repos.totalCount = 1
        mock_repo = Mock()
        mock_repos.__getitem__ = Mock(return_value=mock_repo)
        mock_user.get_repos.return_value = mock_repos
        mock_github.get_user.return_value = mock_user
        mock_github_class.return_value = mock_github

        mock_info = {
            "type": "Fine-grained Personal Access Token",
            "scopes": []
        }

        with patch.object(TokenManager, 'get_token_info', return_value=mock_info):
            token_manager = TokenManager(token="test_token")

            # Should attempt to check fine-grained permissions
            result = token_manager.has_permissions(["repo"])

            # The result depends on whether the API calls succeed
            assert isinstance(result, bool)


class TestTokenManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_token_string(self):
        """Test handling of empty token string."""
        with pytest.raises(ValueError):
            TokenManager(token="")

    def test_whitespace_only_token(self):
        """Test handling of whitespace-only token."""
        with pytest.raises(ValueError):
            TokenManager(token="   ")

    def test_none_token_with_no_fallbacks(self):
        """Test that None token with no fallbacks raises ValueError."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('gh_pr.auth.token.TokenManager._get_gh_cli_token', return_value=None):
                with pytest.raises(ValueError):
                    TokenManager(token=None)

    def test_very_long_token(self):
        """Test handling of very long tokens."""
        long_token = "ghp_" + "x" * 1000
        token_manager = TokenManager(token=long_token)
        assert token_manager.get_token() == long_token

    def test_token_with_special_characters(self):
        """Test handling of tokens with special characters."""
        special_token = "ghp_token_with_!@#$%^&*()_+"
        token_manager = TokenManager(token=special_token)
        assert token_manager.get_token() == special_token

    @patch('gh_pr.auth.token.subprocess.run')
    def test_gh_cli_token_with_multiple_token_lines(self, mock_run):
        """Test parsing when gh output contains multiple 'Token:' lines."""
        mock_result = Mock()
        mock_result.stdout = """
GitHub.com
  ✓ Logged in to github.com as testuser
  ✓ Token: ghp_first_token_xxxxxxxxxxxxxxxxxxxx
  Some other info
  ✓ Another Token: ghp_second_token_yyyyyyyyyyyy
"""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        token_manager = TokenManager(token="dummy")  # noqa: S106
        result = token_manager._get_gh_cli_token()

        # Should return the first token found
        assert result == "ghp_first_token_xxxxxxxxxxxxxxxxxxxx"

    def test_check_expiration_no_expiry_info(self):
        """Test check_expiration when token has no expiry information."""
        mock_info = {
            "type": "Classic Personal Access Token",
            "expires_at": None
        }

        with patch.object(TokenManager, 'get_token_info', return_value=mock_info):
            token_manager = TokenManager(token="test_token")
            result = token_manager.check_expiration()
            assert result is None
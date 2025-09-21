"""Integration tests for token management features."""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner
from github import Github

from gh_pr.auth.token import TokenManager, SUBPROCESS_TIMEOUT
from gh_pr.cli import main
from gh_pr.utils.config import ConfigManager


class TestTokenIntegration:
    """Integration tests for token management."""

    def _create_mock_github_with_user(self, username="testuser"):
        """Create a mock GitHub instance with user setup."""
        mock_github = Mock()
        mock_user = Mock()
        mock_user.login = username
        mock_github.get_user.return_value = mock_user
        return mock_github

    def _create_mock_rate_limit(self, limit=5000, remaining=4999, hours_until_reset=1):
        """Create a mock rate limit object."""
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = limit
        mock_rate_limit.core.remaining = remaining
        mock_rate_limit.core.reset = datetime.now(timezone.utc) + timedelta(hours=hours_until_reset)
        return mock_rate_limit

    def _setup_complete_github_mock(self, username="testuser"):
        """Create a complete GitHub mock with user and rate limit."""
        mock_github = self._create_mock_github_with_user(username)
        mock_rate_limit = self._create_mock_rate_limit()
        mock_github.get_rate_limit.return_value = mock_rate_limit
        return mock_github

    def _create_mock_github_with_permissions(self, username="testuser"):
        """Create a GitHub mock with user and repository permissions."""
        mock_github = self._create_mock_github_with_user(username)

        # Setup repository access
        mock_repos = Mock()
        mock_repos.totalCount = 2
        mock_repo = Mock()
        mock_repo.get_pulls.return_value = []
        mock_repo.get_issues.return_value = []
        mock_repos.__getitem__ = Mock(return_value=mock_repo)

        mock_github.get_user.return_value.get_repos.return_value = mock_repos

        # Add rate limit
        mock_rate_limit = self._create_mock_rate_limit()
        mock_github.get_rate_limit.return_value = mock_rate_limit

        return mock_github

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary config file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write("""
[github]
token = "ghp_FAKE_CONFIG_TOKEN_FOR_TESTS_ONLY"  # noqa: S105
check_token_expiry = true

[cache]
enabled = false
""")
            yield f.name
        # Cleanup
        Path(f.name).unlink(missing_ok=True)

    @pytest.fixture
    def mock_github(self):
        """Mock GitHub API responses."""
        with patch("gh_pr.auth.token.Github") as mock_github_class:
            mock_github = self._setup_complete_github_mock()
            mock_github_class.return_value = mock_github
            yield mock_github

    def test_token_info_command(self, mock_github):
        """Test --token-info command displays detailed token information."""
        runner = CliRunner()
        with patch.dict(os.environ, {"GH_TOKEN": "ghp_FAKE_ENV_TOKEN_FOR_TESTS"}):  # noqa: S106
            result = runner.invoke(main, ["--token-info"])

        assert result.exit_code == 0
        assert "GitHub Token Information" in result.output
        assert "Token Type:" in result.output
        assert "Rate Limit:" in result.output
        assert "Testing Permissions:" in result.output

    def test_token_from_config_file(self, temp_config_file, mock_github):
        """Test token loading from configuration file."""
        runner = CliRunner()
        with patch.dict(os.environ, {}, clear=True):
            result = runner.invoke(main, ["--config", temp_config_file, "--token-info"])

        assert result.exit_code == 0
        assert "Token Type:" in result.output

    def test_token_expiration_warning_displayed(self, mock_github):
        """Test that token expiration warning is displayed."""
        runner = CliRunner()

        # Mock token with near expiration
        with patch("gh_pr.auth.token.TokenManager.check_expiration") as mock_exp:
            mock_exp.return_value = {
                "expired": False,
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
                "days_remaining": 5,
                "warning": True,
            }

            with patch.dict(os.environ, {"GH_TOKEN": "github_pat_test_token"}):  # noqa: S106
                result = runner.invoke(main, ["--token-info"])

        assert result.exit_code == 0
        assert "Expiring" in result.output or "warning" in result.output.lower()

    def test_expired_token_error(self, mock_github):
        """Test that expired token shows error."""
        runner = CliRunner()

        # Mock expired token
        with patch("gh_pr.auth.token.TokenManager.check_expiration") as mock_exp:
            mock_exp.return_value = {
                "expired": True,
                "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                "days_remaining": -1,
                "warning": False,
            }

            with patch.dict(os.environ, {"GH_TOKEN": "github_pat_expired_token"}):  # noqa: S106
                # Don't auto-confirm the prompt
                result = runner.invoke(main, ["53"], input="n\n")

        # Should exit with error when user doesn't confirm
        assert result.exit_code != 0

    def test_expired_token_user_confirms_continue(self, mock_github):
        """Test expired token with user confirmation to continue."""
        runner = CliRunner()

        # Mock expired token
        with patch("gh_pr.auth.token.TokenManager.check_expiration") as mock_exp:
            mock_exp.return_value = {
                "expired": True,
                "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                "days_remaining": -1,
                "warning": False,
            }

            # Simulate user confirmation with 'y' input
            with patch.dict(os.environ, {"GH_TOKEN": "github_pat_expired_token"}):  # noqa: S106
                result = runner.invoke(main, ["--token-info"], input="y\n")

        # The CLI should continue even with expired token when user confirms
        assert "expired" in result.output.lower()

    def test_gh_cli_token_fallback(self, mock_github):
        """Test that gh CLI token is used as fallback when other sources unavailable."""
        runner = CliRunner()

        # Clear env vars and no config file
        with patch.dict(os.environ, {}, clear=True):
            with patch("gh_pr.auth.token.TokenManager._get_gh_cli_token") as mock_gh:
                mock_gh.return_value = "ghp_gh_cli_token"

                with patch("gh_pr.auth.token.TokenManager.validate_token") as mock_val:
                    mock_val.return_value = True

                    with patch("gh_pr.auth.token.TokenManager.get_token_info") as mock_info:
                        mock_info.return_value = {
                            "type": "Classic Personal Access Token",
                            "rate_limit": {"limit": 5000, "remaining": 4999},
                        }

                        result = runner.invoke(main, ["--token-info"])

        assert result.exit_code == 0
        assert "Token Type:" in result.output

    def test_token_priority_order_integration(self, temp_config_file, mock_github):
        """Test token discovery priority order in full CLI context."""
        runner = CliRunner()

        # Test 1: Direct token flag has highest priority
        with patch.dict(os.environ, {"GH_TOKEN": "env_token"}):
            with patch("gh_pr.auth.token.TokenManager.get_token") as mock_get:
                mock_get.return_value = "direct_token"
                result = runner.invoke(main, ["--token", "direct_token", "--token-info"])
                mock_get.assert_called()

        # Test 2: Environment variable has priority over config
        with patch.dict(os.environ, {"GH_TOKEN": "env_token"}):
            with patch.multiple(
                "gh_pr.auth.token.TokenManager",
                __init__=Mock(return_value=None),
                validate_token=Mock(return_value=True),
                get_token_info=Mock(return_value={"type": "test"})
            ):
                result = runner.invoke(main, ["--config", temp_config_file, "--token-info"])


class TestTokenPermissions:
    """Integration tests for permission checking."""

    def _create_mock_github_with_permissions(self, username="testuser"):
        """Create a GitHub mock with user and repository permissions."""
        mock_github = Mock()
        mock_user = Mock()
        mock_user.login = username
        mock_github.get_user.return_value = mock_user

        # Setup repository access
        mock_repos = Mock()
        mock_repos.totalCount = 2
        mock_repo = Mock()
        mock_repo.get_pulls.return_value = []
        mock_repo.get_issues.return_value = []
        mock_repos.__getitem__ = Mock(return_value=mock_repo)

        mock_user.get_repos.return_value = mock_repos

        # Add rate limit
        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_github.get_rate_limit.return_value = mock_rate_limit

        return mock_github

    @pytest.fixture
    def mock_github_with_permissions(self):
        """Mock GitHub with permission testing capabilities."""
        with patch("gh_pr.auth.token.Github") as mock_github_class:
            mock_github = self._create_mock_github_with_permissions()
            mock_github_class.return_value = mock_github
            yield mock_github

    def test_permission_check_for_automation(self, mock_github_with_permissions):
        """Test permission checking before automation commands."""
        runner = CliRunner()

        with patch.dict(os.environ, {"GH_TOKEN": "ghp_FAKE_TEST_TOKEN_PERMISSIONS"}):  # noqa: S106
            # Try to use automation without proper permissions
            with patch("gh_pr.auth.token.TokenManager.has_permissions") as mock_perm:
                mock_perm.return_value = False

                # Should warn about missing permissions
                result = runner.invoke(main, ["--resolve-outdated", "53"], input="n\n")

                assert "Token lacks required permissions" in result.output
                mock_perm.assert_called_with(["repo", "write:discussion"])

    def test_fine_grained_token_permission_detection(self):
        """Test permission detection for fine-grained tokens."""
        config = ConfigManager()
        manager = TokenManager(token="github_pat_fine_grained", config_manager=config)  # noqa: S106

        with patch.object(manager, "_check_fine_grained_permissions") as mock_check:
            mock_check.return_value = True

            result = manager.has_permissions(["repo"])

            assert result is True
            mock_check.assert_called_once_with(["repo"])


class TestTokenStorage:
    """Integration tests for token storage in configuration."""

    def _create_token_manager_with_mock_github(self, token="github_pat_test123", config_manager=None):
        """Helper method to create TokenManager with mocked GitHub API."""
        manager = TokenManager(token=token, config_manager=config_manager)  # noqa: S106

        with patch("gh_pr.auth.token.Github") as mock_github_class:
            mock_github = Mock()
            mock_rate_limit = Mock()
            mock_rate_limit.core.limit = 5000
            mock_rate_limit.core.remaining = 4999
            mock_rate_limit.core.reset = datetime.now(timezone.utc)
            mock_github.get_rate_limit.return_value = mock_rate_limit

            mock_user = Mock()
            mock_user.login = "testuser"
            mock_github.get_user.return_value = mock_user

            mock_github_class.return_value = mock_github
            yield manager, mock_github

    def test_store_and_retrieve_token_metadata(self):
        """Test storing and retrieving token metadata from configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"

            # Create and save config with token metadata
            config = ConfigManager(str(config_path))
            manager = TokenManager(token="github_pat_test123", config_manager=config)  # noqa: S106

            expires_at = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
            manager.store_token_metadata(expires_at=expires_at)

            # Save config to file
            config.save(str(config_path))

            # Load config in new instance
            config2 = ConfigManager(str(config_path))
            # Get the hashed token key that was actually stored
            token_key = manager._get_token_key()
            stored_metadata = config2.get(f"tokens.{token_key}")

            assert stored_metadata is not None
            assert stored_metadata["expires_at"] == expires_at
            assert "created_at" in stored_metadata

    def test_token_expiration_from_stored_metadata(self):
        """Test loading token expiration from stored metadata."""
        config = ConfigManager()

        # Create token manager first to get the proper hashed key
        manager = TokenManager(token="github_pat_12345", config_manager=config)  # noqa: S106
        token_key = manager._get_token_key()

        # Store metadata for a token using the correct hashed key
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        config.set(f"tokens.{token_key}.expires_at", future_date.isoformat())

        with patch("gh_pr.auth.token.Github") as mock_github_class:
            mock_github = Mock()
            mock_rate_limit = Mock()
            mock_rate_limit.core.limit = 5000
            mock_rate_limit.core.remaining = 4999
            mock_rate_limit.core.reset = datetime.now(timezone.utc)
            mock_github.get_rate_limit.return_value = mock_rate_limit
            mock_github_class.return_value = mock_github

            # Get token info should include expiration from metadata
            info = manager.get_token_info()
            assert info["expires_at"] == future_date.isoformat()
            assert info["days_remaining"] in [29, 30]  # Depending on exact timing

            # Check expiration should use the stored metadata
            expiration = manager.check_expiration()
            assert expiration is not None
            assert expiration["expired"] is False
            assert expiration["warning"] is False

    def test_gh_cli_token_fallback_integration(self):
        """Test that gh CLI token fallback works when no other token sources are available."""
        with patch("subprocess.run") as mock_subprocess:
            # Mock successful gh CLI auth status check
            mock_subprocess.side_effect = [
                # First call: gh auth status --show-token (succeeds)
                Mock(
                    returncode=0,
                    stdout="Logged in to github.com as testuser (oauth_token)\nToken: ghp_FAKE_CLI_FALLBACK_TOKEN\n",
                    stderr=""
                ),
                # Second call: gh auth token (fallback, also succeeds)
                Mock(
                    returncode=0,
                    stdout="ghp_FAKE_CLI_FALLBACK_TOKEN\n",
                    stderr=""
                )
            ]

            # Ensure no environment variables interfere
            env_vars_to_clear = ['GH_TOKEN', 'GITHUB_TOKEN', 'GH_ACCESS_TOKEN']
            with patch.dict(os.environ, {var: "" for var in env_vars_to_clear}, clear=False):
                # Create manager without explicit token (should fallback to gh CLI)
                manager = TokenManager()

                # Should successfully get token from gh CLI
                token = manager.get_token()
                assert token == "ghp_FAKE_CLI_FALLBACK_TOKEN"

                # Verify both subprocess calls were made correctly
                assert mock_subprocess.call_count == 2

                # First call should be gh auth status --show-token
                first_call = mock_subprocess.call_args_list[0]
                assert first_call[0][0] == ["gh", "auth", "status", "--show-token"]
                assert first_call[1]["capture_output"] is True
                assert first_call[1]["text"] is True
                assert first_call[1]["timeout"] == SUBPROCESS_TIMEOUT

                # Second call should be gh auth token
                second_call = mock_subprocess.call_args_list[1]
                assert second_call[0][0] == ["gh", "auth", "token"]
                assert second_call[1]["capture_output"] is True
                assert second_call[1]["text"] is True
                assert second_call[1]["timeout"] == SUBPROCESS_TIMEOUT

    def test_gh_cli_token_fallback_failure_integration(self):
        """Test behavior when gh CLI token fallback fails."""
        import subprocess as subprocess_module

        with patch("subprocess.run") as mock_subprocess:
            # Mock gh CLI commands failing
            mock_subprocess.side_effect = subprocess_module.SubprocessError("gh command failed")

            # Ensure no environment variables provide tokens
            env_vars_to_clear = ['GH_TOKEN', 'GITHUB_TOKEN', 'GH_ACCESS_TOKEN']
            with patch.dict(os.environ, {var: "" for var in env_vars_to_clear}, clear=False):
                # TokenManager.__init__ calls _get_token which raises ValueError on discovery failure
                with pytest.raises(ValueError) as exc_info:
                    TokenManager()

                # Verify the error message is appropriate
                assert "No GitHub token found" in str(exc_info.value)

                # Verify subprocess was attempted (gh CLI fallback was tried)
                assert mock_subprocess.call_count >= 1


class TestCLITokenFeatures:
    """Integration tests for CLI token features."""

    def _create_mock_github_with_user_and_rate_limit(self, username="testuser"):
        """Create a mock GitHub instance with user and rate limit setup."""
        mock_github = Mock()
        mock_user = Mock()
        mock_user.login = username
        mock_github.get_user.return_value = mock_user

        mock_rate_limit = Mock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4999
        mock_rate_limit.core.reset = datetime.now(timezone.utc)
        mock_github.get_rate_limit.return_value = mock_rate_limit

        return mock_github

    def _create_mock_pr_summary(self):
        """Create a default mock PR summary."""
        return {
            "total_threads": 0,
            "unresolved_active": 0,
            "unresolved_outdated": 0,
            "resolved_active": 0,
            "resolved_outdated": 0,
            "approvals": 0,
            "changes_requested": 0,
            "comments": 0,
        }

    def test_verbose_mode_shows_token_info(self):
        """Test that verbose mode displays token information."""
        runner = CliRunner()

        with patch("gh_pr.auth.token.Github") as mock_github_class:
            mock_github = self._create_mock_github_with_user_and_rate_limit()
            mock_github.get_pull_request = Mock()
            mock_github_class.return_value = mock_github

            with patch.dict(os.environ, {"GH_TOKEN": "ghp_FAKE_TEST_TOKEN_VERBOSE"}):  # noqa: S106
                with patch("gh_pr.core.pr_manager.PRManager.auto_detect_pr") as mock_auto:
                    mock_auto.return_value = "owner/repo#1"
                    with patch("gh_pr.core.pr_manager.PRManager.fetch_pr_data") as mock_fetch:
                        mock_fetch.return_value = {
                            "number": 1,
                            "title": "Test PR",
                            "state": "open",
                            "author": "testuser",
                        }
                        with patch("gh_pr.core.pr_manager.PRManager.fetch_pr_comments") as mock_comments:
                            mock_comments.return_value = []
                            with patch("gh_pr.core.pr_manager.PRManager.get_pr_summary") as mock_summary:
                                mock_summary.return_value = self._create_mock_pr_summary()

                                result = runner.invoke(main, ["--verbose"])

        assert result.exit_code == 0
        assert "Token Information" in result.output or "Rate Limit" in result.output

    def test_invalid_token_error_message(self):
        """Test error message for invalid token."""
        runner = CliRunner()

        with patch("gh_pr.auth.token.TokenManager.validate_token") as mock_validate:
            mock_validate.return_value = False

            with patch.dict(os.environ, {"GH_TOKEN": "invalid_token"}):
                result = runner.invoke(main, ["53"])

        assert result.exit_code == 1
        assert "Invalid or expired GitHub token" in result.output

    def test_missing_token_error_message(self):
        """Test error message when no token is provided."""
        runner = CliRunner()

        # Clear all token sources
        with patch.dict(os.environ, {}, clear=True):
            with patch("gh_pr.auth.token.TokenManager._get_gh_cli_token") as mock_gh:
                mock_gh.return_value = None

                with patch("gh_pr.auth.token.ConfigManager.get") as mock_cfg:
                    mock_cfg.return_value = None

                    result = runner.invoke(main, ["53"])

        assert result.exit_code != 0
        assert "token" in result.output.lower() or "authentication" in result.output.lower()

    def test_gh_cli_fallback_integration(self):
        """Test that gh CLI token is used when other sources are unavailable."""
        runner = CliRunner()

        # Clear environment variables so gh CLI fallback is used
        with patch.dict(os.environ, {}, clear=True):
            with patch("gh_pr.auth.token.TokenManager._get_gh_cli_token") as mock_gh_cli:
                mock_gh_cli.return_value = "ghp_cli_fallback_token"

                with patch("gh_pr.auth.token.Github") as mock_github_class:
                    mock_github = Mock()
                    mock_user = Mock()
                    mock_user.login = "testuser"
                    mock_github.get_user.return_value = mock_user

                    mock_rate_limit = Mock()
                    mock_rate_limit.core.limit = 5000
                    mock_rate_limit.core.remaining = 4999
                    mock_rate_limit.core.reset = datetime.now(timezone.utc)
                    mock_github.get_rate_limit.return_value = mock_rate_limit
                    mock_github_class.return_value = mock_github

                    result = runner.invoke(main, ["--token-info"])

        assert result.exit_code == 0
        assert "Token Type:" in result.output
        # Verify gh CLI token was used
        mock_gh_cli.assert_called()
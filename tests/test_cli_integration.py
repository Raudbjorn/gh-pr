"""Integration tests for CLI functionality."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from click.testing import CliRunner
from github import GithubException

from gh_pr.cli import cli_group as cli


class TestCLIIntegration:
    """Test CLI integration scenarios."""

    @pytest.fixture
    def runner(self):
        """Create a CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_github_client(self):
        """Create a mock GitHub client."""
        with patch('gh_pr.cli.GitHubClient') as mock:
            yield mock

    @pytest.fixture
    def mock_pr_manager(self):
        """Create a mock PR manager."""
        with patch('gh_pr.cli.PRManager') as mock:
            yield mock

    @pytest.fixture
    def mock_token_manager(self):
        """Create a mock token manager."""
        with patch('gh_pr.cli.TokenManager') as mock:
            mock_instance = mock.return_value
            mock_instance.get_token.return_value = "test_token"
            mock_instance.validate_token.return_value = True
            yield mock

    def test_cli_help(self, runner):
        """Test CLI help output."""
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'GitHub PR Review Tool' in result.output
        assert 'Options:' in result.output
        assert 'Commands:' in result.output

    def test_view_command_with_pr_url(self, runner, mock_github_client, mock_pr_manager, mock_token_manager):
        """Test view command with PR URL."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
        mock_manager.fetch_pr_data.return_value = {
            "number": 42,
            "title": "Test PR",
            "state": "open",
        }

        result = runner.invoke(cli, ['view', 'https://github.com/owner/repo/pull/42'])
        assert result.exit_code == 0

    def test_view_command_with_auto_detect(self, runner, mock_pr_manager, mock_token_manager):
        """Test view command with auto-detection."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.auto_detect_pr.return_value = "owner/repo#42"
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
        mock_manager.fetch_pr_data.return_value = {
            "number": 42,
            "title": "Auto-detected PR",
            "state": "open",
        }

        result = runner.invoke(cli, ['view'])
        assert result.exit_code == 0

    def test_view_command_no_pr_found(self, runner, mock_pr_manager, mock_token_manager):
        """Test view command when no PR is found."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.auto_detect_pr.return_value = None

        result = runner.invoke(cli, ['view'])
        assert result.exit_code != 0
        assert "No PR identifier provided" in result.output

    def test_comments_command(self, runner, mock_pr_manager, mock_token_manager):
        """Test comments command."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
        mock_manager.fetch_pr_comments.return_value = [
            {
                "id": "thread1",
                "path": "file.py",
                "comments": [{"body": "Test comment"}],
            }
        ]

        result = runner.invoke(cli, ['comments', 'owner/repo#42'])
        assert result.exit_code == 0

    def test_comments_command_with_filters(self, runner, mock_pr_manager, mock_token_manager):
        """Test comments command with filters."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
        mock_manager.fetch_pr_comments.return_value = []

        result = runner.invoke(cli, [
            'comments', 'owner/repo#42',
            '--filter', 'unresolved',
            '--author', 'reviewer1',
            '--path', 'src/main.py'
        ])
        assert result.exit_code == 0

    def test_checks_command(self, runner, mock_pr_manager, mock_token_manager):
        """Test checks command."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
        mock_manager.fetch_check_status.return_value = {
            "total": 3,
            "success": 2,
            "failure": 1,
            "pending": 0,
            "checks": []
        }

        result = runner.invoke(cli, ['checks', 'owner/repo#42'])
        assert result.exit_code == 0

    def test_files_command(self, runner, mock_pr_manager, mock_token_manager):
        """Test files command."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
        mock_manager.github.get_pr_files.return_value = [
            {
                "filename": "src/main.py",
                "status": "modified",
                "additions": 10,
                "deletions": 5,
            }
        ]

        result = runner.invoke(cli, ['files', 'owner/repo#42'])
        assert result.exit_code == 0

    def test_summary_command(self, runner, mock_pr_manager, mock_token_manager):
        """Test summary command."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
        mock_manager.get_pr_summary.return_value = {
            "total_threads": 5,
            "unresolved_active": 2,
            "resolved_active": 3,
            "approvals": 1,
        }

        result = runner.invoke(cli, ['summary', 'owner/repo#42'])
        assert result.exit_code == 0

    def test_export_command_json(self, runner, mock_pr_manager, mock_token_manager):
        """Test export command with JSON format."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_file = Path(f.name)

        try:
            with patch('gh_pr.utils.export.ExportManager') as mock_export:
                mock_export_instance = mock_export.return_value
                mock_export_instance.export_pr_data.return_value = True

                result = runner.invoke(cli, [
                    'export', 'owner/repo#42',
                    '--output', str(output_file),
                    '--format', 'json'
                ])
                assert result.exit_code == 0
        finally:
            output_file.unlink(missing_ok=True)

    def test_token_option(self, runner, mock_pr_manager):
        """Test --token option."""
        with patch('gh_pr.cli.TokenManager') as mock_tm:
            mock_instance = mock_tm.return_value
            mock_instance.get_token.return_value = "custom_token"
            mock_instance.validate_token.return_value = True

            mock_manager = mock_pr_manager.return_value
            mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
            mock_manager.fetch_pr_data.return_value = {"number": 42}

            result = runner.invoke(cli, [
                '--token', 'custom_token',
                'view', 'owner/repo#42'
            ])
            assert result.exit_code == 0
            mock_tm.assert_called_with(token='custom_token')

    def test_no_cache_option(self, runner, mock_pr_manager, mock_token_manager):
        """Test --no-cache option."""
        with patch('gh_pr.cli.CacheManager') as mock_cache:
            mock_manager = mock_pr_manager.return_value
            mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
            mock_manager.fetch_pr_data.return_value = {"number": 42}

            result = runner.invoke(cli, [
                '--no-cache',
                'view', 'owner/repo#42'
            ])
            assert result.exit_code == 0
            mock_cache.assert_called_with(enabled=False)

    def test_token_info_option(self, runner):
        """Test --token-info option."""
        with patch('gh_pr.cli.TokenManager') as mock_tm:
            mock_instance = mock_tm.return_value
            mock_instance.get_token.return_value = "test_token"
            mock_instance.validate_token.return_value = True
            mock_instance.get_token_info.return_value = {
                "type": "Classic Personal Access Token",
                "rate_limit": {"limit": 5000, "remaining": 4999},
            }

            result = runner.invoke(cli, ['--token-info'])
            assert result.exit_code == 0
            assert "GitHub Token Information" in result.output

    def test_invalid_token(self, runner, mock_pr_manager):
        """Test handling of invalid token."""
        with patch('gh_pr.cli.TokenManager') as mock_tm:
            mock_instance = mock_tm.return_value
            mock_instance.get_token.return_value = "invalid_token"
            mock_instance.validate_token.return_value = False

            result = runner.invoke(cli, ['view', 'owner/repo#42'])
            assert result.exit_code != 0
            assert "Invalid GitHub token" in result.output

    def test_github_api_error(self, runner, mock_pr_manager, mock_token_manager):
        """Test handling of GitHub API errors."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
        mock_manager.fetch_pr_data.side_effect = ValueError("API Error: Not found")

        result = runner.invoke(cli, ['view', 'owner/repo#42'])
        assert result.exit_code != 0
        assert "API Error" in result.output

    def test_interactive_selection(self, runner, mock_pr_manager, mock_token_manager):
        """Test interactive PR selection."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.select_pr_interactive.return_value = "owner/repo#42"
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
        mock_manager.fetch_pr_data.return_value = {"number": 42}

        with patch('click.confirm', return_value=True):
            result = runner.invoke(cli, ['view'])
            # Would need proper interactive testing setup

    def test_export_command_markdown(self, runner, mock_pr_manager, mock_token_manager):
        """Test export command with Markdown format."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)

        with tempfile.TemporaryFile(mode='w', suffix='.md') as f:
            with patch('gh_pr.utils.export.ExportManager') as mock_export:
                result = runner.invoke(cli, [
                    'export', 'owner/repo#42',
                    '--format', 'markdown'
                ])
                assert result.exit_code == 0

    def test_verbose_output(self, runner, mock_pr_manager, mock_token_manager):
        """Test verbose output option."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
        mock_manager.fetch_pr_data.return_value = {"number": 42}

        result = runner.invoke(cli, [
            '--verbose',
            'view', 'owner/repo#42'
        ])
        assert result.exit_code == 0

    def test_config_file_option(self, runner, mock_pr_manager, mock_token_manager):
        """Test --config option."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml') as f:
            config_path = Path(f.name)
            f.write('[github]\ntoken = "config_token"\n')
            f.flush()

            with patch('gh_pr.utils.config.ConfigManager') as mock_config:
                result = runner.invoke(cli, [
                    '--config', str(config_path),
                    'view', 'owner/repo#42'
                ])
                mock_config.assert_called_with(config_path=config_path)

    def test_copy_to_clipboard(self, runner, mock_pr_manager, mock_token_manager):
        """Test copying to clipboard."""
        mock_manager = mock_pr_manager.return_value
        mock_manager.parse_pr_identifier.return_value = ("owner", "repo", 42)
        mock_manager.fetch_pr_comments.return_value = []

        with patch('gh_pr.utils.clipboard.ClipboardManager') as mock_clipboard:
            mock_clip_instance = mock_clipboard.return_value
            mock_clip_instance.copy.return_value = True

            result = runner.invoke(cli, [
                'comments', 'owner/repo#42',
                '--copy'
            ])
            assert result.exit_code == 0
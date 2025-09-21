"""
Unit tests for cli module.

Tests command-line interface functionality and option handling.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

import click
from click.testing import CliRunner

from gh_pr.cli import CLIConfig, MAX_CONTEXT_LINES


class TestCLIConfig(unittest.TestCase):
    """Test CLIConfig dataclass."""

    def test_cli_config_defaults(self):
        """Test CLIConfig default values."""
        config = CLIConfig()

        self.assertIsNone(config.pr_identifier)
        self.assertFalse(config.interactive)
        self.assertIsNone(config.repo)
        self.assertIsNone(config.token)
        self.assertFalse(config.show_all)
        self.assertFalse(config.resolved_active)
        self.assertFalse(config.unresolved_outdated)
        self.assertFalse(config.current_unresolved)
        self.assertFalse(config.checks)
        self.assertFalse(config.verbose)
        self.assertEqual(config.context, 3)
        self.assertFalse(config.no_code)
        self.assertFalse(config.no_cache)
        self.assertFalse(config.clear_cache)
        self.assertFalse(config.resolve_outdated)
        self.assertFalse(config.accept_suggestions)
        self.assertFalse(config.copy)
        self.assertIsNone(config.export)
        self.assertIsNone(config.config)
        # Phase 4 options
        self.assertFalse(config.batch)
        self.assertIsNone(config.batch_file)
        self.assertFalse(config.export_enhanced)
        self.assertFalse(config.export_stats)
        self.assertEqual(config.rate_limit, 2.0)
        self.assertEqual(config.max_concurrent, 5)

    def test_cli_config_custom_values(self):
        """Test CLIConfig with custom values."""
        config = CLIConfig(
            pr_identifier="123",
            interactive=True,
            repo="owner/repo",
            token="test_token",
            verbose=True,
            context=5,
            batch=True,
            rate_limit=1.5,
            max_concurrent=10
        )

        self.assertEqual(config.pr_identifier, "123")
        self.assertTrue(config.interactive)
        self.assertEqual(config.repo, "owner/repo")
        self.assertEqual(config.token, "test_token")
        self.assertTrue(config.verbose)
        self.assertEqual(config.context, 5)
        self.assertTrue(config.batch)
        self.assertEqual(config.rate_limit, 1.5)
        self.assertEqual(config.max_concurrent, 10)

    def test_cli_config_is_dataclass(self):
        """Test that CLIConfig is properly structured as a dataclass."""
        config = CLIConfig()

        # Should be able to convert to dict
        config_dict = asdict(config)
        self.assertIsInstance(config_dict, dict)
        self.assertIn('pr_identifier', config_dict)
        self.assertIn('interactive', config_dict)

        # Should be able to create from keyword arguments
        new_config = CLIConfig(**config_dict)
        self.assertEqual(config.pr_identifier, new_config.pr_identifier)


class TestCLIConstants(unittest.TestCase):
    """Test CLI module constants."""

    def test_max_context_lines_defined(self):
        """Test that MAX_CONTEXT_LINES is properly defined."""
        self.assertIsInstance(MAX_CONTEXT_LINES, int)
        self.assertGreater(MAX_CONTEXT_LINES, 0)
        self.assertLessEqual(MAX_CONTEXT_LINES, 100)  # Reasonable upper bound


class TestCLICommand(unittest.TestCase):
    """Test CLI command functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

        # We need to import the command after setting up mocks
        # to avoid import-time side effects
        self.patcher_console = patch('gh_pr.cli.console')
        self.mock_console = self.patcher_console.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.patcher_console.stop()

    def test_cli_command_exists(self):
        """Test that CLI command is properly defined."""
        from gh_pr.cli import main  # Import after patches are active

        self.assertIsInstance(main, click.Command)
        self.assertEqual(main.name, "main")

    def test_cli_help_option(self):
        """Test CLI help option."""
        # Import the command after mocks are set up
        from gh_pr.cli import main

        result = self.runner.invoke(main, ['--help'])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Usage:", result.output)
        self.assertIn("--interactive", result.output)
        self.assertIn("--repo", result.output)
        self.assertIn("--token", result.output)

    def test_cli_pr_identifier_argument(self):
        """Test CLI with PR identifier argument."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.TokenManager') as mock_token_manager, \
             patch('gh_pr.cli.GitHubClient') as mock_github_client, \
             patch('gh_pr.cli.PRManager') as mock_pr_manager, \
             patch('gh_pr.cli.CacheManager') as mock_cache_manager, \
             patch('gh_pr.cli.DisplayManager') as mock_display_manager:

            # Mock successful initialization
            mock_token_manager.return_value.get_token.return_value = "test_token"
            mock_github_client.return_value = Mock()
            mock_pr_manager.return_value = Mock()
            mock_cache_manager.return_value = Mock()
            mock_display_manager.return_value = Mock()

            # Mock PR manager methods
            mock_pr_manager.return_value.parse_pr_identifier.return_value = ("owner", "repo", 123)
            mock_pr_manager.return_value.fetch_pr_data.return_value = {"number": 123, "title": "Test"}
            mock_pr_manager.return_value.fetch_pr_comments.return_value = []
            mock_pr_manager.return_value.get_pr_summary.return_value = {"total_threads": 0}

            result = self.runner.invoke(main, ['123'])

            # Should not exit with error (though it might not complete due to mocking)
            self.assertNotEqual(result.exit_code, 2)  # Not a usage error

    def test_cli_interactive_option(self):
        """Test CLI with interactive option."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.TokenManager') as mock_token_manager, \
             patch('gh_pr.cli.GitHubClient') as mock_github_client, \
             patch('gh_pr.cli.PRManager') as mock_pr_manager, \
             patch('gh_pr.cli.CacheManager') as mock_cache_manager, \
             patch('gh_pr.cli.DisplayManager') as mock_display_manager:

            # Mock successful initialization
            mock_token_manager.return_value.get_token.return_value = "test_token"
            mock_pr_manager.return_value.select_pr_interactive.return_value = "owner/repo#123"
            mock_pr_manager.return_value.parse_pr_identifier.return_value = ("owner", "repo", 123)
            mock_pr_manager.return_value.fetch_pr_data.return_value = {"number": 123}
            mock_pr_manager.return_value.fetch_pr_comments.return_value = []
            mock_pr_manager.return_value.get_pr_summary.return_value = {"total_threads": 0}

            result = self.runner.invoke(main, ['--interactive'])

            # Should call select_pr_interactive
            mock_pr_manager.return_value.select_pr_interactive.assert_called_once()

    def test_cli_context_option_validation(self):
        """Test CLI context option validation."""
        from gh_pr.cli import main

        # Test with invalid context value (negative)
        result = self.runner.invoke(main, ['--context', '-1', '123'])
        self.assertNotEqual(result.exit_code, 0)

        # Test with invalid context value (too high)
        result = self.runner.invoke(main, ['--context', str(MAX_CONTEXT_LINES + 1), '123'])
        self.assertNotEqual(result.exit_code, 0)

        # Test with valid context value
        with patch('gh_pr.cli.TokenManager'), \
             patch('gh_pr.cli.GitHubClient'), \
             patch('gh_pr.cli.PRManager'), \
             patch('gh_pr.cli.CacheManager'), \
             patch('gh_pr.cli.DisplayManager'):

            result = self.runner.invoke(main, ['--context', '5', '123'])
            # Should not fail validation
            self.assertNotEqual(result.exit_code, 2)

    def test_cli_token_option(self):
        """Test CLI with token option."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.TokenManager') as mock_token_manager, \
             patch('gh_pr.cli.GitHubClient'), \
             patch('gh_pr.cli.PRManager'), \
             patch('gh_pr.cli.CacheManager'), \
             patch('gh_pr.cli.DisplayManager'):

            result = self.runner.invoke(main, ['--token', 'custom_token', '123'])

            # Should pass custom token to TokenManager
            mock_token_manager.assert_called_with(token='custom_token')

    def test_cli_repo_option(self):
        """Test CLI with repo option."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.TokenManager') as mock_token_manager, \
             patch('gh_pr.cli.GitHubClient'), \
             patch('gh_pr.cli.PRManager') as mock_pr_manager, \
             patch('gh_pr.cli.CacheManager'), \
             patch('gh_pr.cli.DisplayManager'):

            mock_token_manager.return_value.get_token.return_value = "test_token"
            mock_pr_manager.return_value.parse_pr_identifier.return_value = ("owner", "repo", 123)
            mock_pr_manager.return_value.fetch_pr_data.return_value = {"number": 123}
            mock_pr_manager.return_value.fetch_pr_comments.return_value = []
            mock_pr_manager.return_value.get_pr_summary.return_value = {"total_threads": 0}

            result = self.runner.invoke(main, ['--repo', 'owner/repo', '123'])

            # Should pass repo to parse_pr_identifier
            mock_pr_manager.return_value.parse_pr_identifier.assert_called_with('123', default_repo='owner/repo')

    def test_cli_verbose_option(self):
        """Test CLI with verbose option."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.TokenManager') as mock_token_manager, \
             patch('gh_pr.cli.GitHubClient'), \
             patch('gh_pr.cli.PRManager') as mock_pr_manager, \
             patch('gh_pr.cli.CacheManager'), \
             patch('gh_pr.cli.DisplayManager') as mock_display_manager:

            mock_token_manager.return_value.get_token.return_value = "test_token"
            mock_pr_manager.return_value.parse_pr_identifier.return_value = ("owner", "repo", 123)
            mock_pr_manager.return_value.fetch_pr_data.return_value = {"number": 123}
            mock_pr_manager.return_value.fetch_pr_comments.return_value = []
            mock_pr_manager.return_value.get_pr_summary.return_value = {"total_threads": 0}

            result = self.runner.invoke(main, ['--verbose', '123'])

            # DisplayManager should be called (indicating verbose processing)
            mock_display_manager.assert_called()

    def test_cli_no_cache_option(self):
        """Test CLI with no-cache option."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.TokenManager') as mock_token_manager, \
             patch('gh_pr.cli.GitHubClient'), \
             patch('gh_pr.cli.PRManager') as mock_pr_manager, \
             patch('gh_pr.cli.CacheManager') as mock_cache_manager, \
             patch('gh_pr.cli.DisplayManager'):

            mock_token_manager.return_value.get_token.return_value = "test_token"
            mock_pr_manager.return_value.parse_pr_identifier.return_value = ("owner", "repo", 123)
            mock_pr_manager.return_value.fetch_pr_data.return_value = {"number": 123}
            mock_pr_manager.return_value.fetch_pr_comments.return_value = []
            mock_pr_manager.return_value.get_pr_summary.return_value = {"total_threads": 0}

            result = self.runner.invoke(main, ['--no-cache', '123'])

            # CacheManager should be initialized with enabled=False
            mock_cache_manager.assert_called_with(enabled=False)

    def test_cli_clear_cache_option(self):
        """Test CLI with clear-cache option."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.TokenManager') as mock_token_manager, \
             patch('gh_pr.cli.GitHubClient'), \
             patch('gh_pr.cli.PRManager'), \
             patch('gh_pr.cli.CacheManager') as mock_cache_manager, \
             patch('gh_pr.cli.DisplayManager'), \
             patch('gh_pr.cli.console') as mock_console:

            mock_cache_manager.return_value.clear.return_value = True

            result = self.runner.invoke(main, ['--clear-cache'])

            # Should clear cache and print message
            mock_cache_manager.return_value.clear.assert_called_once()
            mock_console.print.assert_called()

    def test_cli_filter_options(self):
        """Test CLI filter options."""
        from gh_pr.cli import main

        filter_options = [
            '--all',
            '--resolved-active',
            '--unresolved-outdated',
            '--current-unresolved'
        ]

        for option in filter_options:
            with self.subTest(option=option):
                with patch('gh_pr.cli.TokenManager') as mock_token_manager, \
                     patch('gh_pr.cli.GitHubClient'), \
                     patch('gh_pr.cli.PRManager') as mock_pr_manager, \
                     patch('gh_pr.cli.CacheManager'), \
                     patch('gh_pr.cli.DisplayManager'):

                    mock_token_manager.return_value.get_token.return_value = "test_token"
                    mock_pr_manager.return_value.parse_pr_identifier.return_value = ("owner", "repo", 123)
                    mock_pr_manager.return_value.fetch_pr_data.return_value = {"number": 123}
                    mock_pr_manager.return_value.fetch_pr_comments.return_value = []
                    mock_pr_manager.return_value.get_pr_summary.return_value = {"total_threads": 0}

                    result = self.runner.invoke(main, [option, '123'])

                    # Should not exit with error
                    self.assertNotEqual(result.exit_code, 2)

    def test_cli_export_option(self):
        """Test CLI with export option."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.TokenManager') as mock_token_manager, \
             patch('gh_pr.cli.GitHubClient'), \
             patch('gh_pr.cli.PRManager') as mock_pr_manager, \
             patch('gh_pr.cli.CacheManager'), \
             patch('gh_pr.cli.DisplayManager'), \
             patch('gh_pr.cli.ExportManager') as mock_export_manager:

            mock_token_manager.return_value.get_token.return_value = "test_token"
            mock_pr_manager.return_value.parse_pr_identifier.return_value = ("owner", "repo", 123)
            mock_pr_manager.return_value.fetch_pr_data.return_value = {"number": 123}
            mock_pr_manager.return_value.fetch_pr_comments.return_value = []
            mock_pr_manager.return_value.get_pr_summary.return_value = {"total_threads": 0}
            mock_export_manager.return_value.export.return_value = "exported_file.md"

            result = self.runner.invoke(main, ['--export', 'markdown', '123'])

            # Should call export manager
            mock_export_manager.return_value.export.assert_called()

    def test_cli_copy_option(self):
        """Test CLI with copy option."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.TokenManager') as mock_token_manager, \
             patch('gh_pr.cli.GitHubClient'), \
             patch('gh_pr.cli.PRManager') as mock_pr_manager, \
             patch('gh_pr.cli.CacheManager'), \
             patch('gh_pr.cli.DisplayManager'), \
             patch('gh_pr.cli.ClipboardManager') as mock_clipboard_manager:

            mock_token_manager.return_value.get_token.return_value = "test_token"
            mock_pr_manager.return_value.parse_pr_identifier.return_value = ("owner", "repo", 123)
            mock_pr_manager.return_value.fetch_pr_data.return_value = {"number": 123}
            mock_pr_manager.return_value.fetch_pr_comments.return_value = []
            mock_pr_manager.return_value.get_pr_summary.return_value = {"total_threads": 0}
            mock_clipboard_manager.return_value.is_available.return_value = True
            mock_clipboard_manager.return_value.copy.return_value = True

            result = self.runner.invoke(main, ['--copy', '123'])

            # Should use clipboard manager
            mock_clipboard_manager.return_value.copy.assert_called()

    def test_cli_batch_options(self):
        """Test CLI Phase 4 batch options."""
        from gh_pr.cli import main

        batch_options = [
            ['--batch'],
            ['--batch-file', 'prs.txt'],
            ['--export-enhanced'],
            ['--export-stats'],
            ['--rate-limit', '1.5'],
            ['--max-concurrent', '10']
        ]

        for options in batch_options:
            with self.subTest(options=options):
                # Test that options are accepted without error
                result = self.runner.invoke(main, options + ['--help'])
                self.assertEqual(result.exit_code, 0)

    def test_cli_config_option(self):
        """Test CLI with config option."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.ConfigManager') as mock_config_manager, \
             patch('gh_pr.cli.TokenManager'), \
             patch('gh_pr.cli.GitHubClient'), \
             patch('gh_pr.cli.PRManager'), \
             patch('gh_pr.cli.CacheManager'), \
             patch('gh_pr.cli.DisplayManager'):

            result = self.runner.invoke(main, ['--config', 'custom_config.toml', '123'])

            # Should pass config path to ConfigManager
            mock_config_manager.assert_called_with(config_path='custom_config.toml')

    def test_cli_error_handling_no_pr_identifier(self):
        """Test CLI error handling when no PR identifier is provided."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.TokenManager') as mock_token_manager, \
             patch('gh_pr.cli.GitHubClient'), \
             patch('gh_pr.cli.PRManager') as mock_pr_manager, \
             patch('gh_pr.cli.CacheManager'), \
             patch('gh_pr.cli.DisplayManager'):

            mock_token_manager.return_value.get_token.return_value = "test_token"
            mock_pr_manager.return_value.auto_detect_pr.return_value = None
            mock_pr_manager.return_value.select_pr_interactive.return_value = None

            result = self.runner.invoke(main, [])

            # Should attempt auto-detection and interactive selection
            mock_pr_manager.return_value.auto_detect_pr.assert_called_once()

    def test_cli_error_handling_invalid_token(self):
        """Test CLI error handling with invalid token."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.TokenManager') as mock_token_manager:
            mock_token_manager.side_effect = ValueError("No GitHub token found")

            result = self.runner.invoke(main, ['123'])

            # Should exit with error
            self.assertNotEqual(result.exit_code, 0)

    def test_cli_progress_display(self):
        """Test that CLI shows progress for long operations."""
        from gh_pr.cli import main

        with patch('gh_pr.cli.TokenManager') as mock_token_manager, \
             patch('gh_pr.cli.GitHubClient'), \
             patch('gh_pr.cli.PRManager') as mock_pr_manager, \
             patch('gh_pr.cli.CacheManager'), \
             patch('gh_pr.cli.DisplayManager'), \
             patch('gh_pr.cli.Progress') as mock_progress:

            mock_token_manager.return_value.get_token.return_value = "test_token"
            mock_pr_manager.return_value.parse_pr_identifier.return_value = ("owner", "repo", 123)
            mock_pr_manager.return_value.fetch_pr_data.return_value = {"number": 123}
            mock_pr_manager.return_value.fetch_pr_comments.return_value = []
            mock_pr_manager.return_value.get_pr_summary.return_value = {"total_threads": 0}

            result = self.runner.invoke(main, ['123'])

            # Progress should be used for operations
            mock_progress.assert_called()

    def test_cli_console_import(self):
        """Test that console is properly imported and available."""
        from gh_pr.cli import console
        from rich.console import Console

        self.assertIsInstance(console, Console)


if __name__ == '__main__':
    unittest.main()
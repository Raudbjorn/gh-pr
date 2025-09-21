"""Integration tests for the TUI interactive mode."""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock

from src.gh_pr.ui.interactive import GhPrTUI
from src.gh_pr.core.github import GitHubClient
from src.gh_pr.core.pr_manager import PRManager
from src.gh_pr.utils.config import ConfigManager


@pytest.fixture
def mock_pr_data():
    """Create mock PR data for testing."""
    return [
        {
            "number": 123,
            "title": "Add new feature",
            "author": "alice",
            "branch": "feature-branch",
            "head_ref": "feature-branch",
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-16T14:30:00Z",
            "draft": False,
            "mergeable": True,
            "labels": ["enhancement", "review-needed"],
        },
        {
            "number": 124,
            "title": "Fix bug in authentication",
            "author": "bob",
            "branch": "fix-auth",
            "head_ref": "fix-auth",
            "created_at": "2024-01-16T09:00:00Z",
            "updated_at": "2024-01-17T11:00:00Z",
            "draft": True,
            "mergeable": False,
            "labels": ["bug"],
        },
    ]


@pytest.fixture
def mock_comments():
    """Create mock review comments for testing."""
    return [
        {
            "id": 1001,
            "author": "reviewer1",
            "body": "This looks good, but consider adding error handling.",
            "created_at": "2024-01-15T11:00:00Z",
            "updated_at": "2024-01-15T11:00:00Z",
            "path": "src/main.py",
            "line": 42,
            "diff_hunk": "@@ -40,6 +40,8 @@",
            "position": 1,
            "original_position": 1,
        },
        {
            "id": 1002,
            "author": "reviewer2",
            "body": "Need to add tests for this function.",
            "created_at": "2024-01-15T12:00:00Z",
            "updated_at": "2024-01-15T12:00:00Z",
            "path": "src/utils.py",
            "line": 15,
            "diff_hunk": "@@ -12,7 +12,9 @@",
            "position": 2,
            "original_position": 2,
        },
    ]


@pytest.fixture
def mock_github_client(mock_pr_data, mock_comments):
    """Create a mock GitHub client."""
    client = Mock(spec=GitHubClient)
    client.get_open_prs = Mock(return_value=mock_pr_data)
    client.get_pr_review_comments = Mock(return_value=mock_comments)
    client.get_pr_issue_comments = Mock(return_value=[])
    client.get_pull_request = Mock()
    return client


@pytest.fixture
def mock_pr_manager(mock_github_client):
    """Create a mock PR manager."""
    manager = Mock(spec=PRManager)
    manager.parse_pr_identifier = Mock(return_value=("owner", "repo", 123))
    manager.fetch_pr_data = Mock(return_value={
        "number": 123,
        "title": "Test PR",
        "author": "test-user",
        "state": "open",
        "created_at": "2024-01-15T10:00:00Z",
        "changed_files": 3,
    })
    manager.fetch_pr_comments = Mock(return_value=[])
    return manager


@pytest.fixture
def mock_config_manager():
    """Create a mock configuration manager."""
    config = Mock(spec=ConfigManager)
    config.github_token = "test_token"
    config.default_repo = "test/repo"
    config.cache_ttl = 300
    config.theme = "default"
    return config


class TestTUIIntegration:
    """Integration tests for the TUI application."""

    @pytest.mark.asyncio
    async def test_tui_startup_and_display(self, mock_github_client, mock_pr_manager, mock_config_manager):
        """Test TUI starts up and displays basic layout."""
        app = GhPrTUI(
            github_client=mock_github_client,
            pr_manager=mock_pr_manager,
            config_manager=mock_config_manager,
            initial_repo="test/repo",
        )

        async with app.run_test() as pilot:
            # Wait for app to load
            await pilot.pause(0.1)

            # Check that basic components are present
            pr_list = app.query_one("#pr-list")
            assert pr_list is not None

            pr_details = app.query_one("PRDetailsView")
            assert pr_details is not None

            search_input = app.query_one("#search_input")
            assert search_input is not None

    @pytest.mark.asyncio
    async def test_keyboard_navigation(self, mock_github_client, mock_pr_manager, mock_config_manager):
        """Test keyboard navigation in the TUI."""
        app = GhPrTUI(
            github_client=mock_github_client,
            pr_manager=mock_pr_manager,
            config_manager=mock_config_manager,
            initial_repo="test/repo",
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.1)

            # Test navigation keys - these should trigger the actions
            await pilot.press("j")  # Move down
            await pilot.press("k")  # Move up

            # Verify no exceptions were raised and app is still running
            assert app.is_running

    @pytest.mark.asyncio
    async def test_search_functionality(self, mock_github_client, mock_pr_manager, mock_config_manager):
        """Test search functionality in the TUI."""
        app = GhPrTUI(
            github_client=mock_github_client,
            pr_manager=mock_pr_manager,
            config_manager=mock_config_manager,
            initial_repo="test/repo",
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.1)

            # Focus search input
            await pilot.press("s")

            # Type in search input
            search_input = app.query_one("#search_input")
            search_input.value = "123"

            # Trigger search
            await pilot.press("enter")

            # Verify search was triggered (PR manager parse method called)
            mock_pr_manager.parse_pr_identifier.assert_called()

    @pytest.mark.asyncio
    async def test_filter_menu_toggle(self, mock_github_client, mock_pr_manager, mock_config_manager):
        """Test filter menu toggle functionality."""
        app = GhPrTUI(
            github_client=mock_github_client,
            pr_manager=mock_pr_manager,
            config_manager=mock_config_manager,
            initial_repo="test/repo",
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.1)

            # Toggle filter menu
            await pilot.press("f")

            # Check that filter state changed
            assert app.show_filter_menu == True

            # Toggle again
            await pilot.press("f")
            assert app.show_filter_menu == False

    @pytest.mark.asyncio
    async def test_refresh_functionality(self, mock_github_client, mock_pr_manager, mock_config_manager):
        """Test refresh functionality."""
        app = GhPrTUI(
            github_client=mock_github_client,
            pr_manager=mock_pr_manager,
            config_manager=mock_config_manager,
            initial_repo="test/repo",
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.1)

            # Clear previous calls
            mock_github_client.get_open_prs.reset_mock()

            # Trigger refresh
            await pilot.press("r")
            await pilot.pause(0.1)

            # Verify refresh was triggered
            mock_github_client.get_open_prs.assert_called()

    @pytest.mark.asyncio
    async def test_help_display(self, mock_github_client, mock_pr_manager, mock_config_manager):
        """Test help display functionality."""
        app = GhPrTUI(
            github_client=mock_github_client,
            pr_manager=mock_pr_manager,
            config_manager=mock_config_manager,
            initial_repo="test/repo",
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.1)

            # Trigger help - this should show a notification
            await pilot.press("?")

            # Check that app is still running (help was displayed)
            assert app.is_running

    @pytest.mark.asyncio
    async def test_quit_application(self, mock_github_client, mock_pr_manager, mock_config_manager):
        """Test quitting the application."""
        app = GhPrTUI(
            github_client=mock_github_client,
            pr_manager=mock_pr_manager,
            config_manager=mock_config_manager,
            initial_repo="test/repo",
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.1)

            # Quit application
            await pilot.press("q")

            # App should exit gracefully (no exception)

    @pytest.mark.asyncio
    async def test_error_handling_github_failure(self, mock_pr_manager, mock_config_manager):
        """Test error handling when GitHub API fails."""
        # Create a failing GitHub client
        failing_client = Mock(spec=GitHubClient)
        failing_client.get_open_prs = Mock(side_effect=Exception("API Error"))

        app = GhPrTUI(
            github_client=failing_client,
            pr_manager=mock_pr_manager,
            config_manager=mock_config_manager,
            initial_repo="test/repo",
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.1)

            # App should handle the error gracefully and still be running
            assert app.is_running

    @pytest.mark.asyncio
    async def test_pr_list_selection(self, mock_github_client, mock_pr_manager, mock_config_manager, mock_pr_data):
        """Test PR list selection functionality."""
        # Set up mock to return PR data
        mock_github_client.get_open_prs.return_value = mock_pr_data

        app = GhPrTUI(
            github_client=mock_github_client,
            pr_manager=mock_pr_manager,
            config_manager=mock_config_manager,
            initial_repo="test/repo",
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.1)

            # Select first PR
            await pilot.press("enter")

            # Verify that some action was taken (no error occurred)
            assert app.is_running

    @pytest.mark.asyncio
    async def test_copy_url_functionality(self, mock_github_client, mock_pr_manager, mock_config_manager):
        """Test copy URL functionality."""
        app = GhPrTUI(
            github_client=mock_github_client,
            pr_manager=mock_pr_manager,
            config_manager=mock_config_manager,
            initial_repo="test/repo",
        )

        # Set up a current PR
        app.current_pr = {"number": 123}
        app.current_repo = "test/repo"

        async with app.run_test() as pilot:
            await pilot.pause(0.1)

            # Try to copy URL
            with patch("src.gh_pr.utils.clipboard.ClipboardManager") as mock_clipboard:
                mock_clipboard_instance = Mock()
                mock_clipboard_instance.copy.return_value = True
                mock_clipboard.return_value = mock_clipboard_instance

                await pilot.press("ctrl+c")

                # Verify copy was attempted
                mock_clipboard_instance.copy.assert_called_once()
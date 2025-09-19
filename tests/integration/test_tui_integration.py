"""Integration tests for the TUI interactive mode."""

import asyncio
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
from textual.pilot import Pilot

from src.gh_pr.ui.interactive import GhPrTUI
from src.gh_pr.core.models import PullRequest, ReviewComment, CheckRun
from src.gh_pr.ui.themes import ThemeManager


@pytest.fixture
def mock_pr_data():
    """Create mock PR data for testing."""
    return [
        PullRequest(
            number=123,
            title="Add new feature",
            author="alice",
            state="open",
            draft=False,
            created_at="2024-01-15T10:00:00Z",
            updated_at="2024-01-16T14:30:00Z",
            url="https://github.com/test/repo/pull/123",
            additions=150,
            deletions=20,
            changed_files=5,
            comments=3,
            review_comments=2,
            mergeable=True,
            mergeable_state="clean",
            base_branch="main",
            head_branch="feature-branch",
            labels=["enhancement", "review-needed"],
            assignees=["bob"],
            milestone="v1.0",
            body="This PR adds a new feature for better user experience.",
        ),
        PullRequest(
            number=124,
            title="Fix bug in authentication",
            author="bob",
            state="open",
            draft=True,
            created_at="2024-01-16T09:00:00Z",
            updated_at="2024-01-17T11:00:00Z",
            url="https://github.com/test/repo/pull/124",
            additions=30,
            deletions=10,
            changed_files=2,
            comments=1,
            review_comments=0,
            mergeable=False,
            mergeable_state="conflicting",
            base_branch="main",
            head_branch="fix-auth",
            labels=["bug"],
            assignees=["alice"],
            milestone=None,
            body="Fixes authentication issue reported in #100.",
        ),
    ]


@pytest.fixture
def mock_comments():
    """Create mock review comments for testing."""
    return [
        ReviewComment(
            id=1001,
            pr_number=123,
            author="reviewer1",
            body="This looks good, but consider adding error handling.",
            created_at="2024-01-15T11:00:00Z",
            updated_at="2024-01-15T11:00:00Z",
            path="src/main.py",
            line=42,
            state="pending",
            url="https://github.com/test/repo/pull/123#discussion_r1001",
        ),
        ReviewComment(
            id=1002,
            pr_number=123,
            author="reviewer2",
            body="Need to add tests for this function.",
            created_at="2024-01-15T12:00:00Z",
            updated_at="2024-01-15T12:00:00Z",
            path="src/utils.py",
            line=15,
            state="pending",
            url="https://github.com/test/repo/pull/123#discussion_r1002",
        ),
    ]


@pytest.fixture
def mock_checks():
    """Create mock check runs for testing."""
    return [
        CheckRun(
            id=5001,
            name="CI / Tests",
            status="completed",
            conclusion="success",
            url="https://github.com/test/repo/actions/runs/5001",
        ),
        CheckRun(
            id=5002,
            name="CI / Lint",
            status="completed",
            conclusion="failure",
            url="https://github.com/test/repo/actions/runs/5002",
        ),
    ]


@pytest.fixture
def mock_github_service(mock_pr_data, mock_comments, mock_checks):
    """Create a mock GitHub service."""
    service = Mock()
    service.get_pull_requests = Mock(return_value=mock_pr_data)
    service.get_review_comments = Mock(return_value=mock_comments)
    service.get_pr_checks = Mock(return_value=mock_checks)
    service.search_pull_requests = Mock(return_value=mock_pr_data[:1])
    return service


@pytest.fixture
def mock_cache_service():
    """Create a mock cache service."""
    service = Mock()
    service.get = Mock(return_value=None)
    service.set = Mock()
    service.clear = Mock()
    return service


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    config = Mock()
    config.github_token = "test_token"
    config.default_repo = "test/repo"
    config.cache_ttl = 300
    config.theme = "default"
    config.tui_settings = {
        "auto_refresh": False,
        "refresh_interval": 60,
        "show_drafts": True,
    }
    return config


class TestTUIIntegration:
    """Integration tests for the TUI application."""

    @pytest.mark.asyncio
    async def test_tui_startup_and_display(self, mock_github_service, mock_cache_service, mock_config):
        """Test TUI starts up and displays PR list."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            # Wait for app to load
            await pilot.pause(0.5)

            # Check that PR list is displayed
            pr_list = app.query_one("#pr-list")
            assert pr_list is not None

            # Verify PRs are loaded
            assert len(app.pull_requests) == 2
            assert app.pull_requests[0].number == 123
            assert app.pull_requests[1].number == 124

    @pytest.mark.asyncio
    async def test_keyboard_navigation(self, mock_github_service, mock_cache_service, mock_config):
        """Test keyboard navigation in the TUI."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Test navigation keys
            await pilot.press("j")  # Move down
            assert app.selected_pr_index == 1

            await pilot.press("k")  # Move up
            assert app.selected_pr_index == 0

            await pilot.press("g")  # Go to top
            assert app.selected_pr_index == 0

            await pilot.press("G")  # Go to bottom
            assert app.selected_pr_index == 1

    @pytest.mark.asyncio
    async def test_pr_details_view(self, mock_github_service, mock_cache_service, mock_config):
        """Test viewing PR details."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Select a PR and view details
            await pilot.press("enter")

            # Check that details view is shown
            details_view = app.query_one("#pr-details")
            assert details_view is not None
            assert details_view.display == True

            # Verify comments are loaded
            mock_github_service.get_review_comments.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_search_functionality(self, mock_github_service, mock_cache_service, mock_config):
        """Test search functionality in the TUI."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Open search
            await pilot.press("/")

            # Type search query
            search_input = app.query_one("#search-input")
            search_input.value = "feature"

            await pilot.press("enter")

            # Verify search was performed
            mock_github_service.search_pull_requests.assert_called()

    @pytest.mark.asyncio
    async def test_filter_menu(self, mock_github_service, mock_cache_service, mock_config):
        """Test filter menu functionality."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Open filter menu
            await pilot.press("f")

            # Check filter menu is visible
            filter_menu = app.query_one("#filter-menu")
            assert filter_menu is not None
            assert filter_menu.display == True

            # Apply filter
            await pilot.press("tab")  # Navigate to options
            await pilot.press("space")  # Select option
            await pilot.press("enter")  # Apply

            # Verify PRs are filtered
            assert app.filters_active == True

    @pytest.mark.asyncio
    async def test_sort_functionality(self, mock_github_service, mock_cache_service, mock_config):
        """Test sort functionality in the TUI."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Open sort menu
            await pilot.press("s")

            # Select sort option
            sort_menu = app.query_one("#sort-menu")
            assert sort_menu is not None

            # Apply sort
            await pilot.press("enter")

            # Verify PRs are sorted
            assert app.current_sort != "newest"  # Changed from default

    @pytest.mark.asyncio
    async def test_refresh_functionality(self, mock_github_service, mock_cache_service, mock_config):
        """Test refresh functionality."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Clear mock call count
            mock_github_service.get_pull_requests.reset_mock()

            # Refresh
            await pilot.press("r")
            await pilot.pause(0.5)

            # Verify data was reloaded
            mock_github_service.get_pull_requests.assert_called_once()
            mock_cache_service.clear.assert_called()

    @pytest.mark.asyncio
    async def test_theme_switching(self, mock_github_service, mock_cache_service, mock_config):
        """Test theme switching functionality."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            initial_theme = app.theme_manager.current_theme_name

            # Open settings/theme menu
            await pilot.press(",")  # Settings shortcut

            # Navigate to theme selection
            await pilot.press("t")  # Theme submenu

            # Select different theme
            await pilot.press("2")  # Select second theme

            # Verify theme changed
            assert app.theme_manager.current_theme_name != initial_theme

    @pytest.mark.asyncio
    async def test_export_functionality(self, mock_github_service, mock_cache_service, mock_config):
        """Test export functionality."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Open export menu
            await pilot.press("e")

            export_menu = app.query_one("#export-menu")
            assert export_menu is not None

            # Select export format and execute
            await pilot.press("enter")  # Select markdown

            # Verify export was triggered
            assert app.last_export_format == "markdown"

    @pytest.mark.asyncio
    async def test_help_display(self, mock_github_service, mock_cache_service, mock_config):
        """Test help display functionality."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Open help
            await pilot.press("?")

            # Check help screen is visible
            help_screen = app.query_one("#help-screen")
            assert help_screen is not None
            assert help_screen.display == True

            # Close help
            await pilot.press("escape")
            assert help_screen.display == False

    @pytest.mark.asyncio
    async def test_quit_application(self, mock_github_service, mock_cache_service, mock_config):
        """Test quitting the application."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Quit application
            await pilot.press("q")

            # Verify app is exiting
            assert app.is_running == False

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_cache_service, mock_config):
        """Test error handling in the TUI."""
        # Create a failing GitHub service
        failing_service = Mock()
        failing_service.get_pull_requests = Mock(side_effect=Exception("API Error"))

        app = GhPrTUI(
            github_service=failing_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Check error message is displayed
            error_widget = app.query_one(".error-message")
            assert error_widget is not None
            assert "API Error" in error_widget.renderable

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, mock_github_service, mock_cache_service, mock_config):
        """Test concurrent operations don't cause issues."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Trigger multiple concurrent operations
            await pilot.press("r")  # Refresh
            await pilot.press("f")  # Open filter
            await pilot.press("/")  # Open search

            # App should handle these gracefully
            assert app.is_running == True
            assert len(app.pending_operations) <= 1  # Should queue or cancel

    @pytest.mark.asyncio
    async def test_accessibility_features(self, mock_github_service, mock_cache_service, mock_config):
        """Test accessibility features in the TUI."""
        app = GhPrTUI(
            github_service=mock_github_service,
            cache_service=mock_cache_service,
            config=mock_config,
        )

        async with app.run_test() as pilot:
            await pilot.pause(0.5)

            # Test screen reader announcements
            await pilot.press("j")  # Navigate

            # Check aria labels are present
            pr_items = app.query(".pr-item")
            for item in pr_items:
                assert item.aria_label is not None
                assert item.aria_label != ""

            # Test high contrast mode
            await pilot.press("ctrl+h")  # Toggle high contrast
            assert app.high_contrast_mode == True
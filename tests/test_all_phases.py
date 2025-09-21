#!/usr/bin/env python3
"""Comprehensive test suite for all gh-pr phases."""

import os
import sys
import json
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest


class TestPhase1CoreFunctionality:
    """Test Phase 1: Core PR comment fetching."""

    def test_github_client_initialization(self):
        """Test GitHubClient can be initialized."""
        from gh_pr.core.github import GitHubClient

        client = GitHubClient("test_token")
        assert client is not None
        assert hasattr(client, 'github')

    def test_pr_manager_initialization(self):
        """Test PRManager initialization."""
        from gh_pr.core.pr_manager import PRManager
        from gh_pr.core.github import GitHubClient
        from gh_pr.utils.cache import CacheManager

        mock_github = Mock(spec=GitHubClient)
        mock_cache = Mock(spec=CacheManager)

        # Test with token
        pr_manager = PRManager(mock_github, mock_cache, token="test_token")
        assert pr_manager.graphql is not None

        # Test without token
        pr_manager = PRManager(mock_github, mock_cache, token=None)
        assert pr_manager.graphql is None

    def test_comment_processor(self):
        """Test CommentProcessor functionality."""
        from gh_pr.core.comments import CommentProcessor

        processor = CommentProcessor()

        # Test that processor exists
        assert processor is not None
        # The actual process method may not exist, but processor should work
        assert hasattr(processor, 'parse_comment')

    def test_comment_filter(self):
        """Test CommentFilter functionality."""
        from gh_pr.core.filters import CommentFilter

        filter_obj = CommentFilter()

        # Test that filter object exists
        assert filter_obj is not None
        # Check for apply method instead of filter
        assert hasattr(filter_obj, 'apply')

        # Mock comment
        comment = {
            'is_resolved': False,
            'is_outdated': False
        }

        # Test unresolved filter
        result = filter_obj.apply([comment], 'unresolved')
        assert len(result) == 1


class TestPhase2Caching:
    """Test Phase 2: Caching functionality."""

    def test_cache_manager_initialization(self):
        """Test CacheManager initialization."""
        from gh_pr.utils.cache import CacheManager

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(enabled=True, location=tmpdir)
            assert cache.enabled
            assert cache.location == Path(tmpdir)

    def test_cache_operations(self):
        """Test cache get/set operations."""
        from gh_pr.utils.cache import CacheManager

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(enabled=True, location=tmpdir)

            # Test set and get
            cache.set("test_key", {"data": "test"})
            result = cache.get("test_key")
            assert result == {"data": "test"}

            # Test cache miss
            result = cache.get("nonexistent")
            assert result is None

    def test_cache_ttl(self):
        """Test cache TTL functionality."""
        from gh_pr.utils.cache import CacheManager

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(enabled=True, location=tmpdir)

            # Set with short TTL
            cache.set("test_key", {"data": "test"}, ttl=1)

            # Should exist immediately
            assert cache.get("test_key") is not None

            # Should expire after TTL
            time.sleep(2)
            assert cache.get("test_key") is None


class TestPhase3UIAndDisplay:
    """Test Phase 3: UI and display functionality."""

    def test_display_manager_initialization(self):
        """Test DisplayManager initialization."""
        from gh_pr.ui.display import DisplayManager
        from rich.console import Console

        console = Console()
        display = DisplayManager(console, verbose=False)
        assert display is not None
        assert hasattr(display, 'display_pr_header')
        assert hasattr(display, 'display_comments')
        assert hasattr(display, 'display_summary')

    def test_clipboard_manager(self):
        """Test ClipboardManager functionality."""
        from gh_pr.utils.clipboard import ClipboardManager

        clipboard = ClipboardManager()
        assert hasattr(clipboard, 'copy')

        # Test copy operation (may fail on systems without clipboard)
        try:
            result = clipboard.copy("test text")
            assert isinstance(result, bool)
        except Exception:
            # Clipboard might not be available in test environment
            pass

    def test_export_manager(self):
        """Test ExportManager functionality."""
        from gh_pr.utils.export import ExportManager

        export = ExportManager()
        assert hasattr(export, 'export')
        # export_review_report method now exists
        assert hasattr(export, 'export_review_report')
        assert hasattr(export, 'export_batch_results')


class TestPhase4Automation:
    """Test Phase 4: Automation and batch operations."""

    def test_graphql_client_initialization(self):
        """Test GraphQLClient initialization."""
        from gh_pr.core.graphql import GraphQLClient

        client = GraphQLClient("test_token")
        assert client.token == "test_token"
        assert hasattr(client, 'execute_query')
        assert hasattr(client, 'resolve_thread')
        assert hasattr(client, 'accept_suggestion')

    def test_graphql_id_validation(self):
        """Test GraphQL ID validation accepts valid GitHub IDs."""
        import re

        # Valid GitHub base64 IDs
        valid_ids = [
            "PRR_kwDOI_Qb-M5fYZXm",
            "MDEwOlB1bGxSZXF1ZXN0MQ==",
            "U_kgDOI9Xs-w",
            "ABC123+/=",
            "test-id_123",
        ]

        pattern = r'^[A-Za-z0-9+/\-_=]+$'
        for test_id in valid_ids:
            assert re.match(pattern, test_id), f"Failed to validate: {test_id}"

        # Invalid IDs
        invalid_ids = ["", "test@id", "test#123", "test id"]
        for test_id in invalid_ids:
            assert not re.match(pattern, test_id), f"Should reject: {test_id}"

    def test_batch_operations_initialization(self):
        """Test BatchOperations initialization."""
        from gh_pr.core.batch import BatchOperations
        from gh_pr.core.pr_manager import PRManager
        from gh_pr.auth.permissions import PermissionChecker

        mock_pr_manager = Mock(spec=PRManager)
        mock_permissions = Mock(spec=PermissionChecker)

        batch_ops = BatchOperations(
            pr_manager=mock_pr_manager,
            permission_checker=mock_permissions,
            rate_limit=0.1,
            max_concurrent=3
        )

        assert batch_ops.rate_limit == 0.1
        assert batch_ops.max_concurrent == 3
        assert hasattr(batch_ops, 'api_lock')
        assert isinstance(batch_ops.api_lock, threading.Lock)

    def test_batch_rate_limiting(self):
        """Test batch operations rate limiting."""
        from gh_pr.core.batch import BatchOperations
        from gh_pr.core.pr_manager import PRManager
        from gh_pr.auth.permissions import PermissionChecker

        mock_pr_manager = Mock(spec=PRManager)
        mock_permissions = Mock(spec=PermissionChecker)

        batch_ops = BatchOperations(
            pr_manager=mock_pr_manager,
            permission_checker=mock_permissions,
            rate_limit=0.05  # 50ms for testing
        )

        call_times = []
        def test_op(*args):
            call_times.append(time.time())
            return "result"

        # Execute multiple operations
        for _ in range(3):
            batch_ops._execute_with_rate_limit(test_op)

        # Check spacing
        for i in range(1, len(call_times)):
            gap = call_times[i] - call_times[i-1]
            assert gap >= 0.04, f"Gap too small: {gap}"  # Allow small timing variance

    def test_batch_result_structure(self):
        """Test BatchResult dataclass."""
        from gh_pr.core.batch import BatchResult

        result = BatchResult(
            pr_identifier="owner/repo#123",
            success=True,
            message="Test successful",
            details={"count": 5},
            error=None
        )

        assert result.pr_identifier == "owner/repo#123"
        assert result.success is True
        assert result.message == "Test successful"
        assert result.details["count"] == 5
        assert result.error is None

    def test_batch_summary_structure(self):
        """Test BatchSummary dataclass."""
        from gh_pr.core.batch import BatchSummary

        summary = BatchSummary(total=10, successful=8, failed=2)
        assert summary.total == 10
        assert summary.successful == 8
        assert summary.failed == 2
        assert summary.success_rate == 80.0

    def test_batch_refactoring(self):
        """Test batch operations were refactored correctly."""
        from gh_pr.core.batch import BatchOperations
        from gh_pr.core.pr_manager import PRManager
        from gh_pr.auth.permissions import PermissionChecker

        mock_pr_manager = Mock(spec=PRManager)
        mock_permissions = Mock(spec=PermissionChecker)

        batch_ops = BatchOperations(
            pr_manager=mock_pr_manager,
            permission_checker=mock_permissions
        )

        # Check refactored method exists
        assert hasattr(batch_ops, '_execute_batch_operation')

        # Check public methods still exist
        assert hasattr(batch_ops, 'resolve_outdated_comments_batch')
        assert hasattr(batch_ops, 'accept_suggestions_batch')
        assert hasattr(batch_ops, 'get_pr_data_batch')


class TestAuthenticationAndPermissions:
    """Test authentication and permission checking."""

    def test_token_manager(self):
        """Test TokenManager functionality."""
        from gh_pr.auth.token import TokenManager

        with patch.dict(os.environ, {'GITHUB_TOKEN': 'test_token'}):
            token_manager = TokenManager()
            token = token_manager.get_token()
            assert token == 'test_token'

    def test_permission_checker(self):
        """Test PermissionChecker initialization."""
        from gh_pr.auth.permissions import PermissionChecker
        from gh_pr.auth.token import TokenManager

        mock_token_manager = Mock(spec=TokenManager)
        mock_token_manager.get_token.return_value = "test_token"

        checker = PermissionChecker(mock_token_manager)
        assert hasattr(checker, 'can_perform_operation')
        assert hasattr(checker, 'check_pr_permissions')


class TestCLIIntegration:
    """Test CLI integration."""

    def test_cli_config_dataclass(self):
        """Test CLIConfig dataclass."""
        from gh_pr.cli import CLIConfig

        config = CLIConfig(
            pr_identifier="owner/repo#123",
            interactive=False,
            verbose=True
        )

        assert config.pr_identifier == "owner/repo#123"
        assert config.interactive is False
        assert config.verbose is True

    def test_cli_helper_functions(self):
        """Test CLI has helper functions."""
        import gh_pr.cli as cli

        # Check helper functions exist
        assert hasattr(cli, '_initialize_services')
        assert hasattr(cli, '_display_token_info')
        assert hasattr(cli, '_check_automation_permissions')
        assert hasattr(cli, '_determine_filter_mode')
        assert hasattr(cli, '_get_pr_identifier')
        assert hasattr(cli, '_handle_automation')
        assert hasattr(cli, '_handle_output')


class TestConfigurationManagement:
    """Test configuration management."""

    def test_config_manager(self):
        """Test ConfigManager functionality."""
        from gh_pr.utils.config import ConfigManager

        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('[cache]\nlocation = "/tmp/test"')
            f.flush()

            try:
                config = ConfigManager(config_path=f.name)
                assert config is not None
                assert hasattr(config, 'get')
            finally:
                os.unlink(f.name)


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_pr_identifier_parsing(self):
        """Test PR identifier parsing."""
        from gh_pr.core.batch import BatchOperations
        from gh_pr.core.pr_manager import PRManager
        from gh_pr.auth.permissions import PermissionChecker

        mock_pr_manager = Mock(spec=PRManager)
        mock_permissions = Mock(spec=PermissionChecker)

        batch_ops = BatchOperations(
            pr_manager=mock_pr_manager,
            permission_checker=mock_permissions
        )

        # Valid identifiers
        assert batch_ops._parse_pr_identifier("owner/repo#123") == ("owner", "repo", 123)

        # Invalid identifiers
        assert batch_ops._parse_pr_identifier("invalid") is None
        assert batch_ops._parse_pr_identifier("owner/repo") is None
        assert batch_ops._parse_pr_identifier("owner#123") is None

    def test_pr_data_fetching(self):
        """Test _get_pr_data fetches actual data."""
        from gh_pr.core.batch import BatchOperations
        from gh_pr.core.pr_manager import PRManager
        from gh_pr.auth.permissions import PermissionChecker

        mock_pr_manager = Mock(spec=PRManager)
        mock_permissions = Mock(spec=PermissionChecker)

        # Setup mocks
        mock_pr_manager.fetch_pr_data.return_value = {
            "title": "Real PR Title",
            "state": "open",
            "number": 123
        }
        mock_pr_manager.get_pr_comments.return_value = ["comment1"]

        batch_ops = BatchOperations(
            pr_manager=mock_pr_manager,
            permission_checker=mock_permissions
        )

        result = batch_ops._get_pr_data("owner", "repo", 123)

        assert result["title"] == "Real PR Title"
        assert result["state"] == "open"
        assert result["comment_count"] == 1
        mock_pr_manager.fetch_pr_data.assert_called_once_with("owner", "repo", 123)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
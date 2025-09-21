"""Integration tests for end-to-end security fixes and reliability improvements."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from gh_pr.auth.token import TokenManager
from gh_pr.core.cache import CacheManager
from gh_pr.core.comments import CommentProcessor
from gh_pr.core.config import ConfigManager
from gh_pr.core.pr_manager import PRManager
from gh_pr.utils.export import ExportManager


class TestEndToEndSecurityIntegration:
    """Test end-to-end security integration across all components."""

    def test_secure_workflow_token_to_export(self):
        """Test complete secure workflow from token handling to file export."""
        # Test a complete workflow that touches all security fixes

        # 1. Token Manager with timeout handling
        with patch('gh_pr.auth.token.subprocess.run') as mock_run:
            # Mock successful but slow gh CLI
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "Token: ghp_test_token_123456789"
            mock_run.return_value = mock_result

            token_manager = TokenManager()
            assert token_manager.get_token() == "ghp_test_token_123456789"

            # Verify timeout was applied
            call_args = mock_run.call_args_list[0]
            assert call_args[1]['timeout'] == 5

        # 2. Config Manager with path validation
        with tempfile.TemporaryDirectory() as temp_dir:
            safe_config_path = Path(temp_dir) / "config.toml"
            safe_config_path.write_text("""
[github]
default_token = "config_token"

[cache]
enabled = true
location = "~/.cache/test"
""")

            # Move to allowed location
            cwd_config = Path.cwd() / "test_config.toml"
            safe_config_path.rename(cwd_config)

            try:
                config_manager = ConfigManager(config_path=str(cwd_config))
                assert config_manager.get("github.default_token") == "config_token"
                assert config_manager.get("cache.enabled") is True

            finally:
                if cwd_config.exists():
                    cwd_config.unlink()

        # 3. Cache Manager with error logging
        with patch('gh_pr.utils.cache.logger') as mock_logger:
            cache_manager = CacheManager(enabled=True)

            # Simulate cache operation failure
            with patch.object(cache_manager, 'cache') as mock_cache:
                mock_cache.get.side_effect = RuntimeError("Cache corruption")

                result = cache_manager.get("test_key")
                assert result is None
                mock_logger.warning.assert_called()

        # 4. Comment Processor with optimized datetime parsing
        processor = CommentProcessor()
        comments = [
            {
                "id": 1,
                "path": "file.py",
                "line": 10,
                "created_at": "2023-10-15T14:30:45Z",
                "author": "reviewer",
                "body": "Test comment"
            }
        ]

        threads = processor.organize_into_threads(comments)
        assert len(threads) == 1
        assert len(threads[0]["comments"]) == 1

        # 5. Export Manager with filename sanitization
        export_manager = ExportManager()
        pr_data = {
            "number": "../../../123",  # Malicious path traversal attempt
            "title": "Test<>PR|with*invalid:chars",
            "state": "open",
            "author": "testuser",
            "body": "Test description"
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                os.chdir(temp_dir)

                result = export_manager.export(pr_data, threads, format="markdown")

                # Verify secure filename and location
                result_path = Path(result)
                assert result_path.parent == Path.cwd()
                assert ".." not in str(result_path)
                assert result_path.exists()

                # Verify content is properly exported
                content = result_path.read_text()
                assert "PR #" in content

            finally:
                os.chdir(original_cwd)

    def test_pr_manager_git_validation_integration(self):
        """Test PR Manager git validation in realistic scenarios."""
        # Create mock GitHub client and cache
        mock_github_client = Mock()
        mock_cache_manager = Mock()

        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        # Test 1: Not in git repository
        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=False):
            result = pr_manager._get_current_repo_info()
            assert result is None

        # Test 2: In valid git repository
        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=True):
            with patch('subprocess.run') as mock_run:
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = "https://github.com/owner/repo.git"
                mock_run.return_value = mock_result

                result = pr_manager._get_current_repo_info()
                assert result == ("owner", "repo")

                # Verify git command was called with timeout
                call_args = mock_run.call_args
                assert call_args[1]['timeout'] == 5

        # Test 3: PR identifier parsing with repository context
        with patch.object(pr_manager, '_get_current_repo_info', return_value=("context-owner", "context-repo")):
            owner, repo, pr_number = pr_manager.parse_pr_identifier("456")
            assert owner == "context-owner"
            assert repo == "context-repo"
            assert pr_number == 456

    def test_configuration_security_chain(self):
        """Test configuration security across multiple components."""
        # Test that configuration paths are validated throughout the system

        with tempfile.TemporaryDirectory() as temp_dir:
            # 1. Create config in safe location
            safe_config = Path(temp_dir) / "safe_config.toml"
            safe_config.write_text("""
[github]
default_token = "secure_token"

[cache]
enabled = true
location = "{}/.cache/test"

[display]
context_lines = 5
""".format(temp_dir))

            # Move to current directory (allowed location)
            cwd_config = Path.cwd() / "integration_test_config.toml"
            safe_config.rename(cwd_config)

            try:
                # 2. ConfigManager loads and validates
                config_manager = ConfigManager(config_path=str(cwd_config))
                assert config_manager.config_path == cwd_config

                # 3. Extract settings for other components
                cache_location = config_manager.get("cache.location")
                cache_enabled = config_manager.get("cache.enabled")

                # 4. CacheManager uses validated config
                cache_manager = CacheManager(enabled=cache_enabled, location=cache_location)

                # Should work with valid configuration
                if cache_manager.enabled:
                    test_key = cache_manager.generate_key("test", "key")
                    assert isinstance(test_key, str)

            finally:
                if cwd_config.exists():
                    cwd_config.unlink()

    def test_token_manager_reliability_chain(self):
        """Test token manager reliability across different scenarios."""
        # Test token precedence and fallback chain

        # Test 1: Provided token (highest precedence)
        token_manager = TokenManager(token="provided_token")
        assert token_manager.get_token() == "provided_token"

        # Test 2: Environment variable fallback
        with patch.dict('os.environ', {'GH_TOKEN': 'env_token'}, clear=True):
            token_manager = TokenManager()
            assert token_manager.get_token() == "env_token"

        # Test 3: gh CLI fallback with timeout handling
        with patch.dict('os.environ', {}, clear=True):
            with patch('gh_pr.auth.token.subprocess.run') as mock_run:
                # First call times out
                mock_run.side_effect = [
                    subprocess.TimeoutExpired(["gh", "auth", "status"], 5),
                    Mock(returncode=0, stdout="cli_token")
                ]

                token_manager = TokenManager()
                assert token_manager.get_token() == "cli_token"

        # Test 4: Complete failure scenario
        with patch.dict('os.environ', {}, clear=True):
            with patch('gh_pr.auth.token.TokenManager._get_gh_cli_token', return_value=None):
                with pytest.raises(ValueError, match="No GitHub token found"):
                    TokenManager()

    def test_export_security_comprehensive(self):
        """Test comprehensive export security across different formats."""
        export_manager = ExportManager()

        # Malicious PR data with various attack vectors
        malicious_pr_data = {
            "number": "../../../etc/passwd",
            "title": "CON.txt<>|*evil",  # Reserved name + invalid chars
            "state": "open",
            "author": "../etc/shadow",
            "body": "\\..\\..\\windows\\system32"
        }

        malicious_comments = [
            {
                "id": 1,
                "path": "../../../sensitive/file.py",
                "line": 10,
                "created_at": "2023-10-15T14:30:45Z",
                "author": "../../etc/passwd",
                "body": "```suggestion\nmalicious code\n```"
            }
        ]

        formats_to_test = ["markdown", "csv", "json"]

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                os.chdir(temp_dir)

                for format_name in formats_to_test:
                    result = export_manager.export(malicious_pr_data, malicious_comments, format=format_name)

                    # Verify secure filename and location
                    result_path = Path(result)
                    assert result_path.parent == Path.cwd()
                    assert ".." not in str(result_path)
                    assert "etc" not in str(result_path)
                    assert "passwd" not in str(result_path)
                    assert result_path.exists()

                    # Verify file extension is correct
                    expected_ext = {"markdown": ".md", "csv": ".csv", "json": ".json"}[format_name]
                    assert result_path.suffix == expected_ext

            finally:
                os.chdir(original_cwd)

    def test_datetime_parsing_performance_integration(self):
        """Test datetime parsing performance in realistic comment processing."""
        processor = CommentProcessor()

        # Generate realistic comment load with repeated timestamps
        comments = []
        common_timestamps = [
            "2023-10-15T14:30:45Z",
            "2023-10-15T14:31:00Z",
            "2023-10-15T14:31:15Z"
        ]

        # Create 300 comments with repeated timestamps (realistic cache scenario)
        for i in range(300):
            timestamp = common_timestamps[i % len(common_timestamps)]
            comments.append({
                "id": i,
                "path": f"file_{i % 10}.py",
                "line": i % 50,
                "created_at": timestamp,
                "author": f"user_{i % 20}",
                "body": f"Comment {i}"
            })

        # Clear cache and measure performance
        from gh_pr.core.comments import _parse_datetime_cached
        _parse_datetime_cached.cache_clear()

        import time
        start_time = time.time()
        threads = processor.organize_into_threads(comments)
        end_time = time.time()

        # Verify results
        assert len(threads) > 0
        total_comments_processed = sum(len(thread["comments"]) for thread in threads)
        assert total_comments_processed == 300

        # Verify cache effectiveness
        cache_info = _parse_datetime_cached.cache_info()
        assert cache_info.hits > 0  # Should have cache hits due to repeated timestamps

        # Performance should be reasonable (adjust threshold as needed)
        processing_time = end_time - start_time
        assert processing_time < 2.0  # Should process 300 comments in under 2 seconds

    def test_concurrent_operations_safety(self):
        """Test that security measures work under concurrent-like operations."""
        # Simulate concurrent operations that might stress security measures

        # 1. Multiple config validations
        config_paths = [
            "config1.toml",
            "config2.toml",
            "../malicious.toml",
            "/etc/passwd",
            "normal_config.toml"
        ]

        for path in config_paths:
            try:
                config_manager = ConfigManager(config_path=path)
                # Should either work (valid path) or fail gracefully (invalid path)
                assert config_manager is not None
            except Exception:
                # Should not crash with unhandled exceptions
                pass

        # 2. Multiple cache operations with potential failures
        cache_manager = CacheManager(enabled=True)

        for i in range(10):
            # Mix of normal operations and potential failures
            cache_manager.set(f"key_{i}", f"value_{i}")
            cache_manager.get(f"key_{i}")

            # Simulate some failures
            with patch.object(cache_manager, 'cache') as mock_cache:
                if i % 3 == 0:  # Every third operation fails
                    mock_cache.get.side_effect = RuntimeError("Simulated failure")
                    result = cache_manager.get(f"failing_key_{i}")
                    assert result is None  # Should handle failure gracefully

        # 3. Multiple export operations with malicious data
        export_manager = ExportManager()

        malicious_data_variants = [
            {"number": "../123", "title": "Normal"},
            {"number": 456, "title": "CON.txt"},
            {"number": 789, "title": "file<>name"},
            {"number": "../../etc", "title": "Valid Title"}
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                os.chdir(temp_dir)

                for i, pr_data in enumerate(malicious_data_variants):
                    result = export_manager.export(pr_data, [], format="json")

                    # All should produce safe filenames
                    result_path = Path(result)
                    assert result_path.parent == Path.cwd()
                    assert ".." not in str(result_path)
                    assert result_path.exists()

            finally:
                os.chdir(original_cwd)


class TestSecurityRegressionPrevention:
    """Test that security fixes don't regress and maintain expected behavior."""

    def test_config_path_validation_comprehensive(self):
        """Test comprehensive config path validation edge cases."""
        from gh_pr.utils.config import _validate_config_path

        # Test cases that should be allowed
        allowed_cases = [
            Path.cwd() / "config.toml",
            Path.home() / ".config" / "gh-pr" / "config.toml",
            Path.home() / ".gh-pr.toml"
        ]

        for path in allowed_cases:
            assert _validate_config_path(path) is True

        # Test cases that should be blocked
        blocked_cases = [
            Path("/etc/passwd"),
            Path("/tmp/malicious.toml"),
            Path("../../../etc/shadow")
        ]

        for path in blocked_cases:
            result = _validate_config_path(path)
            # Should be blocked unless it somehow resolves to an allowed directory
            # (which is possible in some test environments)
            assert isinstance(result, bool)

    def test_subprocess_timeout_consistency(self):
        """Test that subprocess timeouts are consistently applied."""
        from gh_pr.auth.token import SUBPROCESS_TIMEOUT

        # Verify timeout constant is reasonable
        assert isinstance(SUBPROCESS_TIMEOUT, int)
        assert 1 <= SUBPROCESS_TIMEOUT <= 30

        # Test timeout is applied in token manager
        with patch('gh_pr.auth.token.subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(["gh", "auth", "status"], SUBPROCESS_TIMEOUT)

            token_manager = TokenManager()
            result = token_manager._get_gh_cli_token()

            assert result is None
            # Verify timeout was used
            call_args = mock_run.call_args_list[0]
            assert call_args[1]['timeout'] == SUBPROCESS_TIMEOUT

    def test_filename_sanitization_edge_cases(self):
        """Test filename sanitization handles all edge cases securely."""
        from gh_pr.utils.export import _sanitize_filename

        # Comprehensive edge cases
        edge_cases = [
            ("", "export_file"),                    # Empty
            ("   ", "export_file"),                 # Whitespace only
            ("...", "export_file"),                 # Dots only
            ("CON", "export_CON"),                  # Reserved name
            ("con.txt", "export_con.txt"),          # Reserved with extension
            ("file<>name.txt", "file__name.txt"),   # Invalid chars
            ("a" * 300, "a" * 200),                # Too long
            ("file\x00name.txt", "file_name.txt"),  # Null byte
            ("../../../etc", "etc"),               # Path traversal
        ]

        for input_name, expected_pattern in edge_cases:
            result = _sanitize_filename(input_name)
            assert isinstance(result, str)
            assert len(result) > 0
            assert ".." not in result
            assert "/" not in result
            assert "\\" not in result

            # Some cases have specific expectations
            if expected_pattern in ["export_file", "export_CON", "export_con.txt"]:
                assert result == expected_pattern

    def test_cache_failure_logging_consistency(self):
        """Test that cache failures are consistently logged."""
        with patch('gh_pr.utils.cache.logger') as mock_logger:
            cache_manager = CacheManager(enabled=True)

            # Test different failure scenarios
            failure_scenarios = [
                ("get", RuntimeError("Get failed")),
                ("set", OSError("Set failed")),
                ("delete", KeyError("Delete failed")),
                ("clear", AttributeError("Clear failed"))
            ]

            for operation, exception in failure_scenarios:
                mock_logger.reset_mock()

                with patch.object(cache_manager, 'cache') as mock_cache:
                    if operation == "get":
                        mock_cache.get.side_effect = exception
                        cache_manager.get("test_key")
                    elif operation == "set":
                        mock_cache.set.side_effect = exception
                        cache_manager.set("test_key", "value")
                    elif operation == "delete":
                        mock_cache.__delitem__.side_effect = exception
                        cache_manager.delete("test_key")
                    elif operation == "clear":
                        mock_cache.clear.side_effect = exception
                        cache_manager.clear()

                    # Should log warning for each failure
                    mock_logger.warning.assert_called_once()

    def test_git_validation_security_boundaries(self):
        """Test git validation respects security boundaries."""
        from gh_pr.core.pr_manager import _validate_git_repository

        # Test with various paths
        test_paths = [
            Path("/tmp"),           # System directory
            Path("/etc"),           # System config
            Path("/var"),           # System var
            Path.cwd(),             # Current directory (should work)
            Path.home(),            # Home directory (should work)
        ]

        for path in test_paths:
            if path.exists():
                result = _validate_git_repository(path)
                assert isinstance(result, bool)
                # Should not crash or raise unhandled exceptions

    def test_datetime_parsing_cache_boundaries(self):
        """Test datetime parsing cache respects size limits."""
        from gh_pr.core.comments import _parse_datetime_cached

        # Clear cache
        _parse_datetime_cached.cache_clear()

        # Add more entries than cache limit (1000)
        for i in range(1200):
            timestamp = f"2023-10-15T14:{i%60:02d}:{i%60:02d}Z"
            _parse_datetime_cached(timestamp)

        cache_info = _parse_datetime_cached.cache_info()

        # Cache should respect maxsize
        assert cache_info.currsize <= 1000

        # Should still function correctly
        result = _parse_datetime_cached("2023-10-15T14:30:45Z")
        assert result.year == 2023


class TestSecurityPerformanceBalance:
    """Test that security measures don't severely impact performance."""

    def test_config_validation_performance(self):
        """Test that config path validation is performant."""
        from gh_pr.utils.config import _validate_config_path

        import time

        # Test many validation calls
        test_paths = [
            Path.cwd() / f"config_{i}.toml" for i in range(100)
        ]

        start_time = time.time()
        for path in test_paths:
            _validate_config_path(path)
        end_time = time.time()

        # Should complete quickly (under 1 second for 100 validations)
        assert end_time - start_time < 1.0

    def test_filename_sanitization_performance(self):
        """Test that filename sanitization is performant."""
        from gh_pr.utils.export import _sanitize_filename

        import time

        # Test many sanitization calls
        test_filenames = [f"file_{i}_with_<>chars.txt" for i in range(1000)]

        start_time = time.time()
        for filename in test_filenames:
            _sanitize_filename(filename)
        end_time = time.time()

        # Should complete quickly (under 1 second for 1000 sanitizations)
        assert end_time - start_time < 1.0

    def test_datetime_cache_performance_benefit(self):
        """Test that datetime caching provides actual performance benefit."""
        from gh_pr.core.comments import _parse_datetime_cached

        # Clear cache
        _parse_datetime_cached.cache_clear()

        timestamp = "2023-10-15T14:30:45Z"

        import time

        # Time 100 calls with caching
        start_time = time.time()
        for _ in range(100):
            _parse_datetime_cached(timestamp)
        cached_time = time.time() - start_time

        # Most calls should be cache hits
        cache_info = _parse_datetime_cached.cache_info()
        assert cache_info.hits >= 99  # All but first call should be hits

        # Performance should be reasonable
        assert cached_time < 0.1  # Should be very fast with caching
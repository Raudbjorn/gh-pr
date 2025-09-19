"""Unit tests for BatchOperations functionality."""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch, MagicMock

import pytest
from rich.console import Console

from gh_pr.core.batch import (
    BatchOperations,
    BatchResult,
    BatchSummary,
    DEFAULT_RATE_LIMIT,
    MAX_CONCURRENT_OPERATIONS,
)
from gh_pr.core.pr_manager import PRManager


class TestBatchResult:
    """Test BatchResult dataclass."""

    def test_creation_with_required_fields(self):
        """Test BatchResult creation with required fields only."""
        result = BatchResult(pr_number=123, success=True)

        assert result.pr_number == 123
        assert result.success is True
        assert result.result is None
        assert result.errors == []  # Should be initialized by __post_init__
        assert result.duration == 0.0

    def test_creation_with_all_fields(self):
        """Test BatchResult creation with all fields."""
        errors = ["Error 1", "Error 2"]
        result = BatchResult(
            pr_number=456,
            success=False,
            result=42,
            errors=errors,
            duration=1.5
        )

        assert result.pr_number == 456
        assert result.success is False
        assert result.result == 42
        assert result.errors == errors
        assert result.duration == 1.5

    def test_post_init_errors_list(self):
        """Test that __post_init__ initializes errors list when None."""
        result = BatchResult(pr_number=123, success=True, errors=None)
        assert result.errors == []

        # Should not modify existing list
        existing_errors = ["Error"]
        result = BatchResult(pr_number=123, success=True, errors=existing_errors)
        assert result.errors == existing_errors


class TestBatchSummary:
    """Test BatchSummary dataclass."""

    def test_creation_with_required_fields(self):
        """Test BatchSummary creation with required fields."""
        summary = BatchSummary(total_prs=10, successful=8, failed=2)

        assert summary.total_prs == 10
        assert summary.successful == 8
        assert summary.failed == 2
        assert summary.total_items_processed == 0
        assert summary.total_duration == 0.0
        assert summary.errors == []

    def test_creation_with_all_fields(self):
        """Test BatchSummary creation with all fields."""
        errors = ["Error 1", "Error 2"]
        summary = BatchSummary(
            total_prs=5,
            successful=3,
            failed=2,
            total_items_processed=42,
            total_duration=10.5,
            errors=errors
        )

        assert summary.total_prs == 5
        assert summary.successful == 3
        assert summary.failed == 2
        assert summary.total_items_processed == 42
        assert summary.total_duration == 10.5
        assert summary.errors == errors

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        # Normal case
        summary = BatchSummary(total_prs=10, successful=8, failed=2)
        assert summary.success_rate == 80.0

        # 100% success
        summary = BatchSummary(total_prs=5, successful=5, failed=0)
        assert summary.success_rate == 100.0

        # 0% success
        summary = BatchSummary(total_prs=3, successful=0, failed=3)
        assert summary.success_rate == 0.0

        # Edge case: no PRs
        summary = BatchSummary(total_prs=0, successful=0, failed=0)
        assert summary.success_rate == 0.0

    def test_post_init_errors_list(self):
        """Test that __post_init__ initializes errors list when None."""
        summary = BatchSummary(total_prs=1, successful=1, failed=0, errors=None)
        assert summary.errors == []


class TestBatchOperations:
    """Test BatchOperations functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_pr_manager = Mock(spec=PRManager)
        self.batch_ops = BatchOperations(self.mock_pr_manager)

    def test_initialization(self):
        """Test BatchOperations initialization."""
        assert self.batch_ops.pr_manager is self.mock_pr_manager
        assert self.batch_ops.rate_limit == DEFAULT_RATE_LIMIT
        assert self.batch_ops.max_concurrent == MAX_CONCURRENT_OPERATIONS

    def test_set_rate_limit_valid(self):
        """Test setting valid rate limits."""
        self.batch_ops.set_rate_limit(2.5)
        assert self.batch_ops.rate_limit == 2.5

        self.batch_ops.set_rate_limit(0.0)
        assert self.batch_ops.rate_limit == 0.0

        self.batch_ops.set_rate_limit(0)
        assert self.batch_ops.rate_limit == 0

    def test_set_rate_limit_invalid(self):
        """Test setting invalid rate limits."""
        with pytest.raises(ValueError, match="Rate limit must be non-negative"):
            self.batch_ops.set_rate_limit(-1.0)

        with pytest.raises(ValueError, match="Rate limit must be non-negative"):
            self.batch_ops.set_rate_limit(-0.1)

    def test_set_concurrency_valid(self):
        """Test setting valid concurrency limits."""
        self.batch_ops.set_concurrency(1)
        assert self.batch_ops.max_concurrent == 1

        self.batch_ops.set_concurrency(10)
        assert self.batch_ops.max_concurrent == 10

    def test_set_concurrency_invalid(self):
        """Test setting invalid concurrency limits."""
        with pytest.raises(ValueError, match="Concurrency must be at least 1"):
            self.batch_ops.set_concurrency(0)

        with pytest.raises(ValueError, match="Concurrency must be at least 1"):
            self.batch_ops.set_concurrency(-1)

    @patch('time.sleep')
    def test_execute_with_rate_limit_basic(self, mock_sleep):
        """Test basic execution with rate limiting."""
        # Mock operation
        def mock_operation(owner, repo, pr_number):
            return f"result_{pr_number}"

        pr_identifiers = [
            ("owner1", "repo1", 1),
            ("owner2", "repo2", 2),
        ]

        results = self.batch_ops._execute_with_rate_limit(
            mock_operation,
            pr_identifiers,
            "Test Operation",
            show_progress=False
        )

        assert len(results) == 2

        # Check results
        result1, result2 = results
        assert result1.pr_number == 1
        assert result1.success is True
        assert result1.result == "result_1"

        assert result2.pr_number == 2
        assert result2.success is True
        assert result2.result == "result_2"

        # Should have rate limited (called sleep once between operations)
        assert mock_sleep.call_count >= 1

    @patch('time.sleep')
    def test_execute_with_rate_limit_no_rate_limit(self, mock_sleep):
        """Test execution with rate limit disabled."""
        self.batch_ops.set_rate_limit(0.0)

        def mock_operation(owner, repo, pr_number):
            return pr_number

        pr_identifiers = [("owner", "repo", 1), ("owner", "repo", 2)]

        results = self.batch_ops._execute_with_rate_limit(
            mock_operation,
            pr_identifiers,
            "Test Operation",
            show_progress=False
        )

        # Should not sleep when rate limit is 0
        mock_sleep.assert_not_called()
        assert len(results) == 2

    def test_execute_with_rate_limit_empty_list(self):
        """Test execution with empty PR list."""
        results = self.batch_ops._execute_with_rate_limit(
            lambda o, r, p: "result",
            [],
            "Test Operation",
            show_progress=False
        )

        assert results == []

    def test_execute_with_rate_limit_operation_exception(self):
        """Test handling of operation exceptions."""
        def failing_operation(owner, repo, pr_number):
            if pr_number == 2:
                raise ValueError("Test error")
            return f"result_{pr_number}"

        pr_identifiers = [
            ("owner", "repo", 1),
            ("owner", "repo", 2),
            ("owner", "repo", 3),
        ]

        results = self.batch_ops._execute_with_rate_limit(
            failing_operation,
            pr_identifiers,
            "Test Operation",
            show_progress=False
        )

        assert len(results) == 3

        # Find results by PR number
        results_by_pr = {r.pr_number: r for r in results}

        assert results_by_pr[1].success is True
        assert results_by_pr[1].result == "result_1"

        assert results_by_pr[2].success is False
        assert "Test error" in results_by_pr[2].errors[0]

        assert results_by_pr[3].success is True
        assert results_by_pr[3].result == "result_3"

    def test_execute_single_operation_success(self):
        """Test _execute_single_operation with successful operation."""
        def mock_operation(owner, repo, pr_number):
            return f"result_{pr_number}"

        result = self.batch_ops._execute_single_operation(
            mock_operation, "owner", "repo", 123
        )

        assert result.pr_number == 123
        assert result.success is True
        assert result.result == "result_123"
        assert result.errors == []
        assert result.duration > 0  # Should have some duration

    def test_execute_single_operation_tuple_result(self):
        """Test _execute_single_operation with tuple result (count, errors)."""
        def mock_operation(owner, repo, pr_number):
            return (5, ["error1", "error2"])

        result = self.batch_ops._execute_single_operation(
            mock_operation, "owner", "repo", 123
        )

        assert result.pr_number == 123
        assert result.success is False  # Has errors
        assert result.result == 5
        assert result.errors == ["error1", "error2"]

    def test_execute_single_operation_tuple_no_errors(self):
        """Test _execute_single_operation with tuple result but no errors."""
        def mock_operation(owner, repo, pr_number):
            return (3, [])

        result = self.batch_ops._execute_single_operation(
            mock_operation, "owner", "repo", 123
        )

        assert result.pr_number == 123
        assert result.success is True  # No errors
        assert result.result == 3
        assert result.errors == []

    def test_execute_single_operation_exception(self):
        """Test _execute_single_operation with operation exception."""
        def failing_operation(owner, repo, pr_number):
            raise RuntimeError("Operation failed")

        result = self.batch_ops._execute_single_operation(
            failing_operation, "owner", "repo", 123
        )

        assert result.pr_number == 123
        assert result.success is False
        assert result.result is None
        assert "Operation failed" in result.errors[0]
        assert result.duration > 0

    def test_resolve_outdated_comments_batch(self):
        """Test resolve_outdated_comments_batch method."""
        # Mock the PR manager method
        self.mock_pr_manager.resolve_outdated_comments.side_effect = [
            (3, []),        # PR 1: 3 comments resolved, no errors
            (0, ["Error"]), # PR 2: 0 comments resolved, 1 error
            (5, []),        # PR 3: 5 comments resolved, no errors
        ]

        pr_identifiers = [
            ("owner", "repo", 1),
            ("owner", "repo", 2),
            ("owner", "repo", 3),
        ]

        with patch.object(self.batch_ops, '_execute_with_rate_limit') as mock_execute:
            # Mock the internal execution to return our expected results
            mock_execute.return_value = [
                BatchResult(1, True, 3, [], 1.0),
                BatchResult(2, False, 0, ["Error"], 0.5),
                BatchResult(3, True, 5, [], 1.5),
            ]

            summary = self.batch_ops.resolve_outdated_comments_batch(
                pr_identifiers, show_progress=False
            )

            # Verify the method was called correctly
            mock_execute.assert_called_once_with(
                self.mock_pr_manager.resolve_outdated_comments,
                pr_identifiers,
                "Resolving outdated comments",
                False
            )

        assert summary.total_prs == 3
        assert summary.successful == 2
        assert summary.failed == 1
        assert summary.total_items_processed == 8  # 3 + 0 + 5

    def test_accept_suggestions_batch(self):
        """Test accept_suggestions_batch method."""
        pr_identifiers = [("owner", "repo", 1)]

        with patch.object(self.batch_ops, '_execute_with_rate_limit') as mock_execute:
            mock_execute.return_value = [BatchResult(1, True, 2, [], 1.0)]

            summary = self.batch_ops.accept_suggestions_batch(
                pr_identifiers, show_progress=False
            )

            mock_execute.assert_called_once_with(
                self.mock_pr_manager.accept_all_suggestions,
                pr_identifiers,
                "Accepting suggestions",
                False
            )

        assert summary.total_prs == 1
        assert summary.successful == 1
        assert summary.failed == 0

    def test_get_pr_data_batch(self):
        """Test get_pr_data_batch method."""
        pr_identifiers = [("owner", "repo", 1)]

        # Mock the PR manager methods
        self.mock_pr_manager.get_pr_data.return_value = {"number": 1, "title": "Test PR"}
        self.mock_pr_manager.get_pr_comments.return_value = [{"id": "comment1"}]

        with patch.object(self.batch_ops, '_execute_with_rate_limit') as mock_execute:
            expected_result = {
                "pr_data": {"number": 1, "title": "Test PR"},
                "comments": [{"id": "comment1"}]
            }
            mock_execute.return_value = [BatchResult(1, True, expected_result, [], 1.0)]

            results = self.batch_ops.get_pr_data_batch(pr_identifiers, show_progress=False)

            # Check that the wrapper function would be called
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args
            operation_func = call_args[0][0]

            # Test the wrapper function
            result = operation_func("owner", "repo", 1)
            assert result["pr_data"]["number"] == 1
            assert len(result["comments"]) == 1

    def test_get_pr_data_batch_wrapper_exception(self):
        """Test get_pr_data_batch wrapper function exception handling."""
        # Mock PR manager method to raise exception
        self.mock_pr_manager.get_pr_data.side_effect = Exception("API Error")

        pr_identifiers = [("owner", "repo", 1)]

        with patch.object(self.batch_ops, '_execute_with_rate_limit') as mock_execute:
            # The wrapper should catch and re-raise with context
            def test_wrapper():
                # Access the wrapper function from the call
                self.batch_ops.get_pr_data_batch(pr_identifiers, show_progress=False)
                operation_func = mock_execute.call_args[0][0]
                return operation_func("owner", "repo", 1)

            with pytest.raises(Exception, match="Failed to get PR data"):
                test_wrapper()

    def test_create_summary(self):
        """Test _create_summary method."""
        results = [
            BatchResult(1, True, 5, [], 1.0),
            BatchResult(2, False, 0, ["Error 1", "Error 2"], 0.5),
            BatchResult(3, True, 3, [], 1.5),
            BatchResult(4, False, 2, ["Error 3"], 2.0),
        ]

        summary = self.batch_ops._create_summary(results, "items processed")

        assert summary.total_prs == 4
        assert summary.successful == 2
        assert summary.failed == 2
        assert summary.total_items_processed == 8  # 5 + 0 + 3 + 0 (only successful int results)
        assert summary.total_duration == 5.0  # 1.0 + 0.5 + 1.5 + 2.0
        assert len(summary.errors) == 3  # Total error messages
        assert "PR #2: Error 1" in summary.errors
        assert "PR #2: Error 2" in summary.errors
        assert "PR #4: Error 3" in summary.errors

    def test_create_summary_non_int_results(self):
        """Test _create_summary with non-integer results."""
        results = [
            BatchResult(1, True, "string_result", [], 1.0),
            BatchResult(2, True, {"data": "dict"}, [], 1.0),
            BatchResult(3, True, None, [], 1.0),
        ]

        summary = self.batch_ops._create_summary(results, "items")

        assert summary.total_items_processed == 0  # Non-int results not counted

    def test_create_summary_empty_results(self):
        """Test _create_summary with empty results."""
        summary = self.batch_ops._create_summary([], "items")

        assert summary.total_prs == 0
        assert summary.successful == 0
        assert summary.failed == 0
        assert summary.total_items_processed == 0
        assert summary.total_duration == 0.0
        assert summary.errors == []

    @patch('gh_pr.core.batch.console.print')
    def test_print_summary(self, mock_console_print):
        """Test print_summary method."""
        summary = BatchSummary(
            total_prs=10,
            successful=8,
            failed=2,
            total_items_processed=42,
            total_duration=15.5,
            errors=["Error 1", "Error 2"]
        )

        self.batch_ops.print_summary(summary, "Test Operation")

        # Should print the panel and errors
        assert mock_console_print.call_count >= 2  # Panel + errors header + errors

    @patch('gh_pr.core.batch.console.print')
    def test_print_summary_many_errors(self, mock_console_print):
        """Test print_summary with many errors (should limit display)."""
        errors = [f"Error {i}" for i in range(15)]
        summary = BatchSummary(
            total_prs=15,
            successful=0,
            failed=15,
            errors=errors
        )

        self.batch_ops.print_summary(summary, "Test Operation")

        # Should mention that there are more errors
        print_calls = [call[0][0] for call in mock_console_print.call_args_list if call[0]]
        error_summary_found = any("and 5 more errors" in str(call) for call in print_calls)
        assert error_summary_found

    @patch('gh_pr.core.batch.console.print')
    def test_print_summary_no_errors(self, mock_console_print):
        """Test print_summary with no errors."""
        summary = BatchSummary(
            total_prs=5,
            successful=5,
            failed=0,
            errors=[]
        )

        self.batch_ops.print_summary(summary, "Test Operation")

        # Should only print the panel, no error section
        print_calls = [str(call) for call in mock_console_print.call_args_list]
        error_section = any("Errors encountered" in call for call in print_calls)
        assert not error_section


class TestBatchOperationsIntegration:
    """Test integration patterns for BatchOperations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_pr_manager = Mock(spec=PRManager)
        self.batch_ops = BatchOperations(self.mock_pr_manager)

    def test_rate_limiting_timing(self):
        """Test that rate limiting actually delays execution."""
        self.batch_ops.set_rate_limit(0.1)  # Short delay for testing

        def quick_operation(owner, repo, pr_number):
            return pr_number

        pr_identifiers = [("owner", "repo", 1), ("owner", "repo", 2)]

        start_time = time.time()
        results = self.batch_ops._execute_with_rate_limit(
            quick_operation,
            pr_identifiers,
            "Test",
            show_progress=False
        )
        end_time = time.time()

        # Should take at least the rate limit time
        assert end_time - start_time >= 0.1
        assert len(results) == 2

    def test_concurrency_control(self):
        """Test that concurrency is properly controlled."""
        self.batch_ops.set_concurrency(2)  # Limit to 2 concurrent operations
        self.batch_ops.set_rate_limit(0)   # No rate limiting for this test

        execution_times = []
        lock = threading.Lock()

        def slow_operation(owner, repo, pr_number):
            start = time.time()
            time.sleep(0.1)  # Simulate work
            end = time.time()
            with lock:
                execution_times.append((start, end, pr_number))
            return pr_number

        pr_identifiers = [(f"owner", f"repo", i) for i in range(4)]

        results = self.batch_ops._execute_with_rate_limit(
            slow_operation,
            pr_identifiers,
            "Test",
            show_progress=False
        )

        assert len(results) == 4

        # Check that no more than 2 operations were running concurrently
        execution_times.sort(key=lambda x: x[0])  # Sort by start time

        for i in range(len(execution_times)):
            concurrent_count = 0
            current_start, current_end, _ = execution_times[i]

            for j, (other_start, other_end, _) in enumerate(execution_times):
                if i != j:
                    # Check if operations overlap
                    if (other_start <= current_start <= other_end or
                        other_start <= current_end <= other_end or
                        current_start <= other_start <= current_end):
                        concurrent_count += 1

            # Should never have more than 1 other concurrent operation (total 2)
            assert concurrent_count <= 1

    def test_progress_bar_integration(self):
        """Test that progress bar works correctly."""
        with patch('rich.progress.Progress') as mock_progress_class:
            mock_progress = Mock()
            mock_task = Mock()
            mock_progress.add_task.return_value = mock_task
            mock_progress_class.return_value = mock_progress

            def mock_operation(owner, repo, pr_number):
                return pr_number

            pr_identifiers = [("owner", "repo", 1), ("owner", "repo", 2)]

            # Test with progress enabled
            results = self.batch_ops._execute_with_rate_limit(
                mock_operation,
                pr_identifiers,
                "Test Operation",
                show_progress=True
            )

            # Progress should be created and used
            mock_progress_class.assert_called_once()
            mock_progress.add_task.assert_called_once()
            assert mock_progress.advance.call_count == 2  # Once per PR

    def test_error_aggregation_pattern(self):
        """Test pattern for collecting and reporting errors across batch."""
        def mixed_operation(owner, repo, pr_number):
            if pr_number % 2 == 0:
                return (0, [f"Error in PR {pr_number}"])
            else:
                return (1, [])

        pr_identifiers = [(f"owner", f"repo", i) for i in range(1, 6)]

        results = self.batch_ops._execute_with_rate_limit(
            mixed_operation,
            pr_identifiers,
            "Test",
            show_progress=False
        )

        summary = self.batch_ops._create_summary(results, "items")

        # Should have errors for even-numbered PRs
        assert summary.failed == 2  # PRs 2 and 4
        assert summary.successful == 3  # PRs 1, 3, and 5
        assert len(summary.errors) == 2
        assert any("Error in PR 2" in error for error in summary.errors)
        assert any("Error in PR 4" in error for error in summary.errors)

    @patch('gh_pr.core.batch.logger')
    def test_logging_integration(self, mock_logger):
        """Test that appropriate logging occurs."""
        results = [
            BatchResult(1, True, 5, [], 1.0),
            BatchResult(2, False, 0, ["Error"], 0.5),
        ]

        summary = self.batch_ops._create_summary(results, "comments resolved")

        # Should log completion summary
        mock_logger.info.assert_called()
        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]

        # Should log about successful/failed PRs and items processed
        completion_log = next((call for call in info_calls if "Batch operation completed" in call), None)
        assert completion_log is not None
        assert "1/2 PRs successful" in completion_log
        assert "5 comments resolved" in completion_log

        # Should log warning about errors
        mock_logger.warning.assert_called()
        warning_calls = [call[0][0] for call in mock_logger.warning.call_args_list]
        error_warning = next((call for call in warning_calls if "errors during batch operation" in call), None)
        assert error_warning is not None


class TestBatchOperationsEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_pr_manager = Mock(spec=PRManager)
        self.batch_ops = BatchOperations(self.mock_pr_manager)

    def test_very_large_batch(self):
        """Test handling of very large batch operations."""
        # Test with 100 PRs
        large_pr_list = [(f"owner{i}", f"repo{i}", i) for i in range(100)]

        def quick_operation(owner, repo, pr_number):
            return pr_number

        results = self.batch_ops._execute_with_rate_limit(
            quick_operation,
            large_pr_list,
            "Large Batch Test",
            show_progress=False
        )

        assert len(results) == 100
        assert all(r.success for r in results)

    def test_zero_rate_limit_performance(self):
        """Test performance with zero rate limiting."""
        self.batch_ops.set_rate_limit(0.0)

        def quick_operation(owner, repo, pr_number):
            return pr_number

        pr_identifiers = [(f"owner", f"repo", i) for i in range(10)]

        start_time = time.time()
        results = self.batch_ops._execute_with_rate_limit(
            quick_operation,
            pr_identifiers,
            "Performance Test",
            show_progress=False
        )
        end_time = time.time()

        # Should complete quickly without rate limiting
        assert end_time - start_time < 1.0  # Should be much faster
        assert len(results) == 10

    def test_single_concurrent_operation(self):
        """Test with concurrency limited to 1."""
        self.batch_ops.set_concurrency(1)

        execution_order = []
        lock = threading.Lock()

        def ordered_operation(owner, repo, pr_number):
            with lock:
                execution_order.append(pr_number)
            time.sleep(0.01)  # Small delay to ensure ordering
            return pr_number

        pr_identifiers = [("owner", "repo", i) for i in [3, 1, 4, 2]]

        results = self.batch_ops._execute_with_rate_limit(
            ordered_operation,
            pr_identifiers,
            "Sequential Test",
            show_progress=False
        )

        assert len(results) == 4
        # With concurrency=1, operations should be more predictably ordered
        # (though ThreadPoolExecutor doesn't guarantee exact ordering)
        assert len(execution_order) == 4

    def test_operation_returning_none(self):
        """Test operation that returns None."""
        def none_operation(owner, repo, pr_number):
            return None

        pr_identifiers = [("owner", "repo", 1)]

        results = self.batch_ops._execute_with_rate_limit(
            none_operation,
            pr_identifiers,
            "None Test",
            show_progress=False
        )

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].result is None

    def test_operation_returning_complex_data(self):
        """Test operation that returns complex data structures."""
        def complex_operation(owner, repo, pr_number):
            return {
                "pr": pr_number,
                "data": ["item1", "item2"],
                "metadata": {"key": "value"}
            }

        pr_identifiers = [("owner", "repo", 1)]

        results = self.batch_ops._execute_with_rate_limit(
            complex_operation,
            pr_identifiers,
            "Complex Test",
            show_progress=False
        )

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].result["pr"] == 1
        assert len(results[0].result["data"]) == 2

    def test_mixed_exception_types(self):
        """Test handling of different exception types."""
        def mixed_exceptions(owner, repo, pr_number):
            if pr_number == 1:
                raise ValueError("Value error")
            elif pr_number == 2:
                raise RuntimeError("Runtime error")
            elif pr_number == 3:
                raise Exception("Generic exception")
            else:
                return f"success_{pr_number}"

        pr_identifiers = [("owner", "repo", i) for i in range(1, 5)]

        results = self.batch_ops._execute_with_rate_limit(
            mixed_exceptions,
            pr_identifiers,
            "Exception Test",
            show_progress=False
        )

        assert len(results) == 4

        results_by_pr = {r.pr_number: r for r in results}

        assert results_by_pr[1].success is False
        assert "Value error" in results_by_pr[1].errors[0]

        assert results_by_pr[2].success is False
        assert "Runtime error" in results_by_pr[2].errors[0]

        assert results_by_pr[3].success is False
        assert "Generic exception" in results_by_pr[3].errors[0]

        assert results_by_pr[4].success is True
        assert results_by_pr[4].result == "success_4"
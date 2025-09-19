"""Batch operations for multiple PRs."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from .pr_manager import PRManager

logger = logging.getLogger(__name__)
console = Console()

# Rate limiting constants
DEFAULT_RATE_LIMIT = 2.0  # seconds between requests
MAX_CONCURRENT_OPERATIONS = 5


@dataclass
class BatchResult:
    """Result of a batch operation."""
    pr_number: int
    success: bool
    result: Any = None
    errors: list[str] = None
    duration: float = 0.0

    def __post_init__(self):
        """Initialize errors list if None."""
        if self.errors is None:
            self.errors = []


@dataclass
class BatchSummary:
    """Summary of batch operation results."""
    total_prs: int
    successful: int
    failed: int
    total_items_processed: int = 0
    total_duration: float = 0.0
    errors: list[str] = None

    def __post_init__(self):
        """Initialize errors list if None."""
        if self.errors is None:
            self.errors = []

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_prs == 0:
            return 0.0
        return (self.successful / self.total_prs) * 100


class BatchOperations:
    """Manages batch operations across multiple PRs."""

    def __init__(self, pr_manager: PRManager):
        """
        Initialize batch operations manager.

        Args:
            pr_manager: PRManager instance for operations
        """
        self.pr_manager = pr_manager
        self.rate_limit = DEFAULT_RATE_LIMIT
        self.max_concurrent = MAX_CONCURRENT_OPERATIONS

    def set_rate_limit(self, seconds: float) -> None:
        """
        Set rate limit between operations.

        Args:
            seconds: Delay in seconds between operations
        """
        if seconds < 0:
            raise ValueError("Rate limit must be non-negative")
        self.rate_limit = seconds

    def set_concurrency(self, max_concurrent: int) -> None:
        """
        Set maximum concurrent operations.

        Args:
            max_concurrent: Maximum number of concurrent operations
        """
        if max_concurrent < 1:
            raise ValueError("Concurrency must be at least 1")
        self.max_concurrent = max_concurrent

    def _execute_with_rate_limit(
        self,
        operation: Callable,
        pr_identifiers: list[tuple[str, str, int]],
        operation_name: str,
        show_progress: bool = True
    ) -> list[BatchResult]:
        """
        Execute operation on multiple PRs with rate limiting and progress tracking.

        Args:
            operation: Function to execute on each PR
            pr_identifiers: List of (owner, repo, pr_number) tuples
            operation_name: Human-readable operation name
            show_progress: Whether to show progress bar

        Returns:
            List of BatchResult objects
        """
        results = []

        if not pr_identifiers:
            logger.warning("No PRs provided for batch operation")
            return results

        # Create progress bar
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            disable=not show_progress
        )

        with progress:
            task = progress.add_task(
                f"[blue]{operation_name}...",
                total=len(pr_identifiers)
            )

            # Use ThreadPoolExecutor for controlled concurrency
            with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
                # Submit all tasks
                future_to_pr = {}
                for owner, repo, pr_number in pr_identifiers:
                    future = executor.submit(self._execute_single_operation, operation, owner, repo, pr_number)
                    future_to_pr[future] = (owner, repo, pr_number)

                # Process completed futures
                for future in as_completed(future_to_pr):
                    owner, repo, pr_number = future_to_pr[future]

                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Unexpected error processing PR {owner}/{repo}#{pr_number}: {e}")
                        results.append(BatchResult(
                            pr_number=pr_number,
                            success=False,
                            errors=[f"Unexpected error: {str(e)}"]
                        ))

                    progress.advance(task)

                    # Rate limiting
                    if self.rate_limit > 0:
                        time.sleep(self.rate_limit)

        return results

    def _execute_single_operation(
        self,
        operation: Callable,
        owner: str,
        repo: str,
        pr_number: int
    ) -> BatchResult:
        """
        Execute a single operation with timing and error handling.

        Args:
            operation: Function to execute
            owner: Repository owner
            repo: Repository name
            pr_number: PR number

        Returns:
            BatchResult with operation outcome
        """
        start_time = time.time()

        try:
            result = operation(owner, repo, pr_number)
            duration = time.time() - start_time

            # Handle different return types from operations
            if isinstance(result, tuple) and len(result) == 2:
                # Operations that return (count, errors)
                count, errors = result
                return BatchResult(
                    pr_number=pr_number,
                    success=len(errors) == 0,
                    result=count,
                    errors=errors,
                    duration=duration
                )
            else:
                # Simple operations that return a single value
                return BatchResult(
                    pr_number=pr_number,
                    success=True,
                    result=result,
                    duration=duration
                )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Operation failed for PR {owner}/{repo}#{pr_number}: {e}")
            return BatchResult(
                pr_number=pr_number,
                success=False,
                errors=[str(e)],
                duration=duration
            )

    def resolve_outdated_comments_batch(
        self,
        pr_identifiers: list[tuple[str, str, int]],
        show_progress: bool = True
    ) -> list[BatchResult]:
        """
        Resolve outdated comments for multiple PRs.

        Args:
            pr_identifiers: List of (owner, repo, pr_number) tuples
            show_progress: Whether to show progress bar

        Returns:
            List of BatchResult objects with detailed results for each PR
        """
        logger.info(f"Starting batch resolve outdated comments for {len(pr_identifiers)} PRs")

        results = self._execute_with_rate_limit(
            self.pr_manager.resolve_outdated_comments,
            pr_identifiers,
            "Resolving outdated comments",
            show_progress
        )

        return results

    def accept_suggestions_batch(
        self,
        pr_identifiers: list[tuple[str, str, int]],
        show_progress: bool = True
    ) -> list[BatchResult]:
        """
        Accept all suggestions for multiple PRs.

        Args:
            pr_identifiers: List of (owner, repo, pr_number) tuples
            show_progress: Whether to show progress bar

        Returns:
            List of BatchResult objects with detailed results for each PR
        """
        logger.info(f"Starting batch accept suggestions for {len(pr_identifiers)} PRs")

        results = self._execute_with_rate_limit(
            self.pr_manager.accept_all_suggestions,
            pr_identifiers,
            "Accepting suggestions",
            show_progress
        )

        return results

    def get_pr_data_batch(
        self,
        pr_identifiers: list[tuple[str, str, int]],
        show_progress: bool = True
    ) -> list[BatchResult]:
        """
        Get PR data for multiple PRs.

        Args:
            pr_identifiers: List of (owner, repo, pr_number) tuples
            show_progress: Whether to show progress bar

        Returns:
            List of BatchResult objects with PR data
        """
        logger.info(f"Starting batch PR data collection for {len(pr_identifiers)} PRs")

        def get_pr_data_wrapper(owner: str, repo: str, pr_number: int):
            """Wrapper to get PR data and comments."""
            try:
                pr_data = self.pr_manager.fetch_pr_data(owner, repo, pr_number)
                comments = self.pr_manager.fetch_pr_comments(owner, repo, pr_number)
                return {"pr_data": pr_data, "comments": comments}
            except Exception as e:
                raise Exception(f"Failed to get PR data: {str(e)}")

        return self._execute_with_rate_limit(
            get_pr_data_wrapper,
            pr_identifiers,
            "Collecting PR data",
            show_progress
        )

    @staticmethod
    def create_summary_from_results(results: list[BatchResult], item_description: str) -> BatchSummary:
        """
        Create a summary from batch results.

        This is a static method to allow callers to create summaries from results if needed.

        Args:
            results: List of BatchResult objects
            item_description: Description of items processed (e.g., "comments resolved")

        Returns:
            BatchSummary with aggregated results
        """
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_items = sum(r.result if r.success and isinstance(r.result, int) else 0 for r in results)
        total_duration = sum(r.duration for r in results)

        # Collect all errors
        all_errors = []
        for result in results:
            if result.errors:
                for error in result.errors:
                    all_errors.append(f"PR #{result.pr_number}: {error}")

        return BatchSummary(
            total_prs=len(results),
            successful=successful,
            failed=failed,
            total_items_processed=total_items,
            total_duration=total_duration,
            errors=all_errors
        )

    def _create_summary(self, results: list[BatchResult], item_description: str) -> BatchSummary:
        """
        Create a summary from batch results.

        Args:
            results: List of BatchResult objects
            item_description: Description of items processed (e.g., "comments resolved")

        Returns:
            BatchSummary with aggregated results
        """
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_items = sum(r.result if r.success and isinstance(r.result, int) else 0 for r in results)
        total_duration = sum(r.duration for r in results)

        # Collect all errors
        all_errors = []
        for result in results:
            if result.errors:
                for error in result.errors:
                    all_errors.append(f"PR #{result.pr_number}: {error}")

        summary = BatchSummary(
            total_prs=len(results),
            successful=successful,
            failed=failed,
            total_items_processed=total_items,
            total_duration=total_duration,
            errors=all_errors
        )

        # Log summary
        logger.info(
            f"Batch operation completed: {successful}/{len(results)} PRs successful, "
            f"{total_items} {item_description}, {failed} failures"
        )

        if all_errors:
            logger.warning(f"Encountered {len(all_errors)} errors during batch operation")

        return summary

    def print_summary(self, summary: BatchSummary, operation_name: str) -> None:
        """
        Print a formatted summary to console.

        Args:
            summary: BatchSummary to display
            operation_name: Name of the operation performed
        """
        pass  # Panel imported at top
        pass  # Table imported at top

        # Create summary table
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total PRs", str(summary.total_prs))
        table.add_row("Successful", str(summary.successful))
        table.add_row("Failed", str(summary.failed))
        table.add_row("Success Rate", f"{summary.success_rate:.1f}%")
        table.add_row("Items Processed", str(summary.total_items_processed))
        table.add_row("Total Duration", f"{summary.total_duration:.2f}s")

        # Create panel with table
        panel = Panel(
            table,
            title=f"[bold white]{operation_name} Summary[/bold white]",
            border_style="blue"
        )

        console.print(panel)

        # Print errors if any
        if summary.errors:
            console.print("\n[bold red]Errors encountered:[/bold red]")
            for error in summary.errors[:10]:  # Limit to first 10 errors
                console.print(f"  • {error}")

            if len(summary.errors) > 10:
                console.print(f"  ... and {len(summary.errors) - 10} more errors")
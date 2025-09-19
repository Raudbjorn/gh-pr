"""Batch operations for processing multiple PRs."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Callable
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID

from .pr_manager import PRManager
from ..auth.permissions import PermissionChecker

logger = logging.getLogger(__name__)

# Constants for batch operations
DEFAULT_RATE_LIMIT = 2.0  # seconds between API calls
DEFAULT_MAX_CONCURRENT = 5
DEFAULT_BATCH_SIZE = 10


@dataclass
class BatchResult:
    """Result from a single batch operation."""
    pr_identifier: str
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class BatchSummary:
    """Summary of batch operation results."""
    total: int = 0
    successful: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)
    results: List[BatchResult] = field(default_factory=list)
    duration: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total == 0:
            return 0.0
        return (self.successful / self.total) * 100


class BatchOperations:
    """Handles batch operations for multiple PRs."""

    def __init__(
        self,
        pr_manager: PRManager,
        permission_checker: PermissionChecker,
        rate_limit: float = DEFAULT_RATE_LIMIT,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT
    ):
        """
        Initialize batch operations.

        Args:
            pr_manager: PRManager instance for operations
            permission_checker: Permission checker instance
            rate_limit: Seconds to wait between API calls
            max_concurrent: Maximum concurrent operations
        """
        self.pr_manager = pr_manager
        self.permission_checker = permission_checker
        self.rate_limit = max(0.1, rate_limit)  # Minimum 0.1 seconds
        self.max_concurrent = max(1, min(max_concurrent, 20))  # Between 1 and 20
        # Lock for rate limiting API calls
        self.api_lock = threading.Lock()

    def _parse_pr_identifier(self, identifier: str) -> Optional[Tuple[str, str, int]]:
        """
        Parse PR identifier in format owner/repo#number.

        Args:
            identifier: PR identifier string

        Returns:
            Tuple of (owner, repo, pr_number) or None if invalid
        """
        try:
            # Expected format: owner/repo#123
            if "#" not in identifier:
                return None

            repo_part, pr_part = identifier.split("#", 1)

            if "/" not in repo_part:
                return None

            owner, repo = repo_part.split("/", 1)
            pr_number = int(pr_part)

            # Validate components
            if not all([owner, repo]) or pr_number <= 0:
                return None

            return owner, repo, pr_number

        except (ValueError, AttributeError):
            return None

    def _execute_with_rate_limit(
        self,
        operation: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute an operation with rate limiting.

        Args:
            operation: Function to execute
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation

        Returns:
            Result from operation
        """
        # Use lock to ensure only one API call happens at a time
        # This properly enforces rate limiting across all threads
        with self.api_lock:
            result = operation(*args, **kwargs)
            time.sleep(self.rate_limit)
        return result

    def resolve_outdated_comments_batch(
        self,
        pr_identifiers: List[str],
        progress: Optional[Progress] = None
    ) -> List[BatchResult]:
        """
        Resolve outdated comments for multiple PRs.

        Args:
            pr_identifiers: List of PR identifiers (owner/repo#number)
            progress: Optional Rich Progress instance

        Returns:
            List of BatchResult objects with detailed results for each PR
        """
        results = []
        start_time = time.time()

        # Setup progress tracking
        task_id = None
        if progress:
            task_id = progress.add_task(
                "[cyan]Resolving outdated comments...",
                total=len(pr_identifiers)
            )

        def process_pr(identifier: str) -> BatchResult:
            """Process a single PR."""
            # Parse identifier
            parsed = self._parse_pr_identifier(identifier)
            if not parsed:
                return BatchResult(
                    pr_identifier=identifier,
                    success=False,
                    message="Invalid PR identifier format",
                    error="Expected format: owner/repo#123"
                )

            owner, repo, pr_number = parsed

            try:
                # Check permissions
                if not self.permission_checker.has_pr_permissions(
                    owner, repo, ["resolve_comments"]
                ):
                    return BatchResult(
                        pr_identifier=identifier,
                        success=False,
                        message="Insufficient permissions",
                        error="Cannot resolve comments without write access"
                    )

                # Execute operation with rate limiting
                resolved_count, errors = self._execute_with_rate_limit(
                    self.pr_manager.resolve_outdated_comments,
                    owner, repo, pr_number
                )

                if errors:
                    return BatchResult(
                        pr_identifier=identifier,
                        success=False,
                        message=f"Failed to resolve comments",
                        details={"resolved": resolved_count},
                        error="; ".join(errors)
                    )

                return BatchResult(
                    pr_identifier=identifier,
                    success=True,
                    message=f"Resolved {resolved_count} outdated comments",
                    details={"resolved": resolved_count}
                )

            except Exception as e:
                logger.error(f"Error processing {identifier}: {e}")
                return BatchResult(
                    pr_identifier=identifier,
                    success=False,
                    message="Unexpected error",
                    error=str(e)
                )

        # Process PRs concurrently
        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            futures = {
                executor.submit(process_pr, identifier): identifier
                for identifier in pr_identifiers
            }

            for future in as_completed(futures):
                result = future.result()
                results.append(result)

                # Result tracking handled by caller if needed

                # Update progress
                if progress and task_id is not None:
                    progress.update(task_id, advance=1)

        return results

    def accept_suggestions_batch(
        self,
        pr_identifiers: List[str],
        progress: Optional[Progress] = None
    ) -> List[BatchResult]:
        """
        Accept all suggestions for multiple PRs.

        Args:
            pr_identifiers: List of PR identifiers (owner/repo#number)
            progress: Optional Rich Progress instance

        Returns:
            List of BatchResult objects with detailed results for each PR
        """
        results = []
        start_time = time.time()

        # Setup progress tracking
        task_id = None
        if progress:
            task_id = progress.add_task(
                "[cyan]Accepting suggestions...",
                total=len(pr_identifiers)
            )

        def process_pr(identifier: str) -> BatchResult:
            """Process a single PR."""
            # Parse identifier
            parsed = self._parse_pr_identifier(identifier)
            if not parsed:
                return BatchResult(
                    pr_identifier=identifier,
                    success=False,
                    message="Invalid PR identifier format",
                    error="Expected format: owner/repo#123"
                )

            owner, repo, pr_number = parsed

            try:
                # Check permissions
                if not self.permission_checker.has_pr_permissions(
                    owner, repo, ["accept_suggestions"]
                ):
                    return BatchResult(
                        pr_identifier=identifier,
                        success=False,
                        message="Insufficient permissions",
                        error="Cannot accept suggestions without write access"
                    )

                # Execute operation with rate limiting
                accepted_count, errors = self._execute_with_rate_limit(
                    self.pr_manager.accept_all_suggestions,
                    owner, repo, pr_number
                )

                if errors:
                    return BatchResult(
                        pr_identifier=identifier,
                        success=False,
                        message=f"Failed to accept suggestions",
                        details={"accepted": accepted_count},
                        error="; ".join(errors)
                    )

                return BatchResult(
                    pr_identifier=identifier,
                    success=True,
                    message=f"Accepted {accepted_count} suggestions",
                    details={"accepted": accepted_count}
                )

            except Exception as e:
                logger.error(f"Error processing {identifier}: {e}")
                return BatchResult(
                    pr_identifier=identifier,
                    success=False,
                    message="Unexpected error",
                    error=str(e)
                )

        # Process PRs concurrently
        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            futures = {
                executor.submit(process_pr, identifier): identifier
                for identifier in pr_identifiers
            }

            for future in as_completed(futures):
                result = future.result()
                results.append(result)

                # Result tracking handled by caller if needed

                # Update progress
                if progress and task_id is not None:
                    progress.update(task_id, advance=1)

        return results

    def get_pr_data_batch(
        self,
        pr_identifiers: List[str],
        progress: Optional[Progress] = None
    ) -> Tuple[List[Dict[str, Any]], BatchSummary]:
        """
        Get PR data for multiple PRs.

        Args:
            pr_identifiers: List of PR identifiers (owner/repo#number)
            progress: Optional Rich Progress instance

        Returns:
            Tuple of (pr_data_list, summary)
        """
        summary = BatchSummary(total=len(pr_identifiers))
        pr_data_list = []
        start_time = time.time()

        # Setup progress tracking
        task_id = None
        if progress:
            task_id = progress.add_task(
                "[cyan]Fetching PR data...",
                total=len(pr_identifiers)
            )

        def fetch_pr(identifier: str) -> Tuple[Optional[Dict[str, Any]], BatchResult]:
            """Fetch data for a single PR."""
            # Parse identifier
            parsed = self._parse_pr_identifier(identifier)
            if not parsed:
                result = BatchResult(
                    pr_identifier=identifier,
                    success=False,
                    message="Invalid PR identifier format",
                    error="Expected format: owner/repo#123"
                )
                return None, result

            owner, repo, pr_number = parsed

            try:
                # Get PR data with rate limiting
                pr_data = self._execute_with_rate_limit(
                    self._get_pr_data,
                    owner, repo, pr_number
                )

                result = BatchResult(
                    pr_identifier=identifier,
                    success=True,
                    message="Successfully fetched PR data",
                    details={
                        "title": pr_data.get("title", ""),
                        "comment_count": pr_data.get("comment_count", 0)
                    }
                )
                return pr_data, result

            except Exception as e:
                logger.error(f"Error fetching {identifier}: {e}")
                result = BatchResult(
                    pr_identifier=identifier,
                    success=False,
                    message="Failed to fetch PR data",
                    error=str(e)
                )
                return None, result

        # Fetch PRs concurrently
        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            futures = {
                executor.submit(fetch_pr, identifier): identifier
                for identifier in pr_identifiers
            }

            for future in as_completed(futures):
                pr_data, result = future.result()
                results.append(result)

                if result.success and pr_data:
                    pr_data_list.append(pr_data)
                    summary.successful += 1
                else:
                    summary.failed += 1
                    if result.error:
                        summary.errors.append(f"{result.pr_identifier}: {result.error}")

                # Update progress
                if progress and task_id is not None:
                    progress.update(task_id, advance=1)

        summary.duration = time.time() - start_time
        return pr_data_list, summary

    def _get_pr_data(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """
        Get PR data from GitHub.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number

        Returns:
            Dictionary with PR data
        """
        # This would normally use the PRManager to get PR data
        # For now, returning a simplified version
        comments = self.pr_manager.get_pr_comments(owner, repo, pr_number)

        return {
            "owner": owner,
            "repo": repo,
            "number": pr_number,
            "identifier": f"{owner}/{repo}#{pr_number}",
            "title": f"PR #{pr_number}",  # Would fetch from API
            "comment_count": len(comments) if comments else 0,
            "comments": comments
        }
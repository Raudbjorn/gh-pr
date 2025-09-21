"""PR management and business logic."""

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from github import GithubException

from ..utils.cache import CacheManager
from .comments import CommentProcessor
from .filters import CommentFilter
from .github import GitHubClient
from .graphql import GraphQLClient

logger = logging.getLogger(__name__)


def _validate_git_repository(directory: Path = None) -> bool:
    """
    Validate that the current or specified directory is a git repository.

    Args:
        directory: Directory to check (defaults to current working directory)

    Returns:
        True if directory is a git repository, False otherwise
    """
    try:
        check_dir = directory or Path.cwd()
        # Check if .git directory exists or if we're in a git worktree
        git_dir = check_dir / ".git"
        if git_dir.exists():
            return True

        # Alternative check using git command
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            timeout=5,
            cwd=check_dir
        )
        return result.returncode == 0

    except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
        logger.debug(f"Git repository validation failed: {e}")
        return False


class PRManager:
    """Manages PR operations and business logic."""

    def __init__(self, github_client: GitHubClient, cache_manager: CacheManager):
        """
        Initialize PRManager.

        Args:
            github_client: GitHub API client
            cache_manager: Cache manager instance
        """
        self.github = github_client
        self.cache = cache_manager
        self.comment_processor = CommentProcessor()
        self.filter = CommentFilter()
        # Initialize GraphQL client with same token as REST client
        self._graphql_client = None

    @property
    def graphql(self) -> GraphQLClient:
        """Get GraphQL client, initializing if needed."""
        if self._graphql_client is None:
            # Use the token stored in GitHubClient
            token = self.github.token
            self._graphql_client = GraphQLClient(token)
        return self._graphql_client

    def parse_pr_identifier(
        self, identifier: str, default_repo: Optional[str] = None
    ) -> tuple[str, str, int]:
        """
        Parse PR identifier into owner, repo, and number.

        Args:
            identifier: PR number, URL, or owner/repo#number
            default_repo: Default repository in owner/repo format

        Returns:
            Tuple of (owner, repo, pr_number)

        Raises:
            ValueError: If identifier cannot be parsed
        """
        # Match full GitHub URL
        url_pattern = r"(?:https?://)?github\.com/([^/]+)/([^/]+)/pull/(\d+)"
        match = re.match(url_pattern, identifier)
        if match:
            return match.group(1), match.group(2), int(match.group(3))

        # Match owner/repo#number format
        repo_pr_pattern = r"([^/]+)/([^/#]+)#(\d+)"
        match = re.match(repo_pr_pattern, identifier)
        if match:
            return match.group(1), match.group(2), int(match.group(3))

        # Match just PR number
        if identifier.isdigit():
            if default_repo and "/" in default_repo:
                owner, repo = default_repo.split("/", 1)
                return owner, repo, int(identifier)

            # Try to get from current git repo
            repo_info = self._get_current_repo_info()
            if repo_info:
                return repo_info[0], repo_info[1], int(identifier)

            raise ValueError("PR number provided but no repository context found")

        raise ValueError(f"Cannot parse PR identifier: {identifier}")

    def auto_detect_pr(self) -> Optional[str]:
        """
        Auto-detect PR for current branch or subdirectories.

        Returns:
            PR identifier string or None
        """
        # First, try current directory
        pr_info = self._get_current_branch_pr()
        if pr_info:
            return pr_info

        # Then try subdirectories
        git_repos = self._find_git_repos()
        if not git_repos:
            return None

        prs = []
        for repo_dir in git_repos:
            pr_info = self._get_pr_from_directory(repo_dir)
            if pr_info:
                prs.append(pr_info)

        if len(prs) == 1:
            return prs[0]["identifier"]
        elif len(prs) > 1:
            # In a real TUI, we would show a selection dialog
            # For now, return the first one
            return prs[0]["identifier"]

        return None

    def _get_current_repo_info(self) -> Optional[tuple[str, str]]:
        """
        Get current git repository info.

        Returns:
            Tuple of (owner, repo) or None
        """
        if not _validate_git_repository():
            logger.debug("Not in a git repository")
            return None

        try:
            # Get remote URL
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return None

            url = result.stdout.strip()

            # Parse GitHub URL
            patterns = [
                r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$",
                r"https?://github\.com/([^/]+)/(.+?)(?:\.git)?$",
            ]

            for pattern in patterns:
                match = re.match(pattern, url)
                if match:
                    repo = match.group(2)
                    if repo.endswith('.git'):
                        repo = repo[:-4]
                    return match.group(1), repo

        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return None

    def _get_current_branch_pr(self) -> Optional[str]:
        """
        Get PR for current git branch using GitHub API.

        Returns:
            PR identifier or None
        """
        if not _validate_git_repository():
            logger.debug("Not in a git repository")
            return None

        try:

            # Get current branch name
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return None

            branch_name = result.stdout.strip()
            if not branch_name:
                return None

            # Get repository info
            repo_info = self._get_current_repo_info()
            if not repo_info:
                return None

            owner, repo = repo_info

            # Use GitHub API to find PR for this branch
            try:
                # List PRs and find one matching our branch
                prs = self.github.get_open_prs(owner, repo, limit=100)
                for pr in prs:
                    if pr.get('head_ref') == branch_name:
                        return f"{owner}/{repo}#{pr['number']}"
            except (GithubException, KeyError, ValueError) as e:
                logger.debug(f"Failed to get PR for branch {branch_name}: {e}")
                pass

        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.debug(f"Failed to detect current branch PR: {e}")
            pass

        return None

    def _find_git_repos(self) -> list[Path]:
        """
        Find git repositories in current directory and subdirectories.

        Returns:
            List of repository paths
        """
        repos = []

        # Check current directory
        if Path(".git").exists():
            repos.append(Path("."))

        # Check immediate subdirectories
        for path in Path(".").iterdir():
            if path.is_dir() and (path / ".git").exists():
                repos.append(path)

        return repos

    def _get_pr_from_directory(self, directory: Path) -> Optional[dict[str, Any]]:
        """
        Get PR info from a specific directory.

        Args:
            directory: Directory path

        Returns:
            PR info dictionary or None
        """
        original_cwd = os.getcwd()
        try:
            os.chdir(directory)

            # Validate git repository in this directory
            if not _validate_git_repository(directory):
                logger.debug(f"Directory {directory} is not a git repository")
                return None

            # Get current branch
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return None

            branch_name = result.stdout.strip()
            if not branch_name:
                return None

            # Get repo info
            repo_info = self._get_current_repo_info()

            if not repo_info:
                return None

            owner, repo = repo_info

            # Use GitHub API to find PR for this branch
            try:
                prs = self.github.get_open_prs(owner, repo, limit=100)
                for pr in prs:
                    if pr.get('head_ref') == branch_name:
                        return {
                            "identifier": f"{owner}/{repo}#{pr['number']}",
                            "number": pr["number"],
                            "title": pr.get("title", ""),
                            "branch": branch_name,
                            "directory": str(directory),
                        }
            except (GithubException, KeyError, ValueError) as e:
                logger.debug(f"Failed to get PR for branch in {directory}: {e}")

        except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
            logger.error(f"Unexpected error in _get_pr_from_directory: {e}", exc_info=True)
        finally:
            os.chdir(original_cwd)

        return None

    def select_pr_interactive(self, repo: Optional[str] = None) -> Optional[str]:
        """
        Interactive PR selection.

        Args:
            repo: Repository in owner/repo format

        Returns:
            Selected PR identifier or None
        """
        # Get open PRs
        if repo:
            owner, repo_name = repo.split("/", 1)
        else:
            repo_info = self._get_current_repo_info()
            if not repo_info:
                return None
            owner, repo_name = repo_info

        try:
            prs = self.github.get_open_prs(owner, repo_name, limit=30)

            if not prs:
                return None

            # In a real implementation, this would use a TUI library
            # For now, return the first PR
            if prs:
                return f"{owner}/{repo_name}#{prs[0]['number']}"

        except GithubException:
            pass

        return None

    def fetch_pr_data(
        self, owner: str, repo: str, pr_number: int
    ) -> dict[str, Any]:
        """
        Fetch complete PR data.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number

        Returns:
            Dictionary with PR data
        """
        cache_key = f"pr_data_{owner}_{repo}_{pr_number}"

        # Check cache
        if self.cache.enabled:
            cached = self.cache.get(cache_key)
            if cached:
                return cached

        try:
            pr = self.github.get_pull_request(owner, repo, pr_number)

            data = {
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "author": pr.user.login if pr.user else "Unknown",
                "created_at": pr.created_at.isoformat() if pr.created_at else None,
                "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
                "merged": pr.merged,
                "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
                # Skip mergeable fields - they trigger expensive API calls
                # Only fetch if explicitly needed for merge operations
                # "mergeable": pr.mergeable,
                # "mergeable_state": pr.mergeable_state,
                "head": {
                    "ref": pr.head.ref,
                    "sha": pr.head.sha,
                },
                "base": {
                    "ref": pr.base.ref,
                    "sha": pr.base.sha,
                },
                "body": pr.body,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "changed_files": pr.changed_files,
                "review_comments": pr.review_comments,
                "comments": pr.comments,
                "commits": pr.commits,
                "labels": [label.name for label in pr.labels],
            }

            # Cache the data
            if self.cache.enabled:
                self.cache.set(cache_key, data, ttl=300)  # 5 minutes

            return data

        except GithubException as e:
            raise ValueError(f"Failed to fetch PR data: {str(e)}") from e

    def fetch_pr_comments(
        self, owner: str, repo: str, pr_number: int, filter_mode: str = "unresolved"
    ) -> list[dict[str, Any]]:
        """
        Fetch and filter PR comments.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            filter_mode: Filter mode for comments

        Returns:
            List of filtered comment dictionaries
        """
        # Get review comments
        review_comments = self.github.get_pr_review_comments(owner, repo, pr_number)

        # Process comments into threads
        threads = self.comment_processor.organize_into_threads(review_comments)

        # Apply filters
        filtered_threads = self.filter.filter_comments(threads, filter_mode)

        return filtered_threads

    def fetch_check_status(
        self, owner: str, repo: str, pr_number: int
    ) -> dict[str, Any]:
        """
        Fetch CI/CD check status for a PR.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number

        Returns:
            Dictionary with check status
        """
        check_runs = self.github.get_check_runs(owner, repo, pr_number)

        status = {
            "total": len(check_runs),
            "success": 0,
            "failure": 0,
            "pending": 0,
            "skipped": 0,
            "neutral": 0,
            "cancelled": 0,
            "timed_out": 0,
            "action_required": 0,
            "checks": check_runs,
        }

        for check in check_runs:
            # Pending: status is not completed
            if check.get("status") in ("queued", "in_progress"):
                status["pending"] += 1
            elif check.get("status") == "completed":
                conclusion = check.get("conclusion")
                if conclusion == "success":
                    status["success"] += 1
                elif conclusion == "failure":
                    status["failure"] += 1
                elif conclusion == "skipped":
                    status["skipped"] += 1
                elif conclusion == "neutral":
                    status["neutral"] += 1
                elif conclusion == "cancelled":
                    status["cancelled"] += 1
                elif conclusion == "timed_out":
                    status["timed_out"] += 1
                elif conclusion == "action_required":
                    status["action_required"] += 1

        return status

    def get_pr_summary(
        self, owner: str, repo: str, pr_number: int
    ) -> dict[str, Any]:
        """
        Get a summary of PR status.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number

        Returns:
            Dictionary with PR summary
        """
        # Get review comments
        review_comments = self.github.get_pr_review_comments(owner, repo, pr_number)
        threads = self.comment_processor.organize_into_threads(review_comments)

        # Get reviews
        reviews = self.github.get_pr_reviews(owner, repo, pr_number)

        # Calculate thread counts
        summary = {
            "total_threads": len(threads),
            "unresolved_active": 0,
            "unresolved_outdated": 0,
            "resolved_active": 0,
            "resolved_outdated": 0,
            "approvals": 0,
            "changes_requested": 0,
            "comments": 0,
        }

        for thread in threads:
            if thread.get("is_resolved"):
                if thread.get("is_outdated"):
                    summary["resolved_outdated"] += 1
                else:
                    summary["resolved_active"] += 1
            else:
                if thread.get("is_outdated"):
                    summary["unresolved_outdated"] += 1
                else:
                    summary["unresolved_active"] += 1

        # Count review states
        for review in reviews:
            if review["state"] == "APPROVED":
                summary["approvals"] += 1
            elif review["state"] == "CHANGES_REQUESTED":
                summary["changes_requested"] += 1
            elif review["state"] == "COMMENTED":
                summary["comments"] += 1

        return summary

    def resolve_outdated_comments(
        self, owner: str, repo: str, pr_number: int
    ) -> tuple[int, list[str]]:
        """
        Resolve all outdated unresolved comments.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number

        Returns:
            Tuple of (number of comments resolved, list of error messages)
        """
        errors = []
        resolved_count = 0

        # Input validation
        if not all([owner, repo]):
            errors.append("Owner and repository name are required")
            return 0, errors

        if pr_number <= 0:
            errors.append("PR number must be positive")
            return 0, errors

        try:
            # Check permissions first
            perm_result = self.graphql.check_permissions(owner, repo)
            if not perm_result.success:
                errors.extend([err.message for err in perm_result.errors])
                return 0, errors

            # Check if user has write permissions
            if perm_result.data:
                repo_data = perm_result.data.get("repository", {})
                permission = repo_data.get("viewerPermission", "")
                if permission not in ["WRITE", "ADMIN", "MAINTAIN"]:
                    errors.append(f"Insufficient permissions. Need WRITE or higher, got {permission}")
                    return 0, errors

            # Get all review threads
            threads_result = self.graphql.get_pr_threads(owner, repo, pr_number)
            if not threads_result.success:
                errors.extend([err.message for err in threads_result.errors])
                return 0, errors

            if not threads_result.data:
                errors.append("No data returned from GitHub API")
                return 0, errors

            # Extract threads from response
            pr_data = threads_result.data.get("repository", {}).get("pullRequest", {})
            if not pr_data:
                errors.append(f"Pull request #{pr_number} not found")
                return 0, errors

            threads = pr_data.get("reviewThreads", {}).get("nodes", [])

            # Filter for outdated, unresolved threads
            outdated_threads = [
                thread for thread in threads
                if thread.get("isOutdated", False) and not thread.get("isResolved", False)
            ]

            logger.info(f"Found {len(outdated_threads)} outdated unresolved threads")

            # Resolve each outdated thread
            for thread in outdated_threads:
                thread_id = thread.get("id")
                if not thread_id:
                    errors.append("Thread missing ID, skipping")
                    continue

                resolve_result = self.graphql.resolve_thread(thread_id)
                if resolve_result.success:
                    resolved_count += 1
                    logger.debug(f"Resolved thread {thread_id}")
                else:
                    error_msgs = [err.message for err in resolve_result.errors]
                    errors.append(f"Failed to resolve thread {thread_id}: {'; '.join(error_msgs)}")

        except Exception as e:
            logger.error(f"Unexpected error resolving outdated comments: {e}")
            errors.append(f"Unexpected error: {str(e)}")

        logger.info(f"Resolved {resolved_count} outdated comments with {len(errors)} errors")
        return resolved_count, errors

    def accept_all_suggestions(
        self, owner: str, repo: str, pr_number: int
    ) -> tuple[int, list[str]]:
        """
        Accept all suggestions in PR comments.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number

        Returns:
            Tuple of (number of suggestions accepted, list of error messages)
        """
        errors = []
        accepted_count = 0

        # Input validation
        if not all([owner, repo]):
            errors.append("Owner and repository name are required")
            return 0, errors

        if pr_number <= 0:
            errors.append("PR number must be positive")
            return 0, errors

        try:
            # Check permissions first
            perm_result = self.graphql.check_permissions(owner, repo)
            if not perm_result.success:
                errors.extend([err.message for err in perm_result.errors])
                return 0, errors

            # Check if user has write permissions
            if perm_result.data:
                repo_data = perm_result.data.get("repository", {})
                permission = repo_data.get("viewerPermission", "")
                if permission not in ["WRITE", "ADMIN", "MAINTAIN"]:
                    errors.append(f"Insufficient permissions. Need WRITE or higher, got {permission}")
                    return 0, errors

            # Get all suggestions in PR
            suggestions_result = self.graphql.get_pr_suggestions(owner, repo, pr_number)
            if not suggestions_result.success:
                errors.extend([err.message for err in suggestions_result.errors])
                return 0, errors

            if not suggestions_result.data:
                errors.append("No data returned from GitHub API")
                return 0, errors

            # Extract suggestions from response
            pr_data = suggestions_result.data.get("repository", {}).get("pullRequest", {})
            if not pr_data:
                errors.append(f"Pull request #{pr_number} not found")
                return 0, errors

            reviews = pr_data.get("reviews", {}).get("nodes", [])
            all_suggestions = []

            # Collect all suggestions from all review comments
            for review in reviews:
                comments = review.get("comments", {}).get("nodes", [])
                for comment in comments:
                    suggestions = comment.get("suggestions", {}).get("nodes", [])
                    all_suggestions.extend(suggestions)

            logger.info(f"Found {len(all_suggestions)} suggestions to accept")

            # Accept each suggestion
            for suggestion in all_suggestions:
                suggestion_id = suggestion.get("id")
                if not suggestion_id:
                    errors.append("Suggestion missing ID, skipping")
                    continue

                accept_result = self.graphql.accept_suggestion(suggestion_id)
                if accept_result.success:
                    accepted_count += 1
                    logger.debug(f"Accepted suggestion {suggestion_id}")
                else:
                    error_msgs = [err.message for err in accept_result.errors]
                    errors.append(f"Failed to accept suggestion {suggestion_id}: {'; '.join(error_msgs)}")

        except Exception as e:
            logger.error(f"Unexpected error accepting suggestions: {e}")
            errors.append(f"Unexpected error: {str(e)}")

        logger.info(f"Accepted {accepted_count} suggestions with {len(errors)} errors")
        return accepted_count, errors


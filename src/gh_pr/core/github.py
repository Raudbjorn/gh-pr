"""GitHub API client wrapper."""

from typing import Any, Optional

from github import Auth, Github, GithubException
from github.PullRequest import PullRequest
from github.Repository import Repository


class GitHubClient:
    """Wrapper for GitHub API operations."""

    def __init__(self, token: str):
        """
        Initialize GitHubClient.

        Args:
            token: GitHub authentication token
        """
        # Store token privately to avoid accidental exposure
        self._token = token
        auth = Auth.Token(token)
        self.github = Github(auth=auth)
        self._user = None

    @property
    def user(self):
        """Get the authenticated user."""
        if not self._user:
            self._user = self.github.get_user()
        return self._user

    def get_repository(self, owner: str, repo: str) -> Repository:
        """
        Get a repository object.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Repository object

        Raises:
            GithubException: If repository not found or access denied
        """
        return self.github.get_repo(f"{owner}/{repo}")

    def get_pull_request(self, owner: str, repo: str, pr_number: int) -> PullRequest:
        """
        Get a pull request object.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            PullRequest object

        Raises:
            GithubException: If PR not found or access denied
        """
        repository = self.get_repository(owner, repo)
        return repository.get_pull(pr_number)

    def get_open_pr_count(self, owner: str, repo: str) -> int:
        """
        Get count of open PRs in a repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Number of open PRs
        """
        try:
            repository = self.get_repository(owner, repo)
            return repository.get_pulls(state="open").totalCount
        except GithubException:
            return 0

    def get_open_prs(
        self, owner: str, repo: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        """
        Get list of open PRs in a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            limit: Maximum number of PRs to return

        Returns:
            List of PR dictionaries
        """
        repository = self.get_repository(owner, repo)
        prs = []

        for pr in repository.get_pulls(state="open"):
            if len(prs) >= limit:
                break
            prs.append({
                "number": pr.number,
                "title": pr.title,
                "author": pr.user.login,
                "branch": pr.head.ref,
                "head_ref": pr.head.ref,  # Add head_ref for consistency
                "created_at": pr.created_at.isoformat() if pr.created_at else None,
                "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
                "draft": pr.draft,
                # Skip mergeable field - it triggers expensive API call
                # "mergeable": pr.mergeable,
                "labels": [label.name for label in pr.labels],
            })

        return prs

    def get_pr_reviews(
        self, owner: str, repo: str, pr_number: int
    ) -> list[dict[str, Any]]:
        """
        Get reviews for a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of review dictionaries
        """
        pr = self.get_pull_request(owner, repo, pr_number)
        return [
            {
                "id": review.id,
                "author": review.user.login if review.user else "Unknown",
                "state": review.state,
                "body": review.body,
                "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
            }
            for review in pr.get_reviews()
        ]

    def get_pr_review_comments(
        self, owner: str, repo: str, pr_number: int
    ) -> list[dict[str, Any]]:
        """
        Get review comments for a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of review comment dictionaries
        """
        pr = self.get_pull_request(owner, repo, pr_number)
        return [
            {
                "id": comment.id,
                "author": comment.user.login if comment.user else "Unknown",
                "body": comment.body,
                "path": comment.path,
                "line": comment.line if comment.line else comment.original_line,
                "start_line": comment.start_line if hasattr(comment, 'start_line') else None,
                "commit_id": comment.commit_id,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
                "updated_at": comment.updated_at.isoformat() if comment.updated_at else None,
                "in_reply_to_id": comment.in_reply_to_id if hasattr(comment, 'in_reply_to_id') else None,
                "diff_hunk": comment.diff_hunk,
                "position": comment.position,
                "original_position": comment.original_position,
            }
            for comment in pr.get_review_comments()
        ]

    def get_pr_issue_comments(
        self, owner: str, repo: str, pr_number: int
    ) -> list[dict[str, Any]]:
        """
        Get issue comments for a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of issue comment dictionaries
        """
        pr = self.get_pull_request(owner, repo, pr_number)
        return [
            {
                "id": comment.id,
                "author": comment.user.login if comment.user else "Unknown",
                "body": comment.body,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
                "updated_at": comment.updated_at.isoformat() if comment.updated_at else None,
            }
            for comment in pr.get_issue_comments()
        ]

    def get_pr_files(
        self, owner: str, repo: str, pr_number: int
    ) -> list[dict[str, Any]]:
        """
        Get files changed in a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of file dictionaries
        """
        pr = self.get_pull_request(owner, repo, pr_number)
        return [
            {
                "filename": file.filename,
                "status": file.status,
                "additions": file.additions,
                "deletions": file.deletions,
                "changes": file.changes,
                "patch": file.patch if hasattr(file, 'patch') else None,
            }
            for file in pr.get_files()
        ]

    def get_check_runs(
        self, owner: str, repo: str, pr_number: int
    ) -> list[dict[str, Any]]:
        """
        Get check runs for a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of check run dictionaries
        """
        pr = self.get_pull_request(owner, repo, pr_number)
        check_runs = []

        # Get the latest commit
        latest_commit_sha = pr.head.sha
        if not latest_commit_sha:
            return check_runs

        latest_commit = self.get_repository(owner, repo).get_commit(latest_commit_sha)

        # Get check runs for the commit
        for check_run in latest_commit.get_check_runs():
            check_runs.append({
                "id": check_run.id,
                "name": check_run.name,
                "status": check_run.status,
                "conclusion": check_run.conclusion,
                "started_at": check_run.started_at.isoformat() if check_run.started_at else None,
                "completed_at": check_run.completed_at.isoformat() if check_run.completed_at else None,
                "output": {
                    "title": check_run.output.title if check_run.output else None,
                    "summary": check_run.output.summary if check_run.output else None,
                } if check_run.output else None,
            })

        return check_runs

    def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> Optional[str]:
        """
        Get file content at a specific ref.

        Args:
            owner: Repository owner
            repo: Repository name
            path: File path
            ref: Git ref (commit SHA, branch, tag)

        Returns:
            File content as string or None if not found
        """
        try:
            repository = self.get_repository(owner, repo)
            content = repository.get_contents(path, ref=ref)

            if isinstance(content, list):
                # If path is a directory, return None
                return None

            # Decode content if it's a file
            return content.decoded_content.decode('utf-8')
        except GithubException:
            return None

    def resolve_review_thread(
        self, owner: str, repo: str, pr_number: int, comment_id: int
    ) -> bool:
        """
        Resolve a review thread (requires GraphQL).

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            comment_id: Comment ID to resolve

        Returns:
            True if successful, False otherwise
        """
        # Note: PyGithub doesn't support resolving threads directly
        # This would require GraphQL API or REST API with specific endpoints
        # For now, this is a placeholder
        return False

    def accept_suggestion(
        self, owner: str, repo: str, pr_number: int, comment_id: int
    ) -> bool:
        """
        Accept a suggestion from a review comment.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            comment_id: Comment ID with suggestion

        Returns:
            True if successful, False otherwise
        """
        # Note: This requires special API endpoint not directly supported by PyGithub
        # Would need to use requests library directly
        return False

    def get_current_user_login(self) -> Optional[str]:
        """
        Get the login of the current authenticated user.

        Returns:
            User login string or None if error
        """
        try:
            return self.user.login
        except GithubException:
            return None

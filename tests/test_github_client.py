"""Unit tests for GitHubClient class."""

import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from github import GithubException

from gh_pr.core.github import GitHubClient


class TestGitHubClient:
    """Test GitHubClient class."""

    @pytest.fixture
    def mock_github(self):
        """Create a mock PyGithub instance."""
        with patch('gh_pr.core.github.Github') as mock_github_class:
            mock_instance = Mock()
            mock_github_class.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def client(self, mock_github):
        """Create a GitHubClient instance with mocked PyGithub."""
        with patch('gh_pr.core.github.Github'):
            return GitHubClient("test_token")

    def test_init(self):
        """Test GitHubClient initialization."""
        client = GitHubClient("test_token_123")
        assert client.token == "test_token_123"
        assert client.github is not None
        assert client._user is None

    def test_user_property_caching(self, client, mock_github):
        """Test that user property is cached after first access."""
        mock_user = Mock()
        mock_user.login = "testuser"
        mock_github.get_user.return_value = mock_user

        # First access
        user1 = client.user
        # Second access
        user2 = client.user

        assert user1 == user2
        assert user1 == mock_user
        # Should only call get_user once
        mock_github.get_user.assert_called_once()

    def test_get_repository(self, client, mock_github):
        """Test repository retrieval."""
        mock_repo = Mock()
        mock_repo.name = "test-repo"
        mock_github.get_repo.return_value = mock_repo

        repo = client.get_repository("owner", "repo")

        assert repo == mock_repo
        mock_github.get_repo.assert_called_once_with("owner/repo")

    def test_get_repository_error_handling(self, client, mock_github):
        """Test repository retrieval error handling."""
        mock_github.get_repo.side_effect = GithubException(404, {"message": "Not found"})

        with pytest.raises(GithubException):
            client.get_repository("owner", "nonexistent")

    def test_get_pull_request(self, client, mock_github):
        """Test PR retrieval."""
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.number = 42
        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        pr = client.get_pull_request("owner", "repo", 42)

        assert pr == mock_pr
        mock_repo.get_pull.assert_called_once_with(42)

    def test_get_open_pr_count(self, client, mock_github):
        """Test counting open PRs."""
        mock_repo = Mock()
        mock_pulls = Mock()
        mock_pulls.totalCount = 15
        mock_repo.get_pulls.return_value = mock_pulls
        mock_github.get_repo.return_value = mock_repo

        count = client.get_open_pr_count("owner", "repo")

        assert count == 15
        mock_repo.get_pulls.assert_called_once_with(state="open", per_page=1)

    def test_get_open_pr_count_error_handling(self, client, mock_github):
        """Test open PR count error handling."""
        mock_github.get_repo.side_effect = GithubException(404, {"message": "Not found"})

        count = client.get_open_pr_count("owner", "nonexistent")

        assert count == 0

    def test_get_open_prs(self, client, mock_github):
        """Test listing open PRs."""
        mock_repo = Mock()

        # Create mock PRs
        mock_pr1 = Mock()
        mock_pr1.number = 1
        mock_pr1.title = "PR 1"
        mock_pr1.user.login = "user1"
        mock_pr1.head.ref = "feature-1"
        mock_pr1.created_at = datetime.now(timezone.utc)
        mock_pr1.updated_at = datetime.now(timezone.utc)

        mock_pr2 = Mock()
        mock_pr2.number = 2
        mock_pr2.title = "PR 2"
        mock_pr2.user.login = "user2"
        mock_pr2.head.ref = "feature-2"
        mock_pr2.created_at = datetime.now(timezone.utc)
        mock_pr2.updated_at = datetime.now(timezone.utc)

        mock_repo.get_pulls.return_value = [mock_pr1, mock_pr2]
        mock_github.get_repo.return_value = mock_repo

        prs = client.get_open_prs("owner", "repo", limit=5)

        assert len(prs) == 2
        assert prs[0]["number"] == 1
        assert prs[0]["title"] == "PR 1"
        assert prs[1]["number"] == 2
        mock_repo.get_pulls.assert_called_once_with(state="open", per_page=5)

    def test_get_open_prs_limit_enforcement(self, client, mock_github):
        """Test that PR listing respects limit."""
        mock_repo = Mock()

        # Create many mock PRs
        mock_prs = []
        for i in range(10):
            mock_pr = Mock()
            mock_pr.number = i
            mock_pr.title = f"PR {i}"
            mock_pr.user.login = f"user{i}"
            mock_pr.head.ref = f"feature-{i}"
            mock_pr.created_at = datetime.now(timezone.utc)
            mock_pr.updated_at = datetime.now(timezone.utc)
            mock_prs.append(mock_pr)

        mock_repo.get_pulls.return_value = mock_prs[:3]  # Simulate GitHub's limit
        mock_github.get_repo.return_value = mock_repo

        prs = client.get_open_prs("owner", "repo", limit=3)

        assert len(prs) == 3
        mock_repo.get_pulls.assert_called_once_with(state="open", per_page=3)

    def test_get_pr_reviews(self, client, mock_github):
        """Test review retrieval."""
        mock_repo = Mock()
        mock_pr = Mock()

        mock_review1 = Mock()
        mock_review1.id = 1
        mock_review1.user.login = "reviewer1"
        mock_review1.state = "APPROVED"
        mock_review1.submitted_at = datetime.now(timezone.utc)
        mock_review1.body = "Looks good!"

        mock_review2 = Mock()
        mock_review2.id = 2
        mock_review2.user.login = "reviewer2"
        mock_review2.state = "CHANGES_REQUESTED"
        mock_review2.submitted_at = datetime.now(timezone.utc)
        mock_review2.body = "Please fix"

        mock_pr.get_reviews.return_value = [mock_review1, mock_review2]
        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        reviews = client.get_pr_reviews("owner", "repo", 42)

        assert len(reviews) == 2
        assert reviews[0]["state"] == "APPROVED"
        assert reviews[0]["author"] == "reviewer1"
        assert reviews[1]["state"] == "CHANGES_REQUESTED"

    def test_get_pr_review_comments(self, client, mock_github):
        """Test review comment retrieval."""
        mock_repo = Mock()
        mock_pr = Mock()

        mock_comment = Mock()
        mock_comment.id = 1
        mock_comment.user.login = "commenter"
        mock_comment.body = "Please fix this"
        mock_comment.path = "src/main.py"
        mock_comment.line = 42
        mock_comment.original_line = 42
        mock_comment.diff_hunk = "@@ -1,3 +1,3 @@"
        mock_comment.created_at = datetime.now(timezone.utc)
        mock_comment.commit_id = "abc123"
        mock_comment.pull_request_review_id = 1
        mock_comment.in_reply_to_id = None
        mock_comment.start_line = None
        mock_comment.original_start_line = None
        mock_comment.position = 1
        mock_comment.original_position = 1

        mock_pr.get_review_comments.return_value = [mock_comment]
        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        comments = client.get_pr_review_comments("owner", "repo", 42)

        assert len(comments) == 1
        assert comments[0]["author"] == "commenter"
        assert comments[0]["body"] == "Please fix this"
        assert comments[0]["path"] == "src/main.py"
        assert comments[0]["line"] == 42

    def test_get_pr_review_comments_missing_attributes(self, client, mock_github):
        """Test review comment retrieval with missing optional attributes."""
        mock_repo = Mock()
        mock_pr = Mock()

        mock_comment = Mock()
        mock_comment.id = 1
        mock_comment.user.login = "commenter"
        mock_comment.body = "Comment"
        mock_comment.path = "file.py"
        mock_comment.line = None  # Missing optional attribute
        mock_comment.original_line = None
        mock_comment.diff_hunk = None
        mock_comment.created_at = datetime.now(timezone.utc)
        mock_comment.commit_id = "abc123"

        # Simulate missing attributes
        del mock_comment.start_line
        del mock_comment.original_start_line
        del mock_comment.position
        del mock_comment.original_position

        mock_pr.get_review_comments.return_value = [mock_comment]
        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        comments = client.get_pr_review_comments("owner", "repo", 42)

        assert len(comments) == 1
        assert comments[0]["line"] is None
        assert comments[0].get("start_line") is None
        assert comments[0].get("position") is None

    def test_get_pr_files(self, client, mock_github):
        """Test file listing for PRs."""
        mock_repo = Mock()
        mock_pr = Mock()

        mock_file1 = Mock()
        mock_file1.filename = "src/main.py"
        mock_file1.status = "modified"
        mock_file1.additions = 10
        mock_file1.deletions = 5
        mock_file1.changes = 15
        mock_file1.patch = "@@ -1,3 +1,3 @@"

        mock_file2 = Mock()
        mock_file2.filename = "README.md"
        mock_file2.status = "added"
        mock_file2.additions = 20
        mock_file2.deletions = 0
        mock_file2.changes = 20
        # Simulate missing patch attribute
        del mock_file2.patch

        mock_pr.get_files.return_value = [mock_file1, mock_file2]
        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        files = client.get_pr_files("owner", "repo", 42)

        assert len(files) == 2
        assert files[0]["filename"] == "src/main.py"
        assert files[0]["patch"] == "@@ -1,3 +1,3 @@"
        assert files[1]["filename"] == "README.md"
        assert files[1].get("patch") is None

    def test_get_check_runs(self, client, mock_github):
        """Test CI/CD check run retrieval."""
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.head.sha = "abc123"

        mock_commit = Mock()

        mock_check_run1 = Mock()
        mock_check_run1.id = 1
        mock_check_run1.name = "Unit Tests"
        mock_check_run1.status = "completed"
        mock_check_run1.conclusion = "success"
        mock_check_run1.started_at = datetime.now(timezone.utc)
        mock_check_run1.completed_at = datetime.now(timezone.utc)
        mock_check_run1.html_url = "https://github.com/..."
        mock_check_run1.output.title = "Tests passed"
        mock_check_run1.output.summary = "All tests passed"

        mock_check_run2 = Mock()
        mock_check_run2.id = 2
        mock_check_run2.name = "Linting"
        mock_check_run2.status = "completed"
        mock_check_run2.conclusion = "failure"
        mock_check_run2.started_at = datetime.now(timezone.utc)
        mock_check_run2.completed_at = datetime.now(timezone.utc)
        mock_check_run2.html_url = "https://github.com/..."
        # Simulate missing output
        del mock_check_run2.output

        mock_commit.get_check_runs.return_value = [mock_check_run1, mock_check_run2]
        mock_repo.get_commit.return_value = mock_commit
        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        checks = client.get_check_runs("owner", "repo", 42)

        assert len(checks) == 2
        assert checks[0]["name"] == "Unit Tests"
        assert checks[0]["conclusion"] == "success"
        assert checks[0]["output"]["title"] == "Tests passed"
        assert checks[1]["name"] == "Linting"
        assert checks[1]["conclusion"] == "failure"
        assert checks[1].get("output") is None

    def test_get_check_runs_no_commit(self, client, mock_github):
        """Test check run retrieval when PR has no commit."""
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.head.sha = None  # No commit

        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        checks = client.get_check_runs("owner", "repo", 42)

        assert checks == []

    def test_get_file_content(self, client, mock_github):
        """Test file content retrieval."""
        mock_repo = Mock()
        mock_file = Mock()
        mock_file.type = "file"
        mock_file.decoded_content = b"def main():\n    pass"  # raw bytes

        mock_repo.get_contents.return_value = mock_file
        mock_github.get_repo.return_value = mock_repo

        content = client.get_file_content("owner", "repo", "src/main.py", "main")

        assert content == "def main():\n    pass"
        mock_repo.get_contents.assert_called_once_with("src/main.py", ref="main")

    def test_get_file_content_directory(self, client, mock_github):
        """Test that directories return None."""
        mock_repo = Mock()
        # Return a list to simulate directory contents
        mock_repo.get_contents.return_value = [Mock()]  # Directory returns list
        mock_github.get_repo.return_value = mock_repo

        content = client.get_file_content("owner", "repo", "src/", "main")

        assert content is None

    def test_get_file_content_not_found(self, client, mock_github):
        """Test file content retrieval for missing files."""
        mock_repo = Mock()
        mock_repo.get_contents.side_effect = GithubException(404, {"message": "Not found"})
        mock_github.get_repo.return_value = mock_repo

        content = client.get_file_content("owner", "repo", "missing.py", "main")

        assert content is None

    def test_get_current_user_login(self, client, mock_github):
        """Test getting current user login."""
        mock_user = Mock()
        mock_user.login = "current_user"
        mock_github.get_user.return_value = mock_user

        login = client.get_current_user_login()

        assert login == "current_user"
        mock_github.get_user.assert_called_once()

    def test_get_current_user_login_error(self, client, mock_github):
        """Test getting current user login with error."""
        mock_github.get_user.side_effect = GithubException(401, {"message": "Bad credentials"})

        login = client.get_current_user_login()

        assert login is None

    def test_resolve_review_thread(self, client):
        """Test review thread resolution (placeholder)."""
        result = client.resolve_review_thread("owner", "repo", 42, 1)
        assert result is False  # Not implemented

    def test_accept_suggestion(self, client):
        """Test suggestion acceptance (placeholder)."""
        result = client.accept_suggestion("owner", "repo", 42, 1)
        assert result is False  # Not implemented
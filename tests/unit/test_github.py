"""
Unit tests for core.github module.

Tests GitHub API client wrapper functionality.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from github import Github, GithubException
from github.PullRequest import PullRequest
from github.Repository import Repository

from gh_pr.core.github import GitHubClient

# Test constants
DEFAULT_TIMEOUT = 30
CONNECTION_TIMEOUT = 10


class TestGitHubClient(unittest.TestCase):
    """Test GitHubClient functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.token = "ghp_FAKE_TEST_TOKEN_REPLACED"

        # Mock Github instance
        self.mock_github = Mock(spec=Github)

        with patch('gh_pr.core.github.Github') as mock_github_class:
            mock_github_class.return_value = self.mock_github
            self.client = GitHubClient(self.token)

    def test_init_with_defaults(self):
        """Test initialization with default timeout."""
        with patch('gh_pr.core.github.Github') as mock_github_class:
            client = GitHubClient("test_token")

            mock_github_class.assert_called_once_with("test_token", timeout=DEFAULT_TIMEOUT)
            self.assertEqual(client.timeout, DEFAULT_TIMEOUT)

    def test_init_with_custom_timeout(self):
        """Test initialization with custom timeout."""
        custom_timeout = 60

        with patch('gh_pr.core.github.Github') as mock_github_class:
            client = GitHubClient("test_token", timeout=custom_timeout)

            mock_github_class.assert_called_once_with("test_token", timeout=custom_timeout)
            self.assertEqual(client.timeout, custom_timeout)

    def test_user_property_lazy_loading(self):
        """Test that user property is lazily loaded and cached."""
        mock_user = Mock()
        self.mock_github.get_user.return_value = mock_user

        # First access
        user1 = self.client.user
        self.assertEqual(user1, mock_user)
        self.mock_github.get_user.assert_called_once()

        # Second access should use cached value
        user2 = self.client.user
        self.assertEqual(user2, mock_user)
        # Should still only be called once
        self.mock_github.get_user.assert_called_once()

    def test_get_repository_success(self):
        """Test successful repository retrieval."""
        mock_repo = Mock(spec=Repository)
        self.mock_github.get_repo.return_value = mock_repo

        result = self.client.get_repository("owner", "repo")

        self.assertEqual(result, mock_repo)
        self.mock_github.get_repo.assert_called_once_with("owner/repo")

    def test_get_repository_not_found(self):
        """Test repository retrieval when repository not found."""
        self.mock_github.get_repo.side_effect = GithubException(404, "Not Found")

        with self.assertRaises(GithubException):
            self.client.get_repository("owner", "nonexistent")

    def test_get_pull_request_success(self):
        """Test successful pull request retrieval."""
        mock_repo = Mock(spec=Repository)
        mock_pr = Mock(spec=PullRequest)

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr

        result = self.client.get_pull_request("owner", "repo", 123)

        self.assertEqual(result, mock_pr)
        self.mock_github.get_repo.assert_called_once_with("owner/repo")
        mock_repo.get_pull.assert_called_once_with(123)

    def test_get_pull_request_not_found(self):
        """Test pull request retrieval when PR not found."""
        mock_repo = Mock(spec=Repository)
        mock_repo.get_pull.side_effect = GithubException(404, "Not Found")
        self.mock_github.get_repo.return_value = mock_repo

        with self.assertRaises(GithubException):
            self.client.get_pull_request("owner", "repo", 999)

    def test_get_open_pr_count_success(self):
        """Test getting open PR count successfully."""
        mock_repo = Mock(spec=Repository)
        mock_pulls = Mock()
        mock_pulls.totalCount = 42

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pulls.return_value = mock_pulls

        result = self.client.get_open_pr_count("owner", "repo")

        self.assertEqual(result, 42)
        mock_repo.get_pulls.assert_called_once_with(state="open")

    def test_get_open_pr_count_github_exception(self):
        """Test getting open PR count with GitHub exception."""
        self.mock_github.get_repo.side_effect = GithubException(403, "Forbidden")

        result = self.client.get_open_pr_count("owner", "repo")

        self.assertEqual(result, 0)

    def test_get_open_prs_success(self):
        """Test getting list of open PRs successfully."""
        mock_repo = Mock(spec=Repository)

        # Create mock PRs with all required attributes
        mock_pr1 = Mock()
        mock_pr1.number = 1
        mock_pr1.title = "Test PR 1"
        mock_pr1.user.login = "author1"
        mock_pr1.head.ref = "feature-1"
        mock_pr1.created_at = datetime(2024, 1, 1, 12, 0)
        mock_pr1.updated_at = datetime(2024, 1, 2, 12, 0)
        mock_pr1.draft = False
        mock_pr1.mergeable = True
        mock_pr1.labels = []

        mock_pr2 = Mock()
        mock_pr2.number = 2
        mock_pr2.title = "Test PR 2"
        mock_pr2.user.login = "author2"
        mock_pr2.head.ref = "feature-2"
        mock_pr2.created_at = None
        mock_pr2.updated_at = None
        mock_pr2.draft = True
        mock_pr2.mergeable = False
        mock_pr2.labels = [Mock(name="bug"), Mock(name="urgent")]

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pulls.return_value = [mock_pr1, mock_pr2]

        result = self.client.get_open_prs("owner", "repo", limit=10)

        self.assertEqual(len(result), 2)

        # Check first PR
        self.assertEqual(result[0]["number"], 1)
        self.assertEqual(result[0]["title"], "Test PR 1")
        self.assertEqual(result[0]["author"], "author1")
        self.assertEqual(result[0]["branch"], "feature-1")
        self.assertEqual(result[0]["head_ref"], "feature-1")
        self.assertEqual(result[0]["created_at"], "2024-01-01T12:00:00")
        self.assertEqual(result[0]["updated_at"], "2024-01-02T12:00:00")
        self.assertFalse(result[0]["draft"])
        self.assertTrue(result[0]["mergeable"])
        self.assertEqual(result[0]["labels"], [])

        # Check second PR
        self.assertEqual(result[1]["number"], 2)
        self.assertIsNone(result[1]["created_at"])
        self.assertIsNone(result[1]["updated_at"])
        self.assertTrue(result[1]["draft"])
        self.assertFalse(result[1]["mergeable"])
        self.assertEqual(result[1]["labels"], ["bug", "urgent"])

    def test_get_open_prs_with_limit(self):
        """Test getting open PRs with limit applied."""
        mock_repo = Mock(spec=Repository)

        # Create 5 mock PRs
        mock_prs = []
        for i in range(5):
            mock_pr = Mock()
            mock_pr.number = i + 1
            mock_pr.title = f"Test PR {i + 1}"
            mock_pr.user.login = f"author{i + 1}"
            mock_pr.head.ref = f"feature-{i + 1}"
            mock_pr.created_at = None
            mock_pr.updated_at = None
            mock_pr.draft = False
            mock_pr.mergeable = True
            mock_pr.labels = []
            mock_prs.append(mock_pr)

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pulls.return_value = mock_prs

        result = self.client.get_open_prs("owner", "repo", limit=3)

        # Should only return first 3 PRs
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["number"], 1)
        self.assertEqual(result[2]["number"], 3)

    def test_get_pr_reviews_success(self):
        """Test getting PR reviews successfully."""
        mock_repo = Mock()
        mock_pr = Mock()

        # Create mock reviews
        mock_review1 = Mock()
        mock_review1.id = 1
        mock_review1.user.login = "reviewer1"
        mock_review1.state = "APPROVED"
        mock_review1.body = "Looks good!"
        mock_review1.submitted_at = datetime(2024, 1, 1, 12, 0)

        mock_review2 = Mock()
        mock_review2.id = 2
        mock_review2.user = None  # Test None user handling
        mock_review2.state = "CHANGES_REQUESTED"
        mock_review2.body = "Please fix issues"
        mock_review2.submitted_at = None

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr
        mock_pr.get_reviews.return_value = [mock_review1, mock_review2]

        result = self.client.get_pr_reviews("owner", "repo", 123)

        self.assertEqual(len(result), 2)

        # Check first review
        self.assertEqual(result[0]["id"], 1)
        self.assertEqual(result[0]["author"], "reviewer1")
        self.assertEqual(result[0]["state"], "APPROVED")
        self.assertEqual(result[0]["body"], "Looks good!")
        self.assertEqual(result[0]["submitted_at"], "2024-01-01T12:00:00")

        # Check second review with None user
        self.assertEqual(result[1]["id"], 2)
        self.assertEqual(result[1]["author"], "Unknown")
        self.assertEqual(result[1]["state"], "CHANGES_REQUESTED")
        self.assertIsNone(result[1]["submitted_at"])

    def test_get_pr_review_comments_success(self):
        """Test getting PR review comments successfully."""
        mock_repo = Mock()
        mock_pr = Mock()

        # Create mock review comment
        mock_comment = Mock()
        mock_comment.id = 1
        mock_comment.user.login = "commenter"
        mock_comment.body = "This needs fixing"
        mock_comment.path = "src/main.py"
        mock_comment.line = 42
        mock_comment.original_line = None
        mock_comment.start_line = None
        mock_comment.commit_id = "abc123"
        mock_comment.created_at = datetime(2024, 1, 1, 12, 0)
        mock_comment.updated_at = datetime(2024, 1, 1, 13, 0)
        mock_comment.in_reply_to_id = None
        mock_comment.diff_hunk = "@@ -40,3 +40,3 @@"
        mock_comment.position = 1
        mock_comment.original_position = 1

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr
        mock_pr.get_review_comments.return_value = [mock_comment]

        result = self.client.get_pr_review_comments("owner", "repo", 123)

        self.assertEqual(len(result), 1)
        comment = result[0]

        self.assertEqual(comment["id"], 1)
        self.assertEqual(comment["author"], "commenter")
        self.assertEqual(comment["body"], "This needs fixing")
        self.assertEqual(comment["path"], "src/main.py")
        self.assertEqual(comment["line"], 42)
        self.assertIsNone(comment["start_line"])
        self.assertEqual(comment["commit_id"], "abc123")
        self.assertEqual(comment["created_at"], "2024-01-01T12:00:00")
        self.assertEqual(comment["updated_at"], "2024-01-01T13:00:00")
        self.assertIsNone(comment["in_reply_to_id"])

    def test_get_pr_issue_comments_success(self):
        """Test getting PR issue comments successfully."""
        mock_repo = Mock()
        mock_pr = Mock()

        # Create mock issue comment
        mock_comment = Mock()
        mock_comment.id = 1
        mock_comment.user.login = "commenter"
        mock_comment.body = "General comment"
        mock_comment.created_at = datetime(2024, 1, 1, 12, 0)
        mock_comment.updated_at = None

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr
        mock_pr.get_issue_comments.return_value = [mock_comment]

        result = self.client.get_pr_issue_comments("owner", "repo", 123)

        self.assertEqual(len(result), 1)
        comment = result[0]

        self.assertEqual(comment["id"], 1)
        self.assertEqual(comment["author"], "commenter")
        self.assertEqual(comment["body"], "General comment")
        self.assertEqual(comment["created_at"], "2024-01-01T12:00:00")
        self.assertIsNone(comment["updated_at"])

    def test_get_pr_files_success(self):
        """Test getting PR files successfully."""
        mock_repo = Mock()
        mock_pr = Mock()

        # Create mock file
        mock_file = Mock()
        mock_file.filename = "src/main.py"
        mock_file.status = "modified"
        mock_file.additions = 10
        mock_file.deletions = 5
        mock_file.changes = 15
        mock_file.patch = "@@ -1,3 +1,3 @@\n-old line\n+new line"

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr
        mock_pr.get_files.return_value = [mock_file]

        result = self.client.get_pr_files("owner", "repo", 123)

        self.assertEqual(len(result), 1)
        file_info = result[0]

        self.assertEqual(file_info["filename"], "src/main.py")
        self.assertEqual(file_info["status"], "modified")
        self.assertEqual(file_info["additions"], 10)
        self.assertEqual(file_info["deletions"], 5)
        self.assertEqual(file_info["changes"], 15)
        self.assertEqual(file_info["patch"], "@@ -1,3 +1,3 @@\n-old line\n+new line")

    def test_get_pr_files_no_patch(self):
        """Test getting PR files when patch attribute doesn't exist."""
        mock_repo = Mock()
        mock_pr = Mock()

        # Create mock file without patch attribute
        mock_file = Mock(spec=['filename', 'status', 'additions', 'deletions', 'changes'])
        mock_file.filename = "src/test.py"
        mock_file.status = "added"
        mock_file.additions = 20
        mock_file.deletions = 0
        mock_file.changes = 20

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr
        mock_pr.get_files.return_value = [mock_file]

        result = self.client.get_pr_files("owner", "repo", 123)

        self.assertEqual(len(result), 1)
        file_info = result[0]

        self.assertEqual(file_info["filename"], "src/test.py")
        self.assertIsNone(file_info["patch"])

    def test_get_check_runs_success(self):
        """Test getting check runs successfully."""
        mock_repo = Mock()
        mock_pr = Mock()
        mock_commit = Mock()

        # Create mock check run
        mock_check_run = Mock()
        mock_check_run.id = 1
        mock_check_run.name = "CI Tests"
        mock_check_run.status = "completed"
        mock_check_run.conclusion = "success"
        mock_check_run.started_at = datetime(2024, 1, 1, 12, 0)
        mock_check_run.completed_at = datetime(2024, 1, 1, 12, 30)

        mock_output = Mock()
        mock_output.title = "Tests passed"
        mock_output.summary = "All tests successful"
        mock_check_run.output = mock_output

        mock_pr.head.sha = "abc123"

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_commit.return_value = mock_commit
        mock_commit.get_check_runs.return_value = [mock_check_run]

        result = self.client.get_check_runs("owner", "repo", 123)

        self.assertEqual(len(result), 1)
        check = result[0]

        self.assertEqual(check["id"], 1)
        self.assertEqual(check["name"], "CI Tests")
        self.assertEqual(check["status"], "completed")
        self.assertEqual(check["conclusion"], "success")
        self.assertEqual(check["started_at"], "2024-01-01T12:00:00")
        self.assertEqual(check["completed_at"], "2024-01-01T12:30:00")
        self.assertEqual(check["output"]["title"], "Tests passed")
        self.assertEqual(check["output"]["summary"], "All tests successful")

    def test_get_check_runs_no_head_sha(self):
        """Test getting check runs when PR has no head SHA."""
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.head.sha = None

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr

        result = self.client.get_check_runs("owner", "repo", 123)

        self.assertEqual(result, [])

    def test_get_check_runs_no_output(self):
        """Test getting check runs when check run has no output."""
        mock_repo = Mock()
        mock_pr = Mock()
        mock_commit = Mock()

        # Create mock check run without output
        mock_check_run = Mock()
        mock_check_run.id = 1
        mock_check_run.name = "Lint"
        mock_check_run.status = "completed"
        mock_check_run.conclusion = "failure"
        mock_check_run.started_at = None
        mock_check_run.completed_at = None
        mock_check_run.output = None

        mock_pr.head.sha = "abc123"

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_commit.return_value = mock_commit
        mock_commit.get_check_runs.return_value = [mock_check_run]

        result = self.client.get_check_runs("owner", "repo", 123)

        self.assertEqual(len(result), 1)
        check = result[0]

        self.assertEqual(check["id"], 1)
        self.assertIsNone(check["started_at"])
        self.assertIsNone(check["completed_at"])
        self.assertIsNone(check["output"])

    def test_get_file_content_success(self):
        """Test getting file content successfully."""
        mock_repo = Mock()
        mock_content = Mock()
        mock_content.decoded_content = b"print('Hello, World!')"

        self.mock_github.get_repo.return_value = mock_repo
        mock_repo.get_contents.return_value = mock_content

        result = self.client.get_file_content("owner", "repo", "main.py", "main")

        self.assertEqual(result, "print('Hello, World!')")
        mock_repo.get_contents.assert_called_once_with("main.py", ref="main")

    def test_get_file_content_directory(self):
        """Test getting file content when path is a directory."""
        mock_repo = Mock()
        # Return a list (indicates directory)
        mock_repo.get_contents.return_value = [Mock(), Mock()]

        self.mock_github.get_repo.return_value = mock_repo

        result = self.client.get_file_content("owner", "repo", "src/", "main")

        self.assertIsNone(result)

    def test_get_file_content_not_found(self):
        """Test getting file content when file not found."""
        mock_repo = Mock()
        mock_repo.get_contents.side_effect = GithubException(404, "Not Found")

        self.mock_github.get_repo.return_value = mock_repo

        result = self.client.get_file_content("owner", "repo", "nonexistent.py", "main")

        self.assertIsNone(result)

    def test_resolve_review_thread_placeholder(self):
        """Test resolve_review_thread placeholder method."""
        # This method is currently a placeholder
        result = self.client.resolve_review_thread("owner", "repo", 123, 456)
        self.assertFalse(result)

    def test_accept_suggestion_placeholder(self):
        """Test accept_suggestion placeholder method."""
        # This method is currently a placeholder
        result = self.client.accept_suggestion("owner", "repo", 123, 456)
        self.assertFalse(result)

    def test_get_current_user_login(self):
        """Test getting current user login."""
        mock_user = Mock()
        mock_user.login = "testuser"
        self.mock_github.get_user.return_value = mock_user

        result = self.client.get_current_user_login()

        self.assertEqual(result, "testuser")

    def test_constants_are_defined(self):
        """Test that timeout constants are properly defined."""
        self.assertIsInstance(DEFAULT_TIMEOUT, int)
        self.assertIsInstance(CONNECTION_TIMEOUT, int)
        self.assertGreater(DEFAULT_TIMEOUT, 0)
        self.assertGreater(CONNECTION_TIMEOUT, 0)
        self.assertLessEqual(CONNECTION_TIMEOUT, DEFAULT_TIMEOUT)


if __name__ == '__main__':
    unittest.main()
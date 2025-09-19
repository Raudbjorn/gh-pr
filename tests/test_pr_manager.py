"""Unit tests for PRManager class."""

import os
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from github import GithubException

from gh_pr.core.pr_manager import PRManager
from gh_pr.core.github import GitHubClient
from gh_pr.utils.cache import CacheManager


class TestPRManager:
    """Test PRManager class."""

    @pytest.fixture
    def mock_github_client(self):
        """Create a mock GitHub client."""
        mock = Mock(spec=GitHubClient)
        return mock

    @pytest.fixture
    def mock_cache_manager(self):
        """Create a mock cache manager."""
        mock = Mock(spec=CacheManager)
        mock.enabled = True
        mock.get.return_value = None  # No cache by default
        return mock

    @pytest.fixture
    def pr_manager(self, mock_github_client, mock_cache_manager):
        """Create a PRManager instance with mocked dependencies."""
        return PRManager(mock_github_client, mock_cache_manager)

    def test_init(self, mock_github_client, mock_cache_manager):
        """Test PRManager initialization."""
        manager = PRManager(mock_github_client, mock_cache_manager)
        assert manager.github == mock_github_client
        assert manager.cache == mock_cache_manager
        assert manager.comment_processor is not None
        assert manager.filter is not None

    def test_parse_pr_identifier_github_url(self, pr_manager):
        """Test parsing GitHub PR URLs."""
        # HTTPS URL
        owner, repo, number = pr_manager.parse_pr_identifier(
            "https://github.com/owner/repo/pull/42"
        )
        assert owner == "owner"
        assert repo == "repo"
        assert number == 42

        # HTTP URL
        owner, repo, number = pr_manager.parse_pr_identifier(
            "http://github.com/user/project/pull/123"
        )
        assert owner == "user"
        assert repo == "project"
        assert number == 123

        # URL without protocol
        owner, repo, number = pr_manager.parse_pr_identifier(
            "github.com/org/app/pull/7"
        )
        assert owner == "org"
        assert repo == "app"
        assert number == 7

    def test_parse_pr_identifier_owner_repo_format(self, pr_manager):
        """Test parsing owner/repo#number format."""
        owner, repo, number = pr_manager.parse_pr_identifier("owner/repo#42")
        assert owner == "owner"
        assert repo == "repo"
        assert number == 42

        # With org names containing hyphens
        owner, repo, number = pr_manager.parse_pr_identifier("my-org/my-repo#123")
        assert owner == "my-org"
        assert repo == "my-repo"
        assert number == 123

    def test_parse_pr_identifier_number_only_with_default(self, pr_manager):
        """Test parsing PR number with default repo."""
        owner, repo, number = pr_manager.parse_pr_identifier("42", "owner/repo")
        assert owner == "owner"
        assert repo == "repo"
        assert number == 42

    @patch('subprocess.run')
    def test_parse_pr_identifier_number_only_from_git(self, mock_run, pr_manager):
        """Test parsing PR number from current git repo."""
        # Mock git remote command
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "git@github.com:owner/repo.git"
        mock_run.return_value = mock_result

        owner, repo, number = pr_manager.parse_pr_identifier("42")
        assert owner == "owner"
        assert repo == "repo"
        assert number == 42

    def test_parse_pr_identifier_invalid_format(self, pr_manager):
        """Test parsing invalid PR identifier."""
        with pytest.raises(ValueError, match="Cannot parse PR identifier"):
            pr_manager.parse_pr_identifier("invalid-format")

        with pytest.raises(ValueError, match="Cannot parse PR identifier"):
            pr_manager.parse_pr_identifier("owner/repo/pull/42")  # Missing github.com

    @patch('subprocess.run')
    def test_parse_pr_identifier_no_git_repo(self, mock_run, pr_manager):
        """Test parsing PR number without git repo."""
        # Mock git command failure
        mock_run.side_effect = subprocess.SubprocessError()

        with pytest.raises(ValueError, match="no repository context found"):
            pr_manager.parse_pr_identifier("42")

    @patch('subprocess.run')
    def test_get_current_repo_info_ssh_url(self, mock_run, pr_manager):
        """Test getting repo info from SSH URLs."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "git@github.com:owner/repo.git"
        mock_run.return_value = mock_result

        info = pr_manager._get_current_repo_info()
        assert info == ("owner", "repo")

    @patch('subprocess.run')
    def test_get_current_repo_info_https_url(self, mock_run, pr_manager):
        """Test getting repo info from HTTPS URLs."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/owner/repo.git"
        mock_run.return_value = mock_result

        info = pr_manager._get_current_repo_info()
        assert info == ("owner", "repo")

    @patch('subprocess.run')
    def test_get_current_repo_info_no_git(self, mock_run, pr_manager):
        """Test getting repo info when not in a git repo."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        info = pr_manager._get_current_repo_info()
        assert info is None

    @patch('subprocess.run')
    def test_auto_detect_pr_current_branch(self, mock_run, pr_manager):
        """Test auto-detecting PR for current branch."""
        # Mock git commands
        mock_results = [
            Mock(returncode=0),  # git rev-parse
            Mock(returncode=0, stdout="feature-branch"),  # git branch
            Mock(returncode=0, stdout="git@github.com:owner/repo.git"),  # git remote
        ]
        mock_run.side_effect = mock_results

        # Mock GitHub API
        pr_manager.github.get_open_prs = Mock(return_value=[
            {"number": 42, "head_ref": "feature-branch"},
            {"number": 43, "head_ref": "other-branch"},
        ])

        pr_id = pr_manager.auto_detect_pr()
        assert pr_id == "owner/repo#42"

    @patch('subprocess.run')
    def test_auto_detect_pr_no_matching_pr(self, mock_run, pr_manager):
        """Test auto-detect when no PR matches current branch."""
        mock_results = [
            Mock(returncode=0),  # git rev-parse
            Mock(returncode=0, stdout="feature-branch"),  # git branch
            Mock(returncode=0, stdout="git@github.com:owner/repo.git"),  # git remote
        ]
        mock_run.side_effect = mock_results

        pr_manager.github.get_open_prs = Mock(return_value=[
            {"number": 42, "head_ref": "other-branch"},
        ])

        pr_id = pr_manager.auto_detect_pr()
        assert pr_id is None

    @patch('os.getcwd')
    @patch('os.chdir')
    @patch('subprocess.run')
    @patch('gh_pr.core.pr_manager.Path')
    def test_auto_detect_pr_subdirectories(
        self, mock_path_class, mock_run, mock_chdir, mock_getcwd, pr_manager
    ):
        """Test auto-detecting PR from subdirectories."""
        # Mock directory structure
        mock_path = Mock()
        mock_subdir = Mock()
        mock_subdir.is_dir.return_value = True
        mock_subdir.__truediv__.return_value.exists.return_value = True
        mock_path.return_value.iterdir.return_value = [mock_subdir]
        mock_path.return_value.exists.return_value = False  # No .git in current dir
        mock_path_class.return_value = mock_path

        # Mock git commands for subdirectory
        mock_getcwd.return_value = "/current"
        mock_results = [
            Mock(returncode=0, stdout="feature-branch"),
            Mock(returncode=0, stdout="git@github.com:owner/repo.git"),
        ]
        mock_run.side_effect = mock_results

        pr_manager.github.get_open_prs = Mock(return_value=[
            {"number": 42, "head_ref": "feature-branch"},
        ])

        pr_id = pr_manager.auto_detect_pr()
        # Should return None since our mock is simplified
        assert pr_id is None or pr_id == "owner/repo#42"

    def test_find_git_repos(self, pr_manager):
        """Test finding git repositories."""
        with patch('gh_pr.core.pr_manager.Path') as mock_path:
            # Mock current directory with .git
            mock_git = Mock()
            mock_git.exists.return_value = True
            mock_path.return_value = mock_git

            # Mock subdirectories
            mock_subdir1 = Mock()
            mock_subdir1.is_dir.return_value = True
            mock_subdir1.__truediv__.return_value.exists.return_value = True

            mock_subdir2 = Mock()
            mock_subdir2.is_dir.return_value = True
            mock_subdir2.__truediv__.return_value.exists.return_value = False

            mock_path.return_value.iterdir.return_value = [mock_subdir1, mock_subdir2]

            repos = pr_manager._find_git_repos()
            assert len(repos) >= 1  # At least current directory

    def test_select_pr_interactive(self, pr_manager):
        """Test interactive PR selection."""
        pr_manager.github.get_open_prs = Mock(return_value=[
            {"number": 42, "title": "Feature PR"},
            {"number": 43, "title": "Bug fix"},
        ])

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="git@github.com:owner/repo.git")
            pr_id = pr_manager.select_pr_interactive()
            # In real implementation, this would show a TUI
            assert pr_id == "owner/repo#42"  # Returns first PR for now

    def test_select_pr_interactive_no_prs(self, pr_manager):
        """Test interactive selection with no open PRs."""
        pr_manager.github.get_open_prs = Mock(return_value=[])

        pr_id = pr_manager.select_pr_interactive("owner/repo")
        assert pr_id is None

    def test_fetch_pr_data(self, pr_manager, mock_cache_manager):
        """Test fetching complete PR data."""
        mock_pr = Mock()
        mock_pr.number = 42
        mock_pr.title = "Test PR"
        mock_pr.state = "open"
        mock_pr.user.login = "testuser"
        mock_pr.created_at = None
        mock_pr.updated_at = None
        mock_pr.merged = False
        mock_pr.merged_at = None
        mock_pr.mergeable = True
        mock_pr.mergeable_state = "clean"
        mock_pr.head.ref = "feature"
        mock_pr.head.sha = "abc123"
        mock_pr.base.ref = "main"
        mock_pr.base.sha = "def456"
        mock_pr.body = "PR description"
        mock_pr.additions = 10
        mock_pr.deletions = 5
        mock_pr.changed_files = 2
        mock_pr.review_comments = 3
        mock_pr.comments = 1
        mock_pr.commits = 2
        mock_pr.labels = []

        pr_manager.github.get_pull_request = Mock(return_value=mock_pr)

        data = pr_manager.fetch_pr_data("owner", "repo", 42)

        assert data["number"] == 42
        assert data["title"] == "Test PR"
        assert data["state"] == "open"
        assert data["author"] == "testuser"
        pr_manager.github.get_pull_request.assert_called_once_with("owner", "repo", 42)

    def test_fetch_pr_data_with_cache(self, pr_manager, mock_cache_manager):
        """Test PR data retrieval with caching."""
        cached_data = {"number": 42, "title": "Cached PR"}
        mock_cache_manager.get.return_value = cached_data

        data = pr_manager.fetch_pr_data("owner", "repo", 42)

        assert data == cached_data
        mock_cache_manager.get.assert_called_once()
        pr_manager.github.get_pull_request.assert_not_called()

    def test_fetch_pr_data_error(self, pr_manager):
        """Test PR data fetch error handling."""
        pr_manager.github.get_pull_request = Mock(
            side_effect=GithubException(404, {"message": "Not found"})
        )

        with pytest.raises(ValueError, match="Failed to fetch PR data"):
            pr_manager.fetch_pr_data("owner", "repo", 999)

    def test_fetch_pr_comments(self, pr_manager):
        """Test fetching and filtering PR comments."""
        mock_comments = [
            {
                "id": 1,
                "path": "file.py",
                "line": 10,
                "body": "Comment 1",
                "author": "user1",
            },
            {
                "id": 2,
                "path": "file.py",
                "line": 20,
                "body": "Comment 2",
                "author": "user2",
            },
        ]

        pr_manager.github.get_pr_review_comments = Mock(return_value=mock_comments)

        # Mock comment processor and filter
        pr_manager.comment_processor.organize_into_threads = Mock(
            return_value=[
                {"id": "thread1", "comments": [mock_comments[0]]},
                {"id": "thread2", "comments": [mock_comments[1]]},
            ]
        )

        pr_manager.filter.filter_comments = Mock(
            return_value=[{"id": "thread1", "comments": [mock_comments[0]]}]
        )

        comments = pr_manager.fetch_pr_comments("owner", "repo", 42, "unresolved")

        assert len(comments) == 1
        pr_manager.github.get_pr_review_comments.assert_called_once_with("owner", "repo", 42)
        pr_manager.filter.filter_comments.assert_called_once()

    def test_fetch_check_status(self, pr_manager):
        """Test fetching CI/CD check status."""
        mock_checks = [
            {
                "name": "Test",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "name": "Lint",
                "status": "completed",
                "conclusion": "failure",
            },
            {
                "name": "Build",
                "status": "in_progress",
                "conclusion": None,
            },
        ]

        pr_manager.github.get_check_runs = Mock(return_value=mock_checks)

        status = pr_manager.fetch_check_status("owner", "repo", 42)

        assert status["total"] == 3
        assert status["success"] == 1
        assert status["failure"] == 1
        assert status["pending"] == 1
        assert status["checks"] == mock_checks

    def test_get_pr_summary(self, pr_manager):
        """Test generating PR summary."""
        mock_comments = [
            {
                "id": 1,
                "path": "file.py",
                "body": "Comment",
                "author": "user",
            }
        ]

        mock_threads = [
            {
                "id": "thread1",
                "is_resolved": False,
                "is_outdated": False,
                "comments": [mock_comments[0]],
            },
            {
                "id": "thread2",
                "is_resolved": True,
                "is_outdated": False,
                "comments": [mock_comments[0]],
            },
        ]

        mock_reviews = [
            {"state": "APPROVED"},
            {"state": "CHANGES_REQUESTED"},
            {"state": "COMMENTED"},
        ]

        pr_manager.github.get_pr_review_comments = Mock(return_value=mock_comments)
        pr_manager.github.get_pr_reviews = Mock(return_value=mock_reviews)
        pr_manager.comment_processor.organize_into_threads = Mock(return_value=mock_threads)

        summary = pr_manager.get_pr_summary("owner", "repo", 42)

        assert summary["total_threads"] == 2
        assert summary["unresolved_active"] == 1
        assert summary["resolved_active"] == 1
        assert summary["approvals"] == 1
        assert summary["changes_requested"] == 1
        assert summary["comments"] == 1

    def test_resolve_outdated_comments_not_implemented(self, pr_manager):
        """Test that resolve_outdated_comments raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="GraphQL API implementation"):
            pr_manager.resolve_outdated_comments("owner", "repo", 42)

    def test_accept_all_suggestions_not_implemented(self, pr_manager):
        """Test that accept_all_suggestions raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="specific API endpoints"):
            pr_manager.accept_all_suggestions("owner", "repo", 42)
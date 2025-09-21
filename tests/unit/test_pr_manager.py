"""
Unit tests for core.pr_manager module.

Tests PR management and business logic functionality.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from github import GithubException

from gh_pr.core.pr_manager import PRManager, _validate_git_repository
from gh_pr.core.github import GitHubClient
from gh_pr.core.graphql import GraphQLClient
from gh_pr.core.comments import CommentProcessor
from gh_pr.core.filters import CommentFilter
from gh_pr.utils.cache import CacheManager


class TestValidateGitRepository(unittest.TestCase):
    """Test _validate_git_repository function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_git_repository_with_git_dir(self):
        """Test validation when .git directory exists."""
        git_dir = self.temp_dir / ".git"
        git_dir.mkdir()

        result = _validate_git_repository(self.temp_dir)
        self.assertTrue(result)

    def test_validate_git_repository_current_directory(self):
        """Test validation in current directory."""
        os.chdir(self.temp_dir)
        git_dir = self.temp_dir / ".git"
        git_dir.mkdir()

        result = _validate_git_repository()
        self.assertTrue(result)

    @patch('gh_pr.core.pr_manager.subprocess.run')
    def test_validate_git_repository_with_git_command(self, mock_run):
        """Test validation using git command when .git dir doesn't exist."""
        # Mock successful git command
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = _validate_git_repository(self.temp_dir)
        self.assertTrue(result)

        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            timeout=5,
            cwd=self.temp_dir
        )

    @patch('gh_pr.core.pr_manager.subprocess.run')
    def test_validate_git_repository_git_command_fails(self, mock_run):
        """Test validation when git command fails."""
        # Mock failed git command
        mock_result = Mock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        result = _validate_git_repository(self.temp_dir)
        self.assertFalse(result)

    @patch('gh_pr.core.pr_manager.subprocess.run')
    def test_validate_git_repository_subprocess_error(self, mock_run):
        """Test validation when subprocess raises an exception."""
        mock_run.side_effect = subprocess.SubprocessError("Command failed")

        result = _validate_git_repository(self.temp_dir)
        self.assertFalse(result)

    @patch('gh_pr.core.pr_manager.subprocess.run')
    def test_validate_git_repository_file_not_found(self, mock_run):
        """Test validation when git command is not found."""
        mock_run.side_effect = FileNotFoundError("git command not found")

        result = _validate_git_repository(self.temp_dir)
        self.assertFalse(result)


class TestPRManager(unittest.TestCase):
    """Test PRManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_github = Mock(spec=GitHubClient)
        self.mock_cache = Mock(spec=CacheManager)

        # Don't mock CommentProcessor and CommentFilter for init test
        self.pr_manager = PRManager(self.mock_github, self.mock_cache)

    def test_init(self):
        """Test PRManager initialization."""
        self.assertEqual(self.pr_manager.github, self.mock_github)
        self.assertEqual(self.pr_manager.cache, self.mock_cache)
        self.assertIsInstance(self.pr_manager.comment_processor, CommentProcessor)
        self.assertIsInstance(self.pr_manager.filter, CommentFilter)
        self.assertIsNone(self.pr_manager._graphql_client)

    @patch('gh_pr.core.pr_manager.GraphQLClient')
    def test_graphql_property_lazy_initialization(self, mock_graphql_class):
        """Test that GraphQL client is lazily initialized."""
        mock_graphql_instance = Mock(spec=GraphQLClient)
        mock_graphql_class.return_value = mock_graphql_instance

        # Mock the token extraction from PyGithub
        mock_auth = Mock()
        mock_auth.token = "test_token"
        mock_requester = Mock()
        mock_requester._Requester__auth = mock_auth
        mock_github_instance = Mock()
        mock_github_instance._Github__requester = mock_requester
        self.mock_github.github = mock_github_instance
        self.mock_github.token = "test_token"

        # First access
        graphql1 = self.pr_manager.graphql
        self.assertEqual(graphql1, mock_graphql_instance)
        mock_graphql_class.assert_called_once_with("test_token")

        # Second access should return cached instance
        graphql2 = self.pr_manager.graphql
        self.assertEqual(graphql2, mock_graphql_instance)
        # Should still only be called once
        mock_graphql_class.assert_called_once()

    def test_parse_pr_identifier_full_url(self):
        """Test parsing full GitHub URL."""
        test_cases = [
            "https://github.com/owner/repo/pull/123",
            "http://github.com/owner/repo/pull/123",
            "github.com/owner/repo/pull/123"
        ]

        for url in test_cases:
            with self.subTest(url=url):
                owner, repo, pr_number = self.pr_manager.parse_pr_identifier(url)
                self.assertEqual(owner, "owner")
                self.assertEqual(repo, "repo")
                self.assertEqual(pr_number, 123)

    def test_parse_pr_identifier_owner_repo_format(self):
        """Test parsing owner/repo#number format."""
        owner, repo, pr_number = self.pr_manager.parse_pr_identifier("owner/repo#123")
        self.assertEqual(owner, "owner")
        self.assertEqual(repo, "repo")
        self.assertEqual(pr_number, 123)

    def test_parse_pr_identifier_number_with_default_repo(self):
        """Test parsing just PR number with default repository."""
        owner, repo, pr_number = self.pr_manager.parse_pr_identifier(
            "123", default_repo="default_owner/default_repo"
        )
        self.assertEqual(owner, "default_owner")
        self.assertEqual(repo, "default_repo")
        self.assertEqual(pr_number, 123)

    @patch('gh_pr.core.pr_manager._validate_git_repository')
    @patch('gh_pr.core.pr_manager.subprocess.run')
    def test_parse_pr_identifier_number_from_git_repo(self, mock_run, mock_validate):
        """Test parsing PR number using current git repository."""
        mock_validate.return_value = True

        # Mock git remote get-url command
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "git@github.com:git_owner/git_repo.git"
        mock_run.return_value = mock_result

        owner, repo, pr_number = self.pr_manager.parse_pr_identifier("456")
        self.assertEqual(owner, "git_owner")
        self.assertEqual(repo, "git_repo")
        self.assertEqual(pr_number, 456)

    def test_parse_pr_identifier_number_no_repo_context(self):
        """Test parsing PR number without repository context."""
        with patch.object(self.pr_manager, '_get_current_repo_info', return_value=None):
            with self.assertRaises(ValueError) as context:
                self.pr_manager.parse_pr_identifier("123")

            self.assertIn("no repository context found", str(context.exception).lower())

    def test_parse_pr_identifier_invalid_format(self):
        """Test parsing invalid PR identifier."""
        invalid_identifiers = [
            "invalid",
            "owner/repo#abc",
            "not-a-url-or-number",
            ""
        ]

        for identifier in invalid_identifiers:
            with self.subTest(identifier=identifier):
                with self.assertRaises(ValueError) as context:
                    self.pr_manager.parse_pr_identifier(identifier)

                self.assertIn("Cannot parse PR identifier", str(context.exception))

    @patch('gh_pr.core.pr_manager._validate_git_repository')
    def test_get_current_repo_info_not_git_repo(self, mock_validate):
        """Test _get_current_repo_info when not in a git repository."""
        mock_validate.return_value = False

        result = self.pr_manager._get_current_repo_info()
        self.assertIsNone(result)

    @patch('gh_pr.core.pr_manager._validate_git_repository')
    @patch('gh_pr.core.pr_manager.subprocess.run')
    def test_get_current_repo_info_success_ssh_url(self, mock_run, mock_validate):
        """Test _get_current_repo_info with SSH URL."""
        mock_validate.return_value = True

        # Mock git remote get-url command
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "git@github.com:test_owner/test_repo.git\n"
        mock_run.return_value = mock_result

        result = self.pr_manager._get_current_repo_info()
        self.assertEqual(result, ("test_owner", "test_repo"))

    @patch('gh_pr.core.pr_manager._validate_git_repository')
    @patch('gh_pr.core.pr_manager.subprocess.run')
    def test_get_current_repo_info_success_https_url(self, mock_run, mock_validate):
        """Test _get_current_repo_info with HTTPS URL."""
        mock_validate.return_value = True

        # Mock git remote get-url command
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/test_owner/test_repo\n"
        mock_run.return_value = mock_result

        result = self.pr_manager._get_current_repo_info()
        self.assertEqual(result, ("test_owner", "test_repo"))

    @patch('gh_pr.core.pr_manager._validate_git_repository')
    @patch('gh_pr.core.pr_manager.subprocess.run')
    def test_get_current_repo_info_git_url_without_git_suffix(self, mock_run, mock_validate):
        """Test _get_current_repo_info with URL without .git suffix."""
        mock_validate.return_value = True

        # Mock git remote get-url command
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "git@github.com:test_owner/test_repo\n"
        mock_run.return_value = mock_result

        result = self.pr_manager._get_current_repo_info()
        self.assertEqual(result, ("test_owner", "test_repo"))

    @patch('gh_pr.core.pr_manager._validate_git_repository')
    @patch('gh_pr.core.pr_manager.subprocess.run')
    def test_get_current_repo_info_git_command_fails(self, mock_run, mock_validate):
        """Test _get_current_repo_info when git command fails."""
        mock_validate.return_value = True

        # Mock failed git command
        mock_result = Mock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        result = self.pr_manager._get_current_repo_info()
        self.assertIsNone(result)

    @patch('gh_pr.core.pr_manager._validate_git_repository')
    @patch('gh_pr.core.pr_manager.subprocess.run')
    def test_get_current_repo_info_subprocess_error(self, mock_run, mock_validate):
        """Test _get_current_repo_info when subprocess raises exception."""
        mock_validate.return_value = True
        mock_run.side_effect = subprocess.SubprocessError("Command failed")

        result = self.pr_manager._get_current_repo_info()
        self.assertIsNone(result)

    @patch('gh_pr.core.pr_manager._validate_git_repository')
    def test_get_current_branch_pr_not_git_repo(self, mock_validate):
        """Test _get_current_branch_pr when not in git repository."""
        mock_validate.return_value = False

        result = self.pr_manager._get_current_branch_pr()
        self.assertIsNone(result)

    @patch('gh_pr.core.pr_manager._validate_git_repository')
    @patch('gh_pr.core.pr_manager.subprocess.run')
    def test_get_current_branch_pr_success(self, mock_run, mock_validate):
        """Test _get_current_branch_pr successfully finding PR."""
        mock_validate.return_value = True

        # Mock git branch --show-current
        mock_branch_result = Mock()
        mock_branch_result.returncode = 0
        mock_branch_result.stdout = "feature-branch\n"

        # Mock git remote get-url
        mock_remote_result = Mock()
        mock_remote_result.returncode = 0
        mock_remote_result.stdout = "git@github.com:owner/repo.git\n"

        mock_run.side_effect = [mock_branch_result, mock_remote_result]

        # Mock GitHub API call
        mock_prs = [
            {"number": 123, "head_ref": "feature-branch"},
            {"number": 124, "head_ref": "other-branch"}
        ]
        self.mock_github.get_open_prs.return_value = mock_prs

        with patch.object(self.pr_manager, '_get_current_repo_info', return_value=("owner", "repo")):
            result = self.pr_manager._get_current_branch_pr()

        self.assertEqual(result, "owner/repo#123")

    @patch('gh_pr.core.pr_manager._validate_git_repository')
    @patch('gh_pr.core.pr_manager.subprocess.run')
    def test_get_current_branch_pr_no_matching_pr(self, mock_run, mock_validate):
        """Test _get_current_branch_pr when no PR matches current branch."""
        mock_validate.return_value = True

        # Mock git branch --show-current
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "main\n"
        mock_run.return_value = mock_result

        # Mock GitHub API call with no matching PRs
        mock_prs = [
            {"number": 123, "head_ref": "feature-branch"},
            {"number": 124, "head_ref": "other-branch"}
        ]
        self.mock_github.get_open_prs.return_value = mock_prs

        with patch.object(self.pr_manager, '_get_current_repo_info', return_value=("owner", "repo")):
            result = self.pr_manager._get_current_branch_pr()

        self.assertIsNone(result)

    def test_auto_detect_pr_success(self):
        """Test auto_detect_pr successfully finding PR."""
        with patch.object(self.pr_manager, '_get_current_branch_pr', return_value="owner/repo#123"):
            result = self.pr_manager.auto_detect_pr()
            self.assertEqual(result, "owner/repo#123")

    def test_auto_detect_pr_from_subdirectories(self):
        """Test auto_detect_pr finding PR from subdirectories."""
        with patch.object(self.pr_manager, '_get_current_branch_pr', return_value=None), \
             patch.object(self.pr_manager, '_find_git_repos', return_value=[Path("subdir")]), \
             patch.object(self.pr_manager, '_get_pr_from_directory') as mock_get_pr:

            mock_get_pr.return_value = {
                "identifier": "owner/repo#456",
                "number": 456,
                "title": "Test PR",
                "branch": "feature",
                "directory": "subdir"
            }

            result = self.pr_manager.auto_detect_pr()
            self.assertEqual(result, "owner/repo#456")

    def test_auto_detect_pr_no_git_repos(self):
        """Test auto_detect_pr when no git repositories found."""
        with patch.object(self.pr_manager, '_get_current_branch_pr', return_value=None), \
             patch.object(self.pr_manager, '_find_git_repos', return_value=[]):

            result = self.pr_manager.auto_detect_pr()
            self.assertIsNone(result)

    def test_select_pr_interactive_success(self):
        """Test select_pr_interactive successfully returning PR."""
        mock_prs = [
            {"number": 123, "title": "Test PR 1"},
            {"number": 124, "title": "Test PR 2"}
        ]
        self.mock_github.get_open_prs.return_value = mock_prs

        result = self.pr_manager.select_pr_interactive("owner/repo")
        self.assertEqual(result, "owner/repo#123")

    def test_select_pr_interactive_no_prs(self):
        """Test select_pr_interactive when no PRs found."""
        self.mock_github.get_open_prs.return_value = []

        result = self.pr_manager.select_pr_interactive("owner/repo")
        self.assertIsNone(result)

    def test_select_pr_interactive_github_exception(self):
        """Test select_pr_interactive handling GitHub exception."""
        self.mock_github.get_open_prs.side_effect = GithubException(403, "Forbidden")

        result = self.pr_manager.select_pr_interactive("owner/repo")
        self.assertIsNone(result)

    def test_fetch_pr_data_success(self):
        """Test fetch_pr_data successfully retrieving PR data."""
        # Mock PR object
        mock_pr = Mock()
        mock_pr.number = 123
        mock_pr.title = "Test PR"
        mock_pr.state = "open"
        mock_pr.user.login = "author"
        mock_pr.created_at = Mock()
        mock_pr.updated_at = Mock()
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
        mock_pr.commits = 5
        # Create proper mock labels with name attribute
        bug_label = Mock()
        bug_label.name = "bug"
        feature_label = Mock()
        feature_label.name = "feature"
        mock_pr.labels = [bug_label, feature_label]

        # Mock cache miss
        self.mock_cache.enabled = True
        self.mock_cache.get.return_value = None

        self.mock_github.get_pull_request.return_value = mock_pr

        result = self.pr_manager.fetch_pr_data("owner", "repo", 123)

        self.assertEqual(result["number"], 123)
        self.assertEqual(result["title"], "Test PR")
        self.assertEqual(result["state"], "open")
        self.assertEqual(result["author"], "author")
        self.assertEqual(result["labels"], ["bug", "feature"])

        # Should cache the result
        self.mock_cache.set.assert_called_once()

    def test_fetch_pr_data_cache_hit(self):
        """Test fetch_pr_data returning cached data."""
        cached_data = {"number": 123, "title": "Cached PR"}

        self.mock_cache.enabled = True
        self.mock_cache.get.return_value = cached_data

        result = self.pr_manager.fetch_pr_data("owner", "repo", 123)

        self.assertEqual(result, cached_data)
        self.mock_github.get_pull_request.assert_not_called()
        self.mock_cache.set.assert_not_called()

    def test_fetch_pr_data_github_exception(self):
        """Test fetch_pr_data handling GitHub exception."""
        self.mock_cache.enabled = False
        self.mock_github.get_pull_request.side_effect = GithubException(404, "Not Found")

        with self.assertRaises(ValueError) as context:
            self.pr_manager.fetch_pr_data("owner", "repo", 123)

        self.assertIn("Failed to fetch PR data", str(context.exception))

    @patch('gh_pr.core.pr_manager.CommentProcessor')
    @patch('gh_pr.core.pr_manager.CommentFilter')
    def test_fetch_pr_comments_success(self, mock_filter_class, mock_processor_class):
        """Test fetch_pr_comments successfully filtering comments."""
        # Create a new PR manager with mocked dependencies for this test
        mock_filter_instance = Mock()
        mock_processor_instance = Mock()
        mock_filter_class.return_value = mock_filter_instance
        mock_processor_class.return_value = mock_processor_instance

        pr_manager = PRManager(self.mock_github, self.mock_cache)

        mock_comments = [
            {"id": 1, "body": "Comment 1"},
            {"id": 2, "body": "Comment 2"}
        ]
        mock_threads = [
            {"id": 1, "comments": [mock_comments[0]]},
            {"id": 2, "comments": [mock_comments[1]]}
        ]
        mock_filtered = [mock_threads[0]]  # Only first thread after filtering

        self.mock_github.get_pr_review_comments.return_value = mock_comments
        mock_processor_instance.organize_into_threads.return_value = mock_threads
        mock_filter_instance.filter_comments.return_value = mock_filtered

        result = pr_manager.fetch_pr_comments("owner", "repo", 123, "unresolved")

        self.assertEqual(result, mock_filtered)
        mock_filter_instance.filter_comments.assert_called_once_with(mock_threads, "unresolved")

    @patch('gh_pr.core.pr_manager.CommentProcessor')
    def test_get_pr_summary_success(self, mock_processor_class):
        """Test get_pr_summary calculating summary correctly."""
        # Create a new PR manager with mocked dependencies for this test
        mock_processor_instance = Mock()
        mock_processor_class.return_value = mock_processor_instance

        pr_manager = PRManager(self.mock_github, self.mock_cache)

        mock_threads = [
            {"is_resolved": False, "is_outdated": False},  # unresolved_active
            {"is_resolved": False, "is_outdated": True},   # unresolved_outdated
            {"is_resolved": True, "is_outdated": False},   # resolved_active
            {"is_resolved": True, "is_outdated": True},    # resolved_outdated
        ]
        mock_reviews = [
            {"state": "APPROVED"},
            {"state": "CHANGES_REQUESTED"},
            {"state": "COMMENTED"}
        ]

        self.mock_github.get_pr_review_comments.return_value = []
        mock_processor_instance.organize_into_threads.return_value = mock_threads
        self.mock_github.get_pr_reviews.return_value = mock_reviews

        result = pr_manager.get_pr_summary("owner", "repo", 123)

        expected = {
            "total_threads": 4,
            "unresolved_active": 1,
            "unresolved_outdated": 1,
            "resolved_active": 1,
            "resolved_outdated": 1,
            "approvals": 1,
            "changes_requested": 1,
            "comments": 1,
        }

        self.assertEqual(result, expected)

    def test_resolve_outdated_comments_input_validation(self):
        """Test resolve_outdated_comments with invalid input."""
        # Test empty owner
        resolved, errors = self.pr_manager.resolve_outdated_comments("", "repo", 123)
        self.assertEqual(resolved, 0)
        self.assertIn("Owner and repository name are required", errors)

        # Test negative PR number
        resolved, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", -1)
        self.assertEqual(resolved, 0)
        self.assertIn("PR number must be positive", errors)

    def test_accept_all_suggestions_input_validation(self):
        """Test accept_all_suggestions with invalid input."""
        # Test empty repo
        accepted, errors = self.pr_manager.accept_all_suggestions("owner", "", 123)
        self.assertEqual(accepted, 0)
        self.assertIn("Owner and repository name are required", errors)

        # Test zero PR number
        accepted, errors = self.pr_manager.accept_all_suggestions("owner", "repo", 0)
        self.assertEqual(accepted, 0)
        self.assertIn("PR number must be positive", errors)


if __name__ == '__main__':
    unittest.main()
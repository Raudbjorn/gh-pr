"""Unit tests for pr_manager.py git repository validation and security."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from github import GithubException

from gh_pr.core.pr_manager import PRManager


class TestPRManagerGitIntegration:
    """Test PRManager integration with git repository validation."""

    def test_pr_manager_get_current_repo_info_not_git_repo(self):
        """Test _get_current_repo_info when not in a git repository."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()

        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=False):
            result = pr_manager._get_current_repo_info()
            assert result is None

    @patch('subprocess.run')
    def test_pr_manager_get_current_repo_info_git_remote_success(self, mock_run):
        """Test _get_current_repo_info with successful git remote command."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        # Mock git repository validation success
        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=True):
            # Mock successful git remote get-url command
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "git@github.com:owner/repo.git"
            mock_run.return_value = mock_result

            result = pr_manager._get_current_repo_info()

            assert result == ("owner", "repo")

    @patch('subprocess.run')
    def test_pr_manager_get_current_repo_info_https_url(self, mock_run):
        """Test _get_current_repo_info with HTTPS GitHub URL."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=True):
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "https://github.com/owner/repo.git"
            mock_run.return_value = mock_result

            result = pr_manager._get_current_repo_info()

            assert result == ("owner", "repo")

    @patch('subprocess.run')
    def test_pr_manager_get_current_repo_info_no_git_extension(self, mock_run):
        """Test _get_current_repo_info with URL without .git extension."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=True):
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "https://github.com/owner/repo"
            mock_run.return_value = mock_result

            result = pr_manager._get_current_repo_info()

            assert result == ("owner", "repo")

    @patch('subprocess.run')
    def test_pr_manager_get_current_repo_info_git_command_failure(self, mock_run):
        """Test _get_current_repo_info when git remote command fails."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=True):
            mock_result = Mock()
            mock_result.returncode = 1  # Command failed
            mock_run.return_value = mock_result

            result = pr_manager._get_current_repo_info()

            assert result is None

    @patch('subprocess.run')
    def test_pr_manager_get_current_repo_info_invalid_url(self, mock_run):
        """Test _get_current_repo_info with invalid GitHub URL."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=True):
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "https://gitlab.com/owner/repo.git"  # Not GitHub
            mock_run.return_value = mock_result

            result = pr_manager._get_current_repo_info()

            assert result is None

    @patch('subprocess.run')
    def test_pr_manager_get_current_repo_info_subprocess_error(self, mock_run):
        """Test _get_current_repo_info when subprocess raises exception."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=True):
            mock_run.side_effect = subprocess.SubprocessError("Command failed")

            result = pr_manager._get_current_repo_info()

            assert result is None

    def test_pr_manager_get_current_branch_pr_not_git_repo(self):
        """Test _get_current_branch_pr when not in git repository."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=False):
            result = pr_manager._get_current_branch_pr()
            assert result is None

    @patch('subprocess.run')
    def test_pr_manager_get_current_branch_pr_success(self, mock_run):
        """Test _get_current_branch_pr with successful branch detection."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        # Mock git repository validation
        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=True):
            # Mock git branch command
            branch_result = Mock()
            branch_result.returncode = 0
            branch_result.stdout = "feature-branch"

            # Mock git remote command
            remote_result = Mock()
            remote_result.returncode = 0
            remote_result.stdout = "https://github.com/owner/repo.git"

            mock_run.side_effect = [branch_result, remote_result]

            # Mock GitHub API call
            mock_github_client.get_open_prs.return_value = [
                {"number": 123, "head_ref": "feature-branch"}
            ]

            result = pr_manager._get_current_branch_pr()

            assert result == "owner/repo#123"

    @patch('subprocess.run')
    def test_pr_manager_get_current_branch_pr_no_matching_pr(self, mock_run):
        """Test _get_current_branch_pr when no PR matches current branch."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=True):
            branch_result = Mock()
            branch_result.returncode = 0
            branch_result.stdout = "feature-branch"

            remote_result = Mock()
            remote_result.returncode = 0
            remote_result.stdout = "https://github.com/owner/repo.git"

            mock_run.side_effect = [branch_result, remote_result]

            # No matching PR
            mock_github_client.get_open_prs.return_value = [
                {"number": 123, "head_ref": "different-branch"}
            ]

            result = pr_manager._get_current_branch_pr()

            assert result is None

    @patch('subprocess.run')
    def test_pr_manager_get_current_branch_pr_github_api_error(self, mock_run):
        """Test _get_current_branch_pr when GitHub API fails."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=True):
            branch_result = Mock()
            branch_result.returncode = 0
            branch_result.stdout = "feature-branch"

            remote_result = Mock()
            remote_result.returncode = 0
            remote_result.stdout = "https://github.com/owner/repo.git"

            mock_run.side_effect = [branch_result, remote_result]

            # GitHub API error
            mock_github_client.get_open_prs.side_effect = GithubException(403, "Forbidden")

            result = pr_manager._get_current_branch_pr()

            assert result is None

    def test_pr_manager_get_pr_from_directory_not_git_repo(self):
        """Test _get_pr_from_directory when directory is not git repository."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=False):
                result = pr_manager._get_pr_from_directory(temp_path)
                assert result is None

    @patch('os.chdir')
    @patch('os.getcwd')
    @patch('subprocess.run')
    def test_pr_manager_get_pr_from_directory_success(self, mock_run, mock_getcwd, mock_chdir):
        """Test _get_pr_from_directory with successful PR detection."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        original_cwd = "/original/path"
        mock_getcwd.return_value = original_cwd

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=True):
                # Mock git branch command
                branch_result = Mock()
                branch_result.returncode = 0
                branch_result.stdout = "feature-branch"

                # Mock git remote command
                remote_result = Mock()
                remote_result.returncode = 0
                remote_result.stdout = "https://github.com/owner/repo.git"

                mock_run.side_effect = [branch_result, remote_result]

                # Mock GitHub API call
                mock_github_client.get_open_prs.return_value = [
                    {"number": 456, "head_ref": "feature-branch", "title": "Test PR"}
                ]

                result = pr_manager._get_pr_from_directory(temp_path)

                expected = {
                    "identifier": "owner/repo#456",
                    "number": 456,
                    "title": "Test PR",
                    "branch": "feature-branch",
                    "directory": str(temp_path),
                }

                assert result == expected

                # Verify directory was changed back
                mock_chdir.assert_any_call(original_cwd)

    @patch('os.chdir')
    @patch('os.getcwd')
    @patch('gh_pr.core.pr_manager.logger')
    def test_pr_manager_get_pr_from_directory_os_error_handling(self, mock_logger, mock_getcwd, mock_chdir):
        """Test _get_pr_from_directory with OS error handling."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        original_cwd = "/original/path"
        mock_getcwd.return_value = original_cwd

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Mock chdir to raise OSError
            mock_chdir.side_effect = [OSError("Permission denied"), None]  # Second call succeeds for cleanup

            result = pr_manager._get_pr_from_directory(temp_path)

            assert result is None
            mock_logger.error.assert_called_once()

    def test_pr_manager_find_git_repos_current_directory(self):
        """Test _find_git_repos when current directory is git repo."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                git_dir = Path(".git")
                git_dir.mkdir()

                repos = pr_manager._find_git_repos()

                assert len(repos) == 1
                assert repos[0] == Path(".")

            finally:
                os.chdir(original_cwd)

    def test_pr_manager_find_git_repos_subdirectories(self):
        """Test _find_git_repos with git repos in subdirectories."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)

                # Create subdirectories with git repos
                subdir1 = Path("repo1")
                subdir1.mkdir()
                (subdir1 / ".git").mkdir()

                subdir2 = Path("repo2")
                subdir2.mkdir()
                (subdir2 / ".git").mkdir()

                # Create non-git subdirectory
                subdir3 = Path("not-git")
                subdir3.mkdir()

                repos = pr_manager._find_git_repos()

                assert len(repos) == 2
                assert subdir1 in repos
                assert subdir2 in repos
                assert subdir3 not in repos

            finally:
                os.chdir(original_cwd)

    def test_pr_manager_find_git_repos_no_repos(self):
        """Test _find_git_repos when no git repositories found."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)

                # Create some non-git directories
                Path("dir1").mkdir()
                Path("dir2").mkdir()
                Path("file.txt").write_text("not a directory")

                repos = pr_manager._find_git_repos()

                assert len(repos) == 0

            finally:
                os.chdir(original_cwd)


class TestPRManagerParseIdentifier:
    """Test PR identifier parsing with repository context."""

    def test_parse_pr_identifier_with_default_repo(self):
        """Test parsing PR number with default repository."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        owner, repo, pr_number = pr_manager.parse_pr_identifier("123", default_repo="owner/repo")

        assert owner == "owner"
        assert repo == "repo"
        assert pr_number == 123

    def test_parse_pr_identifier_with_git_context(self):
        """Test parsing PR number using git repository context."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with patch.object(pr_manager, '_get_current_repo_info', return_value=("git-owner", "git-repo")):
            owner, repo, pr_number = pr_manager.parse_pr_identifier("456")

            assert owner == "git-owner"
            assert repo == "git-repo"
            assert pr_number == 456

    def test_parse_pr_identifier_no_context(self):
        """Test parsing PR number without repository context."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with patch.object(pr_manager, '_get_current_repo_info', return_value=None):
            with pytest.raises(ValueError, match="no repository context found"):
                pr_manager.parse_pr_identifier("123")

    def test_parse_pr_identifier_github_url(self):
        """Test parsing full GitHub URL."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        owner, repo, pr_number = pr_manager.parse_pr_identifier(
            "https://github.com/url-owner/url-repo/pull/789"
        )

        assert owner == "url-owner"
        assert repo == "url-repo"
        assert pr_number == 789

    def test_parse_pr_identifier_repo_format(self):
        """Test parsing owner/repo#number format."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        owner, repo, pr_number = pr_manager.parse_pr_identifier("format-owner/format-repo#101")

        assert owner == "format-owner"
        assert repo == "format-repo"
        assert pr_number == 101

    def test_parse_pr_identifier_invalid_format(self):
        """Test parsing invalid identifier format."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with pytest.raises(ValueError, match="Cannot parse PR identifier"):
            pr_manager.parse_pr_identifier("invalid-format")


class TestPRManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_pr_manager_validation_with_symlinks(self):
        """Test git repository validation with symbolic links."""
        with tempfile.TemporaryDirectory() as temp_dir:
            real_repo = Path(temp_dir) / "real_repo"
            real_repo.mkdir()
            (real_repo / ".git").mkdir()

            symlink_repo = Path(temp_dir) / "symlink_repo"
            try:
                symlink_repo.symlink_to(real_repo)

                result = _validate_git_repository(symlink_repo)
                assert result is True

            except OSError:
                # Symlink creation might fail on some systems
                pytest.skip("Symlink creation not supported")

    def test_pr_manager_validation_permission_denied(self):
        """Test git repository validation with permission denied."""
        # Create a path that would cause permission issues
        restricted_path = Path("/root/.git")  # Typically not accessible

        result = _validate_git_repository(restricted_path)
        # Should handle gracefully without crashing
        assert isinstance(result, bool)

    @patch('subprocess.run')
    def test_pr_manager_git_command_with_unicode_path(self, mock_run):
        """Test git commands with Unicode characters in path."""
        unicode_path = Path("测试目录/项目")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = _validate_git_repository(unicode_path)

        # Should handle Unicode paths correctly
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            timeout=5,
            cwd=unicode_path
        )

    def test_pr_manager_empty_git_output(self):
        """Test handling of empty git command output."""
        mock_github_client = Mock()
        mock_cache_manager = Mock()
        pr_manager = PRManager(mock_github_client, mock_cache_manager)

        with patch('gh_pr.core.pr_manager._validate_git_repository', return_value=True):
            with patch('subprocess.run') as mock_run:
                # Mock empty output
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_run.return_value = mock_result

                result = pr_manager._get_current_repo_info()
                assert result is None
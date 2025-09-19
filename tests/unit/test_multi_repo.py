"""
Unit tests for multi-repository support.

Tests multi-repo management, cross-references, and operations.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import asyncio
from pathlib import Path
import tempfile

from gh_pr.core.multi_repo import (
    RepoConfig, CrossRepoPR, MultiRepoManager
)


class TestRepoConfig(unittest.TestCase):
    """Test repository configuration."""

    def test_repo_config_creation(self):
        """Test creating repo configuration."""
        config = RepoConfig(
            owner="octocat",
            name="hello-world",
            default_branch="main",
            pr_limit=20,
            aliases=["hw", "hello"]
        )

        self.assertEqual(config.owner, "octocat")
        self.assertEqual(config.name, "hello-world")
        self.assertEqual(config.default_branch, "main")
        self.assertEqual(config.pr_limit, 20)
        self.assertEqual(config.aliases, ["hw", "hello"])

    def test_repo_full_name(self):
        """Test full repository name generation."""
        config = RepoConfig(owner="octocat", name="hello-world")
        self.assertEqual(config.full_name, "octocat/hello-world")

    def test_repo_from_string(self):
        """Test creating repo config from string."""
        config = RepoConfig.from_string("octocat/hello-world")

        self.assertEqual(config.owner, "octocat")
        self.assertEqual(config.name, "hello-world")
        self.assertEqual(config.default_branch, "main")  # Default

    def test_repo_from_string_invalid(self):
        """Test invalid repository string format."""
        with self.assertRaises(ValueError) as context:
            RepoConfig.from_string("invalid-format")

        self.assertIn("Invalid repository format", str(context.exception))


class TestCrossRepoPR(unittest.TestCase):
    """Test cross-repository PR functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.repo = RepoConfig(owner="test", name="repo")
        self.mock_pr = Mock()
        self.mock_pr.number = 123
        self.mock_pr.title = "Test PR"

    def test_cross_repo_pr_creation(self):
        """Test creating cross-repo PR."""
        cross_pr = CrossRepoPR(
            pr=self.mock_pr,
            repo=self.repo,
            references=["other/repo@abc123"],
            related_prs=[("other/repo", 456)]
        )

        self.assertEqual(cross_pr.pr, self.mock_pr)
        self.assertEqual(cross_pr.repo, self.repo)
        self.assertEqual(cross_pr.references, ["other/repo@abc123"])
        self.assertEqual(cross_pr.related_prs, [("other/repo", 456)])

    def test_has_cross_references(self):
        """Test cross-reference detection."""
        # PR without references
        cross_pr = CrossRepoPR(pr=self.mock_pr, repo=self.repo)
        self.assertFalse(cross_pr.has_cross_references())

        # PR with references
        cross_pr.references = ["other/repo@abc123"]
        self.assertTrue(cross_pr.has_cross_references())

        # PR with related PRs
        cross_pr2 = CrossRepoPR(
            pr=self.mock_pr,
            repo=self.repo,
            related_prs=[("other/repo", 789)]
        )
        self.assertTrue(cross_pr2.has_cross_references())


class TestMultiRepoManager(unittest.TestCase):
    """Test multi-repository manager."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_github_client = Mock()
        self.mock_cache = Mock()
        self.manager = MultiRepoManager(
            self.mock_github_client,
            self.mock_cache
        )

    def test_add_repository(self):
        """Test adding repository to manager."""
        repo = RepoConfig(
            owner="octocat",
            name="hello-world",
            aliases=["hw"]
        )

        self.manager.add_repository(repo)

        # Check main entry
        self.assertIn("octocat/hello-world", self.manager._repos)
        self.assertEqual(
            self.manager._repos["octocat/hello-world"],
            repo
        )

        # Check alias
        self.assertIn("hw", self.manager._repos)
        self.assertEqual(self.manager._repos["hw"], repo)

    def test_remove_repository(self):
        """Test removing repository from manager."""
        repo = RepoConfig(
            owner="octocat",
            name="hello-world",
            aliases=["hw", "hello"]
        )

        self.manager.add_repository(repo)
        result = self.manager.remove_repository("octocat/hello-world")

        self.assertTrue(result)
        self.assertNotIn("octocat/hello-world", self.manager._repos)
        self.assertNotIn("hw", self.manager._repos)
        self.assertNotIn("hello", self.manager._repos)

    def test_remove_nonexistent_repository(self):
        """Test removing non-existent repository."""
        result = self.manager.remove_repository("nonexistent/repo")
        self.assertFalse(result)

    def test_get_repository(self):
        """Test getting repository by name or alias."""
        repo = RepoConfig(
            owner="octocat",
            name="hello-world",
            aliases=["hw"]
        )

        self.manager.add_repository(repo)

        # Get by full name
        retrieved = self.manager.get_repository("octocat/hello-world")
        self.assertEqual(retrieved, repo)

        # Get by alias
        retrieved_alias = self.manager.get_repository("hw")
        self.assertEqual(retrieved_alias, repo)

        # Get non-existent
        none_repo = self.manager.get_repository("nonexistent")
        self.assertIsNone(none_repo)

    def test_list_repositories(self):
        """Test listing all repositories."""
        repo1 = RepoConfig(owner="user1", name="repo1", aliases=["r1"])
        repo2 = RepoConfig(owner="user2", name="repo2", aliases=["r2"])

        self.manager.add_repository(repo1)
        self.manager.add_repository(repo2)

        repos = self.manager.list_repositories()

        self.assertEqual(len(repos), 2)
        self.assertIn(repo1, repos)
        self.assertIn(repo2, repos)

    def test_detect_cross_references(self):
        """Test cross-reference detection in PR body."""
        mock_pr = Mock()
        mock_pr.body = """
        This PR fixes the issue mentioned in owner/other-repo#123
        and references the commit owner/another-repo@abc123def456

        Also see our-org/our-repo#456 for related work.
        """

        repo = RepoConfig(owner="our-org", name="our-repo")
        cross_pr = CrossRepoPR(pr=mock_pr, repo=repo)

        self.manager._detect_cross_references(cross_pr)

        # Check PR references
        self.assertIn(("owner/other-repo", 123), cross_pr.related_prs)
        self.assertNotIn(("our-org/our-repo", 456), cross_pr.related_prs)  # Same repo

        # Check commit references
        self.assertIn("owner/another-repo@abc123def456", cross_pr.references)

    def test_detect_cross_references_no_body(self):
        """Test cross-reference detection with no PR body."""
        mock_pr = Mock()
        mock_pr.body = None

        repo = RepoConfig(owner="test", name="repo")
        cross_pr = CrossRepoPR(pr=mock_pr, repo=repo)

        # Should not crash
        self.manager._detect_cross_references(cross_pr)

        self.assertEqual(cross_pr.related_prs, [])
        self.assertEqual(cross_pr.references, [])

    async def test_get_all_prs_with_cache(self):
        """Test getting PRs from all repos with caching."""
        # Setup repos
        repo1 = RepoConfig(owner="user1", name="repo1")
        repo2 = RepoConfig(owner="user2", name="repo2")
        self.manager.add_repository(repo1)
        self.manager.add_repository(repo2)

        # Setup cache hit
        cached_data = {
            "user1/repo1": [Mock(title="PR1")],
            "user2/repo2": [Mock(title="PR2")]
        }
        self.mock_cache.get.return_value = cached_data

        result = await self.manager.get_all_prs(state='open')

        self.assertEqual(result, cached_data)
        self.mock_cache.get.assert_called_once()

    async def test_get_all_prs_without_cache(self):
        """Test getting PRs from all repos without cache."""
        # Setup repos
        repo1 = RepoConfig(owner="user1", name="repo1")
        self.manager.add_repository(repo1)

        # No cache hit
        self.mock_cache.get.return_value = None

        # Mock repository client
        mock_repo_client = Mock()
        mock_repo_client.get_pulls.return_value = [Mock(title="PR1")]
        self.manager._get_repo_client = Mock(return_value=mock_repo_client)

        # Mock async task
        with patch.object(self.manager, '_get_repo_prs') as mock_get_prs:
            mock_get_prs.return_value = [Mock(title="PR1")]

            result = await self.manager.get_all_prs(state='open')

            self.assertIn("user1/repo1", result)
            self.mock_cache.set.assert_called_once()

    async def test_search_prs(self):
        """Test searching PRs across repositories."""
        # Setup repos
        repo1 = RepoConfig(owner="user1", name="repo1")
        self.manager.add_repository(repo1)

        # Mock GitHub search
        mock_issue = Mock()
        mock_issue.pull_request = True
        mock_issue.repository.full_name = "user1/repo1"
        mock_issue.as_pull_request.return_value = Mock(title="Found PR")

        self.mock_github_client._github.search_issues.return_value = [mock_issue]

        results = await self.manager.search_prs("test query")

        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], CrossRepoPR)
        self.mock_github_client._github.search_issues.assert_called_once()

    async def test_get_pr_graph(self):
        """Test building PR relationship graph."""
        # Mock repository and PR
        mock_repo_client = Mock()
        mock_pr = Mock()
        mock_pr.title = "Main PR"
        mock_pr.state = "open"
        mock_pr.user.login = "author"
        mock_pr.body = "References other/repo#456"
        mock_repo_client.get_pull.return_value = mock_pr

        # Setup repo
        repo = RepoConfig(owner="test", name="repo")
        self.manager.add_repository(repo)
        self.manager._get_repo_client = Mock(return_value=mock_repo_client)

        graph = await self.manager.get_pr_graph(("test/repo", 123), max_depth=1)

        self.assertEqual(graph['root'], "test/repo#123")
        self.assertIn('nodes', graph)
        self.assertIn('edges', graph)

        # Check node was added
        self.assertEqual(len(graph['nodes']), 1)
        node = graph['nodes'][0]
        self.assertEqual(node['id'], "test/repo#123")
        self.assertEqual(node['title'], "Main PR")

    async def test_sync_labels(self):
        """Test syncing labels across repositories."""
        # Mock source repo and labels
        source_repo = RepoConfig(owner="source", name="repo")
        target_repo = RepoConfig(owner="target", name="repo")
        self.manager.add_repository(source_repo)
        self.manager.add_repository(target_repo)

        # Mock label objects
        mock_label = Mock()
        mock_label.name = "bug"
        mock_label.color = "ff0000"
        mock_label.description = "Bug report"

        # Mock repository clients
        source_client = Mock()
        source_client.get_labels.return_value = [mock_label]
        target_client = Mock()
        target_client.create_label.return_value = None

        def get_client(repo_config):
            if repo_config.full_name == "source/repo":
                return source_client
            return target_client

        self.manager._get_repo_client = get_client

        results = await self.manager.sync_labels("source/repo", ["target/repo"])

        self.assertIn("target/repo", results)
        self.assertIn("bug", results["target/repo"])
        target_client.create_label.assert_called_once_with(
            name="bug",
            color="ff0000",
            description="Bug report"
        )

    def test_load_config_from_file(self):
        """Test loading multi-repo configuration from file."""
        # Create temporary config file
        config_content = """
[[repositories]]
owner = "octocat"
name = "hello-world"
default_branch = "main"
pr_limit = 15
aliases = ["hw", "hello"]

[[repositories]]
owner = "github"
name = "docs"
default_branch = "master"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write(config_content)
            config_path = Path(f.name)

        try:
            # Create manager with config file
            manager = MultiRepoManager(
                self.mock_github_client,
                config_path=config_path
            )

            # Check repositories were loaded
            repos = manager.list_repositories()
            self.assertEqual(len(repos), 2)

            # Check first repo
            hw_repo = manager.get_repository("hw")
            self.assertIsNotNone(hw_repo)
            self.assertEqual(hw_repo.owner, "octocat")
            self.assertEqual(hw_repo.pr_limit, 15)

            # Check second repo
            docs_repo = manager.get_repository("github/docs")
            self.assertIsNotNone(docs_repo)
            self.assertEqual(docs_repo.default_branch, "master")

        finally:
            config_path.unlink()


if __name__ == '__main__':
    unittest.main()
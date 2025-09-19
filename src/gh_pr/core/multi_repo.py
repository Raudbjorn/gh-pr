"""
Multi-repository support for gh-pr.

Enables cross-repository PR management and operations
across multiple GitHub repositories.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from github import Github
from github.Repository import Repository
from github.PullRequest import PullRequest

from .github import GitHubClient
from ..utils.cache import CacheManager

logger = logging.getLogger(__name__)

# Constants for multi-repo operations
MAX_CONCURRENT_REPOS = 5
DEFAULT_PR_LIMIT = 10
CACHE_TTL_MINUTES = 10


@dataclass
class RepoConfig:
    """Configuration for a repository."""

    owner: str
    name: str
    default_branch: str = "main"
    pr_limit: int = DEFAULT_PR_LIMIT
    filters: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        """Get full repository name."""
        return f"{self.owner}/{self.name}"

    @classmethod
    def from_string(cls, repo_string: str) -> 'RepoConfig':
        """
        Create RepoConfig from string format.

        Args:
            repo_string: Repository in "owner/name" format

        Returns:
            RepoConfig instance
        """
        parts = repo_string.split('/')
        if len(parts) != 2:
            raise ValueError(f"Invalid repository format: {repo_string}")

        return cls(owner=parts[0], name=parts[1])


@dataclass
class CrossRepoPR:
    """Represents a PR that may reference other repositories."""

    pr: PullRequest
    repo: RepoConfig
    references: List[str] = field(default_factory=list)
    related_prs: List[Tuple[str, int]] = field(default_factory=list)

    def has_cross_references(self) -> bool:
        """Check if PR has cross-repository references."""
        return bool(self.references or self.related_prs)


class MultiRepoManager:
    """
    Manages operations across multiple GitHub repositories.

    Provides unified interface for searching, filtering, and
    managing PRs across multiple repositories.
    """

    def __init__(
        self,
        github_client: GitHubClient,
        cache_manager: Optional[CacheManager] = None,
        config_path: Optional[Path] = None
    ):
        """
        Initialize multi-repo manager.

        Args:
            github_client: GitHub API client
            cache_manager: Optional cache manager
            config_path: Path to multi-repo config file
        """
        self.github_client = github_client
        self.cache_manager = cache_manager
        self._repos: Dict[str, RepoConfig] = {}
        self._repo_clients: Dict[str, Repository] = {}
        self._executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REPOS)

        if config_path and config_path.exists():
            self._load_config(config_path)

    def _load_config(self, config_path: Path) -> None:
        """
        Load multi-repo configuration from file.

        Args:
            config_path: Path to configuration file
        """
        import tomllib

        try:
            with open(config_path, 'rb') as f:
                config = tomllib.load(f)

            repos_config = config.get('repositories', [])
            for repo_cfg in repos_config:
                repo = RepoConfig(
                    owner=repo_cfg['owner'],
                    name=repo_cfg['name'],
                    default_branch=repo_cfg.get('default_branch', 'main'),
                    pr_limit=repo_cfg.get('pr_limit', DEFAULT_PR_LIMIT),
                    filters=repo_cfg.get('filters', {}),
                    aliases=repo_cfg.get('aliases', [])
                )
                self.add_repository(repo)

            logger.info(f"Loaded {len(self._repos)} repositories from config")

        except Exception as e:
            logger.error(f"Failed to load multi-repo config: {e}")

    def add_repository(
        self,
        repo: RepoConfig
    ) -> None:
        """
        Add a repository to manage.

        Args:
            repo: Repository configuration
        """
        self._repos[repo.full_name] = repo

        # Add aliases for quick access
        for alias in repo.aliases:
            self._repos[alias] = repo

        logger.debug(f"Added repository: {repo.full_name}")

    def remove_repository(self, repo_name: str) -> bool:
        """
        Remove a repository from management.

        Args:
            repo_name: Repository name or alias

        Returns:
            True if repository was removed
        """
        if repo_name in self._repos:
            repo = self._repos[repo_name]

            # Remove main entry and aliases
            del self._repos[repo.full_name]
            for alias in repo.aliases:
                self._repos.pop(alias, None)

            # Clear cached client
            self._repo_clients.pop(repo.full_name, None)

            logger.debug(f"Removed repository: {repo.full_name}")
            return True

        return False

    def get_repository(self, repo_name: str) -> Optional[RepoConfig]:
        """
        Get repository configuration by name or alias.

        Args:
            repo_name: Repository name or alias

        Returns:
            Repository configuration or None
        """
        return self._repos.get(repo_name)

    def list_repositories(self) -> List[RepoConfig]:
        """
        List all managed repositories.

        Returns:
            List of repository configurations
        """
        # Deduplicate (aliases point to same config)
        unique_repos = {}
        for repo in self._repos.values():
            unique_repos[repo.full_name] = repo

        return list(unique_repos.values())

    def _get_repo_client(self, repo: RepoConfig) -> Repository:
        """
        Get GitHub repository client.

        Args:
            repo: Repository configuration

        Returns:
            GitHub repository object
        """
        if repo.full_name not in self._repo_clients:
            self._repo_clients[repo.full_name] = \
                self.github_client._github.get_repo(repo.full_name)

        return self._repo_clients[repo.full_name]

    async def get_all_prs(
        self,
        state: str = 'open',
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[PullRequest]]:
        """
        Get PRs from all managed repositories.

        Args:
            state: PR state (open, closed, all)
            filters: Additional filters to apply

        Returns:
            Dictionary mapping repo names to PR lists
        """
        all_prs = {}

        # Use cache if available
        cache_key = f"multi_repo_prs_{state}_{hash(str(filters))}"
        if self.cache_manager:
            cached = self.cache_manager.get(cache_key)
            if cached:
                logger.debug("Using cached multi-repo PRs")
                return cached

        # Fetch PRs concurrently
        tasks = []
        for repo in self.list_repositories():
            task = asyncio.create_task(
                self._get_repo_prs(repo, state, filters)
            )
            tasks.append((repo.full_name, task))

        # Gather results
        for repo_name, task in tasks:
            try:
                prs = await task
                all_prs[repo_name] = prs
            except Exception as e:
                logger.error(f"Failed to fetch PRs for {repo_name}: {e}")
                all_prs[repo_name] = []

        # Cache results
        if self.cache_manager:
            self.cache_manager.set(
                cache_key,
                all_prs,
                ttl=CACHE_TTL_MINUTES * 60
            )

        return all_prs

    async def _get_repo_prs(
        self,
        repo: RepoConfig,
        state: str,
        filters: Optional[Dict[str, Any]]
    ) -> List[PullRequest]:
        """
        Get PRs from a specific repository.

        Args:
            repo: Repository configuration
            state: PR state
            filters: Additional filters

        Returns:
            List of pull requests
        """
        try:
            repo_client = self._get_repo_client(repo)

            # Combine repo-specific and provided filters
            combined_filters = repo.filters.copy()
            if filters:
                combined_filters.update(filters)

            # Fetch PRs
            prs = list(repo_client.get_pulls(
                state=state,
                sort=combined_filters.get('sort', 'created'),
                direction=combined_filters.get('direction', 'desc'),
                base=combined_filters.get('base', repo.default_branch)
            )[:repo.pr_limit])

            return prs

        except Exception as e:
            logger.error(f"Error fetching PRs for {repo.full_name}: {e}")
            return []

    async def search_prs(
        self,
        query: str,
        repos: Optional[List[str]] = None
    ) -> List[CrossRepoPR]:
        """
        Search for PRs across repositories.

        Args:
            query: Search query
            repos: Optional list of repos to search (None = all)

        Returns:
            List of matching PRs with cross-references
        """
        results = []

        # Determine repos to search
        search_repos = []
        if repos:
            for repo_name in repos:
                repo_config = self.get_repository(repo_name)
                if repo_config:
                    search_repos.append(repo_config)
        else:
            search_repos = self.list_repositories()

        # Build GitHub search query
        repo_query_parts = [f"repo:{repo.full_name}" for repo in search_repos]
        full_query = f"{query} is:pr {' '.join(repo_query_parts)}"

        try:
            # Use GitHub search API
            issues = self.github_client._github.search_issues(
                query=full_query,
                sort='updated',
                order='desc'
            )

            for issue in issues[:50]:  # Limit results
                # Convert to PR
                if issue.pull_request:
                    # Find repo config
                    repo_name = issue.repository.full_name
                    repo_config = self._repos.get(repo_name)

                    if repo_config:
                        # Create CrossRepoPR with reference detection
                        cross_pr = CrossRepoPR(
                            pr=issue.as_pull_request(),
                            repo=repo_config
                        )

                        # Detect cross-references
                        self._detect_cross_references(cross_pr)
                        results.append(cross_pr)

        except Exception as e:
            logger.error(f"Search error: {e}")

        return results

    def _detect_cross_references(self, cross_pr: CrossRepoPR) -> None:
        """
        Detect cross-repository references in a PR.

        Args:
            cross_pr: CrossRepoPR to analyze
        """
        # Check PR body for references
        if cross_pr.pr.body:
            import re

            # Look for GitHub PR references (#owner/repo#number)
            pr_refs = re.findall(
                r'(?:^|[^/\w])([a-zA-Z0-9-]+/[a-zA-Z0-9-]+)#(\d+)',
                cross_pr.pr.body
            )

            for repo_ref, pr_num in pr_refs:
                if repo_ref != cross_pr.repo.full_name:
                    cross_pr.related_prs.append((repo_ref, int(pr_num)))

            # Look for commit references
            commit_refs = re.findall(
                r'(?:^|[^/\w])([a-zA-Z0-9-]+/[a-zA-Z0-9-]+)@([a-f0-9]{7,40})',
                cross_pr.pr.body
            )

            for repo_ref, commit_sha in commit_refs:
                if repo_ref != cross_pr.repo.full_name:
                    cross_pr.references.append(f"{repo_ref}@{commit_sha}")

    async def get_pr_graph(
        self,
        start_pr: Tuple[str, int],
        max_depth: int = 2
    ) -> Dict[str, Any]:
        """
        Build a graph of related PRs across repositories.

        Args:
            start_pr: Starting PR (repo_name, pr_number)
            max_depth: Maximum traversal depth

        Returns:
            PR relationship graph
        """
        graph = {
            'nodes': [],
            'edges': [],
            'root': f"{start_pr[0]}#{start_pr[1]}"
        }

        visited = set()
        queue = [(start_pr, 0)]

        while queue:
            (repo_name, pr_num), depth = queue.pop(0)

            if depth > max_depth:
                continue

            pr_key = f"{repo_name}#{pr_num}"
            if pr_key in visited:
                continue

            visited.add(pr_key)

            # Get PR details
            try:
                repo_config = self.get_repository(repo_name)
                if not repo_config:
                    continue

                repo_client = self._get_repo_client(repo_config)
                pr = repo_client.get_pull(pr_num)

                # Add node
                graph['nodes'].append({
                    'id': pr_key,
                    'repo': repo_name,
                    'pr_number': pr_num,
                    'title': pr.title,
                    'state': pr.state,
                    'author': pr.user.login if pr.user else 'Unknown',
                    'depth': depth
                })

                # Find references
                cross_pr = CrossRepoPR(pr=pr, repo=repo_config)
                self._detect_cross_references(cross_pr)

                # Add edges and queue related PRs
                for related_repo, related_pr_num in cross_pr.related_prs:
                    edge_key = f"{pr_key}->{related_repo}#{related_pr_num}"
                    if edge_key not in [e['id'] for e in graph['edges']]:
                        graph['edges'].append({
                            'id': edge_key,
                            'from': pr_key,
                            'to': f"{related_repo}#{related_pr_num}"
                        })

                        # Queue for traversal
                        queue.append(((related_repo, related_pr_num), depth + 1))

            except Exception as e:
                logger.error(f"Error processing {pr_key}: {e}")

        return graph

    async def sync_labels(
        self,
        source_repo: str,
        target_repos: Optional[List[str]] = None
    ) -> Dict[str, List[str]]:
        """
        Sync labels across repositories.

        Args:
            source_repo: Source repository for labels
            target_repos: Target repositories (None = all others)

        Returns:
            Results of label sync operations
        """
        results = {}

        # Get source labels
        source_config = self.get_repository(source_repo)
        if not source_config:
            logger.error(f"Source repository not found: {source_repo}")
            return results

        try:
            source_client = self._get_repo_client(source_config)
            source_labels = list(source_client.get_labels())

            # Determine target repos
            if not target_repos:
                target_repos = [
                    r.full_name for r in self.list_repositories()
                    if r.full_name != source_config.full_name
                ]

            # Sync to each target
            for target_repo_name in target_repos:
                target_config = self.get_repository(target_repo_name)
                if not target_config:
                    continue

                try:
                    target_client = self._get_repo_client(target_config)
                    created_labels = []

                    for label in source_labels:
                        try:
                            # Try to create label
                            target_client.create_label(
                                name=label.name,
                                color=label.color,
                                description=label.description or ""
                            )
                            created_labels.append(label.name)
                        except Exception:
                            # Label might already exist
                            pass

                    results[target_repo_name] = created_labels

                except Exception as e:
                    logger.error(f"Failed to sync labels to {target_repo_name}: {e}")
                    results[target_repo_name] = []

        except Exception as e:
            logger.error(f"Failed to get source labels: {e}")

        return results
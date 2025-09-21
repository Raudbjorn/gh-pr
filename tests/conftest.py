"""Pytest configuration and shared fixtures for gh-pr tests."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from gh_pr.core.github import GitHubClient
from gh_pr.utils.cache import CacheManager


@pytest.fixture
def mock_github_client():
    """Create a mock GitHub client for testing."""
    mock_client = Mock(spec=GitHubClient)

    # Setup mock auth token access
    mock_requester = Mock()
    mock_auth = Mock()
    mock_auth.token = "test_token_12345"
    mock_requester._Requester__auth = mock_auth
    mock_client.github._Github__requester = mock_requester

    return mock_client


@pytest.fixture
def mock_cache_manager():
    """Create a mock cache manager for testing."""
    mock_cache = Mock(spec=CacheManager)
    mock_cache.enabled = True
    mock_cache.get.return_value = None
    mock_cache.set.return_value = True
    return mock_cache


@pytest.fixture
def temp_directory():
    """Create a temporary directory for file operations."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_pr_data():
    """Sample PR data for testing."""
    return {
        "number": 123,
        "title": "Test PR",
        "state": "open",
        "author": "test_user",
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T11:00:00Z",
        "merged": False,
        "merged_at": None,
        "mergeable": True,
        "mergeable_state": "clean",
        "head": {
            "ref": "feature-branch",
            "sha": "abc123def456"
        },
        "base": {
            "ref": "main",
            "sha": "def456abc123"
        },
        "body": "This is a test pull request description.",
        "additions": 50,
        "deletions": 10,
        "changed_files": 3,
        "review_comments": 5,
        "comments": 2,
        "commits": 3,
        "labels": ["enhancement", "needs-review"]
    }


@pytest.fixture
def sample_comments():
    """Sample comment threads for testing."""
    return [
        {
            "path": "src/main.py",
            "line": 42,
            "id": "thread_1",
            "is_resolved": False,
            "is_outdated": False,
            "comments": [
                {
                    "id": "comment_1",
                    "author": "reviewer1",
                    "body": "This function could be optimized",
                    "type": "review",
                    "created_at": "2024-01-15T10:30:00Z",
                    "updated_at": "2024-01-15T10:35:00Z",
                    "in_reply_to_id": None,
                    "suggestions": [],
                    "reactions": [{"type": "thumbs_up"}],
                    "author_association": "COLLABORATOR"
                },
                {
                    "id": "comment_2",
                    "author": "test_user",
                    "body": "Good point, I'll update it",
                    "type": "response",
                    "created_at": "2024-01-15T10:45:00Z",
                    "updated_at": None,
                    "in_reply_to_id": "comment_1",
                    "suggestions": [],
                    "reactions": [],
                    "author_association": "OWNER"
                }
            ]
        },
        {
            "path": "src/utils.py",
            "line": 15,
            "id": "thread_2",
            "is_resolved": True,
            "is_outdated": True,
            "comments": [
                {
                    "id": "comment_3",
                    "author": "reviewer2",
                    "body": "Consider adding error handling here",
                    "type": "review",
                    "created_at": "2024-01-14T15:00:00Z",
                    "updated_at": None,
                    "in_reply_to_id": None,
                    "suggestions": ["try-catch block"],
                    "reactions": [],
                    "author_association": "MEMBER"
                }
            ]
        }
    ]


@pytest.fixture
def sample_batch_results():
    """Sample batch operation results for testing."""
    return [
        {
            "pr_number": 123,
            "success": True,
            "result": 3,
            "errors": [],
            "duration": 1.5
        },
        {
            "pr_number": 124,
            "success": False,
            "result": 0,
            "errors": ["Permission denied", "API timeout"],
            "duration": 0.8
        },
        {
            "pr_number": 125,
            "success": True,
            "result": 1,
            "errors": [],
            "duration": 0.3
        }
    ]


@pytest.fixture
def sample_pr_identifiers():
    """Sample PR identifiers for batch operations."""
    return [
        ("owner1", "repo1", 123),
        ("owner2", "repo2", 124),
        ("owner3", "repo3", 125)
    ]


# Test markers for different test categories
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.slow = pytest.mark.slow
pytest.mark.network = pytest.mark.network


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "network: Tests requiring network access")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on file location."""
    for item in items:
        # Add unit marker to unit tests
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)

        # Add integration marker to integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        # Add slow marker to tests with "slow" in name
        if "slow" in item.name or "performance" in item.name or "large" in item.name:
            item.add_marker(pytest.mark.slow)
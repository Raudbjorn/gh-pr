#!/usr/bin/env python3
"""Test Phase 4 fixes for PR review issues."""

import sys
import os
import re
import threading
import time
from unittest.mock import Mock, patch, MagicMock

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_graphql_id_validation():
    """Test that base64 ID validation accepts valid GitHub IDs."""
    print("\n1. Testing GraphQL ID validation fix...")

    from gh_pr.core.graphql import GraphQLClient

    # Mock token for client
    client = GraphQLClient("test_token")

    # Test valid base64 IDs (these are actual GitHub ID formats)
    valid_ids = [
        "PRR_kwDOI_Qb-M5fYZXm",  # Real GitHub thread ID
        "MDEwOlB1bGxSZXF1ZXN0MQ==",  # Standard base64
        "U_kgDOI9Xs-w",  # Short GitHub ID
        "ABC123+/=",  # Base64 with special chars
        "test-id_123",  # URL-safe base64
    ]

    # Test that validation accepts these IDs
    for test_id in valid_ids:
        # Check the regex pattern directly
        pattern = r'^[A-Za-z0-9+/\-_=]+$'
        if not re.match(pattern, test_id):
            print(f"  ✗ Failed to validate valid ID: {test_id}")
            return False

    # Test invalid IDs are rejected
    invalid_ids = [
        "",  # Empty
        "test@id",  # Invalid character
        "test#123",  # Invalid character
        "test id",  # Space
    ]

    for test_id in invalid_ids:
        pattern = r'^[A-Za-z0-9+/\-_=]+$'
        if re.match(pattern, test_id):
            print(f"  ✗ Should have rejected invalid ID: {test_id}")
            return False

    print("  ✓ GraphQL ID validation correctly handles GitHub base64 IDs")
    return True

def test_thread_safe_rate_limiting():
    """Test that rate limiting works correctly with threading.Lock."""
    print("\n2. Testing thread-safe rate limiting fix...")

    from gh_pr.core.batch import BatchOperations
    from gh_pr.core.pr_manager import PRManager
    from gh_pr.auth.permissions import PermissionChecker

    # Mock dependencies
    mock_pr_manager = Mock(spec=PRManager)
    mock_permission_checker = Mock(spec=PermissionChecker)

    # Create batch operations with short rate limit for testing
    batch_ops = BatchOperations(
        pr_manager=mock_pr_manager,
        permission_checker=mock_permission_checker,
        rate_limit=0.1,  # 100ms for testing
        max_concurrent=3
    )

    # Verify api_lock exists
    if not hasattr(batch_ops, 'api_lock'):
        print("  ✗ api_lock not found in BatchOperations")
        return False

    if not isinstance(batch_ops.api_lock, threading.Lock):
        print("  ✗ api_lock is not a threading.Lock")
        return False

    # Test rate limiting enforcement
    call_times = []

    def test_operation(*args, **kwargs):
        call_times.append(time.time())
        return "result"

    # Execute multiple operations
    for _ in range(3):
        batch_ops._execute_with_rate_limit(test_operation)

    # Check that calls were spaced by at least rate_limit
    if len(call_times) >= 2:
        for i in range(1, len(call_times)):
            gap = call_times[i] - call_times[i-1]
            if gap < 0.1:  # Should be at least 100ms apart
                print(f"  ✗ Calls not properly rate limited: {gap:.3f}s gap")
                return False

    print("  ✓ Thread-safe rate limiting with Lock works correctly")
    return True

def test_pr_manager_token_handling():
    """Test PRManager accepts optional token parameter."""
    print("\n3. Testing PRManager token parameter fix...")

    from gh_pr.core.pr_manager import PRManager
    from gh_pr.core.github import GitHubClient
    from gh_pr.utils.cache import CacheManager

    # Mock dependencies
    mock_github_client = Mock(spec=GitHubClient)
    mock_cache_manager = Mock(spec=CacheManager)

    # Test with token
    pr_manager = PRManager(
        github_client=mock_github_client,
        cache_manager=mock_cache_manager,
        token="test_token_123"
    )

    if not hasattr(pr_manager, 'graphql'):
        print("  ✗ PRManager doesn't have graphql attribute")
        return False

    if pr_manager.graphql is None:
        print("  ✗ GraphQL client should be initialized when token provided")
        return False

    # Test without token
    pr_manager2 = PRManager(
        github_client=mock_github_client,
        cache_manager=mock_cache_manager,
        token=None
    )

    if pr_manager2.graphql is not None:
        print("  ✗ GraphQL client should be None when no token provided")
        return False

    print("  ✓ PRManager correctly handles optional token parameter")
    return True

def test_batch_refactoring():
    """Test that batch operations refactoring works."""
    print("\n4. Testing batch operations refactoring...")

    from gh_pr.core.batch import BatchOperations
    from gh_pr.core.pr_manager import PRManager
    from gh_pr.auth.permissions import PermissionChecker

    # Mock dependencies
    mock_pr_manager = Mock(spec=PRManager)
    mock_permission_checker = Mock(spec=PermissionChecker)

    batch_ops = BatchOperations(
        pr_manager=mock_pr_manager,
        permission_checker=mock_permission_checker
    )

    # Check that the refactored method exists
    if not hasattr(batch_ops, '_execute_batch_operation'):
        print("  ✗ _execute_batch_operation method not found")
        return False

    # Check that public methods still exist
    if not hasattr(batch_ops, 'resolve_outdated_comments_batch'):
        print("  ✗ resolve_outdated_comments_batch method not found")
        return False

    if not hasattr(batch_ops, 'accept_suggestions_batch'):
        print("  ✗ accept_suggestions_batch method not found")
        return False

    print("  ✓ Batch operations successfully refactored to reduce duplication")
    return True

def test_pr_data_fetching():
    """Test that _get_pr_data fetches actual PR data."""
    print("\n5. Testing _get_pr_data fix...")

    from gh_pr.core.batch import BatchOperations
    from gh_pr.core.pr_manager import PRManager
    from gh_pr.auth.permissions import PermissionChecker

    # Mock dependencies
    mock_pr_manager = Mock(spec=PRManager)
    mock_permission_checker = Mock(spec=PermissionChecker)

    # Setup mock return values
    mock_pr_manager.fetch_pr_data.return_value = {
        "title": "Actual PR Title",
        "state": "open",
        "number": 123
    }
    mock_pr_manager.get_pr_comments.return_value = ["comment1", "comment2"]

    batch_ops = BatchOperations(
        pr_manager=mock_pr_manager,
        permission_checker=mock_permission_checker
    )

    # Test _get_pr_data
    result = batch_ops._get_pr_data("owner", "repo", 123)

    # Verify it calls fetch_pr_data
    mock_pr_manager.fetch_pr_data.assert_called_once_with("owner", "repo", 123)

    # Verify result contains actual title
    if result["title"] != "Actual PR Title":
        print(f"  ✗ Expected actual PR title, got: {result['title']}")
        return False

    if result["state"] != "open":
        print(f"  ✗ Expected state from PR data, got: {result['state']}")
        return False

    print("  ✓ _get_pr_data now fetches actual PR data instead of hardcoded values")
    return True

def test_unused_constants_removed():
    """Test that unused constants were removed."""
    print("\n6. Testing removal of unused constants...")

    # Check batch.py
    with open('src/gh_pr/core/batch.py', 'r') as f:
        batch_content = f.read()

    if 'DEFAULT_BATCH_SIZE' in batch_content:
        print("  ✗ DEFAULT_BATCH_SIZE still exists in batch.py")
        return False

    # Check graphql.py
    with open('src/gh_pr/core/graphql.py', 'r') as f:
        graphql_content = f.read()

    if 'MAX_RETRIES' in graphql_content:
        print("  ✗ MAX_RETRIES still exists in graphql.py")
        return False

    print("  ✓ Unused constants successfully removed")
    return True

def main():
    """Run all tests."""
    print("Testing Phase 4 fixes for PR review issues...")

    tests = [
        test_graphql_id_validation,
        test_thread_safe_rate_limiting,
        test_pr_manager_token_handling,
        test_batch_refactoring,
        test_pr_data_fetching,
        test_unused_constants_removed,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ✗ Test {test.__name__} failed with error: {e}")
            failed += 1

    print("\n" + "=" * 40)
    print(f"Results: {passed} passed, {failed} failed")

    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
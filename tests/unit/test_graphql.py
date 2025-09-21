"""Unit tests for GraphQL client functionality."""

import json
import pytest
import requests
from unittest.mock import Mock, patch, MagicMock

from gh_pr.core.graphql import (
    GraphQLClient,
    GraphQLError,
    GraphQLResult,
    GITHUB_GRAPHQL_URL,
    RATE_LIMIT_DELAY,
)


class TestGraphQLError:
    """Test GraphQLError dataclass."""

    def test_creation_with_required_fields(self):
        """Test GraphQLError creation with required fields only."""
        error = GraphQLError("Test error", "TEST_TYPE")
        assert error.message == "Test error"
        assert error.type == "TEST_TYPE"
        assert error.locations is None
        assert error.path is None

    def test_creation_with_all_fields(self):
        """Test GraphQLError creation with all fields."""
        locations = [{"line": 1, "column": 1}]
        path = ["test", "field"]

        error = GraphQLError(
            "Test error",
            "TEST_TYPE",
            locations=locations,
            path=path
        )

        assert error.message == "Test error"
        assert error.type == "TEST_TYPE"
        assert error.locations == locations
        assert error.path == path


class TestGraphQLResult:
    """Test GraphQLResult dataclass."""

    def test_creation_with_data_only(self):
        """Test GraphQLResult creation with data only."""
        data = {"test": "value"}
        result = GraphQLResult(data=data)

        assert result.data == data
        assert result.errors is None
        assert result.success is True

    def test_creation_with_errors(self):
        """Test GraphQLResult creation with errors."""
        errors = [GraphQLError("Test error", "TEST_TYPE")]
        result = GraphQLResult(errors=errors)

        assert result.data is None
        assert result.errors == errors
        assert result.success is False

    def test_creation_with_empty_errors_list(self):
        """Test GraphQLResult with empty errors list is considered success."""
        result = GraphQLResult(errors=[])
        assert result.success is True

    def test_success_property_update(self):
        """Test that success property is correctly updated based on errors."""
        # No errors - success
        result = GraphQLResult()
        assert result.success is True

        # Empty errors list - success
        result = GraphQLResult(errors=[])
        assert result.success is True

        # Has errors - not success
        result = GraphQLResult(errors=[GraphQLError("Error", "TYPE")])
        assert result.success is False


class TestGraphQLClient:
    """Test GraphQLClient functionality."""

    def test_initialization_with_valid_token(self):
        """Test GraphQLClient initialization with valid token."""
        client = GraphQLClient("valid_token")

        assert client.token == "valid_token"
        assert isinstance(client.session, requests.Session)
        assert client.session.headers["Authorization"] == "Bearer valid_token"
        assert client.session.headers["Content-Type"] == "application/json"
        assert client.session.headers["Accept"] == "application/vnd.github.v4+json"
        assert "gh-pr" in client.session.headers["User-Agent"]

    def test_initialization_with_whitespace_token(self):
        """Test GraphQLClient strips whitespace from token."""
        client = GraphQLClient("  valid_token  ")
        assert client.token == "valid_token"

    def test_initialization_with_empty_token(self):
        """Test GraphQLClient raises ValueError for empty token."""
        with pytest.raises(ValueError, match="GitHub token is required"):
            GraphQLClient("")

        with pytest.raises(ValueError, match="GitHub token is required"):
            GraphQLClient("   ")

        with pytest.raises(ValueError, match="GitHub token is required"):
            GraphQLClient(None)

    @patch('requests.Session.post')
    def test_execute_successful_request(self, mock_post):
        """Test successful GraphQL query execution."""
        # Setup mock response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"test": "value"}
        }
        mock_post.return_value = mock_response

        client = GraphQLClient("test_token")
        result = client.execute("query { test }")

        assert result.success is True
        assert result.data == {"test": "value"}
        assert result.errors is None

        # Verify request was made correctly
        mock_post.assert_called_once_with(
            GITHUB_GRAPHQL_URL,
            json={"query": "query { test }"},
            timeout=30
        )

    @patch('requests.Session.post')
    def test_execute_with_variables(self, mock_post):
        """Test GraphQL query execution with variables."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"test": "value"}}
        mock_post.return_value = mock_response

        client = GraphQLClient("test_token")
        variables = {"var1": "value1", "var2": 42}
        result = client.execute("query($var1: String!, $var2: Int!) { test }", variables)

        assert result.success is True
        mock_post.assert_called_once_with(
            GITHUB_GRAPHQL_URL,
            json={
                "query": "query($var1: String!, $var2: Int!) { test }",
                "variables": variables
            },
            timeout=30
        )

    @patch('requests.Session.post')
    def test_execute_with_graphql_errors(self, mock_post):
        """Test handling of GraphQL errors in response."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": None,
            "errors": [
                {
                    "message": "Field 'test' doesn't exist",
                    "type": "VALIDATION_ERROR",
                    "locations": [{"line": 1, "column": 1}],
                    "path": ["test"]
                },
                {
                    "message": "Another error",
                    "type": "EXECUTION_ERROR"
                }
            ]
        }
        mock_post.return_value = mock_response

        client = GraphQLClient("test_token")
        result = client.execute("query { test }")

        assert result.success is False
        assert result.data is None
        assert len(result.errors) == 2

        error1 = result.errors[0]
        assert error1.message == "Field 'test' doesn't exist"
        assert error1.type == "VALIDATION_ERROR"
        assert error1.locations == [{"line": 1, "column": 1}]
        assert error1.path == ["test"]

        error2 = result.errors[1]
        assert error2.message == "Another error"
        assert error2.type == "EXECUTION_ERROR"
        assert error2.locations is None
        assert error2.path is None

    @patch('requests.Session.post')
    def test_execute_401_unauthorized(self, mock_post):
        """Test handling of 401 Unauthorized response."""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        client = GraphQLClient("invalid_token")
        result = client.execute("query { test }")

        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].message == "Invalid or expired GitHub token"
        assert result.errors[0].type == "UNAUTHORIZED"

    @patch('requests.Session.post')
    def test_execute_403_forbidden(self, mock_post):
        """Test handling of 403 Forbidden response."""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 403
        mock_post.return_value = mock_response

        client = GraphQLClient("test_token")
        result = client.execute("query { test }")

        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].message == "Insufficient permissions or rate limited"
        assert result.errors[0].type == "FORBIDDEN"

    @patch('requests.Session.post')
    def test_execute_other_http_error(self, mock_post):
        """Test handling of other HTTP errors."""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        client = GraphQLClient("test_token")
        result = client.execute("query { test }")

        assert result.success is False
        assert len(result.errors) == 1
        assert "HTTP 500: Internal Server Error" in result.errors[0].message
        assert result.errors[0].type == "HTTP_ERROR"

    @patch('requests.Session.post')
    def test_execute_network_error(self, mock_post):
        """Test handling of network errors."""
        mock_post.side_effect = requests.ConnectionError("Network error")

        client = GraphQLClient("test_token")
        result = client.execute("query { test }")

        assert result.success is False
        assert len(result.errors) == 1
        assert "Network error" in result.errors[0].message
        assert result.errors[0].type == "NETWORK_ERROR"

    @patch('requests.Session.post')
    def test_execute_json_decode_error(self, mock_post):
        """Test handling of JSON decode errors."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_post.return_value = mock_response

        client = GraphQLClient("test_token")
        result = client.execute("query { test }")

        assert result.success is False
        assert len(result.errors) == 1
        assert "Invalid response format" in result.errors[0].message
        assert result.errors[0].type == "JSON_ERROR"

    @patch('requests.Session.post')
    def test_execute_unexpected_error(self, mock_post):
        """Test handling of unexpected errors."""
        mock_post.side_effect = Exception("Unexpected error")

        client = GraphQLClient("test_token")
        result = client.execute("query { test }")

        assert result.success is False
        assert len(result.errors) == 1
        assert "Unexpected error" in result.errors[0].message
        assert result.errors[0].type == "UNKNOWN_ERROR"

    def test_resolve_thread_with_valid_id(self):
        """Test resolve_thread with valid thread ID."""
        client = GraphQLClient("test_token")

        with patch.object(client, 'execute') as mock_execute:
            mock_execute.return_value = GraphQLResult(
                data={"resolveReviewThread": {"thread": {"id": "thread123", "isResolved": True}}}
            )

            result = client.resolve_thread("thread123")

            assert result.success is True
            mock_execute.assert_called_once()

            # Check the mutation and variables
            call_args = mock_execute.call_args
            assert "resolveReviewThread" in call_args[0][0]
            assert call_args[0][1] == {"threadId": "thread123"}

    def test_resolve_thread_with_whitespace_id(self):
        """Test resolve_thread strips whitespace from ID."""
        client = GraphQLClient("test_token")

        with patch.object(client, 'execute') as mock_execute:
            mock_execute.return_value = GraphQLResult(data={})

            result = client.resolve_thread("  thread123  ")

            call_args = mock_execute.call_args
            assert call_args[0][1] == {"threadId": "thread123"}

    def test_resolve_thread_with_empty_id(self):
        """Test resolve_thread with empty thread ID."""
        client = GraphQLClient("test_token")

        result = client.resolve_thread("")
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].message == "Thread ID is required"
        assert result.errors[0].type == "INVALID_INPUT"

        result = client.resolve_thread("   ")
        assert result.success is False

        result = client.resolve_thread(None)
        assert result.success is False

    def test_accept_suggestion_with_valid_id(self):
        """Test accept_suggestion with valid suggestion ID."""
        client = GraphQLClient("test_token")

        with patch.object(client, 'execute') as mock_execute:
            mock_execute.return_value = GraphQLResult(
                data={"acceptSuggestion": {"clientMutationId": "mutation123"}}
            )

            result = client.accept_suggestion("suggestion123")

            assert result.success is True
            mock_execute.assert_called_once()

            # Check the mutation and variables
            call_args = mock_execute.call_args
            assert "acceptSuggestion" in call_args[0][0]
            assert call_args[0][1] == {"suggestionId": "suggestion123"}

    def test_accept_suggestion_with_empty_id(self):
        """Test accept_suggestion with empty suggestion ID."""
        client = GraphQLClient("test_token")

        result = client.accept_suggestion("")
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].message == "Suggestion ID is required"
        assert result.errors[0].type == "INVALID_INPUT"

    def test_get_pr_threads_with_valid_params(self):
        """Test get_pr_threads with valid parameters."""
        client = GraphQLClient("test_token")

        with patch.object(client, 'execute') as mock_execute:
            mock_execute.return_value = GraphQLResult(data={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None}
                        }
                    }
                }
            })

            result = client.get_pr_threads("owner", "repo", 123)

            assert result.success is True
            mock_execute.assert_called_once()

            call_args = mock_execute.call_args
            assert "GetPRThreads" in call_args[0][0]
            assert call_args[0][1] == {
                "owner": "owner",
                "repo": "repo",
                "number": 123,
                "cursor": None
            }

    def test_get_pr_threads_strips_whitespace(self):
        """Test get_pr_threads strips whitespace from parameters."""
        client = GraphQLClient("test_token")

        with patch.object(client, 'execute') as mock_execute:
            mock_execute.return_value = GraphQLResult(data={})

            result = client.get_pr_threads("  owner  ", "  repo  ", 123)

            call_args = mock_execute.call_args
            assert call_args[1]["variables"]["owner"] == "owner"
            assert call_args[1]["variables"]["repo"] == "repo"

    def test_get_pr_threads_with_invalid_params(self):
        """Test get_pr_threads with invalid parameters."""
        client = GraphQLClient("test_token")

        # Missing parameters
        result = client.get_pr_threads("", "repo", 123)
        assert result.success is False
        assert "Owner, repo, and PR number are required" in result.errors[0].message

        result = client.get_pr_threads("owner", "", 123)
        assert result.success is False

        result = client.get_pr_threads("owner", "repo", None)
        assert result.success is False

        # Invalid PR number
        result = client.get_pr_threads("owner", "repo", 0)
        assert result.success is False
        assert "PR number must be positive" in result.errors[0].message

        result = client.get_pr_threads("owner", "repo", -1)
        assert result.success is False

    def test_get_pr_suggestions_with_valid_params(self):
        """Test get_pr_suggestions with valid parameters."""
        client = GraphQLClient("test_token")

        with patch.object(client, 'execute') as mock_execute:
            mock_execute.return_value = GraphQLResult(data={"repository": {"pullRequest": {}}})

            result = client.get_pr_suggestions("owner", "repo", 123)

            assert result.success is True
            mock_execute.assert_called_once()

            call_args = mock_execute.call_args
            assert "GetPRSuggestions" in call_args[0][0]
            assert call_args[1]["variables"] == {
                "owner": "owner",
                "repo": "repo",
                "number": 123
            }

    def test_get_pr_suggestions_with_invalid_params(self):
        """Test get_pr_suggestions with invalid parameters."""
        client = GraphQLClient("test_token")

        # Same validation as get_pr_threads
        result = client.get_pr_suggestions("", "repo", 123)
        assert result.success is False

        result = client.get_pr_suggestions("owner", "repo", 0)
        assert result.success is False

    def test_check_permissions_with_valid_params(self):
        """Test check_permissions with valid parameters."""
        client = GraphQLClient("test_token")

        with patch.object(client, 'execute') as mock_execute:
            mock_execute.return_value = GraphQLResult(
                data={
                    "repository": {"viewerPermission": "WRITE"},
                    "viewer": {"login": "testuser"}
                }
            )

            result = client.check_permissions("owner", "repo")

            assert result.success is True
            mock_execute.assert_called_once()

            call_args = mock_execute.call_args
            assert "CheckPermissions" in call_args[0][0]
            assert call_args[1]["variables"] == {
                "owner": "owner",
                "repo": "repo"
            }

    def test_check_permissions_with_invalid_params(self):
        """Test check_permissions with invalid parameters."""
        client = GraphQLClient("test_token")

        result = client.check_permissions("", "repo")
        assert result.success is False
        assert "Owner and repo are required" in result.errors[0].message

        result = client.check_permissions("owner", "")
        assert result.success is False


class TestGraphQLClientEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_large_response_handling(self):
        """Test handling of large GraphQL responses."""
        client = GraphQLClient("test_token")

        # Create a large response
        large_data = {"items": [{"id": i, "data": "x" * 1000} for i in range(1000)]}

        with patch.object(client, 'execute') as mock_execute:
            mock_execute.return_value = GraphQLResult(data=large_data)

            result = client.get_pr_threads("owner", "repo", 123)
            assert result.success is True

    def test_unicode_handling(self):
        """Test handling of Unicode characters in responses."""
        client = GraphQLClient("test_token")

        unicode_data = {
            "message": "测试 🚀 émojis and ünïcode",
            "author": "用户名"
        }

        with patch.object(client, 'execute') as mock_execute:
            mock_execute.return_value = GraphQLResult(data=unicode_data)

            result = client.resolve_thread("thread123")
            assert result.success is True

    def test_concurrent_requests(self):
        """Test that client can handle concurrent requests safely."""
        import threading
        import time

        client = GraphQLClient("test_token")
        results = []

        def make_request():
            with patch.object(client, 'execute') as mock_execute:
                mock_execute.return_value = GraphQLResult(data={"test": "success"})
                result = client.resolve_thread(f"thread_{threading.current_thread().ident}")
                results.append(result.success)

        threads = [threading.Thread(target=make_request) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results)
        assert len(results) == 5

    def test_rate_limit_constant(self):
        """Test that rate limit constant is properly defined."""
        assert RATE_LIMIT_DELAY == 1.0
        assert isinstance(RATE_LIMIT_DELAY, (int, float))

    def test_graphql_url_constant(self):
        """Test that GraphQL URL constant is properly defined."""
        assert GITHUB_GRAPHQL_URL == "https://api.github.com/graphql"
        assert isinstance(GITHUB_GRAPHQL_URL, str)


class TestGraphQLClientIntegrationPatterns:
    """Test integration patterns that would be used by other components."""

    def test_permission_check_integration_pattern(self):
        """Test typical permission checking pattern."""
        client = GraphQLClient("test_token")

        with patch.object(client, 'execute') as mock_execute:
            # Simulate permission check success
            mock_execute.return_value = GraphQLResult(
                data={
                    "repository": {
                        "viewerPermission": "WRITE",
                        "viewerCanCreatePullRequest": True
                    },
                    "viewer": {"login": "testuser"}
                }
            )

            # Pattern: Check permissions before performing operation
            perm_result = client.check_permissions("owner", "repo")

            if perm_result.success:
                repo_data = perm_result.data.get("repository", {})
                permission = repo_data.get("viewerPermission", "")

                assert permission in ["WRITE", "ADMIN", "MAINTAIN"]

                # Would then proceed with actual operation
                thread_result = client.resolve_thread("thread123")

    def test_error_aggregation_pattern(self):
        """Test pattern for aggregating errors across multiple operations."""
        client = GraphQLClient("test_token")

        errors = []

        # Simulate multiple operations with some failures
        operations = [
            ("thread1", True),   # Success
            ("thread2", False),  # Failure
            ("thread3", True),   # Success
            ("thread4", False),  # Failure
        ]

        for thread_id, should_succeed in operations:
            with patch.object(client, 'execute') as mock_execute:
                if should_succeed:
                    mock_execute.return_value = GraphQLResult(data={"success": True})
                else:
                    mock_execute.return_value = GraphQLResult(
                        errors=[GraphQLError(f"Failed to resolve {thread_id}", "OPERATION_FAILED")]
                    )

                result = client.resolve_thread(thread_id)

                if not result.success:
                    errors.extend([err.message for err in result.errors])

        assert len(errors) == 2
        assert "Failed to resolve thread2" in errors
        assert "Failed to resolve thread4" in errors

    def test_retry_pattern_simulation(self):
        """Test simulation of retry pattern for transient failures."""
        client = GraphQLClient("test_token")

        attempt_count = 0

        def mock_execute_with_retry(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1

            if attempt_count < 3:  # Fail first 2 attempts
                return GraphQLResult(
                    errors=[GraphQLError("Rate limited", "FORBIDDEN")]
                )
            else:  # Succeed on 3rd attempt
                return GraphQLResult(data={"success": True})

        with patch.object(client, 'execute', side_effect=mock_execute_with_retry):
            # Simulate retry logic
            max_retries = 3
            for attempt in range(max_retries):
                result = client.resolve_thread("thread123")
                if result.success:
                    break
                elif attempt < max_retries - 1:
                    continue  # Would normally wait before retry

            assert result.success is True
            assert attempt_count == 3
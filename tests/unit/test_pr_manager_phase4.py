"""Unit tests for PRManager Phase 4 methods."""

import pytest
from unittest.mock import Mock, MagicMock, patch

from gh_pr.core.pr_manager import PRManager
from gh_pr.core.graphql import GraphQLClient, GraphQLResult, GraphQLError
from gh_pr.core.github import GitHubClient
from gh_pr.utils.cache import CacheManager


class TestPRManagerGraphQLIntegration:
    """Test PRManager integration with GraphQL client."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_github_client = Mock(spec=GitHubClient)
        self.mock_cache_manager = Mock(spec=CacheManager)

        # PRManager.graphql reads GitHubClient.token
        self.mock_github_client.token = "test_token"  # noqa: S105

        self.pr_manager = PRManager(self.mock_github_client, self.mock_cache_manager)

    def test_graphql_property_initialization(self):
        """Test that GraphQL client is properly initialized on first access."""
        # GraphQL client should not be initialized yet
        assert self.pr_manager._graphql_client is None

        # Access the property
        graphql_client = self.pr_manager.graphql

        # Should now be initialized
        assert self.pr_manager._graphql_client is not None
        assert isinstance(graphql_client, GraphQLClient)
        assert graphql_client.token == "test_token"

    def test_graphql_property_caching(self):
        """Test that GraphQL client is cached after first access."""
        client1 = self.pr_manager.graphql
        client2 = self.pr_manager.graphql

        # Should be the same instance
        assert client1 is client2

    def test_graphql_property_with_different_token(self):
        """Test GraphQL client creation with different token."""
        # Change the token in mock
        mock_auth = Mock()
        mock_auth.token = "different_token"
        self.mock_github_client.github._Github__requester._Requester__auth = mock_auth

        # Create new PRManager
        pr_manager = PRManager(self.mock_github_client, self.mock_cache_manager)
        graphql_client = pr_manager.graphql

        assert graphql_client.token == "different_token"


class TestResolveOutdatedComments:
    """Test resolve_outdated_comments method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_github_client = Mock(spec=GitHubClient)
        self.mock_cache_manager = Mock(spec=CacheManager)

        # Mock the GraphQL client
        self.mock_graphql_client = Mock(spec=GraphQLClient)

        # Create PRManager and inject mock GraphQL client
        self.pr_manager = PRManager(self.mock_github_client, self.mock_cache_manager)
        self.pr_manager._graphql_client = self.mock_graphql_client

    def test_resolve_outdated_comments_success(self):
        """Test successful resolution of outdated comments."""
        # Mock permission check - success
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={
                "repository": {"viewerPermission": "WRITE"},
                "viewer": {"login": "testuser"}
            }
        )

        # Mock getting threads - return some outdated unresolved threads
        self.mock_graphql_client.get_pr_threads.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "id": "thread1",
                                    "isOutdated": True,
                                    "isResolved": False
                                },
                                {
                                    "id": "thread2",
                                    "isOutdated": True,
                                    "isResolved": False
                                },
                                {
                                    "id": "thread3",
                                    "isOutdated": False,
                                    "isResolved": False
                                },  # Not outdated
                                {
                                    "id": "thread4",
                                    "isOutdated": True,
                                    "isResolved": True
                                }   # Already resolved
                            ]
                        }
                    }
                }
            }
        )

        # Mock successful thread resolution
        self.mock_graphql_client.resolve_thread.return_value = GraphQLResult(
            data={"resolveReviewThread": {"thread": {"id": "thread1", "isResolved": True}}}
        )

        # Execute method
        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        # Verify results
        assert resolved_count == 2  # Only 2 outdated unresolved threads
        assert len(errors) == 0

        # Verify calls
        self.mock_graphql_client.check_permissions.assert_called_once_with("owner", "repo")
        self.mock_graphql_client.get_pr_threads.assert_called_once_with("owner", "repo", 123)

        # Should resolve thread1 and thread2 only
        assert self.mock_graphql_client.resolve_thread.call_count == 2
        resolve_calls = [call[0][0] for call in self.mock_graphql_client.resolve_thread.call_args_list]
        assert "thread1" in resolve_calls
        assert "thread2" in resolve_calls

    def test_resolve_outdated_comments_permission_denied(self):
        """Test resolve_outdated_comments with insufficient permissions."""
        # Mock permission check - insufficient permissions
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={
                "repository": {"viewerPermission": "READ"},
                "viewer": {"login": "testuser"}
            }
        )

        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        assert resolved_count == 0
        assert len(errors) == 1
        assert "Insufficient permissions" in errors[0]
        assert "READ" in errors[0]

        # Should not proceed to get threads
        self.mock_graphql_client.get_pr_threads.assert_not_called()

    def test_resolve_outdated_comments_permission_check_failed(self):
        """Test resolve_outdated_comments when permission check fails."""
        # Mock permission check failure
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            errors=[GraphQLError("API Error", "API_ERROR")]
        )

        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        assert resolved_count == 0
        assert len(errors) == 1
        assert "API Error" in errors[0]

    def test_resolve_outdated_comments_get_threads_failed(self):
        """Test resolve_outdated_comments when getting threads fails."""
        # Mock successful permission check
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        # Mock get threads failure
        self.mock_graphql_client.get_pr_threads.return_value = GraphQLResult(
            errors=[GraphQLError("PR not found", "NOT_FOUND")]
        )

        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        assert resolved_count == 0
        assert len(errors) == 1
        assert "PR not found" in errors[0]

    def test_resolve_outdated_comments_pr_not_found(self):
        """Test resolve_outdated_comments when PR is not found in response."""
        # Mock successful permission check
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        # Mock response without pullRequest data
        self.mock_graphql_client.get_pr_threads.return_value = GraphQLResult(
            data={"repository": {}}  # No pullRequest
        )

        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        assert resolved_count == 0
        assert len(errors) == 1
        assert "Pull request #123 not found" in errors[0]

    def test_resolve_outdated_comments_some_failures(self):
        """Test resolve_outdated_comments with some thread resolution failures."""
        # Mock successful permission check and thread retrieval
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        self.mock_graphql_client.get_pr_threads.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {"id": "thread1", "isOutdated": True, "isResolved": False},
                                {"id": "thread2", "isOutdated": True, "isResolved": False},
                            ]
                        }
                    }
                }
            }
        )

        # Mock mixed success/failure for thread resolution
        def mock_resolve_thread(thread_id):
            if thread_id == "thread1":
                return GraphQLResult(data={"success": True})
            else:
                return GraphQLResult(errors=[GraphQLError("Failed to resolve", "ERROR")])

        self.mock_graphql_client.resolve_thread.side_effect = mock_resolve_thread

        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        assert resolved_count == 1  # Only thread1 resolved
        assert len(errors) == 1
        assert "Failed to resolve thread thread2" in errors[0]

    def test_resolve_outdated_comments_no_outdated_threads(self):
        """Test resolve_outdated_comments when there are no outdated threads."""
        # Mock successful permission check
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        # Mock response with no outdated threads
        self.mock_graphql_client.get_pr_threads.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {"id": "thread1", "isOutdated": False, "isResolved": False},
                                {"id": "thread2", "isOutdated": True, "isResolved": True},
                            ]
                        }
                    }
                }
            }
        )

        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        assert resolved_count == 0
        assert len(errors) == 0

        # Should not call resolve_thread at all
        self.mock_graphql_client.resolve_thread.assert_not_called()

    def test_resolve_outdated_comments_invalid_input(self):
        """Test resolve_outdated_comments with invalid input."""
        # Test empty owner
        resolved_count, errors = self.pr_manager.resolve_outdated_comments("", "repo", 123)
        assert resolved_count == 0
        assert "Owner and repository name are required" in errors[0]

        # Test empty repo
        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "", 123)
        assert resolved_count == 0
        assert "Owner and repository name are required" in errors[0]

        # Test invalid PR number
        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 0)
        assert resolved_count == 0
        assert "PR number must be positive" in errors[0]

        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", -1)
        assert resolved_count == 0
        assert "PR number must be positive" in errors[0]

    def test_resolve_outdated_comments_thread_missing_id(self):
        """Test resolve_outdated_comments when thread is missing ID."""
        # Mock successful setup
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        self.mock_graphql_client.get_pr_threads.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {"isOutdated": True, "isResolved": False},  # Missing ID
                                {"id": "thread2", "isOutdated": True, "isResolved": False},
                            ]
                        }
                    }
                }
            }
        )

        self.mock_graphql_client.resolve_thread.return_value = GraphQLResult(data={"success": True})

        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        assert resolved_count == 1  # Only thread2 resolved
        assert len(errors) == 1
        assert "Thread missing ID" in errors[0]

    def test_resolve_outdated_comments_unexpected_exception(self):
        """Test resolve_outdated_comments with unexpected exception."""
        # Mock permission check to raise exception
        self.mock_graphql_client.check_permissions.side_effect = Exception("Unexpected error")

        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        assert resolved_count == 0
        assert len(errors) == 1
        assert "Unexpected error" in errors[0]


class TestAcceptAllSuggestions:
    """Test accept_all_suggestions method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_github_client = Mock(spec=GitHubClient)
        self.mock_cache_manager = Mock(spec=CacheManager)
        self.mock_graphql_client = Mock(spec=GraphQLClient)

        self.pr_manager = PRManager(self.mock_github_client, self.mock_cache_manager)
        self.pr_manager._graphql_client = self.mock_graphql_client

    def test_accept_all_suggestions_success(self):
        """Test successful acceptance of all suggestions."""
        # Mock permission check
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        # Mock getting suggestions - return some suggestions
        self.mock_graphql_client.get_pr_suggestions.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviews": {
                            "nodes": [
                                {
                                    "comments": {
                                        "nodes": [
                                            {
                                                "id": "comment1",
                                                "suggestions": {
                                                    "nodes": [
                                                        {"id": "suggestion1"},
                                                        {"id": "suggestion2"}
                                                    ]
                                                }
                                            },
                                            {
                                                "id": "comment2",
                                                "suggestions": {
                                                    "nodes": [
                                                        {"id": "suggestion3"}
                                                    ]
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        )

        # Mock successful suggestion acceptance
        self.mock_graphql_client.accept_suggestion.return_value = GraphQLResult(
            data={"acceptSuggestion": {"clientMutationId": "mutation123"}}
        )

        accepted_count, errors = self.pr_manager.accept_all_suggestions("owner", "repo", 123)

        assert accepted_count == 3  # 3 suggestions total
        assert len(errors) == 0

        # Verify calls
        self.mock_graphql_client.check_permissions.assert_called_once_with("owner", "repo")
        self.mock_graphql_client.get_pr_suggestions.assert_called_once_with("owner", "repo", 123)

        # Should accept all 3 suggestions
        assert self.mock_graphql_client.accept_suggestion.call_count == 3
        accept_calls = [call[0][0] for call in self.mock_graphql_client.accept_suggestion.call_args_list]
        assert "suggestion1" in accept_calls
        assert "suggestion2" in accept_calls
        assert "suggestion3" in accept_calls

    def test_accept_all_suggestions_permission_denied(self):
        """Test accept_all_suggestions with insufficient permissions."""
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "READ"}}
        )

        accepted_count, errors = self.pr_manager.accept_all_suggestions("owner", "repo", 123)

        assert accepted_count == 0
        assert len(errors) == 1
        assert "Insufficient permissions" in errors[0]

    def test_accept_all_suggestions_no_suggestions(self):
        """Test accept_all_suggestions when there are no suggestions."""
        # Mock successful permission check
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        # Mock response with no suggestions
        self.mock_graphql_client.get_pr_suggestions.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviews": {
                            "nodes": [
                                {
                                    "comments": {
                                        "nodes": [
                                            {
                                                "id": "comment1",
                                                "suggestions": {"nodes": []}  # No suggestions
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        )

        accepted_count, errors = self.pr_manager.accept_all_suggestions("owner", "repo", 123)

        assert accepted_count == 0
        assert len(errors) == 0

        # Should not call accept_suggestion
        self.mock_graphql_client.accept_suggestion.assert_not_called()

    def test_accept_all_suggestions_some_failures(self):
        """Test accept_all_suggestions with some acceptance failures."""
        # Mock successful setup
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        self.mock_graphql_client.get_pr_suggestions.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviews": {
                            "nodes": [
                                {
                                    "comments": {
                                        "nodes": [
                                            {
                                                "suggestions": {
                                                    "nodes": [
                                                        {"id": "suggestion1"},
                                                        {"id": "suggestion2"}
                                                    ]
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        )

        # Mock mixed success/failure
        def mock_accept_suggestion(suggestion_id):
            if suggestion_id == "suggestion1":
                return GraphQLResult(data={"success": True})
            else:
                return GraphQLResult(errors=[GraphQLError("Failed to accept", "ERROR")])

        self.mock_graphql_client.accept_suggestion.side_effect = mock_accept_suggestion

        accepted_count, errors = self.pr_manager.accept_all_suggestions("owner", "repo", 123)

        assert accepted_count == 1  # Only suggestion1 accepted
        assert len(errors) == 1
        assert "Failed to accept suggestion suggestion2" in errors[0]

    def test_accept_all_suggestions_invalid_input(self):
        """Test accept_all_suggestions with invalid input."""
        # Same validation as resolve_outdated_comments
        accepted_count, errors = self.pr_manager.accept_all_suggestions("", "repo", 123)
        assert accepted_count == 0
        assert "Owner and repository name are required" in errors[0]

        accepted_count, errors = self.pr_manager.accept_all_suggestions("owner", "repo", 0)
        assert accepted_count == 0
        assert "PR number must be positive" in errors[0]

    def test_accept_all_suggestions_suggestion_missing_id(self):
        """Test accept_all_suggestions when suggestion is missing ID."""
        # Mock successful setup
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        self.mock_graphql_client.get_pr_suggestions.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviews": {
                            "nodes": [
                                {
                                    "comments": {
                                        "nodes": [
                                            {
                                                "suggestions": {
                                                    "nodes": [
                                                        {},  # Missing ID
                                                        {"id": "suggestion2"}
                                                    ]
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        )

        self.mock_graphql_client.accept_suggestion.return_value = GraphQLResult(data={"success": True})

        accepted_count, errors = self.pr_manager.accept_all_suggestions("owner", "repo", 123)

        assert accepted_count == 1  # Only suggestion2 accepted
        assert len(errors) == 1
        assert "Suggestion missing ID" in errors[0]

    def test_accept_all_suggestions_get_suggestions_failed(self):
        """Test accept_all_suggestions when getting suggestions fails."""
        # Mock successful permission check
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        # Mock get suggestions failure
        self.mock_graphql_client.get_pr_suggestions.return_value = GraphQLResult(
            errors=[GraphQLError("API Error", "API_ERROR")]
        )

        accepted_count, errors = self.pr_manager.accept_all_suggestions("owner", "repo", 123)

        assert accepted_count == 0
        assert len(errors) == 1
        assert "API Error" in errors[0]

    def test_accept_all_suggestions_pr_not_found(self):
        """Test accept_all_suggestions when PR is not found in response."""
        # Mock successful permission check
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        # Mock response without pullRequest data
        self.mock_graphql_client.get_pr_suggestions.return_value = GraphQLResult(
            data={"repository": {}}  # No pullRequest
        )

        accepted_count, errors = self.pr_manager.accept_all_suggestions("owner", "repo", 123)

        assert accepted_count == 0
        assert len(errors) == 1
        assert "Pull request #123 not found" in errors[0]

    def test_accept_all_suggestions_no_data_response(self):
        """Test accept_all_suggestions when no data is returned."""
        # Mock successful permission check
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        # Mock response with no data
        self.mock_graphql_client.get_pr_suggestions.return_value = GraphQLResult(data=None)

        accepted_count, errors = self.pr_manager.accept_all_suggestions("owner", "repo", 123)

        assert accepted_count == 0
        assert len(errors) == 1
        assert "No data returned from GitHub API" in errors[0]


class TestPRManagerPhase4EdgeCases:
    """Test edge cases and boundary conditions for Phase 4 methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_github_client = Mock(spec=GitHubClient)
        self.mock_cache_manager = Mock(spec=CacheManager)
        self.mock_graphql_client = Mock(spec=GraphQLClient)

        self.pr_manager = PRManager(self.mock_github_client, self.mock_cache_manager)
        self.pr_manager._graphql_client = self.mock_graphql_client

    def test_different_permission_levels(self):
        """Test behavior with different permission levels."""
        test_cases = [
            ("READ", False),
            ("TRIAGE", False),
            ("WRITE", True),
            ("MAINTAIN", True),
            ("ADMIN", True),
            ("", False),
            (None, False),
        ]

        for permission, should_proceed in test_cases:
            self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
                data={"repository": {"viewerPermission": permission}}
            )

            resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

            if should_proceed:
                # Should proceed to get threads (which we haven't mocked for success)
                self.mock_graphql_client.get_pr_threads.assert_called()
            else:
                assert resolved_count == 0
                assert len(errors) == 1
                assert "Insufficient permissions" in errors[0]

            # Reset mock
            self.mock_graphql_client.reset_mock()

    def test_large_number_of_threads(self):
        """Test handling of large number of threads."""
        # Mock permission check
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        # Create many outdated threads
        large_thread_list = [
            {"id": f"thread{i}", "isOutdated": True, "isResolved": False}
            for i in range(100)
        ]

        self.mock_graphql_client.get_pr_threads.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": large_thread_list}
                    }
                }
            }
        )

        self.mock_graphql_client.resolve_thread.return_value = GraphQLResult(data={"success": True})

        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        assert resolved_count == 100
        assert len(errors) == 0
        assert self.mock_graphql_client.resolve_thread.call_count == 100

    def test_empty_thread_list(self):
        """Test handling of empty thread list."""
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        self.mock_graphql_client.get_pr_threads.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": []}
                    }
                }
            }
        )

        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        assert resolved_count == 0
        assert len(errors) == 0
        self.mock_graphql_client.resolve_thread.assert_not_called()

    def test_malformed_response_data(self):
        """Test handling of malformed response data."""
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        # Test with malformed thread data
        self.mock_graphql_client.get_pr_threads.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {"id": "thread1"},  # Missing isOutdated, isResolved
                                {"isOutdated": True},  # Missing id, isResolved
                                {"isResolved": False},  # Missing id, isOutdated
                                None,  # Null thread
                                {"id": "thread2", "isOutdated": True, "isResolved": False}  # Valid
                            ]
                        }
                    }
                }
            }
        )

        self.mock_graphql_client.resolve_thread.return_value = GraphQLResult(data={"success": True})

        # Should handle malformed data gracefully
        resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        # Only thread2 should be processed (others are malformed/missing data)
        assert resolved_count <= 1
        assert self.mock_graphql_client.resolve_thread.call_count <= 1

    @patch('gh_pr.core.pr_manager.logger')
    def test_logging_behavior(self, mock_logger):
        """Test that appropriate logging occurs."""
        self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        self.mock_graphql_client.get_pr_threads.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {"id": "thread1", "isOutdated": True, "isResolved": False}
                            ]
                        }
                    }
                }
            }
        )

        self.mock_graphql_client.resolve_thread.return_value = GraphQLResult(data={"success": True})

        self.pr_manager.resolve_outdated_comments("owner", "repo", 123)

        # Verify info logging occurred
        mock_logger.info.assert_called()
        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]

        # Should log about finding threads and completion
        assert any("Found" in call and "outdated unresolved threads" in call for call in info_calls)
        assert any("Resolved" in call and "outdated comments" in call for call in info_calls)

    def test_concurrent_method_calls(self):
        """Test thread safety of Phase 4 methods."""
        import threading
        import time

        results = []

        def make_request():
            # Mock successful operation
            self.mock_graphql_client.check_permissions.return_value = GraphQLResult(
                data={"repository": {"viewerPermission": "WRITE"}}
            )
            self.mock_graphql_client.get_pr_threads.return_value = GraphQLResult(
                data={"repository": {"pullRequest": {"reviewThreads": {"nodes": []}}}}
            )

            resolved_count, errors = self.pr_manager.resolve_outdated_comments("owner", "repo", 123)
            results.append((resolved_count, len(errors)))

        threads = [threading.Thread(target=make_request) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should complete successfully
        assert len(results) == 5
        assert all(resolved_count == 0 and error_count == 0 for resolved_count, error_count in results)
"""Integration tests for Phase 4 features - full workflow testing."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from gh_pr.core.batch import BatchOperations, BatchSummary
from gh_pr.core.graphql import GraphQLClient, GraphQLResult, GraphQLError
from gh_pr.core.github import GitHubClient
from gh_pr.core.pr_manager import PRManager
from gh_pr.utils.cache import CacheManager
from gh_pr.utils.export import ExportManager


class TestFullWorkflowIntegration:
    """Test complete workflows combining multiple Phase 4 components."""

    def setup_method(self):
        """Set up integration test fixtures."""
        # Create mock dependencies
        self.mock_github_client = Mock(spec=GitHubClient)
        self.mock_cache_manager = Mock(spec=CacheManager)

        # Set up GitHub client auth token access
        mock_requester = Mock()
        mock_auth = Mock()
        mock_auth.token = "test_integration_token"
        mock_requester._Requester__auth = mock_auth
        self.mock_github_client.github._Github__requester = mock_requester

        # Create main components
        self.pr_manager = PRManager(self.mock_github_client, self.mock_cache_manager)
        self.batch_ops = BatchOperations(self.pr_manager)
        self.export_manager = ExportManager()

    def test_batch_resolve_outdated_comments_with_export_workflow(self):
        """Test complete workflow: batch resolve comments → export results."""
        # Setup: Mock GraphQL responses for permission check and thread retrieval
        mock_graphql = Mock(spec=GraphQLClient)
        self.pr_manager._graphql_client = mock_graphql

        # Mock successful permission checks for all PRs
        mock_graphql.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        # Mock different thread scenarios for each PR
        def mock_get_pr_threads(owner, repo, pr_number):
            if pr_number == 1:
                # PR 1: 2 outdated unresolved threads
                return GraphQLResult(
                    data={
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "nodes": [
                                        {"id": "thread1_1", "isOutdated": True, "isResolved": False},
                                        {"id": "thread1_2", "isOutdated": True, "isResolved": False},
                                        {"id": "thread1_3", "isOutdated": False, "isResolved": False},  # Not outdated
                                    ]
                                }
                            }
                        }
                    }
                )
            elif pr_number == 2:
                # PR 2: 1 outdated unresolved thread
                return GraphQLResult(
                    data={
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "nodes": [
                                        {"id": "thread2_1", "isOutdated": True, "isResolved": False},
                                    ]
                                }
                            }
                        }
                    }
                )
            elif pr_number == 3:
                # PR 3: No outdated threads
                return GraphQLResult(
                    data={
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "nodes": [
                                        {"id": "thread3_1", "isOutdated": False, "isResolved": False},
                                    ]
                                }
                            }
                        }
                    }
                )

        mock_graphql.get_pr_threads.side_effect = mock_get_pr_threads

        # Mock thread resolution - some succeed, some fail
        def mock_resolve_thread(thread_id):
            if "thread1_1" in thread_id or "thread2_1" in thread_id:
                return GraphQLResult(data={"success": True})
            else:
                return GraphQLResult(errors=[GraphQLError("Resolution failed", "ERROR")])

        mock_graphql.resolve_thread.side_effect = mock_resolve_thread

        # Execute batch operation
        pr_identifiers = [
            ("owner1", "repo1", 1),
            ("owner2", "repo2", 2),
            ("owner3", "repo3", 3),
        ]

        summary = self.batch_ops.resolve_outdated_comments_batch(
            pr_identifiers, show_progress=False
        )

        # Verify batch results
        assert summary.total_prs == 3
        assert summary.successful == 3  # All PRs processed (even if some resolutions failed)
        assert summary.failed == 0
        assert summary.total_items_processed == 2  # 2 successfully resolved comments

        # Export the batch results
        batch_results = [
            {
                "pr_number": 1,
                "success": True,
                "result": 1,  # 1 successful, 1 failed resolution
                "errors": ["Failed to resolve thread thread1_2: Resolution failed"],
                "duration": 1.5
            },
            {
                "pr_number": 2,
                "success": True,
                "result": 1,  # 1 successful resolution
                "errors": [],
                "duration": 0.8
            },
            {
                "pr_number": 3,
                "success": True,
                "result": 0,  # No outdated threads
                "errors": [],
                "duration": 0.3
            }
        ]

        # Test export to different formats
        with tempfile.TemporaryDirectory() as temp_dir:
            # Change to temp directory for file operations
            original_cwd = Path.cwd()
            temp_path = Path(temp_dir)

            with patch('pathlib.Path.cwd', return_value=temp_path):
                # Export to markdown
                with patch('gh_pr.utils.export.datetime') as mock_datetime:
                    mock_datetime.now.return_value.strftime.return_value = "20240115_143022"

                    md_file = self.export_manager.export_batch_report(batch_results, "markdown")
                    json_file = self.export_manager.export_batch_report(batch_results, "json")

                    # Verify files would be created with correct names
                    assert "batch_report_20240115_143022.md" in md_file
                    assert "batch_report_20240115_143022.json" in json_file

    def test_batch_accept_suggestions_with_statistics_workflow(self):
        """Test workflow: batch accept suggestions → generate statistics report."""
        # Setup mock GraphQL client
        mock_graphql = Mock(spec=GraphQLClient)
        self.pr_manager._graphql_client = mock_graphql

        # Mock permission checks
        mock_graphql.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        # Mock different suggestion scenarios
        def mock_get_pr_suggestions(owner, repo, pr_number):
            if pr_number == 100:
                # PR 100: Multiple suggestions
                return GraphQLResult(
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
                                                                {"id": "suggestion100_1"},
                                                                {"id": "suggestion100_2"},
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
            elif pr_number == 200:
                # PR 200: Single suggestion
                return GraphQLResult(
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
                                                                {"id": "suggestion200_1"},
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
            else:
                # PR 300: No suggestions
                return GraphQLResult(
                    data={
                        "repository": {
                            "pullRequest": {
                                "reviews": {"nodes": []}
                            }
                        }
                    }
                )

        mock_graphql.get_pr_suggestions.side_effect = mock_get_pr_suggestions

        # Mock suggestion acceptance
        mock_graphql.accept_suggestion.return_value = GraphQLResult(
            data={"acceptSuggestion": {"clientMutationId": "success"}}
        )

        # Execute batch operation
        pr_identifiers = [
            ("owner", "repo", 100),
            ("owner", "repo", 200),
            ("owner", "repo", 300),
        ]

        summary = self.batch_ops.accept_suggestions_batch(
            pr_identifiers, show_progress=False
        )

        # Verify batch results
        assert summary.total_prs == 3
        assert summary.successful == 3
        assert summary.failed == 0
        assert summary.total_items_processed == 3  # 2 + 1 + 0 suggestions

        # Generate comprehensive PR data for statistics
        pr_data_for_stats = [
            {
                "number": 100,
                "state": "open",
                "author": "developer1",
                "comments": [
                    {
                        "path": "file1.py",
                        "comments": [
                            {"author": "reviewer1", "body": "Good work"},
                            {"author": "reviewer2", "body": "Consider optimization"}
                        ]
                    },
                    {
                        "path": "file2.py",
                        "comments": [
                            {"author": "reviewer1", "body": "Looks good"}
                        ]
                    }
                ]
            },
            {
                "number": 200,
                "state": "open",
                "author": "developer2",
                "comments": [
                    {
                        "path": "file1.py",
                        "comments": [
                            {"author": "reviewer3", "body": "Minor issue"}
                        ]
                    }
                ]
            },
            {
                "number": 300,
                "state": "closed",
                "author": "developer1",  # Same author as PR 100
                "comments": []  # No comments
            }
        ]

        # Export statistics report
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            with patch('pathlib.Path.cwd', return_value=temp_path):
                with patch('gh_pr.utils.export.datetime') as mock_datetime:
                    mock_datetime.now.return_value.strftime.return_value = "20240115_150000"

                    stats_file = self.export_manager.export_review_statistics(
                        pr_data_for_stats, "markdown"
                    )

                    assert "review_stats_20240115_150000.md" in stats_file

        # Verify statistics calculation
        stats = self.export_manager._calculate_review_statistics(pr_data_for_stats)
        assert stats["total_prs"] == 3
        assert stats["pr_states"]["open"] == 2
        assert stats["pr_states"]["closed"] == 1
        assert stats["comment_statistics"]["total_comments"] == 4  # 3 + 1 + 0
        assert stats["author_statistics"]["unique_pr_authors"] == 2  # developer1, developer2
        assert stats["author_statistics"]["most_active_pr_author"] == ("developer1", 2)

    def test_error_handling_across_components_workflow(self):
        """Test error handling and recovery across multiple components."""
        # Setup mock GraphQL client with mixed success/failure scenarios
        mock_graphql = Mock(spec=GraphQLClient)
        self.pr_manager._graphql_client = mock_graphql

        # Mock permission failures for some PRs
        def mock_check_permissions(owner, repo):
            if "restricted" in repo:
                return GraphQLResult(
                    errors=[GraphQLError("Access denied", "FORBIDDEN")]
                )
            elif "readonly" in repo:
                return GraphQLResult(
                    data={"repository": {"viewerPermission": "READ"}}
                )
            else:
                return GraphQLResult(
                    data={"repository": {"viewerPermission": "WRITE"}}
                )

        mock_graphql.check_permissions.side_effect = mock_check_permissions

        # Mock API failures for some operations
        def mock_get_pr_threads(owner, repo, pr_number):
            if "api_error" in repo:
                return GraphQLResult(
                    errors=[GraphQLError("API rate limit exceeded", "RATE_LIMITED")]
                )
            else:
                return GraphQLResult(
                    data={
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "nodes": [
                                        {"id": f"thread_{pr_number}", "isOutdated": True, "isResolved": False}
                                    ]
                                }
                            }
                        }
                    }
                )

        mock_graphql.get_pr_threads.side_effect = mock_get_pr_threads
        mock_graphql.resolve_thread.return_value = GraphQLResult(data={"success": True})

        # Test mixed success/failure scenarios
        pr_identifiers = [
            ("owner", "good_repo", 1),      # Should succeed
            ("owner", "restricted_repo", 2), # Permission error
            ("owner", "readonly_repo", 3),   # Insufficient permissions
            ("owner", "api_error_repo", 4),  # API error
            ("owner", "good_repo", 5),      # Should succeed
        ]

        summary = self.batch_ops.resolve_outdated_comments_batch(
            pr_identifiers, show_progress=False
        )

        # Verify mixed results
        assert summary.total_prs == 5
        assert summary.successful == 2  # PRs 1 and 5
        assert summary.failed == 3     # PRs 2, 3, and 4
        assert len(summary.errors) >= 3  # Should have error messages

        # Verify specific error types are captured
        error_text = " ".join(summary.errors)
        assert "Access denied" in error_text or "FORBIDDEN" in error_text
        assert "Insufficient permissions" in error_text
        assert "API rate limit exceeded" in error_text or "RATE_LIMITED" in error_text

        # Export results including errors
        batch_results = [
            {"pr_number": 1, "success": True, "result": 1, "errors": []},
            {"pr_number": 2, "success": False, "result": 0, "errors": ["Access denied"]},
            {"pr_number": 3, "success": False, "result": 0, "errors": ["Insufficient permissions"]},
            {"pr_number": 4, "success": False, "result": 0, "errors": ["API rate limit exceeded"]},
            {"pr_number": 5, "success": True, "result": 1, "errors": []},
        ]

        # Verify error export formats
        with tempfile.TemporaryDirectory():
            with patch('gh_pr.utils.export.datetime') as mock_datetime:
                mock_datetime.now.return_value.strftime.return_value = "20240115_160000"

                # Export should handle errors gracefully
                content = self.export_manager._export_batch_markdown(batch_results)
                assert "Access denied" in content
                assert "Insufficient permissions" in content
                assert "API rate limit exceeded" in content

                csv_content = self.export_manager._export_batch_csv(batch_results)
                assert "Access denied" in csv_content

    def test_concurrent_operations_integration(self):
        """Test concurrent operations across multiple components."""
        import threading
        import time

        # Setup mock GraphQL client for concurrent access
        mock_graphql = Mock(spec=GraphQLClient)
        self.pr_manager._graphql_client = mock_graphql

        # Thread-safe mock responses
        response_lock = threading.Lock()
        call_counts = {"permissions": 0, "threads": 0, "resolve": 0}

        def thread_safe_permission_check(owner, repo):
            with response_lock:
                call_counts["permissions"] += 1
                time.sleep(0.01)  # Simulate API delay
                return GraphQLResult(
                    data={"repository": {"viewerPermission": "WRITE"}}
                )

        def thread_safe_get_threads(owner, repo, pr_number):
            with response_lock:
                call_counts["threads"] += 1
                time.sleep(0.01)  # Simulate API delay
                return GraphQLResult(
                    data={
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "nodes": [
                                        {"id": f"thread_{pr_number}", "isOutdated": True, "isResolved": False}
                                    ]
                                }
                            }
                        }
                    }
                )

        def thread_safe_resolve_thread(thread_id):
            with response_lock:
                call_counts["resolve"] += 1
                time.sleep(0.01)  # Simulate API delay
                return GraphQLResult(data={"success": True})

        mock_graphql.check_permissions.side_effect = thread_safe_permission_check
        mock_graphql.get_pr_threads.side_effect = thread_safe_get_threads
        mock_graphql.resolve_thread.side_effect = thread_safe_resolve_thread

        # Configure batch operations for concurrency
        self.batch_ops.set_concurrency(3)
        self.batch_ops.set_rate_limit(0.0)  # No rate limiting for concurrent test

        # Create multiple PR identifiers
        pr_identifiers = [(f"owner{i}", f"repo{i}", i) for i in range(10)]

        # Execute batch operation
        start_time = time.time()
        summary = self.batch_ops.resolve_outdated_comments_batch(
            pr_identifiers, show_progress=False
        )
        end_time = time.time()

        # Verify all operations completed successfully
        assert summary.total_prs == 10
        assert summary.successful == 10
        assert summary.failed == 0
        assert summary.total_items_processed == 10

        # Verify all API calls were made
        assert call_counts["permissions"] == 10
        assert call_counts["threads"] == 10
        assert call_counts["resolve"] == 10

        # Verify concurrent execution was faster than sequential
        # (This is approximate due to threading overhead)
        sequential_time_estimate = 10 * 3 * 0.01  # 10 PRs * 3 API calls * 0.01s delay
        assert end_time - start_time < sequential_time_estimate

    def test_data_flow_integration(self):
        """Test complete data flow from input to final export."""
        # Setup comprehensive mock data
        mock_graphql = Mock(spec=GraphQLClient)
        self.pr_manager._graphql_client = mock_graphql

        # Mock GraphQL responses for full data flow
        mock_graphql.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        mock_graphql.get_pr_threads.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {"id": "thread_1", "isOutdated": True, "isResolved": False},
                                {"id": "thread_2", "isOutdated": True, "isResolved": False},
                            ]
                        }
                    }
                }
            }
        )

        mock_graphql.resolve_thread.return_value = GraphQLResult(data={"success": True})

        # Also mock get_pr_data_batch dependencies
        self.mock_github_client.get_pr_data = Mock(return_value={
            "number": 123,
            "title": "Test PR",
            "author": "developer1",
            "state": "open"
        })

        self.mock_github_client.get_pr_comments = Mock(return_value=[
            {
                "path": "file1.py",
                "line": 42,
                "comments": [
                    {"author": "reviewer1", "body": "Good change"},
                    {"author": "reviewer2", "body": "Consider edge cases"}
                ]
            }
        ])

        # Execute complete workflow
        pr_identifiers = [("owner", "repo", 123)]

        # Step 1: Resolve outdated comments
        resolve_summary = self.batch_ops.resolve_outdated_comments_batch(
            pr_identifiers, show_progress=False
        )

        # Step 2: Get PR data for analysis
        pr_data_results = self.batch_ops.get_pr_data_batch(
            pr_identifiers, show_progress=False
        )

        # Step 3: Generate comprehensive report
        combined_data = {
            "resolve_summary": {
                "total_prs": resolve_summary.total_prs,
                "successful": resolve_summary.successful,
                "failed": resolve_summary.failed,
                "items_processed": resolve_summary.total_items_processed
            },
            "pr_data": [result.result for result in pr_data_results if result.success]
        }

        # Verify data flow integrity
        assert resolve_summary.total_prs == 1
        assert resolve_summary.successful == 1
        assert resolve_summary.total_items_processed == 2  # 2 threads resolved

        assert len(pr_data_results) == 1
        assert pr_data_results[0].success is True
        assert pr_data_results[0].result["pr_data"]["number"] == 123

        # Step 4: Export combined results
        with tempfile.TemporaryDirectory():
            with patch('gh_pr.utils.export.datetime') as mock_datetime:
                mock_datetime.now.return_value.strftime.return_value = "20240115_170000"

                # Export as JSON for easy verification
                export_data = {
                    "workflow_type": "complete_integration",
                    "timestamp": "2024-01-15T17:00:00Z",
                    "summary": combined_data
                }

                json_content = json.dumps(export_data, indent=2)

                # Verify complete data flow
                assert "resolve_summary" in json_content
                assert "pr_data" in json_content
                assert '"total_prs": 1' in json_content
                assert '"items_processed": 2' in json_content
                assert '"number": 123' in json_content

    def test_performance_and_scalability_integration(self):
        """Test performance characteristics with larger datasets."""
        # Setup mocks for performance testing
        mock_graphql = Mock(spec=GraphQLClient)
        self.pr_manager._graphql_client = mock_graphql

        # Mock fast responses
        mock_graphql.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        mock_graphql.get_pr_threads.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {"id": "thread_1", "isOutdated": True, "isResolved": False}
                            ]
                        }
                    }
                }
            }
        )

        mock_graphql.resolve_thread.return_value = GraphQLResult(data={"success": True})

        # Test with larger dataset
        num_prs = 50
        pr_identifiers = [(f"owner{i}", f"repo{i}", i) for i in range(num_prs)]

        # Configure for performance
        self.batch_ops.set_concurrency(5)
        self.batch_ops.set_rate_limit(0.0)

        # Execute and measure
        start_time = time.time()
        summary = self.batch_ops.resolve_outdated_comments_batch(
            pr_identifiers, show_progress=False
        )
        end_time = time.time()

        # Verify scalability
        assert summary.total_prs == num_prs
        assert summary.successful == num_prs
        assert summary.total_items_processed == num_prs

        # Should complete within reasonable time
        execution_time = end_time - start_time
        assert execution_time < 5.0  # Should complete within 5 seconds

        # Test export performance with large dataset
        large_batch_results = [
            {
                "pr_number": i,
                "success": True,
                "result": 1,
                "errors": [],
                "duration": 0.1
            }
            for i in range(num_prs)
        ]

        # Export should handle large datasets efficiently
        with tempfile.TemporaryDirectory():
            export_start = time.time()

            with patch('gh_pr.utils.export.datetime') as mock_datetime:
                mock_datetime.now.return_value.strftime.return_value = "20240115_180000"

                # Test markdown export with large dataset
                content = self.export_manager._export_batch_markdown(large_batch_results)

            export_end = time.time()

            # Should export efficiently
            export_time = export_end - export_start
            assert export_time < 2.0  # Should export within 2 seconds

            # Verify content completeness
            assert f"**Total PRs Processed:** {num_prs}" in content
            assert f"**Successful Operations:** {num_prs}" in content


class TestPhase4ComponentInteraction:
    """Test interactions between different Phase 4 components."""

    def setup_method(self):
        """Set up component interaction test fixtures."""
        self.mock_github_client = Mock(spec=GitHubClient)
        self.mock_cache_manager = Mock(spec=CacheManager)

        # Setup auth token
        mock_requester = Mock()
        mock_auth = Mock()
        mock_auth.token = "interaction_test_token"
        mock_requester._Requester__auth = mock_auth
        self.mock_github_client.github._Github__requester = mock_requester

        self.pr_manager = PRManager(self.mock_github_client, self.mock_cache_manager)
        self.batch_ops = BatchOperations(self.pr_manager)
        self.export_manager = ExportManager()

    def test_graphql_client_sharing(self):
        """Test that GraphQL client is properly shared across operations."""
        # Access GraphQL client through PRManager
        graphql_client1 = self.pr_manager.graphql

        # Create another PRManager instance with same GitHub client
        pr_manager2 = PRManager(self.mock_github_client, self.mock_cache_manager)
        graphql_client2 = pr_manager2.graphql

        # Should create separate instances but with same token
        assert graphql_client1 is not graphql_client2
        assert graphql_client1.token == graphql_client2.token == "interaction_test_token"

        # Test that both can be used independently
        assert isinstance(graphql_client1, GraphQLClient)
        assert isinstance(graphql_client2, GraphQLClient)

    def test_batch_operations_error_aggregation(self):
        """Test how BatchOperations aggregates errors from different sources."""
        # Setup mock GraphQL client with various error scenarios
        mock_graphql = Mock(spec=GraphQLClient)
        self.pr_manager._graphql_client = mock_graphql

        # Simulate different types of errors
        def mock_check_permissions(owner, repo):
            if repo == "forbidden_repo":
                return GraphQLResult(errors=[GraphQLError("Access forbidden", "FORBIDDEN")])
            else:
                return GraphQLResult(data={"repository": {"viewerPermission": "WRITE"}})

        def mock_get_pr_threads(owner, repo, pr_number):
            if pr_number == 2:
                return GraphQLResult(errors=[GraphQLError("PR not found", "NOT_FOUND")])
            else:
                return GraphQLResult(
                    data={
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "nodes": [
                                        {"id": f"thread_{pr_number}", "isOutdated": True, "isResolved": False}
                                    ]
                                }
                            }
                        }
                    }
                )

        def mock_resolve_thread(thread_id):
            if "thread_3" in thread_id:
                return GraphQLResult(errors=[GraphQLError("Resolution failed", "RESOLUTION_ERROR")])
            else:
                return GraphQLResult(data={"success": True})

        mock_graphql.check_permissions.side_effect = mock_check_permissions
        mock_graphql.get_pr_threads.side_effect = mock_get_pr_threads
        mock_graphql.resolve_thread.side_effect = mock_resolve_thread

        # Execute batch operation with mixed errors
        pr_identifiers = [
            ("owner", "good_repo", 1),      # Should succeed
            ("owner", "good_repo", 2),      # PR not found error
            ("owner", "good_repo", 3),      # Thread resolution error
            ("owner", "forbidden_repo", 4), # Permission error
        ]

        summary = self.batch_ops.resolve_outdated_comments_batch(
            pr_identifiers, show_progress=False
        )

        # Verify error aggregation
        assert summary.total_prs == 4
        assert summary.successful == 1  # Only PR 1 fully succeeds
        assert summary.failed == 3
        assert len(summary.errors) >= 3

        # Check that different error types are captured
        all_errors = " ".join(summary.errors)
        assert "Access forbidden" in all_errors
        assert "PR not found" in all_errors
        assert "Resolution failed" in all_errors

    def test_export_integration_with_batch_results(self):
        """Test ExportManager integration with BatchOperations results."""
        # Create realistic batch results
        batch_results = [
            {
                "pr_number": 101,
                "success": True,
                "result": 3,
                "errors": [],
                "duration": 1.2
            },
            {
                "pr_number": 102,
                "success": False,
                "result": 0,
                "errors": ["Permission denied", "API timeout"],
                "duration": 0.8
            },
            {
                "pr_number": 103,
                "success": True,
                "result": 1,
                "errors": [],
                "duration": 0.5
            }
        ]

        # Test all export formats
        with tempfile.TemporaryDirectory():
            with patch('gh_pr.utils.export.datetime') as mock_datetime:
                mock_datetime.now.return_value.strftime.return_value = "20240115_190000"

                # Test markdown export
                md_content = self.export_manager._export_batch_markdown(batch_results)
                assert "### PR #101" in md_content
                assert "### PR #102" in md_content
                assert "### PR #103" in md_content
                assert "Permission denied" in md_content
                assert "API timeout" in md_content

                # Test JSON export
                json_content = self.export_manager._export_batch_json(batch_results)
                json_data = json.loads(json_content)
                assert json_data["summary"]["total_prs"] == 3
                assert json_data["summary"]["successful"] == 2
                assert json_data["summary"]["failed"] == 1
                assert json_data["summary"]["total_items"] == 4  # 3 + 0 + 1

                # Test CSV export
                csv_content = self.export_manager._export_batch_csv(batch_results)
                lines = csv_content.strip().split('\n')
                assert len(lines) == 4  # Header + 3 data rows
                assert "101,Yes,3,1.20,0," in csv_content
                assert "102,No,0,0.80,2,Permission denied" in csv_content

    def test_memory_management_across_components(self):
        """Test memory efficiency across component interactions."""
        # Create a scenario that could potentially use significant memory
        num_prs = 100
        large_pr_identifiers = [(f"owner{i}", f"repo{i}", i) for i in range(num_prs)]

        # Setup minimal mocks
        mock_graphql = Mock(spec=GraphQLClient)
        self.pr_manager._graphql_client = mock_graphql

        mock_graphql.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        mock_graphql.get_pr_threads.return_value = GraphQLResult(
            data={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {"nodes": []}  # No threads to avoid deep processing
                    }
                }
            }
        )

        # Process large batch
        summary = self.batch_ops.resolve_outdated_comments_batch(
            large_pr_identifiers, show_progress=False
        )

        # Verify processing completed without memory issues
        assert summary.total_prs == num_prs
        assert summary.successful == num_prs

        # Create large export data
        large_batch_results = [
            {
                "pr_number": i,
                "success": True,
                "result": 0,
                "errors": [],
                "duration": 0.1
            }
            for i in range(num_prs)
        ]

        # Test that export can handle large datasets
        with tempfile.TemporaryDirectory():
            md_content = self.export_manager._export_batch_markdown(large_batch_results)

            # Verify content was generated without memory errors
            assert f"**Total PRs Processed:** {num_prs}" in md_content
            assert "### PR #0" in md_content
            assert f"### PR #{num_prs-1}" in md_content

    def test_configuration_consistency(self):
        """Test that configuration is consistent across components."""
        # Test rate limiting configuration
        original_rate_limit = self.batch_ops.rate_limit
        self.batch_ops.set_rate_limit(2.5)
        assert self.batch_ops.rate_limit == 2.5

        # Test concurrency configuration
        original_concurrency = self.batch_ops.max_concurrent
        self.batch_ops.set_concurrency(8)
        assert self.batch_ops.max_concurrent == 8

        # Verify configurations persist across operations
        mock_graphql = Mock(spec=GraphQLClient)
        self.pr_manager._graphql_client = mock_graphql

        mock_graphql.check_permissions.return_value = GraphQLResult(
            data={"repository": {"viewerPermission": "WRITE"}}
        )

        mock_graphql.get_pr_threads.return_value = GraphQLResult(
            data={"repository": {"pullRequest": {"reviewThreads": {"nodes": []}}}}
        )

        # Run operation
        self.batch_ops.resolve_outdated_comments_batch([("owner", "repo", 1)], show_progress=False)

        # Verify configurations unchanged
        assert self.batch_ops.rate_limit == 2.5
        assert self.batch_ops.max_concurrent == 8

        # Reset for cleanup
        self.batch_ops.set_rate_limit(original_rate_limit)
        self.batch_ops.set_concurrency(original_concurrency)
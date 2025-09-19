"""Unit tests for ExportManager Phase 4 methods."""

import csv
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

import pytest

from gh_pr.utils.export import ExportManager


class TestExportManager:
    """Test ExportManager basic functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.export_manager = ExportManager()

    def test_initialization(self):
        """Test ExportManager initialization."""
        assert isinstance(self.export_manager, ExportManager)

    def test_get_extension(self):
        """Test _get_extension method."""
        assert self.export_manager._get_extension("markdown") == "md"
        assert self.export_manager._get_extension("csv") == "csv"
        assert self.export_manager._get_extension("json") == "json"
        assert self.export_manager._get_extension("unknown") == "txt"

    @patch('gh_pr.utils.export.datetime')
    def test_filename_generation(self, mock_datetime):
        """Test that filenames include timestamps."""
        mock_datetime.now.return_value.strftime.return_value = "20240115_143022"

        # Test with mocked file operations
        with patch('pathlib.Path.write_text') as mock_write:
            with patch.object(self.export_manager, '_export_markdown', return_value="test content"):
                filename = self.export_manager.export(
                    {"number": 123}, [], "markdown"
                )

                assert "pr_123_20240115_143022.md" in filename
                mock_write.assert_called_once_with("test content")


class TestExportBatchReport:
    """Test export_batch_report method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.export_manager = ExportManager()

    def test_export_batch_report_empty_results(self):
        """Test export_batch_report with empty results."""
        with pytest.raises(ValueError, match="No batch results provided"):
            self.export_manager.export_batch_report([])

    @patch('pathlib.Path.write_text')
    @patch('gh_pr.utils.export.datetime')
    def test_export_batch_report_markdown(self, mock_datetime, mock_write):
        """Test export_batch_report with markdown format."""
        mock_datetime.now.return_value.strftime.return_value = "20240115_143022"

        batch_results = [
            {
                "pr_number": 123,
                "success": True,
                "result": 5,
                "errors": [],
                "duration": 1.5
            },
            {
                "pr_number": 124,
                "success": False,
                "result": 0,
                "errors": ["Permission denied", "API error"],
                "duration": 0.8
            }
        ]

        filename = self.export_manager.export_batch_report(batch_results, "markdown")

        assert "batch_report_20240115_143022.md" in filename
        mock_write.assert_called_once()

        # Check content structure
        content = mock_write.call_args[0][0]
        assert "# Batch Operation Report" in content
        assert "**Total PRs Processed:** 2" in content
        assert "**Successful Operations:** 1" in content
        assert "**Failed Operations:** 1" in content
        assert "50.0%" in content  # Success rate
        assert "### PR #123" in content
        assert "### PR #124" in content
        assert "✅ Success" in content
        assert "❌ Failed" in content
        assert "Permission denied" in content
        assert "API error" in content

    @patch('pathlib.Path.write_text')
    @patch('gh_pr.utils.export.datetime')
    def test_export_batch_report_json(self, mock_datetime, mock_write):
        """Test export_batch_report with JSON format."""
        mock_datetime.now.return_value.strftime.return_value = "20240115_143022"

        batch_results = [
            {
                "pr_number": 123,
                "success": True,
                "result": 3,
                "errors": []
            }
        ]

        filename = self.export_manager.export_batch_report(batch_results, "json")

        assert "batch_report_20240115_143022.json" in filename
        mock_write.assert_called_once()

        # Parse and validate JSON content
        content = mock_write.call_args[0][0]
        data = json.loads(content)

        assert data["report_type"] == "batch_operation"
        assert "generated_at" in data
        assert data["summary"]["total_prs"] == 1
        assert data["summary"]["successful"] == 1
        assert data["summary"]["failed"] == 0
        assert data["summary"]["total_items"] == 3
        assert data["results"] == batch_results

    @patch('builtins.open', new_callable=mock_open)
    @patch('gh_pr.utils.export.datetime')
    def test_export_batch_report_csv(self, mock_datetime, mock_file):
        """Test export_batch_report with CSV format."""
        mock_datetime.now.return_value.strftime.return_value = "20240115_143022"

        batch_results = [
            {
                "pr_number": 123,
                "success": True,
                "result": 5,
                "duration": 1.5,
                "errors": []
            },
            {
                "pr_number": 124,
                "success": False,
                "result": 0,
                "duration": 0.8,
                "errors": ["Error 1", "Error 2"]
            }
        ]

        filename = self.export_manager.export_batch_report(batch_results, "csv")

        assert "batch_report_20240115_143022.csv" in filename
        mock_file.assert_called_once()

        # Check that CSV was written
        handle = mock_file.return_value.__enter__.return_value
        write_calls = [call[0][0] for call in handle.write.call_args_list]
        csv_content = "".join(write_calls)

        # Verify CSV structure
        assert "PR Number,Success,Items Processed,Duration (s),Error Count,First Error" in csv_content
        assert "123,Yes,5,1.50,0," in csv_content
        assert "124,No,0,0.80,2,Error 1" in csv_content

    def test_export_batch_report_invalid_format(self):
        """Test export_batch_report with invalid format."""
        batch_results = [{"pr_number": 123, "success": True}]

        with pytest.raises(ValueError, match="Unsupported format: invalid"):
            self.export_manager.export_batch_report(batch_results, "invalid")

    def test_export_batch_markdown_detailed(self):
        """Test detailed markdown export content."""
        batch_results = [
            {
                "pr_number": 123,
                "success": True,
                "result": 5,
                "errors": []
            },
            {
                "pr_number": 124,
                "success": False,
                "result": 2,
                "errors": ["Error 1", "Error 2"]
            }
        ]

        with patch('gh_pr.utils.export.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2024-01-15 14:30:22"

            content = self.export_manager._export_batch_markdown(batch_results)

            # Verify detailed content
            assert "**Generated:** 2024-01-15 14:30:22" in content
            assert "**Total PRs Processed:** 2" in content
            assert "**Successful Operations:** 1" in content
            assert "**Failed Operations:** 1" in content
            assert "**Success Rate:** 50.0%" in content
            assert "**Total Items Processed:** 5" in content  # Only successful int results

            # Check individual PR sections
            assert "### PR #123" in content
            assert "### PR #124" in content
            assert "**Items Processed:** 5" in content
            assert "**Items Processed:** 2" in content
            assert "**Errors:**" in content
            assert "- Error 1" in content
            assert "- Error 2" in content

    def test_export_batch_csv_detailed(self):
        """Test detailed CSV export content."""
        batch_results = [
            {
                "pr_number": 123,
                "success": True,
                "result": 5,
                "duration": 1.234,
                "errors": []
            },
            {
                "pr_number": 124,
                "success": False,
                "result": 0,
                "duration": 0.567,
                "errors": ["First error", "Second error"]
            }
        ]

        content = self.export_manager._export_batch_csv(batch_results)

        # Parse CSV to verify content
        lines = content.strip().split('\n')
        assert len(lines) == 3  # Header + 2 data rows

        # Check header
        assert lines[0] == "PR Number,Success,Items Processed,Duration (s),Error Count,First Error"

        # Check first row
        assert lines[1] == "123,Yes,5,1.23,0,"

        # Check second row
        assert lines[2] == "124,No,0,0.57,2,First error"


class TestExportReviewStatistics:
    """Test export_review_statistics method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.export_manager = ExportManager()

    def test_export_review_statistics_empty_data(self):
        """Test export_review_statistics with empty data."""
        with pytest.raises(ValueError, match="No PR data provided"):
            self.export_manager.export_review_statistics([])

    @patch('pathlib.Path.write_text')
    @patch('gh_pr.utils.export.datetime')
    def test_export_review_statistics_markdown(self, mock_datetime, mock_write):
        """Test export_review_statistics with markdown format."""
        mock_datetime.now.return_value.strftime.return_value = "20240115_143022"

        pr_data_list = [
            {
                "number": 123,
                "state": "open",
                "author": "user1",
                "comments": [
                    {
                        "path": "file1.py",
                        "comments": [
                            {"author": "reviewer1", "body": "Comment 1"},
                            {"author": "reviewer2", "body": "Comment 2"}
                        ]
                    }
                ]
            },
            {
                "number": 124,
                "state": "closed",
                "author": "user2",
                "comments": [
                    {
                        "path": "file2.py",
                        "comments": [
                            {"author": "reviewer1", "body": "Comment 3"}
                        ]
                    }
                ]
            }
        ]

        filename = self.export_manager.export_review_statistics(pr_data_list, "markdown")

        assert "review_stats_20240115_143022.md" in filename
        mock_write.assert_called_once()

        content = mock_write.call_args[0][0]
        assert "# Review Statistics Report" in content
        assert "**Total PRs:** 2" in content
        assert "**Open:** 1" in content
        assert "**Closed:** 1" in content
        assert "**Total Comments:** 3" in content
        assert "**Average per PR:** 1.5" in content
        assert "**Unique PR Authors:** 2" in content
        assert "**Files with Comments:** 2" in content

    @patch('pathlib.Path.write_text')
    @patch('gh_pr.utils.export.datetime')
    def test_export_review_statistics_json(self, mock_datetime, mock_write):
        """Test export_review_statistics with JSON format."""
        mock_datetime.now.return_value.strftime.return_value = "20240115_143022"

        pr_data_list = [
            {
                "number": 123,
                "state": "open",
                "author": "user1",
                "comments": []
            }
        ]

        filename = self.export_manager.export_review_statistics(pr_data_list, "json")

        assert "review_stats_20240115_143022.json" in filename
        mock_write.assert_called_once()

        content = mock_write.call_args[0][0]
        data = json.loads(content)

        assert data["total_prs"] == 1
        assert data["pr_states"]["open"] == 1
        assert data["comment_statistics"]["total_comments"] == 0
        assert data["author_statistics"]["unique_pr_authors"] == 1

    def test_calculate_review_statistics_comprehensive(self):
        """Test _calculate_review_statistics with comprehensive data."""
        pr_data_list = [
            {
                "number": 123,
                "state": "open",
                "author": "user1",
                "comments": [
                    {
                        "path": "file1.py",
                        "comments": [
                            {"author": "reviewer1", "body": "Comment 1"},
                            {"author": "reviewer2", "body": "Comment 2"}
                        ]
                    },
                    {
                        "path": "file2.py",
                        "comments": [
                            {"author": "reviewer1", "body": "Comment 3"}
                        ]
                    }
                ]
            },
            {
                "number": 124,
                "state": "closed",
                "author": "user1",  # Same author as PR 123
                "comments": [
                    {
                        "path": "file1.py",  # Same file as in PR 123
                        "comments": [
                            {"author": "reviewer3", "body": "Comment 4"}
                        ]
                    }
                ]
            },
            {
                "number": 125,
                "state": "open",
                "author": "user2",
                "comments": []  # No comments
            }
        ]

        stats = self.export_manager._calculate_review_statistics(pr_data_list)

        # Basic counts
        assert stats["total_prs"] == 3

        # PR states
        assert stats["pr_states"]["open"] == 2
        assert stats["pr_states"]["closed"] == 1

        # Comment statistics
        assert stats["comment_statistics"]["total_comments"] == 4
        assert stats["comment_statistics"]["average_comments_per_pr"] == 4/3  # 4 comments across 3 PRs
        assert stats["comment_statistics"]["median_comments_per_pr"] == 1.0  # [0, 1, 3] -> median is 1
        assert stats["comment_statistics"]["max_comments_per_pr"] == 3
        assert stats["comment_statistics"]["min_comments_per_pr"] == 0

        # Author statistics
        assert stats["author_statistics"]["unique_pr_authors"] == 2  # user1, user2
        assert stats["author_statistics"]["unique_comment_authors"] == 3  # reviewer1, reviewer2, reviewer3
        assert stats["author_statistics"]["most_active_pr_author"] == ("user1", 2)  # user1 has 2 PRs
        assert stats["author_statistics"]["most_active_commenter"] == ("reviewer1", 2)  # reviewer1 has 2 comments

        # File statistics
        assert stats["file_statistics"]["unique_files_commented"] == 2  # file1.py, file2.py
        assert "file1.py" in stats["file_statistics"]["files_list"]
        assert "file2.py" in stats["file_statistics"]["files_list"]

    def test_calculate_review_statistics_edge_cases(self):
        """Test _calculate_review_statistics with edge cases."""
        # Test with missing data
        pr_data_list = [
            {
                "number": 123,
                # Missing state
                # Missing author
                # Missing comments
            },
            {
                "number": 124,
                "state": "draft",
                "author": "",  # Empty author
                "comments": [
                    {
                        # Missing path
                        "comments": [
                            {
                                # Missing author
                                "body": "Comment"
                            }
                        ]
                    }
                ]
            }
        ]

        stats = self.export_manager._calculate_review_statistics(pr_data_list)

        assert stats["total_prs"] == 2
        assert stats["pr_states"]["unknown"] == 1  # Missing state
        assert stats["pr_states"]["draft"] == 1

        # Should handle missing authors gracefully
        assert "unknown" in [author for author, _ in [stats["author_statistics"]["most_active_pr_author"]]]

    def test_export_stats_markdown_detailed(self):
        """Test detailed markdown statistics export."""
        stats = {
            "total_prs": 5,
            "pr_states": {"open": 3, "closed": 2},
            "comment_statistics": {
                "total_comments": 15,
                "average_comments_per_pr": 3.0,
                "median_comments_per_pr": 2.5,
                "max_comments_per_pr": 7,
                "min_comments_per_pr": 0
            },
            "author_statistics": {
                "unique_pr_authors": 3,
                "unique_comment_authors": 5,
                "most_active_pr_author": ("user1", 3),
                "most_active_commenter": ("reviewer1", 8)
            },
            "file_statistics": {
                "unique_files_commented": 25,
                "files_list": [f"file{i}.py" for i in range(25)]  # 25 files
            }
        }

        with patch('gh_pr.utils.export.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2024-01-15 14:30:22"

            content = self.export_manager._export_stats_markdown(stats)

            # Check main sections
            assert "# Review Statistics Report" in content
            assert "**Generated:** 2024-01-15 14:30:22" in content
            assert "**Total PRs:** 5" in content

            # PR states
            assert "**Open:** 3" in content
            assert "**Closed:** 2" in content

            # Comment statistics
            assert "**Total Comments:** 15" in content
            assert "**Average per PR:** 3.0" in content
            assert "**Median per PR:** 2.5" in content
            assert "**Max per PR:** 7" in content
            assert "**Min per PR:** 0" in content

            # Author statistics
            assert "**Unique PR Authors:** 3" in content
            assert "**Unique Comment Authors:** 5" in content
            assert "**Most Active PR Author:** @user1 (3 PRs)" in content
            assert "**Most Active Commenter:** @reviewer1 (8 comments)" in content

            # File statistics
            assert "**Files with Comments:** 25" in content
            assert "### Files Commented On:" in content
            assert "`file0.py`" in content
            assert "`file19.py`" in content  # Should show first 20
            assert "and 5 more files" in content  # Should indicate more files

    def test_export_stats_csv_detailed(self):
        """Test detailed CSV statistics export."""
        stats = {
            "total_prs": 3,
            "pr_states": {"open": 2, "closed": 1},
            "comment_statistics": {
                "total_comments": 10,
                "average_comments_per_pr": 3.3,
                "median_comments_per_pr": 3.0
            },
            "author_statistics": {
                "unique_pr_authors": 2,
                "unique_comment_authors": 3
            }
        }

        content = self.export_manager._export_stats_csv(stats)

        # Parse CSV
        lines = content.strip().split('\n')
        assert lines[0] == "Metric,Value"

        # Check that key metrics are included
        csv_content = content
        assert "Total PRs,3" in csv_content
        assert "PRs open,2" in csv_content
        assert "PRs closed,1" in csv_content
        assert "Total Comments,10" in csv_content
        assert "Average Comments per PR,3.3" in csv_content
        assert "Median Comments per PR,3.0" in csv_content
        assert "Unique PR Authors,2" in csv_content
        assert "Unique Comment Authors,3" in csv_content


class TestExportEnhancedCSV:
    """Test export_enhanced_csv method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.export_manager = ExportManager()

    @patch('builtins.open', new_callable=mock_open)
    @patch('gh_pr.utils.export.datetime')
    def test_export_enhanced_csv_all_fields(self, mock_datetime, mock_file):
        """Test export_enhanced_csv with all fields."""
        mock_datetime.now.return_value.strftime.return_value = "20240115_143022"

        pr_data = {
            "number": 123,
            "title": "Test PR",
            "author": "author1",
            "state": "open"
        }

        comments = [
            {
                "path": "file1.py",
                "line": 42,
                "id": "thread1",
                "is_resolved": True,
                "is_outdated": False,
                "comments": [
                    {
                        "id": "comment1",
                        "author": "reviewer1",
                        "body": "This looks good",
                        "type": "review",
                        "created_at": "2024-01-15T10:00:00Z",
                        "updated_at": "2024-01-15T10:05:00Z",
                        "in_reply_to_id": None,
                        "suggestions": ["suggestion1"],
                        "reactions": [{"type": "thumbs_up"}],
                        "author_association": "COLLABORATOR"
                    }
                ]
            }
        ]

        filename = self.export_manager.export_enhanced_csv(pr_data, comments, include_all_fields=True)

        assert "pr_123_enhanced_20240115_143022.csv" in filename
        mock_file.assert_called_once()

        # Check that enhanced CSV was written
        handle = mock_file.return_value.__enter__.return_value
        write_calls = [call[0][0] for call in handle.write.call_args_list]
        csv_content = "".join(write_calls)

        # Verify enhanced CSV header
        expected_header = (
            "PR Number,PR Title,PR Author,PR State,File Path,Line Number,"
            "Comment ID,Comment Author,Comment Body,Comment Type,"
            "Is Resolved,Is Outdated,Created At,Updated At,Thread ID,"
            "In Reply To,Suggestions Count,Reactions Count,Author Association"
        )
        assert expected_header in csv_content

        # Verify data row
        assert "123,Test PR,author1,open,file1.py,42,comment1,reviewer1" in csv_content
        assert "This looks good,review,Yes,No" in csv_content
        assert "2024-01-15T10:00:00Z,2024-01-15T10:05:00Z,thread1" in csv_content
        assert ",1,1,COLLABORATOR" in csv_content

    @patch('builtins.open', new_callable=mock_open)
    @patch('gh_pr.utils.export.datetime')
    def test_export_enhanced_csv_basic_fields(self, mock_datetime, mock_file):
        """Test export_enhanced_csv with basic fields only."""
        mock_datetime.now.return_value.strftime.return_value = "20240115_143022"

        pr_data = {"number": 123}
        comments = []

        # Test with include_all_fields=False
        with patch.object(self.export_manager, '_export_csv', return_value="basic csv content") as mock_basic:
            filename = self.export_manager.export_enhanced_csv(pr_data, comments, include_all_fields=False)

            mock_basic.assert_called_once_with(pr_data, comments)

    def test_export_enhanced_csv_all_fields_detailed(self):
        """Test detailed _export_enhanced_csv_all_fields method."""
        pr_data = {
            "number": 456,
            "title": "Another PR",
            "author": "author2",
            "state": "closed"
        }

        comments = [
            {
                "path": "file2.py",
                "line": 10,
                "id": "thread2",
                "is_resolved": False,
                "is_outdated": True,
                "comments": [
                    {
                        "id": "comment2",
                        "author": "reviewer2",
                        "body": "Needs improvement",
                        "type": "issue",
                        "created_at": "2024-01-14T15:30:00Z",
                        "updated_at": "2024-01-14T16:00:00Z",
                        "in_reply_to_id": "comment1",
                        "suggestions": [],
                        "reactions": [],
                        "author_association": "MEMBER"
                    },
                    {
                        "id": "comment3",
                        "author": "author2",
                        "body": "Fixed",
                        "type": "response",
                        "created_at": "2024-01-14T17:00:00Z",
                        "updated_at": None,  # No update
                        "in_reply_to_id": "comment2",
                        "suggestions": ["sugg1", "sugg2"],
                        "reactions": [{"type": "heart"}],
                        "author_association": "OWNER"
                    }
                ]
            }
        ]

        content = self.export_manager._export_enhanced_csv_all_fields(pr_data, comments)

        # Parse CSV to verify content
        lines = content.strip().split('\n')
        assert len(lines) == 3  # Header + 2 data rows

        # Verify second comment row (has more interesting data)
        comment3_line = lines[2]
        fields = next(csv.reader([comment3_line]))

        assert fields[0] == "456"  # PR Number
        assert fields[1] == "Another PR"  # PR Title
        assert fields[2] == "author2"  # PR Author
        assert fields[3] == "closed"  # PR State
        assert fields[4] == "file2.py"  # File Path
        assert fields[5] == "10"  # Line Number
        assert fields[6] == "comment3"  # Comment ID
        assert fields[7] == "author2"  # Comment Author
        assert fields[8] == "Fixed"  # Comment Body
        assert fields[9] == "response"  # Comment Type
        assert fields[10] == "No"  # Is Resolved
        assert fields[11] == "Yes"  # Is Outdated
        assert fields[12] == "2024-01-14T17:00:00Z"  # Created At
        assert fields[13] == ""  # Updated At (None)
        assert fields[14] == "thread2"  # Thread ID
        assert fields[15] == "comment2"  # In Reply To
        assert fields[16] == "2"  # Suggestions Count
        assert fields[17] == "1"  # Reactions Count
        assert fields[18] == "OWNER"  # Author Association

    def test_export_enhanced_csv_missing_data(self):
        """Test enhanced CSV export with missing data."""
        pr_data = {}  # Missing all PR data

        comments = [
            {
                # Missing path, line, id
                "comments": [
                    {
                        # Missing most fields
                        "body": "Comment with minimal data"
                    }
                ]
            }
        ]

        content = self.export_manager._export_enhanced_csv_all_fields(pr_data, comments)

        # Should handle missing data gracefully
        lines = content.strip().split('\n')
        assert len(lines) == 2  # Header + 1 data row

        # Check that empty values are properly handled
        data_line = lines[1]
        fields = next(csv.reader([data_line]))

        # Should have empty strings for missing data
        assert fields[0] == ""  # Missing PR number
        assert fields[1] == ""  # Missing PR title
        assert fields[8] == "Comment with minimal data"  # Body present
        assert fields[10] == "No"  # Default resolution status


class TestExportManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.export_manager = ExportManager()

    def test_large_batch_results(self):
        """Test export with large number of batch results."""
        # Create 1000 batch results
        large_batch_results = [
            {
                "pr_number": i,
                "success": i % 2 == 0,  # Alternate success/failure
                "result": i * 2,
                "errors": [] if i % 2 == 0 else [f"Error {i}"],
                "duration": i * 0.1
            }
            for i in range(1000)
        ]

        # Should handle large datasets without issue
        content = self.export_manager._export_batch_markdown(large_batch_results)

        assert "**Total PRs Processed:** 1000" in content
        assert "**Successful Operations:** 500" in content
        assert "**Failed Operations:** 500" in content

    def test_unicode_and_special_characters(self):
        """Test handling of Unicode and special characters."""
        batch_results = [
            {
                "pr_number": 123,
                "success": False,
                "result": 0,
                "errors": [
                    "Unicode error: 测试 🚀 émojis",
                    "Special chars: <>&\"'",
                    "Newlines\nand\ttabs"
                ]
            }
        ]

        # Markdown should handle Unicode properly
        content = self.export_manager._export_batch_markdown(batch_results)
        assert "Unicode error: 测试 🚀 émojis" in content
        assert "Special chars: <>&\"'" in content

        # CSV should handle special characters properly
        csv_content = self.export_manager._export_batch_csv(batch_results)
        assert "Unicode error: 测试 🚀 émojis" in csv_content

    def test_deeply_nested_data_structures(self):
        """Test handling of deeply nested data structures."""
        pr_data_list = [
            {
                "number": 123,
                "state": "open",
                "author": "user1",
                "comments": [
                    {
                        "path": "file1.py",
                        "comments": [
                            {
                                "author": "reviewer1",
                                "body": "Comment 1",
                                "nested_data": {
                                    "level1": {
                                        "level2": {
                                            "level3": "deep_value"
                                        }
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]

        # Should handle nested structures gracefully without errors
        stats = self.export_manager._calculate_review_statistics(pr_data_list)
        assert stats["total_prs"] == 1
        assert stats["comment_statistics"]["total_comments"] == 1

    def test_empty_and_none_values(self):
        """Test handling of empty and None values."""
        batch_results = [
            {
                "pr_number": 123,
                "success": True,
                "result": None,  # None result
                "errors": None,  # None errors
                "duration": 0.0
            },
            {
                "pr_number": 124,
                "success": False,
                "result": "",  # Empty string result
                "errors": [],  # Empty errors list
                "duration": None  # None duration
            }
        ]

        # Should handle None and empty values gracefully
        summary = BatchSummary(
            total_prs=len(batch_results),
            successful=sum(1 for r in batch_results if r.get("success", False)),
            failed=len(batch_results) - sum(1 for r in batch_results if r.get("success", False))
        )

        content = self.export_manager._export_batch_markdown(batch_results)
        assert "### PR #123" in content
        assert "### PR #124" in content

    @patch('gh_pr.utils.export.logger')
    def test_logging_behavior(self, mock_logger):
        """Test that appropriate logging occurs."""
        batch_results = [{"pr_number": 123, "success": True}]

        with patch('pathlib.Path.write_text'):
            with patch('gh_pr.utils.export.datetime') as mock_datetime:
                mock_datetime.now.return_value.strftime.return_value = "20240115_143022"

                filename = self.export_manager.export_batch_report(batch_results, "markdown")

                # Should log export completion
                mock_logger.info.assert_called()
                info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
                assert any("Exported batch report" in call for call in info_calls)

    def test_concurrent_exports(self):
        """Test thread safety of export operations."""
        import threading

        results = []
        errors = []

        def export_operation():
            try:
                batch_results = [{"pr_number": 123, "success": True}]

                with patch('pathlib.Path.write_text'):
                    with patch('gh_pr.utils.export.datetime') as mock_datetime:
                        mock_datetime.now.return_value.strftime.return_value = f"timestamp_{threading.current_thread().ident}"

                        filename = self.export_manager.export_batch_report(batch_results, "markdown")
                        results.append(filename)

            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=export_operation) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All exports should complete successfully
        assert len(results) == 5
        assert len(errors) == 0

    def test_file_permission_simulation(self):
        """Test behavior when file operations might fail."""
        batch_results = [{"pr_number": 123, "success": True}]

        # Simulate write permission error
        with patch('pathlib.Path.write_text', side_effect=PermissionError("Permission denied")):
            with patch('gh_pr.utils.export.datetime') as mock_datetime:
                mock_datetime.now.return_value.strftime.return_value = "20240115_143022"

                with pytest.raises(PermissionError):
                    self.export_manager.export_batch_report(batch_results, "markdown")

    def test_memory_efficiency_large_dataset(self):
        """Test memory efficiency with large datasets."""
        # Create a large PR dataset
        large_pr_data = []
        for i in range(100):
            pr_data = {
                "number": i,
                "state": "open" if i % 2 == 0 else "closed",
                "author": f"user{i % 10}",
                "comments": [
                    {
                        "path": f"file{j}.py",
                        "comments": [
                            {"author": f"reviewer{k}", "body": f"Comment {j}-{k}"}
                            for k in range(5)  # 5 comments per thread
                        ]
                    }
                    for j in range(3)  # 3 threads per PR
                ]
            }
            large_pr_data.append(pr_data)

        # Should calculate statistics without memory issues
        stats = self.export_manager._calculate_review_statistics(large_pr_data)

        assert stats["total_prs"] == 100
        assert stats["comment_statistics"]["total_comments"] == 1500  # 100 * 3 * 5
        assert stats["file_statistics"]["unique_files_commented"] == 300  # 100 * 3 unique files
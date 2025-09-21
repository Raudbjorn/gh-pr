"""
Unit tests for utils.export module.

Tests export functionality for PR data with security and edge case coverage.
"""

import csv
import json
import tempfile
import unittest
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch, mock_open

from gh_pr.utils.export import ExportManager, _sanitize_filename, INVALID_FILENAME_CHARS, MAX_FILENAME_LENGTH, RESERVED_NAMES


class TestSanitizeFilename(unittest.TestCase):
    """Test _sanitize_filename function."""

    def test_sanitize_filename_valid_filename(self):
        """Test sanitizing valid filename."""
        result = _sanitize_filename("valid_filename.txt")
        self.assertEqual(result, "valid_filename.txt")

    def test_sanitize_filename_invalid_characters(self):
        """Test sanitizing filename with invalid characters."""
        invalid_filename = "file<name>with:invalid/chars\\|?*.txt"
        result = _sanitize_filename(invalid_filename)

        # Should replace invalid characters with underscores
        # Note: * is not considered invalid per the regex [<>:"/\\|?]
        expected = "file_name_with_invalid_chars___*.txt"
        self.assertEqual(result, expected)

    def test_sanitize_filename_leading_trailing_dots_spaces(self):
        """Test sanitizing filename with leading/trailing dots and spaces."""
        test_cases = [
            ("  filename.txt  ", "filename.txt"),
            ("...filename.txt...", "filename.txt"),
            (" . filename.txt . ", "filename.txt"),
        ]

        for input_name, expected in test_cases:
            with self.subTest(input=input_name):
                result = _sanitize_filename(input_name)
                self.assertEqual(result, expected)

    def test_sanitize_filename_reserved_names(self):
        """Test sanitizing reserved Windows filenames."""
        reserved_names = ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"]

        for reserved in reserved_names:
            with self.subTest(reserved=reserved):
                result = _sanitize_filename(reserved)
                self.assertEqual(result, f"export_{reserved}")

                # Test with extension
                result_ext = _sanitize_filename(f"{reserved}.txt")
                self.assertEqual(result_ext, f"export_{reserved}.txt")

    def test_sanitize_filename_reserved_names_case_insensitive(self):
        """Test that reserved name checking is case insensitive."""
        result = _sanitize_filename("con.txt")
        self.assertEqual(result, "export_con.txt")

        result = _sanitize_filename("Aux.log")
        self.assertEqual(result, "export_Aux.log")

    def test_sanitize_filename_empty_filename(self):
        """Test sanitizing empty or dot-only filenames."""
        test_cases = [
            ("", "export_file"),
            (".", "export_."),
            ("..", "export_.."),
            ("...", "export_..."),
        ]

        for input_name, expected in test_cases:
            with self.subTest(input=input_name):
                result = _sanitize_filename(input_name)
                self.assertEqual(result, expected)

    def test_sanitize_filename_long_filename(self):
        """Test sanitizing very long filenames."""
        # Create filename longer than MAX_FILENAME_LENGTH
        long_name = "a" * (MAX_FILENAME_LENGTH + 50) + ".txt"
        result = _sanitize_filename(long_name)

        self.assertLessEqual(len(result), MAX_FILENAME_LENGTH)
        self.assertTrue(result.endswith(".txt"))

        # Test without extension
        long_name_no_ext = "a" * (MAX_FILENAME_LENGTH + 50)
        result_no_ext = _sanitize_filename(long_name_no_ext)
        self.assertLessEqual(len(result_no_ext), MAX_FILENAME_LENGTH)

    def test_sanitize_filename_preserves_extension(self):
        """Test that sanitization preserves file extension when truncating."""
        long_base = "a" * (MAX_FILENAME_LENGTH - 4 + 50)  # Will exceed limit
        filename = f"{long_base}.log"

        result = _sanitize_filename(filename)

        self.assertLessEqual(len(result), MAX_FILENAME_LENGTH)
        self.assertTrue(result.endswith(".log"))

    def test_sanitize_filename_constants(self):
        """Test that sanitization constants are properly defined."""
        self.assertIsInstance(INVALID_FILENAME_CHARS, str)
        self.assertIsInstance(MAX_FILENAME_LENGTH, int)
        self.assertIsInstance(RESERVED_NAMES, set)

        self.assertGreater(MAX_FILENAME_LENGTH, 0)
        self.assertGreater(len(RESERVED_NAMES), 0)


class TestExportManager(unittest.TestCase):
    """Test ExportManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.export_manager = ExportManager()
        self.temp_dir = Path(tempfile.mkdtemp())

        # Sample PR data for testing
        self.sample_pr_data = {
            "number": 123,
            "title": "Test PR",
            "state": "open",
            "author": "testuser",
            "created_at": "2024-01-01T12:00:00Z",
            "updated_at": "2024-01-02T12:00:00Z",
            "body": "This is a test PR description.\n\nWith multiple lines."
        }

        # Sample comments for testing
        self.sample_comments = [
            {
                "path": "src/main.py",
                "line": 42,
                "is_resolved": False,
                "is_outdated": False,
                "comments": [
                    {
                        "author": "reviewer1",
                        "body": "This needs to be fixed",
                        "created_at": "2024-01-01T13:00:00Z"
                    },
                    {
                        "author": "author",
                        "body": "Fixed in next commit",
                        "created_at": "2024-01-01T14:00:00Z"
                    }
                ]
            },
            {
                "path": "src/utils.py",
                "line": 15,
                "is_resolved": True,
                "is_outdated": True,
                "comments": [
                    {
                        "author": "reviewer2",
                        "body": "Consider optimization here",
                        "created_at": "2024-01-01T15:00:00Z"
                    }
                ]
            }
        ]

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_extension(self):
        """Test _get_extension method."""
        test_cases = [
            ("markdown", "md"),
            ("csv", "csv"),
            ("json", "json"),
            ("unknown", "txt")
        ]

        for format_type, expected_ext in test_cases:
            with self.subTest(format=format_type):
                result = self.export_manager._get_extension(format_type)
                self.assertEqual(result, expected_ext)

    @patch('gh_pr.utils.export.datetime')
    def test_export_markdown_format(self, mock_datetime):
        """Test export to Markdown format."""
        # Mock datetime for consistent timestamp
        mock_datetime.now.return_value.strftime.return_value = "20240101_120000"

        with patch('pathlib.Path.write_text') as mock_write:
            result = self.export_manager.export(
                self.sample_pr_data,
                self.sample_comments,
                format="markdown"
            )

            self.assertTrue(result.endswith(".md"))
            mock_write.assert_called_once()

            # Check the generated content
            written_content = mock_write.call_args[0][0]
            self.assertIn("# PR #123: Test PR", written_content)
            self.assertIn("**Author:** @testuser", written_content)
            self.assertIn("## Description", written_content)
            self.assertIn("## Review Comments", written_content)
            self.assertIn("src/main.py:42", written_content)
            self.assertIn("⚠ Unresolved", written_content)
            self.assertIn("✓ Resolved", written_content)
            self.assertIn("🕒 Outdated", written_content)

    @patch('gh_pr.utils.export.datetime')
    def test_export_csv_format(self, mock_datetime):
        """Test export to CSV format."""
        mock_datetime.now.return_value.strftime.return_value = "20240101_120000"

        with patch('builtins.open', mock_open()) as mock_file:
            result = self.export_manager.export(
                self.sample_pr_data,
                self.sample_comments,
                format="csv"
            )

            self.assertTrue(result.endswith(".csv"))
            mock_file.assert_called_once()

            # Verify CSV content structure
            written_calls = mock_file.return_value.write.call_args_list
            written_content = "".join(call[0][0] for call in written_calls)

            # Should contain CSV headers
            self.assertIn("PR Number,File,Line,Author,Comment,Resolved,Outdated,Created At", written_content)
            # Should contain data rows
            self.assertIn("123,src/main.py,42,reviewer1", written_content)

    @patch('gh_pr.utils.export.datetime')
    def test_export_json_format(self, mock_datetime):
        """Test export to JSON format."""
        mock_datetime.now.return_value.strftime.return_value = "20240101_120000"
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"

        with patch('pathlib.Path.write_text') as mock_write:
            result = self.export_manager.export(
                self.sample_pr_data,
                self.sample_comments,
                format="json"
            )

            self.assertTrue(result.endswith(".json"))
            mock_write.assert_called_once()

            # Parse and verify JSON content
            written_content = mock_write.call_args[0][0]
            exported_data = json.loads(written_content)

            self.assertEqual(exported_data["pr"]["number"], 123)
            self.assertEqual(exported_data["pr"]["title"], "Test PR")
            self.assertEqual(len(exported_data["comments"]), 2)
            self.assertIn("exported_at", exported_data)

    def test_export_unsupported_format(self):
        """Test export with unsupported format."""
        with self.assertRaises(ValueError) as context:
            self.export_manager.export(
                self.sample_pr_data,
                self.sample_comments,
                format="unsupported"
            )

        self.assertIn("Unsupported format", str(context.exception))

    def test_export_markdown_no_body(self):
        """Test Markdown export when PR has no body."""
        pr_data_no_body = self.sample_pr_data.copy()
        pr_data_no_body["body"] = None

        with patch('pathlib.Path.write_text') as mock_write:
            self.export_manager.export(pr_data_no_body, [], format="markdown")

            written_content = mock_write.call_args[0][0]
            # Should not include Description section
            self.assertNotIn("## Description", written_content)

    def test_export_markdown_no_comments(self):
        """Test Markdown export with no comments."""
        with patch('pathlib.Path.write_text') as mock_write:
            self.export_manager.export(
                self.sample_pr_data,
                [],
                format="markdown"
            )

            written_content = mock_write.call_args[0][0]
            self.assertIn("## Review Comments", written_content)
            # Should still have the comments section but no specific threads

    def test_export_csv_missing_line_number(self):
        """Test CSV export when comment has no line number."""
        comments_no_line = [
            {
                "path": "src/main.py",
                # No line number
                "is_resolved": False,
                "is_outdated": False,
                "comments": [
                    {
                        "author": "reviewer",
                        "body": "General comment",
                        "created_at": "2024-01-01T13:00:00Z"
                    }
                ]
            }
        ]

        with patch('builtins.open', mock_open()) as mock_file:
            self.export_manager.export(
                self.sample_pr_data,
                comments_no_line,
                format="csv"
            )

            written_calls = mock_file.return_value.write.call_args_list
            written_content = "".join(call[0][0] for call in written_calls)

            # Should handle missing line number gracefully
            self.assertIn('123,src/main.py,,reviewer', written_content)

    @patch('gh_pr.utils.export.datetime')
    def test_export_batch_report_markdown(self, mock_datetime):
        """Test export_batch_report with Markdown format."""
        mock_datetime.now.return_value.strftime.return_value = "2024-01-01 12:00:00"

        batch_results = [
            {
                "pr_number": 123,
                "success": True,
                "result": 5,
                "duration": 2.5,
                "errors": []
            },
            {
                "pr_number": 124,
                "success": False,
                "result": 0,
                "duration": 1.0,
                "errors": ["Permission denied", "Network error"]
            }
        ]

        with patch('pathlib.Path.write_text') as mock_write:
            result = self.export_manager.export_batch_report(batch_results, "markdown")

            self.assertTrue(result.startswith("batch_report_"))
            self.assertTrue(result.endswith(".md"))

            written_content = mock_write.call_args[0][0]
            self.assertIn("# Batch Operation Report", written_content)
            self.assertIn("**Total PRs Processed:** 2", written_content)
            self.assertIn("**Successful Operations:** 1", written_content)
            self.assertIn("**Failed Operations:** 1", written_content)
            self.assertIn("**Success Rate:** 50.0%", written_content)
            self.assertIn("### PR #123", written_content)
            self.assertIn("✅ Success", written_content)
            self.assertIn("❌ Failed", written_content)
            self.assertIn("Permission denied", written_content)

    @patch('gh_pr.utils.export.datetime')
    def test_export_batch_report_json(self, mock_datetime):
        """Test export_batch_report with JSON format."""
        mock_datetime.now.return_value.strftime.return_value = "20240101_120000"
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"

        batch_results = [{"pr_number": 123, "success": True, "result": 3}]

        with patch('pathlib.Path.write_text') as mock_write:
            result = self.export_manager.export_batch_report(batch_results, "json")

            self.assertTrue(result.endswith(".json"))

            written_content = mock_write.call_args[0][0]
            exported_data = json.loads(written_content)

            self.assertEqual(exported_data["report_type"], "batch_operation")
            self.assertEqual(exported_data["summary"]["total_prs"], 1)
            self.assertEqual(exported_data["summary"]["successful"], 1)
            self.assertEqual(len(exported_data["results"]), 1)

    @patch('gh_pr.utils.export.datetime')
    def test_export_batch_report_csv(self, mock_datetime):
        """Test export_batch_report with CSV format."""
        mock_datetime.now.return_value.strftime.return_value = "20240101_120000"

        batch_results = [
            {
                "pr_number": 123,
                "success": True,
                "result": 5,
                "duration": 2.5,
                "errors": []
            }
        ]

        with patch('builtins.open', mock_open()) as mock_file:
            result = self.export_manager.export_batch_report(batch_results, "csv")

            self.assertTrue(result.endswith(".csv"))

            written_calls = mock_file.return_value.write.call_args_list
            written_content = "".join(call[0][0] for call in written_calls)

            # Should contain CSV headers and data
            self.assertIn("PR Number,Success,Items Processed,Duration (s),Error Count,First Error", written_content)
            self.assertIn("123,Yes,5,2.50,0,", written_content)

    def test_export_batch_report_empty_results(self):
        """Test export_batch_report with empty results."""
        with self.assertRaises(ValueError) as context:
            self.export_manager.export_batch_report([], "markdown")

        self.assertIn("No batch results provided", str(context.exception))

    def test_export_batch_report_unsupported_format(self):
        """Test export_batch_report with unsupported format."""
        batch_results = [{"pr_number": 123, "success": True}]

        with self.assertRaises(ValueError) as context:
            self.export_manager.export_batch_report(batch_results, "unsupported")

        self.assertIn("Unsupported format", str(context.exception))

    @patch('gh_pr.utils.export.datetime')
    def test_export_enhanced_csv(self, mock_datetime):
        """Test export_enhanced_csv method."""
        mock_datetime.now.return_value.strftime.return_value = "20240101_120000"
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"

        enhanced_comments = [
            {
                "path": "src/main.py",
                "line": 42,
                "id": "thread_1",
                "is_resolved": False,
                "is_outdated": False,
                "comments": [
                    {
                        "id": "comment_1",
                        "author": "reviewer",
                        "body": "Enhanced comment",
                        "type": "review",
                        "created_at": "2024-01-01T13:00:00Z",
                        "updated_at": "2024-01-01T13:30:00Z",
                        "in_reply_to_id": None,
                        "suggestions": ["suggestion1"],
                        "reactions": ["👍", "👎"],
                        "author_association": "COLLABORATOR"
                    }
                ]
            }
        ]

        with patch('builtins.open', mock_open()) as mock_file:
            result = self.export_manager.export_enhanced_csv(
                self.sample_pr_data,
                enhanced_comments
            )

            self.assertTrue(result.endswith(".csv"))

            written_calls = mock_file.return_value.write.call_args_list
            written_content = "".join(call[0][0] for call in written_calls)

            # Should contain extended headers
            self.assertIn("Thread ID,In Reply To,Suggestions Count,Reactions Count,Author Association", written_content)
            # Should contain enhanced data
            self.assertIn("thread_1,,1,2,COLLABORATOR", written_content)

    def test_calculate_review_statistics(self):
        """Test _calculate_review_statistics method."""
        pr_data = {
            "number": 123,
            "state": "open",
            "author": "author1"
        }

        comments = [
            {
                "path": "file1.py",
                "line": 10,
                "comments": [
                    {"author": "reviewer1", "body": "Fix this"},
                    {"author": "reviewer2", "body": "Agreed"}
                ],
                "is_resolved": False,
                "is_outdated": False
            },
            {
                "path": "file2.py",
                "line": 20,
                "comments": [
                    {"author": "reviewer1", "body": "LGTM"}
                ],
                "is_resolved": True,
                "is_outdated": False
            }
        ]

        stats = self.export_manager._calculate_review_statistics(pr_data, comments)

        self.assertEqual(stats["total_comments"], 3)
        self.assertEqual(stats["resolved_comments"], 1)
        self.assertEqual(stats["unresolved_comments"], 2)
        self.assertEqual(stats["unique_authors"], 2)
        self.assertEqual(stats["files_commented"], 2)

    @patch('gh_pr.utils.export.datetime')
    def test_export_review_statistics_markdown(self, mock_datetime):
        """Test export_review_statistics with Markdown format."""
        mock_datetime.now.return_value.strftime.return_value = "20240101_120000"

        pr_data = {
            "number": 456,
            "state": "open",
            "author": "author1"
        }

        comments = [
            {
                "path": "test.py",
                "comments": [{"author": "reviewer1", "body": "comment"}],
                "is_resolved": False,
                "is_outdated": False
            }
        ]

        with patch('pathlib.Path.write_text') as mock_write:
            result = self.export_manager.export_review_statistics(pr_data, comments, "markdown")

            self.assertTrue(result.endswith(".md"))
            self.assertIn("456", result)
            mock_write.assert_called_once()

    def test_export_review_statistics_empty_data(self):
        """Test export_review_statistics with empty data."""
        pr_data = {"number": 789}
        comments = []

        with patch('pathlib.Path.write_text') as mock_write:
            with patch('gh_pr.utils.export.datetime') as mock_datetime:
                mock_datetime.now.return_value.strftime.return_value = "20240101_120000"
                result = self.export_manager.export_review_statistics(pr_data, comments, "markdown")

                self.assertTrue(result.endswith(".md"))
                self.assertIn("789", result)
                mock_write.assert_called_once()
                # Check that the written content includes zero counts
                written_content = mock_write.call_args[0][0]
                self.assertIn("Total Comments: 0", written_content)

    def test_export_stats_csv(self):
        """Test _export_stats_csv method."""
        stats = {
            "total_comments": 10,
            "resolved": 5,
            "unresolved": 5
        }

        with patch('pathlib.Path.write_text') as mock_write:
            result = self.export_manager._export_stats_csv(stats, "test_stats.csv")

            self.assertEqual(result, "test_stats.csv")
            mock_write.assert_called_once()
            # Check the CSV contains the expected data
            written_content = mock_write.call_args[0][0]
            self.assertIn("Metric", written_content)  # Check for header
            self.assertIn("Value", written_content)  # Check for header
            self.assertIn("total_comments", written_content)
            self.assertIn("10", written_content)

    def test_logging_integration(self):
        """Test that export operations work without errors."""
        batch_results = [{"pr_identifier": "PR#123", "success": True, "message": "Test"}]

        with patch('pathlib.Path.write_text'):
            with patch('gh_pr.utils.export.datetime') as mock_datetime:
                mock_datetime.now.return_value.strftime.return_value = "20240101_120000"
                result = self.export_manager.export_batch_report(batch_results, "markdown")
                # Just verify it runs without error
                self.assertIsNotNone(result)


if __name__ == '__main__':
    unittest.main()
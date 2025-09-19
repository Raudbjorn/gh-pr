"""Unit tests for export.py filename sanitization and security."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from gh_pr.utils.export import ExportManager, _sanitize_filename, INVALID_FILENAME_CHARS, MAX_FILENAME_LENGTH, RESERVED_NAMES


class TestFilenameSanitization:
    """Test filename sanitization security features."""

    def test_sanitize_filename_basic_valid_filename(self):
        """Test that valid filenames are preserved."""
        valid_filenames = [
            "normal_file.txt",
            "file123.md",
            "my-file_name.json",
            "file.with.dots.csv",
            "CamelCaseFile.xlsx"
        ]

        for filename in valid_filenames:
            result = _sanitize_filename(filename)
            assert result == filename

    def test_sanitize_filename_invalid_characters_replaced(self):
        """Test that invalid characters are replaced with underscores."""
        test_cases = [
            ("file<name>.txt", "file_name_.txt"),
            ("file>name.txt", "file_name.txt"),
            ("file:name.txt", "file_name.txt"),
            ("file\"name.txt", "file_name.txt"),
            ("file/name.txt", "file_name.txt"),
            ("file\\name.txt", "file_name.txt"),
            ("file|name.txt", "file_name.txt"),
            ("file?name.txt", "file_name.txt"),
            ("file*name.txt", "file_name.txt"),
        ]

        for input_filename, expected in test_cases:
            result = _sanitize_filename(input_filename)
            assert result == expected

    def test_sanitize_filename_control_characters_removed(self):
        """Test that control characters (0x00-0x1f) are replaced."""
        # Test some common control characters
        control_chars = ['\x00', '\x01', '\x1f', '\t', '\n', '\r']

        for char in control_chars:
            filename = f"file{char}name.txt"
            result = _sanitize_filename(filename)
            assert char not in result
            assert result == "file_name.txt"

    def test_sanitize_filename_leading_trailing_dots_spaces(self):
        """Test that leading/trailing dots and spaces are removed."""
        test_cases = [
            ("  filename.txt  ", "filename.txt"),
            ("..filename.txt", "filename.txt"),
            (".filename.txt.", "filename.txt"),
            ("   ..filename.txt..   ", "filename.txt"),
        ]

        for input_filename, expected in test_cases:
            result = _sanitize_filename(input_filename)
            assert result == expected

    def test_sanitize_filename_reserved_names_windows(self):
        """Test that Windows reserved names are prefixed with 'export_'."""
        reserved_names = [
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM9",
            "LPT1", "LPT2", "LPT9"
        ]

        for name in reserved_names:
            # Test uppercase
            result = _sanitize_filename(name)
            assert result == f"export_{name}"

            # Test lowercase (should also be caught due to case conversion)
            result = _sanitize_filename(name.lower())
            assert result == f"export_{name.lower()}"

            # Test with extension
            result = _sanitize_filename(f"{name}.txt")
            assert result == f"export_{name}.txt"

    def test_sanitize_filename_empty_filename_handling(self):
        """Test handling of empty or invalid filenames."""
        test_cases = [
            ("", "export_file"),
            ("   ", "export_file"),
            ("...", "export_file"),
            (".", "export_."),
            (".hidden", "export_.hidden"),
        ]

        for input_filename, expected in test_cases:
            result = _sanitize_filename(input_filename)
            assert result == expected

    def test_sanitize_filename_length_truncation(self):
        """Test that overly long filenames are truncated."""
        # Create a filename longer than MAX_FILENAME_LENGTH
        long_name = "a" * (MAX_FILENAME_LENGTH + 50)
        result = _sanitize_filename(long_name)

        assert len(result) <= MAX_FILENAME_LENGTH
        assert result == "a" * MAX_FILENAME_LENGTH

    def test_sanitize_filename_length_truncation_with_extension(self):
        """Test that truncation preserves file extensions."""
        # Create a long filename with extension
        long_name = "a" * (MAX_FILENAME_LENGTH + 50)
        filename_with_ext = f"{long_name}.txt"

        result = _sanitize_filename(filename_with_ext)

        assert len(result) <= MAX_FILENAME_LENGTH
        assert result.endswith(".txt")
        # Should be: truncated_name + ".txt"
        expected_name_length = MAX_FILENAME_LENGTH - 4  # 4 chars for ".txt"
        expected = "a" * expected_name_length + ".txt"
        assert result == expected

    def test_sanitize_filename_unicode_characters(self):
        """Test handling of Unicode characters."""
        unicode_filenames = [
            "文件名.txt",
            "archivo_español.md",
            "файл.json",
            "🎯_emoji_file.csv"
        ]

        for filename in unicode_filenames:
            result = _sanitize_filename(filename)
            # Unicode chars should be preserved (they're not in INVALID_FILENAME_CHARS)
            assert result == filename

    def test_sanitize_filename_multiple_extensions(self):
        """Test handling of files with multiple extensions."""
        filename = "archive.tar.gz"
        result = _sanitize_filename(filename)
        assert result == filename

        # Test truncation with multiple extensions
        long_name = "a" * (MAX_FILENAME_LENGTH + 50)
        filename_with_multi_ext = f"{long_name}.tar.gz"
        result = _sanitize_filename(filename_with_multi_ext)

        assert len(result) <= MAX_FILENAME_LENGTH
        # Should preserve only the last extension for truncation
        assert result.endswith(".gz")

    def test_sanitize_filename_path_traversal_prevention(self):
        """Test that path traversal attempts are neutralized."""
        malicious_names = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config",
            "....//....//etc//shadow",
            "../config.ini",
            "..\\config.ini"
        ]

        for malicious_name in malicious_names:
            result = _sanitize_filename(malicious_name)
            # All path separators should be replaced with underscores
            assert "/" not in result
            assert "\\" not in result
            # Should not start with dots (leading dots stripped)
            assert not result.startswith(".")

    def test_invalid_filename_chars_constant(self):
        """Test that INVALID_FILENAME_CHARS constant is comprehensive."""
        # Verify the regex pattern includes all dangerous characters
        import re
        pattern = re.compile(INVALID_FILENAME_CHARS)

        dangerous_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in dangerous_chars:
            assert pattern.search(char), f"Character {char} should be in INVALID_FILENAME_CHARS"

        # Test control characters
        for i in range(0x00, 0x20):
            char = chr(i)
            assert pattern.search(char), f"Control character {hex(i)} should be in INVALID_FILENAME_CHARS"

    def test_reserved_names_constant_completeness(self):
        """Test that RESERVED_NAMES includes all Windows reserved names."""
        expected_reserved = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }

        assert RESERVED_NAMES == expected_reserved

    def test_max_filename_length_constant(self):
        """Test that MAX_FILENAME_LENGTH is reasonable."""
        # Should be a reasonable limit (not too small, not too large)
        assert isinstance(MAX_FILENAME_LENGTH, int)
        assert 100 <= MAX_FILENAME_LENGTH <= 1000


class TestExportManagerSecurity:
    """Test ExportManager security features."""

    def test_export_uses_sanitized_filename(self):
        """Test that export() uses sanitized filenames."""
        export_manager = ExportManager()

        pr_data = {
            "number": 123,
            "title": "Test PR",
            "state": "open",
            "author": "testuser",
            "created_at": "2023-10-15T14:30:45Z",
            "body": "Test description"
        }
        comments = []

        with patch('pathlib.Path.write_text') as mock_write:
            with patch('gh_pr.utils.export._sanitize_filename') as mock_sanitize:
                mock_sanitize.return_value = "sanitized_filename.md"

                result = export_manager.export(pr_data, comments, format="markdown")

                # Should use sanitized filename
                mock_sanitize.assert_called_once()
                assert result == "sanitized_filename.md"

    def test_export_malicious_pr_data(self):
        """Test export with potentially malicious PR data."""
        export_manager = ExportManager()

        # PR data with malicious filename characters
        malicious_pr_data = {
            "number": "../../../123",  # Path traversal attempt
            "title": "Test<>PR",  # Invalid filename chars
            "state": "open",
            "author": "test|user",
            "created_at": "2023-10-15T14:30:45Z",
            "body": "Test"
        }
        comments = []

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                # Change to temp directory for test
                import os
                os.chdir(temp_dir)

                result = export_manager.export(malicious_pr_data, comments, format="markdown")

                # Result should be a safe filename in current directory
                result_path = Path(result)
                assert result_path.parent == Path.cwd()
                assert ".." not in str(result_path)
                assert result_path.exists()

            finally:
                os.chdir(original_cwd)

    def test_export_batch_report_filename_sanitization(self):
        """Test that batch report export sanitizes filenames."""
        export_manager = ExportManager()

        batch_results = [
            {"pr_number": 123, "success": True, "result": 5},
            {"pr_number": 456, "success": False, "result": 0, "errors": ["Error message"]}
        ]

        with patch('pathlib.Path.write_text') as mock_write:
            with patch('gh_pr.utils.export._sanitize_filename') as mock_sanitize:
                mock_sanitize.return_value = "sanitized_batch_report.md"

                result = export_manager.export_batch_report(batch_results, output_format="markdown")

                mock_sanitize.assert_called_once()
                assert result == "sanitized_batch_report.md"

    def test_export_review_statistics_filename_sanitization(self):
        """Test that review statistics export sanitizes filenames."""
        export_manager = ExportManager()

        pr_data_list = [
            {
                "number": 123,
                "state": "open",
                "author": "user1",
                "comments": []
            }
        ]

        with patch('pathlib.Path.write_text') as mock_write:
            with patch('gh_pr.utils.export._sanitize_filename') as mock_sanitize:
                mock_sanitize.return_value = "sanitized_stats.md"

                result = export_manager.export_review_statistics(pr_data_list, output_format="markdown")

                mock_sanitize.assert_called_once()
                assert result == "sanitized_stats.md"

    def test_export_enhanced_csv_filename_sanitization(self):
        """Test that enhanced CSV export sanitizes filenames."""
        export_manager = ExportManager()

        pr_data = {"number": 123, "title": "Test"}
        comments = []

        with patch('builtins.open', create=True) as mock_open:
            with patch('gh_pr.utils.export._sanitize_filename') as mock_sanitize:
                mock_sanitize.return_value = "sanitized_enhanced.csv"

                result = export_manager.export_enhanced_csv(pr_data, comments)

                mock_sanitize.assert_called_once()
                assert result == "sanitized_enhanced.csv"

    def test_export_file_creation_safe_location(self):
        """Test that exported files are created in safe locations."""
        export_manager = ExportManager()

        pr_data = {
            "number": 123,
            "title": "Test PR",
            "state": "open",
            "author": "testuser",
            "body": "Test"
        }
        comments = []

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                import os
                os.chdir(temp_dir)

                result = export_manager.export(pr_data, comments, format="json")

                # File should be created in current directory
                result_path = Path(result)
                assert result_path.parent == Path.cwd()
                assert result_path.exists()
                assert result_path.is_file()

                # Verify file is within temp directory (no path traversal)
                assert str(result_path.resolve()).startswith(str(Path(temp_dir).resolve()))

            finally:
                os.chdir(original_cwd)

    def test_export_csv_special_handling(self):
        """Test that CSV files are handled with proper encoding."""
        export_manager = ExportManager()

        pr_data = {"number": 123, "title": "Test PR", "author": "testuser"}
        comments = []

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                import os
                os.chdir(temp_dir)

                result = export_manager.export(pr_data, comments, format="csv")

                # Verify CSV file was created properly
                result_path = Path(result)
                assert result_path.exists()
                assert result_path.suffix == ".csv"

                # Verify file can be read back
                content = result_path.read_text(encoding="utf-8")
                assert "PR Number" in content  # CSV header

            finally:
                os.chdir(original_cwd)


class TestExportManagerPathSafety:
    """Test path safety and traversal prevention in export operations."""

    def test_export_prevents_directory_traversal_in_filename(self):
        """Test that directory traversal in generated filenames is prevented."""
        export_manager = ExportManager()

        # Mock datetime to return predictable timestamp with path traversal
        with patch('gh_pr.utils.export.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "../../../malicious"

            pr_data = {"number": 123, "title": "Test"}
            comments = []

            with tempfile.TemporaryDirectory() as temp_dir:
                original_cwd = Path.cwd()
                try:
                    import os
                    os.chdir(temp_dir)

                    result = export_manager.export(pr_data, comments, format="markdown")

                    # Result should be safe filename in current directory
                    result_path = Path(result)
                    assert result_path.parent == Path.cwd()
                    assert ".." not in str(result_path)

                finally:
                    os.chdir(original_cwd)

    def test_export_filename_timestamp_format(self):
        """Test that timestamp format in filenames is predictable and safe."""
        export_manager = ExportManager()

        pr_data = {"number": 123, "title": "Test"}
        comments = []

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                import os
                os.chdir(temp_dir)

                result = export_manager.export(pr_data, comments, format="markdown")

                # Filename should match expected pattern: pr_123_YYYYMMDD_HHMMSS.md
                import re
                pattern = r"pr_123_\d{8}_\d{6}\.md"
                assert re.match(pattern, result), f"Filename {result} doesn't match expected pattern"

            finally:
                os.chdir(original_cwd)

    def test_export_concurrent_filename_uniqueness(self):
        """Test that concurrent exports generate unique filenames."""
        export_manager = ExportManager()

        pr_data = {"number": 123, "title": "Test"}
        comments = []

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                import os
                os.chdir(temp_dir)

                # Generate multiple exports quickly
                results = []
                for _ in range(3):
                    result = export_manager.export(pr_data, comments, format="json")
                    results.append(result)

                # All filenames should be unique (due to timestamp precision)
                assert len(set(results)) == len(results)

                # All files should exist
                for result in results:
                    assert Path(result).exists()

            finally:
                os.chdir(original_cwd)


class TestExportManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_export_empty_pr_data(self):
        """Test export with minimal PR data."""
        export_manager = ExportManager()

        pr_data = {"number": 1}  # Minimal required data
        comments = []

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                import os
                os.chdir(temp_dir)

                result = export_manager.export(pr_data, comments, format="markdown")

                # Should handle gracefully
                result_path = Path(result)
                assert result_path.exists()

                content = result_path.read_text()
                assert "# PR #1" in content

            finally:
                os.chdir(original_cwd)

    def test_export_unsupported_format(self):
        """Test export with unsupported format."""
        export_manager = ExportManager()

        pr_data = {"number": 123, "title": "Test"}
        comments = []

        with pytest.raises(ValueError, match="Unsupported format"):
            export_manager.export(pr_data, comments, format="unsupported")

    def test_export_unicode_content(self):
        """Test export with Unicode content."""
        export_manager = ExportManager()

        pr_data = {
            "number": 123,
            "title": "测试 PR with émojis 🎯",
            "author": "用户",
            "body": "Unicode content: áéíóú ñç"
        }
        comments = []

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                import os
                os.chdir(temp_dir)

                result = export_manager.export(pr_data, comments, format="markdown")

                # Should handle Unicode properly
                result_path = Path(result)
                assert result_path.exists()

                content = result_path.read_text(encoding="utf-8")
                assert "测试 PR with émojis 🎯" in content
                assert "Unicode content: áéíóú ñç" in content

            finally:
                os.chdir(original_cwd)

    def test_export_very_long_pr_title(self):
        """Test export with very long PR title affecting filename."""
        export_manager = ExportManager()

        # Create PR with very long title that might affect filename generation
        long_title = "A" * 500  # Very long title
        pr_data = {
            "number": 123,
            "title": long_title,
            "author": "testuser"
        }
        comments = []

        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                import os
                os.chdir(temp_dir)

                result = export_manager.export(pr_data, comments, format="markdown")

                # Filename should be properly truncated
                result_path = Path(result)
                assert len(result_path.name) <= MAX_FILENAME_LENGTH
                assert result_path.exists()

            finally:
                os.chdir(original_cwd)

    def test_export_batch_report_empty_results(self):
        """Test batch report export with empty results."""
        export_manager = ExportManager()

        with pytest.raises(ValueError, match="No batch results provided"):
            export_manager.export_batch_report([], output_format="markdown")

    def test_export_review_statistics_empty_pr_list(self):
        """Test review statistics export with empty PR list."""
        export_manager = ExportManager()

        with pytest.raises(ValueError, match="No PR data provided"):
            export_manager.export_review_statistics([], output_format="markdown")

    def test_sanitize_filename_regex_injection_prevention(self):
        """Test that filename sanitization prevents regex injection."""
        # Attempt to inject regex patterns that could cause issues
        malicious_patterns = [
            "file[a-z]*name.txt",
            "file(group)name.txt",
            "file{1,3}name.txt",
            "file^start.txt",
            "file$end.txt"
        ]

        for pattern in malicious_patterns:
            result = _sanitize_filename(pattern)
            # Special regex characters should be replaced or handled safely
            assert result != pattern  # Should be modified
            assert isinstance(result, str)
            assert len(result) > 0
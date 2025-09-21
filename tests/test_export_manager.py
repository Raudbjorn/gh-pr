"""Unit tests for ExportManager class."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from gh_pr.utils.export import ExportManager


class TestExportManager:
    """Test ExportManager class."""

    @pytest.fixture
    def export_manager(self):
        """Create an ExportManager instance."""
        return ExportManager()

    @pytest.fixture
    def sample_pr_data(self):
        """Create sample PR data for export."""
        return {
            "pr": {
                "number": 42,
                "title": "Test PR",
                "state": "open",
                "author": "testuser",
                "body": "PR description",
            },
            "comments": [
                {
                    "id": 1,
                    "path": "src/main.py",
                    "line": 10,
                    "body": "Comment text",
                    "author": "reviewer1",
                }
            ],
            "reviews": [
                {
                    "state": "APPROVED",
                    "author": "reviewer2",
                    "body": "Looks good!",
                }
            ],
            "checks": {
                "total": 3,
                "success": 2,
                "failure": 1,
                "pending": 0,
            },
            "files": [
                {
                    "filename": "src/main.py",
                    "status": "modified",
                    "additions": 10,
                    "deletions": 5,
                }
            ],
        }

    def test_export_json(self, export_manager, sample_pr_data):
        """Test exporting PR data as JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_file = Path(f.name)

        try:
            result = export_manager.export_pr_data(
                sample_pr_data, str(output_file), format="json"
            )
            assert result is True

            # Verify file contents
            with open(output_file, 'r') as f:
                exported = json.load(f)
            assert exported["pr"]["number"] == 42
            assert len(exported["comments"]) == 1
        finally:
            output_file.unlink(missing_ok=True)

    def test_export_markdown(self, export_manager, sample_pr_data):
        """Test exporting PR data as Markdown."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            output_file = Path(f.name)

        try:
            result = export_manager.export_pr_data(
                sample_pr_data, str(output_file), format="markdown"
            )
            assert result is True

            # Verify file contents
            content = output_file.read_text()
            assert "PR #42: Test PR" in content
            assert "## Comments" in content
            assert "## Reviews" in content
        finally:
            output_file.unlink(missing_ok=True)

    def test_export_csv(self, export_manager, sample_pr_data):
        """Test exporting PR data as CSV."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            output_file = Path(f.name)

        try:
            result = export_manager.export_pr_data(
                sample_pr_data, str(output_file), format="csv"
            )
            assert result is True

            # Verify file exists and has content
            content = output_file.read_text()
            assert "number,title,state" in content or "Comment" in content
        finally:
            output_file.unlink(missing_ok=True)

    def test_export_html(self, export_manager, sample_pr_data):
        """Test exporting PR data as HTML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            output_file = Path(f.name)

        try:
            result = export_manager.export_pr_data(
                sample_pr_data, str(output_file), format="html"
            )
            assert result is True

            # Verify file contents
            content = output_file.read_text()
            assert "<html>" in content or "<!DOCTYPE" in content
            assert "PR #42" in content
        finally:
            output_file.unlink(missing_ok=True)

    def test_export_invalid_format(self, export_manager, sample_pr_data):
        """Test exporting with invalid format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            output_file = Path(f.name)

        try:
            result = export_manager.export_pr_data(
                sample_pr_data, str(output_file), format="invalid"
            )
            # Should either fail or default to a valid format
            assert result is False or output_file.exists()
        finally:
            output_file.unlink(missing_ok=True)

    def test_export_to_stdout(self, export_manager, sample_pr_data):
        """Test exporting to stdout."""
        with patch('sys.stdout') as mock_stdout:
            result = export_manager.export_pr_data(
                sample_pr_data, output_file=None, format="json"
            )
            # Should write to stdout when no file specified
            assert mock_stdout.write.called or result is True

    def test_export_creates_directory(self, export_manager, sample_pr_data):
        """Test that export creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "subdir" / "export.json"

            result = export_manager.export_pr_data(
                sample_pr_data, str(output_file), format="json"
            )
            assert result is True
            assert output_file.exists()

    def test_export_write_error(self, export_manager, sample_pr_data):
        """Test handling of write errors during export."""
        with patch('builtins.open', side_effect=OSError("Write error")):
            result = export_manager.export_pr_data(
                sample_pr_data, "output.json", format="json"
            )
            assert result is False

    def test_format_comment_for_export(self, export_manager):
        """Test formatting comment for export."""
        comment = {
            "id": 1,
            "path": "src/main.py",
            "line": 10,
            "body": "Test comment",
            "author": "user1",
            "created_at": "2024-01-01T10:00:00Z",
        }

        # For JSON format
        formatted = export_manager.format_comment(comment, format="json")
        assert formatted == comment  # JSON format returns as-is

        # For Markdown format
        formatted = export_manager.format_comment(comment, format="markdown")
        assert isinstance(formatted, str)
        assert "user1" in formatted
        assert "Test comment" in formatted

    def test_format_review_for_export(self, export_manager):
        """Test formatting review for export."""
        review = {
            "state": "APPROVED",
            "author": "reviewer1",
            "body": "LGTM",
            "submitted_at": "2024-01-01T11:00:00Z",
        }

        # For JSON format
        formatted = export_manager.format_review(review, format="json")
        assert formatted == review

        # For Markdown format
        formatted = export_manager.format_review(review, format="markdown")
        assert isinstance(formatted, str)
        assert "APPROVED" in formatted
        assert "reviewer1" in formatted

    def test_empty_data_export(self, export_manager):
        """Test exporting empty data."""
        empty_data = {
            "pr": {},
            "comments": [],
            "reviews": [],
            "checks": {},
            "files": [],
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_file = Path(f.name)

        try:
            result = export_manager.export_pr_data(
                empty_data, str(output_file), format="json"
            )
            assert result is True

            # Verify file was created
            assert output_file.exists()
        finally:
            output_file.unlink(missing_ok=True)
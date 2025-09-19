"""Export functionality for PR data."""

import csv
import io
import json
import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Optional


logger = logging.getLogger(__name__)

# Constants for filename sanitization
INVALID_FILENAME_CHARS = r'[<>:"/\\|?*\x00-\x1f]'
MAX_FILENAME_LENGTH = 200
RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
}


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent overwriting system files and path traversal.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for filesystem use
    """
    # Remove or replace invalid characters
    sanitized = re.sub(INVALID_FILENAME_CHARS, '_', filename)

    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip('. ')

    # Handle reserved names
    name_without_ext = sanitized.split('.')[0].upper()
    if name_without_ext in RESERVED_NAMES:
        sanitized = f"export_{sanitized}"

    # Prevent empty filenames
    if not sanitized or sanitized.startswith('.'):
        sanitized = f"export_{sanitized}" if sanitized else "export_file"

    # Truncate if too long, preserving extension
    if len(sanitized) > MAX_FILENAME_LENGTH:
        parts = sanitized.rsplit('.', 1)
        if len(parts) == 2:
            name, ext = parts
            max_name_len = MAX_FILENAME_LENGTH - len(ext) - 1
            sanitized = f"{name[:max_name_len]}.{ext}"
        else:
            sanitized = sanitized[:MAX_FILENAME_LENGTH]

    return sanitized


class ExportManager:
    """Manage export of PR data to various formats with advanced reporting."""

    def export(
        self,
        pr_data: dict[str, Any],
        comments: list[dict[str, Any]],
        format: str = "markdown",
    ) -> str:
        """
        Export PR data to specified format.

        Args:
            pr_data: PR data dictionary
            comments: List of comment threads
            format: Export format (markdown, csv, json)

        Returns:
            Path to exported file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"pr_{pr_data['number']}_{timestamp}.{self._get_extension(format)}"
        filename = _sanitize_filename(filename)

        if format == "markdown":
            content = self._export_markdown(pr_data, comments)
        elif format == "csv":
            content = self._export_csv(pr_data, comments)
        elif format == "json":
            content = self._export_json(pr_data, comments)
        else:
            raise ValueError(f"Unsupported format: {format}")

        # Write to file
        output_path = Path(filename)
        if format == "csv":
            # CSV needs special handling
            with open(output_path, "w", newline="") as f:
                f.write(content)
        else:
            output_path.write_text(content)

        return str(output_path)

    def _get_extension(self, format: str) -> str:
        """Get file extension for format."""
        return {"markdown": "md", "csv": "csv", "json": "json"}.get(format, "txt")

    def _export_markdown(
        self, pr_data: dict[str, Any], comments: list[dict[str, Any]]
    ) -> str:
        """Export to Markdown format."""
        lines = []

        # Header
        lines.append(f"# PR #{pr_data['number']}: {pr_data['title']}")
        lines.append("")
        lines.append(f"**Status:** {pr_data['state']}")
        lines.append(f"**Author:** @{pr_data['author']}")
        lines.append(f"**Created:** {pr_data.get('created_at', 'N/A')}")
        lines.append(f"**Updated:** {pr_data.get('updated_at', 'N/A')}")
        lines.append("")

        # Description
        if pr_data.get("body"):
            lines.append("## Description")
            lines.append("")
            lines.append(pr_data["body"])
            lines.append("")

        # Comments
        lines.append("## Review Comments")
        lines.append("")

        for thread in comments:
            lines.append(f"### {thread['path']}:{thread.get('line', 'N/A')}")
            lines.append("")

            status = []
            if thread.get("is_resolved"):
                status.append("✓ Resolved")
            else:
                status.append("⚠ Unresolved")

            if thread.get("is_outdated"):
                status.append("🕒 Outdated")

            lines.append(f"**Status:** {' • '.join(status)}")
            lines.append("")

            for comment in thread.get("comments", []):
                lines.append(f"**@{comment['author']}:**")
                lines.append("")
                lines.append(comment.get("body", ""))
                lines.append("")

        return "\n".join(lines)

    def _export_csv(
        self, pr_data: dict[str, Any], comments: list[dict[str, Any]]
    ) -> str:
        """Export to CSV format."""
        pass  # io imported at top

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "PR Number",
            "File",
            "Line",
            "Author",
            "Comment",
            "Resolved",
            "Outdated",
            "Created At",
        ])

        # Data
        for thread in comments:
            for comment in thread.get("comments", []):
                writer.writerow([
                    pr_data["number"],
                    thread["path"],
                    thread.get("line", ""),
                    comment["author"],
                    comment.get("body", ""),
                    "Yes" if thread.get("is_resolved") else "No",
                    "Yes" if thread.get("is_outdated") else "No",
                    comment.get("created_at", ""),
                ])

        return output.getvalue()

    def _export_json(
        self, pr_data: dict[str, Any], comments: list[dict[str, Any]]
    ) -> str:
        """Export to JSON format."""
        export_data = {
            "pr": pr_data,
            "comments": comments,
            "exported_at": datetime.now().isoformat(),
        }

        return json.dumps(export_data, indent=2, default=str)

    def export_batch_report(
        self,
        batch_results: list[dict[str, Any]],
        output_format: str = "markdown"
    ) -> str:
        """
        Export batch operation results as a comprehensive report.

        Args:
            batch_results: List of batch operation results
            output_format: Output format (markdown, json, csv)

        Returns:
            Path to exported report file
        """
        if not batch_results:
            raise ValueError("No batch results provided")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"batch_report_{timestamp}.{self._get_extension(output_format)}"
        filename = _sanitize_filename(filename)

        if output_format == "markdown":
            content = self._export_batch_markdown(batch_results)
        elif output_format == "json":
            content = self._export_batch_json(batch_results)
        elif output_format == "csv":
            content = self._export_batch_csv(batch_results)
        else:
            raise ValueError(f"Unsupported format: {output_format}")

        # Write to file
        output_path = Path(filename)
        if output_format == "csv":
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                f.write(content)
        else:
            output_path.write_text(content, encoding="utf-8")

        logger.info(f"Exported batch report to {output_path}")
        return str(output_path)

    def export_review_statistics(
        self,
        pr_data_list: list[dict[str, Any]],
        output_format: str = "markdown"
    ) -> str:
        """
        Export review statistics and analytics.

        Args:
            pr_data_list: List of PR data dictionaries
            output_format: Output format (markdown, json, csv)

        Returns:
            Path to exported statistics file
        """
        if not pr_data_list:
            raise ValueError("No PR data provided")

        stats = self._calculate_review_statistics(pr_data_list)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"review_stats_{timestamp}.{self._get_extension(output_format)}"
        filename = _sanitize_filename(filename)

        if output_format == "markdown":
            content = self._export_stats_markdown(stats)
        elif output_format == "json":
            content = json.dumps(stats, indent=2, default=str)
        elif output_format == "csv":
            content = self._export_stats_csv(stats)
        else:
            raise ValueError(f"Unsupported format: {output_format}")

        # Write to file
        output_path = Path(filename)
        if output_format == "csv":
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                f.write(content)
        else:
            output_path.write_text(content, encoding="utf-8")

        logger.info(f"Exported review statistics to {output_path}")
        return str(output_path)

    def export_enhanced_csv(
        self,
        pr_data: dict[str, Any],
        comments: list[dict[str, Any]],
        include_all_fields: bool = True
    ) -> str:
        """
        Export enhanced CSV with all available comment fields.

        Args:
            pr_data: PR data dictionary
            comments: List of comment threads
            include_all_fields: Whether to include all available fields

        Returns:
            Path to exported CSV file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"pr_{pr_data['number']}_enhanced_{timestamp}.csv"
        filename = _sanitize_filename(filename)

        if include_all_fields:
            content = self._export_enhanced_csv_all_fields(pr_data, comments)
        else:
            content = self._export_csv(pr_data, comments)

        # Write to file
        output_path = Path(filename)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Exported enhanced CSV to {output_path}")
        return str(output_path)

    def _export_batch_markdown(self, batch_results: list[dict[str, Any]]) -> str:
        """Export batch results to Markdown format."""
        lines = []

        # Header
        lines.append("# Batch Operation Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Total PRs Processed:** {len(batch_results)}")
        lines.append("")

        # Calculate summary statistics
        successful = sum(1 for r in batch_results if r.get("success", False))
        failed = len(batch_results) - successful
        total_items = sum(r.get("result", 0) if isinstance(r.get("result"), int) else 0 for r in batch_results)

        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Successful Operations:** {successful}")
        lines.append(f"- **Failed Operations:** {failed}")
        lines.append(f"- **Success Rate:** {(successful/len(batch_results)*100):.1f}%")
        lines.append(f"- **Total Items Processed:** {total_items}")
        lines.append("")

        # Individual results
        lines.append("## Individual Results")
        lines.append("")

        for result in batch_results:
            pr_num = result.get("pr_number", "Unknown")
            success = result.get("success", False)
            status = "✅ Success" if success else "❌ Failed"
            items = result.get("result", 0) if isinstance(result.get("result"), int) else 0

            lines.append(f"### PR #{pr_num}")
            lines.append(f"- **Status:** {status}")
            lines.append(f"- **Items Processed:** {items}")

            if result.get("errors"):
                lines.append("- **Errors:**")
                for error in result["errors"]:
                    lines.append(f"  - {error}")

            lines.append("")

        return "\n".join(lines)

    def _export_batch_json(self, batch_results: list[dict[str, Any]]) -> str:
        """Export batch results to JSON format."""
        export_data = {
            "report_type": "batch_operation",
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_prs": len(batch_results),
                "successful": sum(1 for r in batch_results if r.get("success", False)),
                "failed": sum(1 for r in batch_results if not r.get("success", False)),
                "total_items": sum(r.get("result", 0) if isinstance(r.get("result"), int) else 0 for r in batch_results)
            },
            "results": batch_results
        }
        return json.dumps(export_data, indent=2, default=str)

    def _export_batch_csv(self, batch_results: list[dict[str, Any]]) -> str:
        """Export batch results to CSV format."""
        pass  # io imported at top

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "PR Number",
            "Success",
            "Items Processed",
            "Duration (s)",
            "Error Count",
            "First Error"
        ])

        # Data
        for result in batch_results:
            pr_num = result.get("pr_number", "")
            success = "Yes" if result.get("success", False) else "No"
            items = result.get("result", 0) if isinstance(result.get("result"), int) else 0
            duration = result.get("duration", 0.0)
            errors = result.get("errors", [])
            error_count = len(errors)
            first_error = errors[0] if errors else ""

            writer.writerow([pr_num, success, items, f"{duration:.2f}", error_count, first_error])

        return output.getvalue()

    def _export_enhanced_csv_all_fields(
        self,
        pr_data: dict[str, Any],
        comments: list[dict[str, Any]]
    ) -> str:
        """Export CSV with all available comment fields."""
        pass  # io imported at top

        output = io.StringIO()
        writer = csv.writer(output)

        # Extended header with all fields
        writer.writerow([
            "PR Number",
            "PR Title",
            "PR Author",
            "PR State",
            "File Path",
            "Line Number",
            "Comment ID",
            "Comment Author",
            "Comment Body",
            "Comment Type",
            "Is Resolved",
            "Is Outdated",
            "Created At",
            "Updated At",
            "Thread ID",
            "In Reply To",
            "Suggestions Count",
            "Reactions Count",
            "Author Association"
        ])

        # Data with all available fields
        for thread in comments:
            for comment in thread.get("comments", []):
                writer.writerow([
                    pr_data.get("number", ""),
                    pr_data.get("title", ""),
                    pr_data.get("author", ""),
                    pr_data.get("state", ""),
                    thread.get("path", ""),
                    thread.get("line", ""),
                    comment.get("id", ""),
                    comment.get("author", ""),
                    comment.get("body", ""),
                    comment.get("type", ""),
                    "Yes" if thread.get("is_resolved") else "No",
                    "Yes" if thread.get("is_outdated") else "No",
                    comment.get("created_at", ""),
                    comment.get("updated_at", ""),
                    thread.get("id", ""),
                    comment.get("in_reply_to_id", ""),
                    len(comment.get("suggestions", [])),
                    len(comment.get("reactions", [])),
                    comment.get("author_association", "")
                ])

        return output.getvalue()

    def _calculate_review_statistics(self, pr_data_list: list[dict[str, Any]]) -> dict[str, Any]:
        """Calculate comprehensive review statistics."""
        stats = {
            "total_prs": len(pr_data_list),
            "pr_states": {},
            "comment_statistics": {},
            "author_statistics": {},
            "file_statistics": {},
            "timeline_statistics": {}
        }

        all_comments = []
        pr_comment_counts = []
        pr_authors = []
        files_touched = set()
        comment_authors = []

        for pr_data in pr_data_list:
            # PR state tracking
            state = pr_data.get("state", "unknown")
            stats["pr_states"][state] = stats["pr_states"].get(state, 0) + 1

            # PR authors
            pr_authors.append(pr_data.get("author", "unknown"))

            # Comments analysis
            comments = pr_data.get("comments", [])
            pr_comment_counts.append(len(comments))

            for thread in comments:
                files_touched.add(thread.get("path", "unknown"))

                for comment in thread.get("comments", []):
                    all_comments.append(comment)
                    comment_authors.append(comment.get("author", "unknown"))

        # Comment statistics
        stats["comment_statistics"] = {
            "total_comments": len(all_comments),
            "average_comments_per_pr": mean(pr_comment_counts) if pr_comment_counts else 0,
            "median_comments_per_pr": median(pr_comment_counts) if pr_comment_counts else 0,
            "max_comments_per_pr": max(pr_comment_counts) if pr_comment_counts else 0,
            "min_comments_per_pr": min(pr_comment_counts) if pr_comment_counts else 0
        }

        # Author statistics
        pass  # Counter imported at top
        pr_author_counts = Counter(pr_authors)
        comment_author_counts = Counter(comment_authors)

        stats["author_statistics"] = {
            "unique_pr_authors": len(pr_author_counts),
            "unique_comment_authors": len(comment_author_counts),
            "most_active_pr_author": pr_author_counts.most_common(1)[0] if pr_author_counts else ("None", 0),
            "most_active_commenter": comment_author_counts.most_common(1)[0] if comment_author_counts else ("None", 0)
        }

        # File statistics
        stats["file_statistics"] = {
            "unique_files_commented": len(files_touched),
            "files_list": sorted(list(files_touched))
        }

        return stats

    def _export_stats_markdown(self, stats: dict[str, Any]) -> str:
        """Export statistics to Markdown format."""
        lines = []

        lines.append("# Review Statistics Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Overall statistics
        lines.append("## Overall Statistics")
        lines.append("")
        lines.append(f"- **Total PRs:** {stats['total_prs']}")
        lines.append("")

        # PR States
        lines.append("## Pull Request States")
        lines.append("")
        for state, count in stats["pr_states"].items():
            lines.append(f"- **{state.title()}:** {count}")
        lines.append("")

        # Comment statistics
        comment_stats = stats["comment_statistics"]
        lines.append("## Comment Statistics")
        lines.append("")
        lines.append(f"- **Total Comments:** {comment_stats['total_comments']}")
        lines.append(f"- **Average per PR:** {comment_stats['average_comments_per_pr']:.1f}")
        lines.append(f"- **Median per PR:** {comment_stats['median_comments_per_pr']:.1f}")
        lines.append(f"- **Max per PR:** {comment_stats['max_comments_per_pr']}")
        lines.append(f"- **Min per PR:** {comment_stats['min_comments_per_pr']}")
        lines.append("")

        # Author statistics
        author_stats = stats["author_statistics"]
        lines.append("## Author Statistics")
        lines.append("")
        lines.append(f"- **Unique PR Authors:** {author_stats['unique_pr_authors']}")
        lines.append(f"- **Unique Comment Authors:** {author_stats['unique_comment_authors']}")

        most_active_pr = author_stats["most_active_pr_author"]
        most_active_comment = author_stats["most_active_commenter"]

        lines.append(f"- **Most Active PR Author:** @{most_active_pr[0]} ({most_active_pr[1]} PRs)")
        lines.append(f"- **Most Active Commenter:** @{most_active_comment[0]} ({most_active_comment[1]} comments)")
        lines.append("")

        # File statistics
        file_stats = stats["file_statistics"]
        lines.append("## File Statistics")
        lines.append("")
        lines.append(f"- **Files with Comments:** {file_stats['unique_files_commented']}")
        lines.append("")

        if file_stats["files_list"]:
            lines.append("### Files Commented On:")
            for file_path in file_stats["files_list"][:20]:  # Limit to first 20
                lines.append(f"- `{file_path}`")
            if len(file_stats["files_list"]) > 20:
                lines.append(f"- ... and {len(file_stats['files_list']) - 20} more files")

        return "\n".join(lines)

    def _export_stats_csv(self, stats: dict[str, Any]) -> str:
        """Export statistics to CSV format."""
        pass  # io imported at top

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["Metric", "Value"])

        # Basic statistics
        writer.writerow(["Total PRs", stats["total_prs"]])

        # PR states
        for state, count in stats["pr_states"].items():
            writer.writerow([f"PRs {state}", count])

        # Comment statistics
        comment_stats = stats["comment_statistics"]
        writer.writerow(["Total Comments", comment_stats["total_comments"]])
        writer.writerow(["Average Comments per PR", f"{comment_stats['average_comments_per_pr']:.1f}"])
        writer.writerow(["Median Comments per PR", f"{comment_stats['median_comments_per_pr']:.1f}"])

        # Author statistics
        author_stats = stats["author_statistics"]
        writer.writerow(["Unique PR Authors", author_stats["unique_pr_authors"]])
        writer.writerow(["Unique Comment Authors", author_stats["unique_comment_authors"]])

        return output.getvalue()

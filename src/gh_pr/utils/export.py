"""Export functionality for PR data."""

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

# Constants for test compatibility
INVALID_FILENAME_CHARS = r'[<>:"/\\|?*]'
MAX_FILENAME_LENGTH = 255
RESERVED_NAMES = ['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1, 10)] + [f'LPT{i}' for i in range(1, 10)]

def _sanitize_filename(filename: str) -> str:
    """Sanitize filename for filesystem safety."""
    # Handle empty or whitespace-only filenames
    if not filename or not filename.strip():
        return "export_file"

    # Remove invalid characters
    sanitized = re.sub(INVALID_FILENAME_CHARS, '_', filename)

    # Strip leading/trailing dots and spaces
    sanitized = sanitized.strip(' .')

    # Handle dot-only or empty after stripping
    if not sanitized or sanitized in ['.', '..', '...']:
        return f"export_{sanitized or 'file'}"

    # Check reserved names
    name_without_ext = sanitized.split('.')[0].upper()
    if name_without_ext in RESERVED_NAMES:
        sanitized = f"export_{sanitized}"

    # Truncate if too long while preserving extension
    if len(sanitized) > MAX_FILENAME_LENGTH:
        # Try to preserve the extension if present
        parts = sanitized.rsplit('.', 1)
        if len(parts) == 2 and len(parts[1]) <= 10:  # Reasonable extension length
            name, ext = parts
            # Keep as much of the name as possible while fitting the limit
            max_name_len = MAX_FILENAME_LENGTH - len(ext) - 1
            if max_name_len > 0:
                sanitized = f"{name[:max_name_len]}.{ext}"
            else:
                sanitized = sanitized[:MAX_FILENAME_LENGTH]
        else:
            sanitized = sanitized[:MAX_FILENAME_LENGTH]

    return sanitized or "export_file"


class ExportManager:
    """Manage export of PR data to various formats."""

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
        import io

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

    def export_review_report(
        self, pr_data: dict[str, Any], summary: dict[str, Any]
    ) -> str:
        """
        Export a review report for the PR.

        Args:
            pr_data: PR data dictionary
            summary: PR summary data

        Returns:
            Path to exported report file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"pr_{pr_data['number']}_review_report_{timestamp}.md"

        lines = []
        lines.append("# Pull Request Review Report")
        lines.append("")
        lines.append(f"## PR #{pr_data['number']}: {pr_data['title']}")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # PR Details
        lines.append("### PR Details")
        lines.append(f"- **Author:** @{pr_data['author']}")
        lines.append(f"- **Status:** {pr_data['state']}")
        lines.append(f"- **Base Branch:** {pr_data['base']['ref']}")
        lines.append(f"- **Head Branch:** {pr_data['head']['ref']}")
        lines.append(f"- **Changed Files:** {pr_data.get('changed_files', 0)}")
        lines.append(f"- **Additions:** +{pr_data.get('additions', 0)}")
        lines.append(f"- **Deletions:** -{pr_data.get('deletions', 0)}")
        lines.append("")

        # Review Status
        lines.append("### Review Status")
        lines.append(f"- **Approvals:** {summary.get('approvals', 0)}")
        lines.append(f"- **Changes Requested:** {summary.get('changes_requested', 0)}")
        lines.append(f"- **Comments:** {summary.get('comments', 0)}")
        lines.append("")

        # Thread Summary
        lines.append("### Comment Threads")
        lines.append(f"- **Total Threads:** {summary.get('total_threads', 0)}")
        lines.append(f"- **Unresolved (Active):** {summary.get('unresolved_active', 0)}")
        lines.append(f"- **Unresolved (Outdated):** {summary.get('unresolved_outdated', 0)}")
        lines.append(f"- **Resolved (Active):** {summary.get('resolved_active', 0)}")
        lines.append(f"- **Resolved (Outdated):** {summary.get('resolved_outdated', 0)}")
        lines.append("")

        # Recommendations
        lines.append("### Recommendations")
        if summary.get('unresolved_active', 0) > 0:
            lines.append("- ⚠️ Address unresolved active comments before merging")
        if summary.get('unresolved_outdated', 0) > 0:
            lines.append("- 🕒 Consider resolving outdated comments to clean up the PR")
        if summary.get('changes_requested', 0) > 0:
            lines.append("- 🔴 Address requested changes before merging")
        if summary.get('approvals', 0) == 0:
            lines.append("- ⚡ Obtain at least one approval before merging")
        lines.append("")

        output_path = Path(filename)
        output_path.write_text("\n".join(lines))
        return str(output_path)

    def export_batch_results(
        self, results: list[dict[str, Any]], operation: str
    ) -> str:
        """
        Export batch operation results.

        Args:
            results: List of batch operation results
            operation: Name of the batch operation

        Returns:
            Path to exported results file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"batch_{operation}_{timestamp}.csv"

        import io
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "PR Identifier",
            "Success",
            "Message",
            "Details",
            "Error"
        ])

        # Data
        for result in results:
            writer.writerow([
                result.get("pr_identifier", ""),
                "Yes" if result.get("success") else "No",
                result.get("message", ""),
                json.dumps(result.get("details", {})) if result.get("details") else "",
                result.get("error", "")
            ])

        output_path = Path(filename)
        output_path.write_text(output.getvalue())
        return str(output_path)

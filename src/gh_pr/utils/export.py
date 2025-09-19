"""Export functionality for PR data."""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


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

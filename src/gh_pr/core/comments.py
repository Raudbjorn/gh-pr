"""Comment processing and organization."""

import datetime
import hashlib
from functools import lru_cache
from typing import Any, Optional


# Helper function for backwards compatibility with tests
@lru_cache(maxsize=128)
def _parse_datetime_cached(date_string: str) -> datetime.datetime:
    """Parse datetime string with caching."""
    return datetime.datetime.fromisoformat(date_string.replace('Z', '+00:00'))


class CommentProcessor:
    """Process and organize PR comments."""

    def process(self, pr, comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Process PR and comments into organized threads.

        Args:
            pr: PR object (unused for now, kept for compatibility)
            comments: List of comment dictionaries

        Returns:
            List of organized comment threads
        """
        return self.organize_into_threads(comments)

    def parse_comment(self, comment: dict[str, Any]) -> dict[str, Any]:
        """
        Parse a single comment into standard format.

        Args:
            comment: Raw comment dictionary

        Returns:
            Parsed comment dictionary
        """
        return {
            "id": comment.get("id"),
            "author": comment.get("author"),
            "body": comment.get("body"),
            "path": comment.get("path"),
            "line": comment.get("line"),
            "created_at": comment.get("created_at"),
            "is_outdated": self._is_comment_outdated(comment),
        }

    def organize_into_threads(
        self, comments: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Organize comments into conversation threads.

        Args:
            comments: List of comment dictionaries

        Returns:
            List of thread dictionaries
        """
        threads = {}

        for comment in comments:
            # Create unique thread key using hash to prevent collisions
            thread_fields = (
                f"{comment['path']}:"
                f"{comment.get('start_line', '')}:"
                f"{comment.get('line', '')}:"
                f"{comment.get('commit_id', '')}"
            )
            thread_key = hashlib.sha256(thread_fields.encode()).hexdigest()[:16]

            if thread_key not in threads:
                threads[thread_key] = {
                    "id": thread_key,
                    "path": comment["path"],
                    "line": comment.get("line"),
                    "start_line": comment.get("start_line"),
                    "is_resolved": False,  # Would need to check via API
                    "is_outdated": self._is_comment_outdated(comment),
                    "diff_hunk": comment.get("diff_hunk"),  # Include diff hunk for code context
                    "comments": [],
                }

            threads[thread_key]["comments"].append(comment)

        # Sort comments within threads by creation time
        for thread in threads.values():
            def parse_created_at(comment):
                created_at = comment.get("created_at", "")
                try:
                    # Try parsing ISO 8601 format, fallback to empty string
                    return datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    return datetime.datetime.max  # Put comments with invalid/missing dates last

            thread["comments"].sort(
                key=parse_created_at,
            )

        return list(threads.values())

    def _is_comment_outdated(self, comment: dict[str, Any]) -> bool:
        """
        Determine if a comment is outdated.

        Args:
            comment: Comment dictionary

        Returns:
            True if comment is outdated
        """
        # Check if position or original_position are missing or differ
        position = comment.get("position")
        original_position = comment.get("original_position")

        if position is not None and original_position is not None:
            return position != original_position
        # One or both are None
        return not (position is None and original_position is None)

    def extract_suggestions(
        self, comments: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Extract suggestions from comments.

        Args:
            comments: List of comment dictionaries

        Returns:
            List of suggestion dictionaries
        """
        suggestions = []

        for comment in comments:
            body = comment.get("body", "")

            # Look for suggestion blocks
            if "```suggestion" in body:
                # Extract suggestion content
                import re
                # Extract suggestion content
                pattern = r"```suggestion\n(.*?)\n```"
                matches = []
                for match in re.finditer(pattern, body, re.DOTALL):
                    # Extract suggestion content directly
                    suggestion_content = match.group(1).strip()
                    matches.append(suggestion_content)

                for match in matches:
                    suggestions.append({
                        "comment_id": comment["id"],
                        "author": comment["author"],
                        "path": comment["path"],
                        "line": comment.get("line"),
                        "suggestion": match,
                        "original_code": self._extract_original_code(comment),
                    })

        return suggestions

    def _extract_original_code(self, comment: dict[str, Any]) -> Optional[str]:
        """
        Extract original code from diff hunk.

        Args:
            comment: Comment dictionary

        Returns:
            Original code string or None
        """
        diff_hunk = comment.get("diff_hunk", "")
        if not diff_hunk:
            return None

        # Parse diff hunk to get the relevant line
        lines = diff_hunk.split("\n")

        return next(
            (
                line[1:].strip()
                for line in lines
                if line.startswith("+") or line.startswith("-")
            ),
            None,
        )


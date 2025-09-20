"""Comment processing and organization."""

import datetime
import hashlib
import re
from functools import lru_cache
from typing import Any, Optional


@lru_cache(maxsize=1000)
def _parse_datetime_cached(date_string: str) -> datetime.datetime:
    """
    Parse datetime string with caching for performance.

    Args:
        date_string: ISO 8601 datetime string

    Returns:
        Parsed datetime object, or datetime.max for invalid dates
    """
    try:
        # Handle ISO 8601 format with 'Z' timezone indicator
        if date_string.endswith('Z'):
            date_string = date_string[:-1] + '+00:00'
        return datetime.datetime.fromisoformat(date_string)
    except (ValueError, AttributeError):
        return datetime.datetime.max  # Put invalid dates last


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

        # Sort comments within threads by creation time using cached parsing
        for thread in threads.values():
            thread["comments"].sort(
                key=lambda comment: _parse_datetime_cached(comment.get("created_at", "")),
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
                # Extract suggestion content with improved regex
                pass  # re imported at top
                # Handle suggestions with optional newlines and whitespace variations
                pattern = r"```suggestion\s*(.*?)(?:\n)?```"
                matches = []
                for match in re.finditer(pattern, body, re.DOTALL):
                    # Extract and clean suggestion content
                    suggestion_content = match.group(1).strip()
                    if suggestion_content:  # Only add non-empty suggestions
                        matches.append(suggestion_content)

                suggestions.extend([{
                    "comment_id": comment["id"],
                    "author": comment["author"],
                    "path": comment["path"],
                    "line": comment.get("line"),
                    "suggestion": match,
                    "original_code": self._extract_original_code(comment),
                } for match in matches])

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


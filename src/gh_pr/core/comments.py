"""Comment processing and organization."""

from typing import Dict, List, Any, Optional
from datetime import datetime


class CommentProcessor:
    """Process and organize PR comments."""

    def organize_into_threads(
        self, comments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Organize comments into conversation threads.

        Args:
            comments: List of comment dictionaries

        Returns:
            List of thread dictionaries
        """
        threads = {}

        for comment in comments:
            # Create thread key based on file, line, start_line, and comment id to prevent collisions
            thread_key = f"{comment['path']}:{comment.get('start_line', comment.get('line', 'general'))}:{comment.get('line', 'general')}:{comment.get('id', 'noid')}"

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

        import datetime

        # Sort comments within threads by creation time
        for thread in threads.values():
            def parse_created_at(comment):
                created_at = comment.get("created_at", "")
                try:
                    # Try parsing ISO 8601 format, fallback to empty string
                    return datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except Exception:
                    return datetime.datetime.max  # Put comments with invalid/missing dates last

            thread["comments"].sort(
                key=parse_created_at,
            )

        return list(threads.values())

    def _is_comment_outdated(self, comment: Dict[str, Any]) -> bool:
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
        elif position is None and original_position is None:
            return False  # Cannot determine, assume not outdated
        else:
            return True  # One is missing, mapping is incomplete, consider outdated

        # If position is None, comment is outdated
        return comment.get("position") is None

    def extract_suggestions(
        self, comments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
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
                pattern = r"```suggestion\s*(.*?)(?:\n)?(.*?)\n?```"
                matches = []
                for match in re.finditer(r"```suggestion\s*(.*?)(?:\n)?(.*?)\n?```", body, re.DOTALL):
                    # Combine optional description and suggestion content
                    suggestion_content = (match.group(1) + match.group(2)).strip()
                    matches.append(suggestion_content)
                matches = re.findall(pattern, body, re.DOTALL)

                for match in matches:
                    suggestions.append({
                        "comment_id": comment["id"],
                        "author": comment["author"],
                        "path": comment["path"],
                        "line": comment.get("line"),
                        "suggestion": match.strip(),
                        "original_code": self._extract_original_code(comment),
                    })

        return suggestions

    def _extract_original_code(self, comment: Dict[str, Any]) -> Optional[str]:
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
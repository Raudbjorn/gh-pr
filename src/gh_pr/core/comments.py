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
                    "comments": [],
                }

            threads[thread_key]["comments"].append(comment)

        # Sort comments within threads by creation time
        for thread in threads.values():
            thread["comments"].sort(
                key=lambda c: c.get("created_at", ""),
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
        # Check if position differs from original position
        if comment.get("position") and comment.get("original_position"):
            return comment["position"] != comment["original_position"]

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
                pattern = r"```suggestion\s*\n(.*?)\n```"
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

        # Find the line at the comment position
        for line in lines:
            if line.startswith("+") or line.startswith("-"):
                # This is a changed line
                return line[1:].strip()

        return None
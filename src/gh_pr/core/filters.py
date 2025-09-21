"""Comment filtering logic."""

from typing import Any


class CommentFilter:
    """Filter PR comments based on various criteria."""

    def filter_comments(
        self, threads: list[dict[str, Any]], mode: str = "unresolved"
    ) -> list[dict[str, Any]]:
        """
        Filter comment threads based on mode.

        Args:
            threads: List of thread dictionaries
            mode: Filter mode ('all', 'unresolved', 'resolved_active',
                  'unresolved_outdated', 'current_unresolved')

        Returns:
            Filtered list of threads

        Note:
            If an unrecognized mode is provided, defaults to 'all' behavior
            and returns all threads.
        """
        if mode == "all":
            return threads

        filtered = []

        for thread in threads:
            should_include = False

            if mode == "unresolved":
                # Show all unresolved threads
                should_include = not thread.get("is_resolved", False)
            elif mode == "resolved_active":
                # Show resolved but not outdated
                should_include = (
                    thread.get("is_resolved", False) and
                    not thread.get("is_outdated", False)
                )
            elif mode == "unresolved_outdated":
                # Show unresolved and outdated
                should_include = (
                    not thread.get("is_resolved", False) and
                    thread.get("is_outdated", False)
                )
            elif mode == "current_unresolved":
                # Show unresolved and not outdated
                should_include = (
                    not thread.get("is_resolved", False) and
                    not thread.get("is_outdated", False)
                )
            else:
                # Unknown mode - default to showing all threads (like 'all' mode)
                should_include = True

            if should_include:
                filtered.append(thread)

        return filtered

    def filter_by_author(
        self, threads: list[dict[str, Any]], author: str
    ) -> list[dict[str, Any]]:
        """
        Filter threads by comment author.

        Args:
            threads: List of thread dictionaries
            author: Author username

        Returns:
            Filtered list of threads
        """
        filtered = []

        for thread in threads:
            has_author_comment = any(
                comment.get("author") == author
                for comment in thread.get("comments", [])
            )

            if has_author_comment:
                filtered.append(thread)

        return filtered

    def filter_by_path(
        self, threads: list[dict[str, Any]], path_pattern: str
    ) -> list[dict[str, Any]]:
        """
        Filter threads by file path pattern.

        Args:
            threads: List of thread dictionaries
            path_pattern: Path pattern (supports wildcards)

        Returns:
            Filtered list of threads
        """
        import fnmatch

        filtered = []

        for thread in threads:
            path = thread.get("path", "")
            if fnmatch.fnmatch(path, path_pattern):
                filtered.append(thread)

        return filtered

    def filter_by_keyword(
        self, threads: list[dict[str, Any]], keyword: str
    ) -> list[dict[str, Any]]:
        """
        Filter threads by keyword in comment body.

        Args:
            threads: List of thread dictionaries
            keyword: Keyword to search for (case-insensitive)

        Returns:
            Filtered list of threads
        """
        # No-op on empty/blank keywords
        if not keyword or not keyword.strip():
            return threads

        filtered = []
        keyword_lower = keyword.lower().strip()

        for thread in threads:
            has_keyword = any(
                keyword_lower in comment.get("body", "").lower()
                for comment in thread.get("comments", [])
            )

            if has_keyword:
                filtered.append(thread)

        return filtered

    def get_filter_stats(self, threads: list[dict[str, Any]]) -> dict[str, int]:
        """
        Get statistics about threads.

        Args:
            threads: List of thread dictionaries

        Returns:
            Dictionary with statistics
        """
        stats = {
            "total": len(threads),
            "unresolved": 0,
            "resolved": 0,
            "active": 0,
            "outdated": 0,
        }

        for thread in threads:
            if thread.get("is_resolved", False):
                stats["resolved"] += 1
            else:
                stats["unresolved"] += 1

            # Use XOR logic - threads are either outdated OR active
            if thread.get("is_outdated", False):
                stats["outdated"] += 1
            else:
                stats["active"] += 1

        return stats

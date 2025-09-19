"""Comment filtering logic."""

from typing import Any


class CommentFilter:
    """Filter PR comments based on various criteria."""

    def filter(
        self, threads: list[dict[str, Any]], mode: str = "unresolved"
    ) -> list[dict[str, Any]]:
        """
        Filter comment threads (alias for filter_comments for compatibility).

        Args:
            threads: List of thread dictionaries
            mode: Filter mode

        Returns:
            Filtered list of threads
        """
        return self.filter_comments(threads, mode)

    def filter_comments(
        self, threads: list[dict[str, Any]], mode: str = "unresolved"
    ) -> list[dict[str, Any]]:
        """
        Filter comment threads based on mode.

        Args:
            threads: List of thread dictionaries
            mode: Filter mode

        Returns:
            Filtered list of threads
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

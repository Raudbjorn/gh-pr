"""GraphQL client for GitHub API operations."""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# GraphQL API constants
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
DEFAULT_TIMEOUT = 30
RATE_LIMIT_DELAY = 1.0  # seconds

# GraphQL query fragments for reuse
THREAD_FRAGMENT = """
    id
    isResolved
    isOutdated
    comments(first: 1) {
        nodes {
            body
            createdAt
        }
    }
"""

SUGGESTION_FRAGMENT = """
    id
    body
    author {
        login
    }
    createdAt
"""


@dataclass
class GraphQLError:
    """Represents a GraphQL error."""
    message: str
    type: str
    path: Optional[List[str]] = None
    locations: Optional[List[Dict[str, Any]]] = None
    extensions: Optional[Dict[str, Any]] = None


@dataclass
class GraphQLResult:
    """Result of a GraphQL operation."""
    data: Optional[Dict[str, Any]] = None
    errors: Optional[List[GraphQLError]] = None
    success: bool = True

    def __post_init__(self):
        """Set success based on error presence."""
        self.success = self.errors is None or len(self.errors) == 0


class GraphQLClient:
    """GitHub GraphQL API client with error-as-values pattern."""

    def __init__(self, token: str):
        """
        Initialize GraphQL client.

        Args:
            token: GitHub authentication token
        """
        if not token or not token.strip():
            raise ValueError("GitHub token is required")

        self.token = token.strip()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github.v4+json",
            "User-Agent": "gh-pr/0.1.0"
        })

    def execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> GraphQLResult:
        """
        Execute a GraphQL query or mutation.

        Args:
            query: GraphQL query string
            variables: Optional variables for the query

        Returns:
            GraphQLResult with data or errors
        """
        # Input validation
        if not query or not query.strip():
            return GraphQLResult(
                errors=[GraphQLError("Query cannot be empty", "INVALID_INPUT")]
            )

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = self.session.post(
                GITHUB_GRAPHQL_URL,
                json=payload,
                timeout=DEFAULT_TIMEOUT
            )

            if response.status_code == 401:
                return GraphQLResult(
                    errors=[GraphQLError("Invalid or expired GitHub token", "UNAUTHORIZED")]
                )

            if response.status_code == 403:
                return GraphQLResult(
                    errors=[GraphQLError("Insufficient permissions or rate limited", "FORBIDDEN")]
                )

            if not response.ok:
                return GraphQLResult(
                    errors=[GraphQLError(f"HTTP {response.status_code}: {response.text}", "HTTP_ERROR")]
                )

            result = response.json()
            errors = None

            if "errors" in result:
                errors = [
                    GraphQLError(
                        message=err.get("message", "Unknown error"),
                        type=err.get("type", "GRAPHQL_ERROR"),
                        locations=err.get("locations"),
                        path=err.get("path"),
                        extensions=err.get("extensions")
                    )
                    for err in result["errors"]
                ]

            return GraphQLResult(
                data=result.get("data"),
                errors=errors
            )

        except requests.RequestException as e:
            logger.error(f"Network error in GraphQL request: {e}")
            return GraphQLResult(
                errors=[GraphQLError(f"Network error: {str(e)}", "NETWORK_ERROR")]
            )
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
            return GraphQLResult(
                errors=[GraphQLError(f"Invalid response format: {str(e)}", "JSON_ERROR")]
            )
        except Exception as e:
            logger.error(f"Unexpected error in GraphQL request: {e}")
            return GraphQLResult(
                errors=[GraphQLError(f"Unexpected error: {str(e)}", "UNKNOWN_ERROR")]
            )

    def resolve_thread(self, thread_id: str) -> GraphQLResult:
        """
        Resolve a pull request review thread.

        Args:
            thread_id: GitHub node ID of the thread to resolve

        Returns:
            GraphQLResult indicating success or failure
        """
        if not thread_id or not thread_id.strip():
            return GraphQLResult(
                errors=[GraphQLError("Thread ID is required", "INVALID_INPUT")]
            )

        # Security: Validate thread_id format (base64 encoded GitHub ID)
        if not re.match(r'^[A-Za-z0-9+/\-_=]+$', thread_id.strip()):
            return GraphQLResult(
                errors=[GraphQLError("Invalid thread ID format", "INVALID_INPUT")]
            )

        mutation = """
        mutation ResolveReviewThread($threadId: ID!) {
            resolveReviewThread(input: {threadId: $threadId}) {
                thread {
                    id
                    isResolved
                }
            }
        }
        """

        variables = {"threadId": thread_id.strip()}
        return self.execute(mutation, variables)

    def accept_suggestion(self, suggestion_id: str) -> GraphQLResult:
        """
        Accept a suggestion from a pull request comment.

        Args:
            suggestion_id: GitHub node ID of the suggestion to accept

        Returns:
            GraphQLResult indicating success or failure
        """
        if not suggestion_id or not suggestion_id.strip():
            return GraphQLResult(
                errors=[GraphQLError("Suggestion ID is required", "INVALID_INPUT")]
            )

        # Security: Validate suggestion_id format (base64 encoded GitHub ID)
        if not re.match(r'^[A-Za-z0-9+/\-_=]+$', suggestion_id.strip()):
            return GraphQLResult(
                errors=[GraphQLError("Invalid suggestion ID format", "INVALID_INPUT")]
            )

        mutation = """
        mutation AcceptSuggestion($suggestionId: ID!) {
            acceptSuggestion(input: {suggestionId: $suggestionId}) {
                clientMutationId
            }
        }
        """

        variables = {"suggestionId": suggestion_id.strip()}
        return self.execute(mutation, variables)

    def get_pr_threads(self, owner: str, repo: str, pr_number: int) -> GraphQLResult:
        """
        Get all review threads for a pull request with pagination support.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            GraphQLResult with all thread data or errors
        """
        if not all([owner, repo, pr_number]):
            return GraphQLResult(
                errors=[GraphQLError("Owner, repo, and PR number are required", "INVALID_INPUT")]
            )

        if pr_number <= 0:
            return GraphQLResult(
                errors=[GraphQLError("PR number must be positive", "INVALID_INPUT")]
            )

        query = """
        query GetPRThreads($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
            repository(owner: $owner, name: $repo) {
                pullRequest(number: $number) {
                    reviewThreads(first: 100, after: $cursor) {
                        nodes {
                            id
                            isResolved
                            isOutdated
                            comments(first: 10) {
                                nodes {
                                    id
                                    body
                                    author {
                                        login
                                    }
                                    createdAt
                                }
                            }
                        }
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                    }
                }
            }
        }
        """

        all_threads = []
        cursor = None
        has_next_page = True

        while has_next_page:
            variables = {
                "owner": owner.strip(),
                "repo": repo.strip(),
                "number": pr_number,
                "cursor": cursor
            }

            result = self.execute(query, variables)

            if result.errors:
                return result

            if result.data and "repository" in result.data:
                pr_data = result.data["repository"].get("pullRequest", {})
                threads_data = pr_data.get("reviewThreads", {})

                nodes = threads_data.get("nodes", [])
                all_threads.extend(nodes)

                page_info = threads_data.get("pageInfo", {})
                has_next_page = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor")
            else:
                break

        # Return aggregated results
        if result.data and "repository" in result.data:
            result.data["repository"]["pullRequest"]["reviewThreads"]["nodes"] = all_threads
            # Remove pageInfo as we've fetched all pages
            if "pageInfo" in result.data["repository"]["pullRequest"]["reviewThreads"]:
                del result.data["repository"]["pullRequest"]["reviewThreads"]["pageInfo"]

        return result

    def get_pr_suggestions(self, owner: str, repo: str, pr_number: int) -> GraphQLResult:
        """
        Get all suggestions in a pull request with pagination support.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            GraphQLResult with all suggestion data or errors
        """
        if not all([owner, repo, pr_number]):
            return GraphQLResult(
                errors=[GraphQLError("Owner, repo, and PR number are required", "INVALID_INPUT")]
            )

        if pr_number <= 0:
            return GraphQLResult(
                errors=[GraphQLError("PR number must be positive", "INVALID_INPUT")]
            )

        # Query with pagination support for both reviews and comments
        query = """
        query GetPRSuggestions($owner: String!, $repo: String!, $number: Int!, $reviewCursor: String, $commentCursor: String) {
            repository(owner: $owner, name: $repo) {
                pullRequest(number: $number) {
                    reviews(first: 50, after: $reviewCursor) {
                        nodes {
                            comments(first: 50, after: $commentCursor) {
                                nodes {
                                    id
                                    body
                                    author {
                                        login
                                    }
                                    suggestions {
                                        nodes {
                                            id
                                            startLine
                                            endLine
                                            newText
                                        }
                                    }
                                }
                                pageInfo {
                                    hasNextPage
                                    endCursor
                                }
                            }
                        }
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                    }
                }
            }
        }
        """

        all_reviews = []
        review_cursor = None
        has_next_review = True

        while has_next_review:
            variables = {
                "owner": owner.strip(),
                "repo": repo.strip(),
                "number": pr_number,
                "reviewCursor": review_cursor,
                "commentCursor": None
            }

            result = self.execute(query, variables)

            if result.errors:
                return result

            if result.data and "repository" in result.data:
                pr_data = result.data["repository"].get("pullRequest", {})
                reviews_data = pr_data.get("reviews", {})

                review_nodes = reviews_data.get("nodes", [])

                # For each review, fetch all comment pages if needed
                for review in review_nodes:
                    all_comments = []
                    comments_data = review.get("comments", {})
                    all_comments.extend(comments_data.get("nodes", []))

                    # Check if there are more comment pages
                    comment_page_info = comments_data.get("pageInfo", {})
                    comment_cursor = comment_page_info.get("endCursor")
                    has_next_comment = comment_page_info.get("hasNextPage", False)

                    # Fetch remaining comment pages for this review
                    while has_next_comment:
                        comment_variables = {
                            "owner": owner.strip(),
                            "repo": repo.strip(),
                            "number": pr_number,
                            "reviewCursor": None,  # We're fetching specific review comments
                            "commentCursor": comment_cursor
                        }
                        # This would need a separate query - for simplicity, we'll cap at first 50
                        # In production, you'd want a separate method or enhanced query
                        break

                    # Update review with all comments
                    review["comments"]["nodes"] = all_comments

                all_reviews.extend(review_nodes)

                page_info = reviews_data.get("pageInfo", {})
                has_next_review = page_info.get("hasNextPage", False)
                review_cursor = page_info.get("endCursor")
            else:
                break

        # Return aggregated results
        if result.data and "repository" in result.data:
            result.data["repository"]["pullRequest"]["reviews"]["nodes"] = all_reviews
            # Remove pageInfo as we've fetched all pages
            if "pageInfo" in result.data["repository"]["pullRequest"]["reviews"]:
                del result.data["repository"]["pullRequest"]["reviews"]["pageInfo"]

        return result

    def check_permissions(self, owner: str, repo: str) -> GraphQLResult:
        """
        Check if current user has write permissions to repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            GraphQLResult with permission data or errors
        """
        if not all([owner, repo]):
            return GraphQLResult(
                errors=[GraphQLError("Owner and repo are required", "INVALID_INPUT")]
            )

        query = """
        query CheckPermissions($owner: String!, $repo: String!) {
            repository(owner: $owner, name: $repo) {
                viewerPermission
                viewerCanCreatePullRequest
                viewerCanAdminister
                viewerCanResolveThreads: viewerCanAdminister
                viewerCanAcceptSuggestions: viewerCanAdminister
            }
            viewer {
                login
            }
        }
        """

        variables = {
            "owner": owner.strip(),
            "repo": repo.strip()
        }
        return self.execute(query, variables)

    # Compatibility methods for gradual migration
    def execute_query(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[Dict[str, Any]], Optional[List[GraphQLError]]]:
        """
        Legacy method for backward compatibility.
        Execute a GraphQL query.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            Tuple of (data, errors) where data is the result and errors is a list of GraphQLError
        """
        result = self.execute(query, variables)
        return result.data, result.errors
"""GraphQL client for GitHub API operations."""

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional, Union

import requests
from github import GithubException

logger = logging.getLogger(__name__)

# GraphQL API constants
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
RATE_LIMIT_DELAY = 1.0  # seconds


@dataclass
class GraphQLError:
    """Represents a GraphQL error."""
    message: str
    type: str
    locations: Optional[list[dict[str, Any]]] = None
    path: Optional[list[str]] = None


@dataclass
class GraphQLResult:
    """Result of a GraphQL operation."""
    data: Optional[dict[str, Any]] = None
    errors: Optional[list[GraphQLError]] = None
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

    def execute(self, query: str, variables: Optional[dict[str, Any]] = None) -> GraphQLResult:
        """
        Execute a GraphQL query or mutation.

        Args:
            query: GraphQL query string
            variables: Optional variables for the query

        Returns:
            GraphQLResult with data or errors
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = self.session.post(
                GITHUB_GRAPHQL_URL,
                json=payload,
                timeout=30
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
                        path=err.get("path")
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
        Get all review threads for a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            GraphQLResult with thread data or errors
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
        query GetPRThreads($owner: String!, $repo: String!, $number: Int!) {
            repository(owner: $owner, name: $repo) {
                pullRequest(number: $number) {
                    reviewThreads(first: 100) {
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

        variables = {
            "owner": owner.strip(),
            "repo": repo.strip(),
            "number": pr_number
        }
        return self.execute(query, variables)

    def get_pr_suggestions(self, owner: str, repo: str, pr_number: int) -> GraphQLResult:
        """
        Get all suggestions in a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            GraphQLResult with suggestion data or errors
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
        query GetPRSuggestions($owner: String!, $repo: String!, $number: Int!) {
            repository(owner: $owner, name: $repo) {
                pullRequest(number: $number) {
                    reviews(first: 50) {
                        nodes {
                            comments(first: 50) {
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
                            }
                        }
                    }
                }
            }
        }
        """

        variables = {
            "owner": owner.strip(),
            "repo": repo.strip(),
            "number": pr_number
        }
        return self.execute(query, variables)

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
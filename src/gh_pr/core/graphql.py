"""GraphQL client for GitHub API operations requiring GraphQL."""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
import requests
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Constants for GraphQL operations
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
GRAPHQL_ENDPOINT = "https://api.github.com/graphql"

# GraphQL query fragments
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
    """Represents a GraphQL API error."""
    message: str
    type: str
    path: Optional[List[str]] = None
    extensions: Optional[Dict[str, Any]] = None


class GraphQLClient:
    """Client for GitHub GraphQL API operations."""

    def __init__(self, token: str):
        """
        Initialize GraphQL client.

        Args:
            token: GitHub personal access token
        """
        if not token:
            raise ValueError("Token is required for GraphQL client")

        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github.v4+json"
        })

    def execute_query(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[Dict[str, Any]], Optional[List[GraphQLError]]]:
        """
        Execute a GraphQL query.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            Tuple of (data, errors) where data is the result and errors is a list of GraphQLError
        """
        # Input validation
        if not query or not query.strip():
            return None, [GraphQLError("Query cannot be empty", "validation")]

        payload = {
            "query": query,
            "variables": variables or {}
        }

        try:
            response = self.session.post(
                GRAPHQL_ENDPOINT,
                json=payload,
                timeout=DEFAULT_TIMEOUT
            )

            # Handle HTTP errors
            if response.status_code == 401:
                return None, [GraphQLError("Authentication failed. Check your token.", "auth")]
            elif response.status_code == 403:
                return None, [GraphQLError("Permission denied. Check token scopes.", "permission")]
            elif response.status_code >= 500:
                return None, [GraphQLError(f"GitHub server error: {response.status_code}", "server")]

            response.raise_for_status()

            # Parse response
            result = response.json()

            # Handle GraphQL errors
            if "errors" in result:
                errors = [
                    GraphQLError(
                        message=err.get("message", "Unknown error"),
                        type=err.get("type", "unknown"),
                        path=err.get("path"),
                        extensions=err.get("extensions")
                    )
                    for err in result["errors"]
                ]
                return result.get("data"), errors

            return result.get("data"), None

        except requests.RequestException as e:
            logger.error(f"Network error during GraphQL request: {e}")
            return None, [GraphQLError(f"Network error: {str(e)}", "network")]
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse GraphQL response: {e}")
            return None, [GraphQLError(f"Invalid response format: {str(e)}", "parse")]
        except Exception as e:
            logger.error(f"Unexpected error in GraphQL request: {e}")
            return None, [GraphQLError(f"Unexpected error: {str(e)}", "unknown")]

    def resolve_thread(self, thread_id: str) -> Tuple[bool, Optional[str]]:
        """
        Resolve a review thread.

        Args:
            thread_id: GitHub thread ID

        Returns:
            Tuple of (success, error_message)
        """
        # Input validation
        if not thread_id:
            return False, "Thread ID is required"

        # Security: Validate thread_id format (should be base64 encoded GitHub ID)
        # Base64 can contain A-Z, a-z, 0-9, +, /, and = for padding
        # GitHub also uses - and _ in URL-safe base64
        import re
        if not re.match(r'^[A-Za-z0-9+/\-_=]+$', thread_id):
            return False, "Invalid thread ID format"

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

        variables = {"threadId": thread_id}

        data, errors = self.execute_query(mutation, variables)

        if errors:
            error_msg = "; ".join(err.message for err in errors)
            logger.error(f"Failed to resolve thread {thread_id}: {error_msg}")
            return False, error_msg

        if not data:
            return False, "No data returned from API"

        try:
            resolved = data["resolveReviewThread"]["thread"]["isResolved"]
            return resolved, None
        except (KeyError, TypeError) as e:
            logger.error(f"Unexpected response structure: {e}")
            return False, f"Unexpected response format: {str(e)}"

    def accept_suggestion(self, suggestion_id: str) -> Tuple[bool, Optional[str]]:
        """
        Accept a code suggestion.

        Args:
            suggestion_id: GitHub suggestion comment ID

        Returns:
            Tuple of (success, error_message)
        """
        # Input validation
        if not suggestion_id:
            return False, "Suggestion ID is required"

        # Security: Validate suggestion_id format (base64 encoded GitHub ID)
        # Base64 can contain A-Z, a-z, 0-9, +, /, and = for padding
        # GitHub also uses - and _ in URL-safe base64
        if not re.match(r'^[A-Za-z0-9+/\-_=]+$', suggestion_id):
            return False, "Invalid suggestion ID format"

        mutation = """
        mutation AcceptSuggestion($suggestionId: ID!) {
            applySuggestion(input: {suggestionId: $suggestionId}) {
                success
                message
            }
        }
        """

        variables = {"suggestionId": suggestion_id}

        data, errors = self.execute_query(mutation, variables)

        if errors:
            error_msg = "; ".join(err.message for err in errors)
            logger.error(f"Failed to accept suggestion {suggestion_id}: {error_msg}")
            return False, error_msg

        if not data:
            return False, "No data returned from API"

        try:
            result = data["applySuggestion"]
            if result["success"]:
                return True, None
            else:
                return False, result.get("message", "Failed to apply suggestion")
        except (KeyError, TypeError) as e:
            logger.error(f"Unexpected response structure: {e}")
            return False, f"Unexpected response format: {str(e)}"

    def get_pr_threads(
        self,
        owner: str,
        repo: str,
        pr_number: int
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Get all review threads for a PR.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            Tuple of (threads, error_message)
        """
        # Input validation
        if not all([owner, repo, pr_number]):
            return None, "Owner, repo, and PR number are required"

        if not isinstance(pr_number, int) or pr_number <= 0:
            return None, "PR number must be a positive integer"

        query = f"""
        query GetPRThreads($owner: String!, $repo: String!, $number: Int!, $cursor: String) {{
            repository(owner: $owner, name: $repo) {{
                pullRequest(number: $number) {{
                    reviewThreads(first: 100, after: $cursor) {{
                        nodes {{
                            {THREAD_FRAGMENT}
                        }}
                        pageInfo {{
                            hasNextPage
                            endCursor
                        }}
                    }}
                }}
            }}
        }}
        """

        all_threads = []
        cursor = None

        while True:
            variables = {
                "owner": owner,
                "repo": repo,
                "number": pr_number,
                "cursor": cursor
            }

            data, errors = self.execute_query(query, variables)

            if errors:
                error_msg = "; ".join(err.message for err in errors)
                return None, error_msg

            if not data:
                return None, "No data returned from API"

            try:
                review_threads = data["repository"]["pullRequest"]["reviewThreads"]
                threads = review_threads["nodes"]
                all_threads.extend(threads)

                page_info = review_threads["pageInfo"]
                if not page_info["hasNextPage"]:
                    break
                cursor = page_info["endCursor"]

            except (KeyError, TypeError) as e:
                logger.error(f"Unexpected response structure: {e}")
                return None, f"Unexpected response format: {str(e)}"

        return all_threads, None

    def get_pr_suggestions(
        self,
        owner: str,
        repo: str,
        pr_number: int
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Get all suggestions in a PR.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            Tuple of (suggestions, error_message)
        """
        # Input validation
        if not all([owner, repo, pr_number]):
            return None, "Owner, repo, and PR number are required"

        if not isinstance(pr_number, int) or pr_number <= 0:
            return None, "PR number must be a positive integer"

        query = f"""
        query GetPRSuggestions($owner: String!, $repo: String!, $number: Int!, $cursor: String) {{
            repository(owner: $owner, name: $repo) {{
                pullRequest(number: $number) {{
                    reviewComments(first: 100, after: $cursor) {{
                        nodes {{
                            {SUGGESTION_FRAGMENT}
                            hasSuggestion: body
                        }}
                        pageInfo {{
                            hasNextPage
                            endCursor
                        }}
                    }}
                }}
            }}
        }}
        """

        all_suggestions = []
        cursor = None

        while True:
            variables = {
                "owner": owner,
                "repo": repo,
                "number": pr_number,
                "cursor": cursor
            }

            data, errors = self.execute_query(query, variables)

            if errors:
                error_msg = "; ".join(err.message for err in errors)
                return None, error_msg

            if not data:
                return None, "No data returned from API"

            try:
                review_comments = data["repository"]["pullRequest"]["reviewComments"]
                comments = review_comments["nodes"]

                # Filter for comments with suggestions (contain "```suggestion")
                suggestions = [
                    comment for comment in comments
                    if "```suggestion" in comment.get("hasSuggestion", "")
                ]
                all_suggestions.extend(suggestions)

                page_info = review_comments["pageInfo"]
                if not page_info["hasNextPage"]:
                    break
                cursor = page_info["endCursor"]

            except (KeyError, TypeError) as e:
                logger.error(f"Unexpected response structure: {e}")
                return None, f"Unexpected response format: {str(e)}"

        return all_suggestions, None

    def check_permissions(self, owner: str, repo: str) -> Dict[str, bool]:
        """
        Check user permissions for a repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Dictionary of permission types and their status
        """
        query = """
        query CheckPermissions($owner: String!, $repo: String!) {
            repository(owner: $owner, name: $repo) {
                viewerCanAdminister
                viewerCanCreateProjects
                viewerCanSubscribe
                viewerCanUpdateTopics
                viewerPermission
                viewerCanResolveThreads: viewerCanAdminister
                viewerCanAcceptSuggestions: viewerCanAdminister
            }
        }
        """

        variables = {
            "owner": owner,
            "repo": repo
        }

        data, errors = self.execute_query(query, variables)

        if errors or not data:
            # Return safe defaults if we can't check permissions
            return {
                "can_resolve_threads": False,
                "can_accept_suggestions": False,
                "can_administer": False,
                "permission_level": "NONE"
            }

        try:
            repo_data = data["repository"]
            return {
                "can_resolve_threads": repo_data.get("viewerCanResolveThreads", False),
                "can_accept_suggestions": repo_data.get("viewerCanAcceptSuggestions", False),
                "can_administer": repo_data.get("viewerCanAdminister", False),
                "permission_level": repo_data.get("viewerPermission", "NONE")
            }
        except (KeyError, TypeError):
            return {
                "can_resolve_threads": False,
                "can_accept_suggestions": False,
                "can_administer": False,
                "permission_level": "NONE"
            }
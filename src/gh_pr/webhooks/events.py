"""
Webhook event definitions and types.

Provides event type enumeration and event data structures
for GitHub webhook processing.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime


class EventType(Enum):
    """GitHub webhook event types."""

    # PR events
    PULL_REQUEST = "pull_request"
    PULL_REQUEST_REVIEW = "pull_request_review"
    PULL_REQUEST_REVIEW_COMMENT = "pull_request_review_comment"
    PULL_REQUEST_REVIEW_THREAD = "pull_request_review_thread"

    # Issue events
    ISSUES = "issues"
    ISSUE = "issues"  # Alias for compatibility
    ISSUE_COMMENT = "issue_comment"

    # Repository events
    PUSH = "push"
    RELEASE = "release"
    DEPLOYMENT = "deployment"
    DEPLOYMENT_STATUS = "deployment_status"

    # Workflow events
    WORKFLOW_RUN = "workflow_run"
    WORKFLOW_JOB = "workflow_job"
    CHECK_RUN = "check_run"
    CHECK_SUITE = "check_suite"

    # Other events
    STATUS = "status"
    PING = "ping"
    META = "meta"
    OTHER = "other"  # For unknown/unhandled event types


@dataclass
class WebhookEvent:
    """
    Represents a GitHub webhook event.

    Attributes:
        type: Event type
        delivery_id: Unique delivery ID from GitHub
        payload: Event payload data
        headers: HTTP headers from webhook request
        received_at: Timestamp when event was received
    """

    type: EventType
    delivery_id: str
    payload: Dict[str, Any]
    headers: Dict[str, str] = field(default_factory=dict)
    received_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def action(self) -> Optional[str]:
        """Get event action if available."""
        return self.payload.get('action')

    @property
    def repository(self) -> Optional[Dict[str, Any]]:
        """Get repository information if available."""
        return self.payload.get('repository')

    @property
    def sender(self) -> Optional[Dict[str, Any]]:
        """Get sender (user) information."""
        return self.payload.get('sender')

    @property
    def pull_request(self) -> Optional[Dict[str, Any]]:
        """Get pull request data for PR events."""
        return self.payload.get('pull_request')

    @property
    def review(self) -> Optional[Dict[str, Any]]:
        """Get review data for review events."""
        return self.payload.get('review')

    @property
    def comment(self) -> Optional[Dict[str, Any]]:
        """Get comment data for comment events."""
        return self.payload.get('comment')

    def is_pr_event(self) -> bool:
        """Check if this is a PR-related event."""
        return self.type in {
            EventType.PULL_REQUEST,
            EventType.PULL_REQUEST_REVIEW,
            EventType.PULL_REQUEST_REVIEW_COMMENT,
            EventType.PULL_REQUEST_REVIEW_THREAD
        }
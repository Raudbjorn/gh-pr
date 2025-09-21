"""
Webhook event handlers.

Provides base handler class and specific event processors
for different GitHub webhook events.
"""

import logging
from typing import Dict, Any, List, Optional, Callable, Awaitable
from abc import ABC, abstractmethod
import asyncio
from datetime import datetime, timedelta

from .events import WebhookEvent, EventType
from ..utils.notifications import NotificationManager

logger = logging.getLogger(__name__)


class EventHandler(ABC):
    """Abstract base class for event handlers."""

    @abstractmethod
    async def can_handle(self, event: WebhookEvent) -> bool:
        """Check if this handler can process the event."""
        pass

    @abstractmethod
    async def handle(self, event: WebhookEvent) -> Any:
        """Process the event."""
        pass


class PREventHandler(EventHandler):
    """Handler for pull request events."""

    def __init__(self, notification_manager: Optional[NotificationManager] = None):
        """Initialize PR event handler."""
        self.notification_manager = notification_manager

    async def can_handle(self, event: WebhookEvent) -> bool:
        """Check if this is a PR event we can handle."""
        return event.is_pr_event()

    async def handle(self, event: WebhookEvent) -> Dict[str, Any]:
        """
        Process PR event.

        Args:
            event: PR webhook event

        Returns:
            Processing result
        """
        result = {
            'event_type': event.type.value,
            'action': event.action,
            'processed_at': datetime.utcnow().isoformat()
        }

        # Extract PR information
        pr = event.pull_request
        if not pr:
            logger.warning("PR event without pull_request data")
            return result

        # Build notification message
        repo_name = event.repository.get('full_name', 'Unknown') if event.repository else 'Unknown'
        pr_number = pr.get('number', '?')
        pr_title = pr.get('title', 'No title')
        author = event.sender.get('login', 'Unknown') if event.sender else 'Unknown'

        message_parts = []

        if event.type == EventType.PULL_REQUEST:
            action = event.action
            if action == 'opened':
                message_parts.append(f"🆕 New PR #{pr_number} opened by {author}")
            elif action == 'closed':
                if pr.get('merged'):
                    message_parts.append(f"✅ PR #{pr_number} merged")
                else:
                    message_parts.append(f"❌ PR #{pr_number} closed without merge")
            elif action == 'reopened':
                message_parts.append(f"🔄 PR #{pr_number} reopened")
            elif action == 'ready_for_review':
                message_parts.append(f"👀 PR #{pr_number} ready for review")
            else:
                message_parts.append(f"PR #{pr_number} {action}")

        elif event.type == EventType.PULL_REQUEST_REVIEW:
            review = event.review
            if review:
                state = review.get('state', 'unknown')
                reviewer = review.get('user', {}).get('login', 'Unknown')
                if state == 'approved':
                    message_parts.append(f"✅ PR #{pr_number} approved by {reviewer}")
                elif state == 'changes_requested':
                    message_parts.append(f"🔧 Changes requested on PR #{pr_number} by {reviewer}")
                elif state == 'commented':
                    message_parts.append(f"💬 Review comment on PR #{pr_number} by {reviewer}")

        elif event.type == EventType.PULL_REQUEST_REVIEW_COMMENT:
            comment = event.comment
            if comment:
                commenter = comment.get('user', {}).get('login', 'Unknown')
                message_parts.append(f"💬 New review comment on PR #{pr_number} by {commenter}")

        # Add PR title and repository
        if message_parts:
            message_parts.append(f'"{pr_title}"')
            message_parts.append(f"in {repo_name}")

            # Send notification if manager available
            if self.notification_manager:
                try:
                    await self.notification_manager.notify(
                        title="GitHub PR Update",
                        message=" ".join(message_parts),
                        pr_number=pr_number,
                        repo=repo_name
                    )
                    result['notification_sent'] = True
                except Exception as e:
                    logger.error(f"Failed to send notification: {e}")
                    result['notification_error'] = str(e)

        result['message'] = " ".join(message_parts) if message_parts else "No message generated"
        return result


class WebhookHandler:
    """
    Main webhook handler that routes events to specific handlers.

    Manages event processing, statistics, and handler chain.
    """

    def __init__(self):
        """Initialize webhook handler."""
        self.handlers: List[EventHandler] = []
        self._statistics = {
            'total_events': 0,
            'events_by_type': {},
            'errors': 0,
            'last_event': None
        }
        self._plugins: Dict[str, Callable] = {}

    def add_handler(self, handler: EventHandler) -> None:
        """
        Add an event handler to the processing chain.

        Args:
            handler: Event handler to add
        """
        self.handlers.append(handler)

    def register_plugin(
        self,
        name: str,
        handler: Callable[[WebhookEvent], Awaitable[Any]]
    ) -> None:
        """
        Register a plugin handler.

        Args:
            name: Plugin name
            handler: Async function to handle events
        """
        self._plugins[name] = handler
        logger.info(f"Registered webhook plugin: {name}")

    async def handle(self, event: WebhookEvent) -> Dict[str, Any]:
        """
        Process webhook event through handler chain.

        Args:
            event: Webhook event to process

        Returns:
            Processing results
        """
        # Update statistics
        self._statistics['total_events'] += 1
        event_type = event.type.value
        self._statistics['events_by_type'][event_type] = \
            self._statistics['events_by_type'].get(event_type, 0) + 1
        self._statistics['last_event'] = datetime.utcnow().isoformat()

        results = {
            'event_id': event.delivery_id,
            'event_type': event_type,
            'handlers_executed': []
        }

        try:
            # Process through handler chain
            for handler in self.handlers:
                if await handler.can_handle(event):
                    handler_name = handler.__class__.__name__
                    try:
                        result = await handler.handle(event)
                        results['handlers_executed'].append({
                            'handler': handler_name,
                            'result': result
                        })
                    except Exception as e:
                        logger.error(f"Handler {handler_name} error: {e}", exc_info=True)
                        results['handlers_executed'].append({
                            'handler': handler_name,
                            'error': str(e)
                        })

            # Process through plugins
            plugin_tasks = []
            for plugin_name, plugin_handler in self._plugins.items():
                task = asyncio.create_task(self._run_plugin(plugin_name, plugin_handler, event))
                plugin_tasks.append(task)

            if plugin_tasks:
                plugin_results = await asyncio.gather(*plugin_tasks, return_exceptions=True)
                results['plugins'] = []
                for plugin_name, result in zip(self._plugins.keys(), plugin_results):
                    if isinstance(result, Exception):
                        results['plugins'].append({
                            'plugin': plugin_name,
                            'error': str(result)
                        })
                    else:
                        results['plugins'].append({
                            'plugin': plugin_name,
                            'result': result
                        })

        except Exception as e:
            self._statistics['errors'] += 1
            logger.error(f"Event handling error: {e}", exc_info=True)
            results['error'] = str(e)

        return results

    async def _run_plugin(
        self,
        name: str,
        handler: Callable,
        event: WebhookEvent
    ) -> Any:
        """
        Run a plugin handler with error handling.

        Args:
            name: Plugin name
            handler: Plugin handler function
            event: Event to process

        Returns:
            Plugin result or error
        """
        try:
            return await handler(event)
        except Exception as e:
            logger.error(f"Plugin {name} error: {e}", exc_info=True)
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """Get handler statistics."""
        return self._statistics.copy()

    # Compatibility methods for tests
    def register_handler(self, event_type: EventType, handler: Callable) -> None:
        """Register a handler for a specific event type (test compatibility)."""
        self._plugins[f"{event_type.value}_{id(handler)}"] = handler

    def unregister_handler(self, event_type: EventType, handler: Callable) -> None:
        """Unregister a handler for a specific event type (test compatibility)."""
        key = f"{event_type.value}_{id(handler)}"
        if key in self._plugins:
            del self._plugins[key]

    async def handle_event(self, event: WebhookEvent) -> List[Any]:
        """Handle an event and return list of results (test compatibility)."""
        results = []

        # Run all registered handlers for this event type
        for key, handler in list(self._plugins.items()):
            if key.startswith(f"{event.type.value}_"):
                try:
                    result = await handler(event)
                    results.append(result)
                except Exception as e:
                    # Return dict with error key for test compatibility
                    results.append({'error': str(e)})

        return results

    def parse_github_event(self, headers: Dict[str, str], payload: Dict[str, Any]) -> WebhookEvent:
        """Parse GitHub webhook headers and payload into WebhookEvent."""
        from .events import EventType, WebhookEvent

        # Map GitHub event types to our EventType enum
        github_event = headers.get('X-GitHub-Event', '')
        event_type_map = {
            'pull_request': EventType.PULL_REQUEST,
            'issues': EventType.ISSUE,  # Use ISSUE for test compatibility
            'issue_comment': EventType.ISSUE_COMMENT,
            'pull_request_review': EventType.PULL_REQUEST_REVIEW,
            'pull_request_review_comment': EventType.PULL_REQUEST_REVIEW_COMMENT,
            'push': EventType.PUSH,
            'release': EventType.RELEASE,
            'workflow_run': EventType.WORKFLOW_RUN,
        }

        event_type = event_type_map.get(github_event, EventType.OTHER)
        action = payload.get('action', '')
        delivery_id = headers.get('X-GitHub-Delivery', '')

        return WebhookEvent(
            type=event_type,
            action=action,
            payload=payload,
            delivery_id=delivery_id
        )
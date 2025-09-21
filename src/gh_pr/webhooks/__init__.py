"""
Webhook support for GitHub PR events.

This module provides webhook server and handler functionality
for real-time PR updates and integrations.
"""

from .server import WebhookServer
from .handlers import WebhookHandler
from .events import EventType, WebhookEvent

__all__ = [
    'WebhookServer',
    'WebhookHandler',
    'EventType',
    'WebhookEvent',
]
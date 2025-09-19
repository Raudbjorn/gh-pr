"""
Unit tests for webhook functionality.

Tests webhook server, handlers, and event processing.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import asyncio
import json
import hmac
import hashlib
from aiohttp import web
from datetime import datetime, timedelta

from gh_pr.webhooks.server import WebhookServer
from gh_pr.webhooks.handler import WebhookHandler
from gh_pr.webhooks.events import WebhookEvent, EventType


class TestWebhookServer(unittest.TestCase):
    """Test webhook server functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Mock()
        self.config.port = 8080
        self.config.secret = "test_secret"
        self.config.rate_limit = 100
        self.config.rate_window = 60

        self.server = WebhookServer(self.config)
        self.server.handler = Mock()

    def test_verify_signature_valid(self):
        """Test signature verification with valid signature."""
        payload = b'{"test": "data"}'
        secret = "test_secret"

        # Generate correct signature
        expected_sig = 'sha256=' + hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Create server with test secret
        config = Mock(secret=secret)
        server = WebhookServer(config)

        # Verify signature
        self.assertTrue(server._verify_signature(payload, expected_sig))

    def test_verify_signature_invalid(self):
        """Test signature verification with invalid signature."""
        payload = b'{"test": "data"}'
        invalid_sig = 'sha256=invalid_signature'

        self.assertFalse(self.server._verify_signature(payload, invalid_sig))

    def test_rate_limit_check_within_limit(self):
        """Test rate limiting allows requests within limit."""
        client_id = "127.0.0.1"

        # First request should pass
        self.assertTrue(self.server._check_rate_limit(client_id))

        # Additional requests within limit should pass
        for _ in range(10):
            self.assertTrue(self.server._check_rate_limit(client_id))

    def test_rate_limit_check_exceeds_limit(self):
        """Test rate limiting blocks excessive requests."""
        client_id = "127.0.0.1"

        # Fill up the rate limit
        for _ in range(self.config.rate_limit):
            self.server._check_rate_limit(client_id)

        # Next request should be blocked
        self.assertFalse(self.server._check_rate_limit(client_id))

    def test_rate_limit_window_expiry(self):
        """Test rate limit resets after window expires."""
        client_id = "127.0.0.1"
        now = datetime.now()

        # Add requests with old timestamps
        old_time = now - timedelta(seconds=self.config.rate_window + 1)
        self.server._request_history[client_id] = [old_time] * self.config.rate_limit

        # New request should pass as old ones expired
        self.assertTrue(self.server._check_rate_limit(client_id))

    @patch('aiohttp.web.Application')
    @patch('aiohttp.web.run_app')
    async def test_start_server(self, mock_run_app, mock_app):
        """Test server startup."""
        await self.server.start()

        mock_app.assert_called_once()
        mock_run_app.assert_called_once()


class TestWebhookHandler(unittest.TestCase):
    """Test webhook handler functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.handler = WebhookHandler()

    def test_register_handler(self):
        """Test handler registration."""
        mock_handler = Mock()

        self.handler.register_handler(EventType.PULL_REQUEST, mock_handler)
        self.assertIn(mock_handler, self.handler._handlers[EventType.PULL_REQUEST])

    def test_unregister_handler(self):
        """Test handler unregistration."""
        mock_handler = Mock()

        self.handler.register_handler(EventType.PULL_REQUEST, mock_handler)
        self.handler.unregister_handler(EventType.PULL_REQUEST, mock_handler)

        self.assertNotIn(mock_handler, self.handler._handlers[EventType.PULL_REQUEST])

    async def test_handle_event(self):
        """Test event handling dispatch."""
        mock_handler = AsyncMock(return_value={'status': 'ok'})
        event = WebhookEvent(
            type=EventType.PULL_REQUEST,
            action='opened',
            payload={'test': 'data'}
        )

        self.handler.register_handler(EventType.PULL_REQUEST, mock_handler)
        results = await self.handler.handle_event(event)

        mock_handler.assert_called_once_with(event)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], {'status': 'ok'})

    async def test_handle_event_with_error(self):
        """Test event handling with handler error."""
        mock_handler = AsyncMock(side_effect=Exception("Handler error"))
        event = WebhookEvent(
            type=EventType.PULL_REQUEST,
            action='opened',
            payload={'test': 'data'}
        )

        self.handler.register_handler(EventType.PULL_REQUEST, mock_handler)
        results = await self.handler.handle_event(event)

        # Should handle error gracefully
        self.assertEqual(len(results), 1)
        self.assertIn('error', results[0])

    def test_parse_github_event(self):
        """Test GitHub event parsing."""
        headers = {
            'X-GitHub-Event': 'pull_request',
            'X-GitHub-Delivery': 'test-delivery-id'
        }
        payload = {
            'action': 'opened',
            'pull_request': {'id': 123}
        }

        event = self.handler.parse_github_event(headers, payload)

        self.assertEqual(event.type, EventType.PULL_REQUEST)
        self.assertEqual(event.action, 'opened')
        self.assertEqual(event.payload, payload)
        self.assertEqual(event.delivery_id, 'test-delivery-id')


class TestWebhookEvent(unittest.TestCase):
    """Test webhook event model."""

    def test_event_creation(self):
        """Test event creation with all fields."""
        event = WebhookEvent(
            type=EventType.PULL_REQUEST,
            action='opened',
            payload={'test': 'data'},
            delivery_id='test-id',
            signature='test-sig'
        )

        self.assertEqual(event.type, EventType.PULL_REQUEST)
        self.assertEqual(event.action, 'opened')
        self.assertEqual(event.payload, {'test': 'data'})
        self.assertEqual(event.delivery_id, 'test-id')
        self.assertEqual(event.signature, 'test-sig')
        self.assertIsNotNone(event.timestamp)

    def test_event_serialization(self):
        """Test event to dict conversion."""
        event = WebhookEvent(
            type=EventType.ISSUE,
            action='closed',
            payload={'issue': {'id': 456}}
        )

        event_dict = event.to_dict()

        self.assertEqual(event_dict['type'], 'issue')
        self.assertEqual(event_dict['action'], 'closed')
        self.assertEqual(event_dict['payload'], {'issue': {'id': 456}})
        self.assertIn('timestamp', event_dict)


if __name__ == '__main__':
    unittest.main()
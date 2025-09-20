"""
Integration tests for webhook system.

Tests complete webhook flow from server to event handling.
"""

import unittest
import asyncio
import json
import hmac
import hashlib
from unittest.mock import Mock, patch, AsyncMock
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from gh_pr.webhooks.server import WebhookServer
from gh_pr.webhooks.handlers import WebhookHandler
from gh_pr.webhooks.events import EventType, WebhookEvent


class TestWebhookIntegration(AioHTTPTestCase):
    """Integration tests for webhook system."""

    async def get_application(self):
        """Create test application."""
        # Create webhook config
        self.config = Mock()
        self.config.port = 8080
        self.config.secret = "test_secret_key"
        self.config.rate_limit = 100
        self.config.rate_window = 60

        # Create server and handler
        self.webhook_handler = WebhookHandler()
        self.server = WebhookServer(self.config)
        self.server.handler = self.webhook_handler

        # Register test handler
        self.test_handler_called = False
        self.test_handler_event = None

        async def test_handler(event):
            self.test_handler_called = True
            self.test_handler_event = event
            return {'status': 'handled', 'event_id': event.delivery_id}

        self.webhook_handler.register_handler(EventType.PULL_REQUEST, test_handler)

        # Create app
        app = web.Application()
        app.router.add_post('/webhook', self.server._handle_webhook)
        return app

    def generate_signature(self, payload: bytes) -> str:
        """Generate valid webhook signature."""
        return 'sha256=' + hmac.new(
            self.config.secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

    @unittest_run_loop
    async def test_valid_webhook_request(self):
        """Test valid webhook request processing."""
        payload = {
            'action': 'opened',
            'pull_request': {
                'id': 123,
                'title': 'Test PR',
                'user': {'login': 'testuser'}
            }
        }
        payload_bytes = json.dumps(payload).encode()
        signature = self.generate_signature(payload_bytes)

        headers = {
            'X-Hub-Signature-256': signature,
            'X-GitHub-Event': 'pull_request',
            'X-GitHub-Delivery': 'test-delivery-123'
        }

        resp = await self.client.post(
            '/webhook',
            data=payload_bytes,
            headers=headers
        )

        self.assertEqual(resp.status, 200)

        # Verify handler was called
        self.assertTrue(self.test_handler_called)
        self.assertIsNotNone(self.test_handler_event)
        self.assertEqual(self.test_handler_event.type, EventType.PULL_REQUEST)
        self.assertEqual(self.test_handler_event.action, 'opened')

    @unittest_run_loop
    async def test_invalid_signature(self):
        """Test webhook request with invalid signature."""
        payload = {'test': 'data'}
        payload_bytes = json.dumps(payload).encode()

        headers = {
            'X-Hub-Signature-256': 'sha256=invalid_signature',
            'X-GitHub-Event': 'pull_request',
            'X-GitHub-Delivery': 'test-delivery-456'
        }

        resp = await self.client.post(
            '/webhook',
            data=payload_bytes,
            headers=headers
        )

        self.assertEqual(resp.status, 401)
        self.assertFalse(self.test_handler_called)

    @unittest_run_loop
    async def test_rate_limiting(self):
        """Test rate limiting functionality."""
        payload = {'test': 'data'}
        payload_bytes = json.dumps(payload).encode()
        signature = self.generate_signature(payload_bytes)

        headers = {
            'X-Hub-Signature-256': signature,
            'X-GitHub-Event': 'push',
            'X-GitHub-Delivery': 'test-delivery-789'
        }

        # Make requests up to the rate limit
        for i in range(self.config.rate_limit):
            resp = await self.client.post(
                '/webhook',
                data=payload_bytes,
                headers={**headers, 'X-GitHub-Delivery': f'delivery-{i}'}
            )
            self.assertEqual(resp.status, 200)

        # Next request should be rate limited
        resp = await self.client.post(
            '/webhook',
            data=payload_bytes,
            headers={**headers, 'X-GitHub-Delivery': 'delivery-over-limit'}
        )
        self.assertEqual(resp.status, 429)

    @unittest_run_loop
    async def test_multiple_handlers(self):
        """Test multiple handlers for same event type."""
        handler1_called = False
        handler2_called = False

        async def handler1(event):
            nonlocal handler1_called
            handler1_called = True
            return {'handler': 1}

        async def handler2(event):
            nonlocal handler2_called
            handler2_called = True
            return {'handler': 2}

        self.webhook_handler.register_plugin('handler1', handler1)
        self.webhook_handler.register_plugin('handler2', handler2)

        payload = {'action': 'opened', 'issue': {'id': 456}}
        payload_bytes = json.dumps(payload).encode()
        signature = self.generate_signature(payload_bytes)

        headers = {
            'X-Hub-Signature-256': signature,
            'X-GitHub-Event': 'issues',
            'X-GitHub-Delivery': 'multi-handler-test'
        }

        resp = await self.client.post(
            '/webhook',
            data=payload_bytes,
            headers=headers
        )

        self.assertEqual(resp.status, 200)
        self.assertTrue(handler1_called)
        self.assertTrue(handler2_called)


class TestWebhookEventFlow(unittest.TestCase):
    """Test complete webhook event flow."""

    def setUp(self):
        """Set up test fixtures."""
        self.handler = WebhookHandler()

    def test_event_type_mapping(self):
        """Test GitHub event type to internal mapping."""
        test_cases = [
            ('pull_request', EventType.PULL_REQUEST),
            ('issues', EventType.ISSUE),
            ('issue_comment', EventType.ISSUE_COMMENT),
            ('pull_request_review', EventType.PULL_REQUEST_REVIEW),
            ('pull_request_review_comment', EventType.PULL_REQUEST_REVIEW_COMMENT),
            ('push', EventType.PUSH),
            ('release', EventType.RELEASE),
            ('workflow_run', EventType.WORKFLOW_RUN),
            ('unknown_event', EventType.OTHER)
        ]

        for github_event, expected_type in test_cases:
            headers = {'X-GitHub-Event': github_event}
            payload = {'action': 'test'}

            event = self.handler.parse_github_event(headers, payload)
            self.assertEqual(event.type, expected_type)

    async def test_error_handling_in_handler(self):
        """Test error handling in event handlers."""
        error_handler = AsyncMock(side_effect=Exception("Handler error"))
        success_handler = AsyncMock(return_value={'status': 'ok'})

        self.handler.register_handler(EventType.PUSH, error_handler)
        self.handler.register_handler(EventType.PUSH, success_handler)

        event = WebhookEvent(
            type=EventType.PUSH,
            action='push',
            payload={'commits': []}
        )

        results = await self.handler.handle_event(event)

        # Should have results from both handlers
        self.assertEqual(len(results), 2)

        # Error handler result should contain error
        self.assertTrue(any('error' in r for r in results))

        # Success handler should still be called
        success_handler.assert_called_once()

    async def test_handler_registration_and_removal(self):
        """Test handler lifecycle management."""
        handler1 = AsyncMock(return_value={'id': 1})
        handler2 = AsyncMock(return_value={'id': 2})

        # Register handlers
        self.handler.register_handler(EventType.ISSUE, handler1)
        self.handler.register_handler(EventType.ISSUE, handler2)

        event = WebhookEvent(
            type=EventType.ISSUE,
            action='opened',
            payload={}
        )

        # Both handlers should be called
        results = await self.handler.handle_event(event)
        self.assertEqual(len(results), 2)

        # Unregister one handler
        self.handler.unregister_handler(EventType.ISSUE, handler1)

        # Reset mocks
        handler1.reset_mock()
        handler2.reset_mock()

        # Only handler2 should be called
        results = await self.handler.handle_event(event)
        self.assertEqual(len(results), 1)
        handler1.assert_not_called()
        handler2.assert_called_once()


if __name__ == '__main__':
    unittest.main()
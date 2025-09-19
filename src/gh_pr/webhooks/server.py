"""
Webhook server implementation for GitHub events.

Provides a lightweight HTTP server to receive and process GitHub webhooks
with security validation and event routing.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from pathlib import Path
import secrets

from aiohttp import web
try:
    import aiohttp_cors
    HAS_CORS = True
except ImportError:
    HAS_CORS = False

from .events import WebhookEvent, EventType
from .handlers import WebhookHandler

logger = logging.getLogger(__name__)

# Security constants
SIGNATURE_HEADER = 'X-Hub-Signature-256'
EVENT_HEADER = 'X-GitHub-Event'
DELIVERY_HEADER = 'X-GitHub-Delivery'
MAX_PAYLOAD_SIZE = 10 * 1024 * 1024  # 10MB max payload


@dataclass
class WebhookConfig:
    """Configuration for webhook server."""

    host: str = '127.0.0.1'
    port: int = 8080
    secret: Optional[str] = None
    ssl_cert: Optional[Path] = None
    ssl_key: Optional[Path] = None
    allowed_events: List[EventType] = None
    rate_limit: int = 100  # requests per minute

    def __post_init__(self):
        """Initialize with defaults if not provided."""
        if self.allowed_events is None:
            self.allowed_events = list(EventType)
        if not self.secret:
            # Generate a secure random secret if none provided
            self.secret = secrets.token_urlsafe(32)
            logger.warning(f"Generated webhook secret: {self.secret}")


class WebhookServer:
    """
    Async webhook server for GitHub events.

    Provides secure webhook endpoint with HMAC validation,
    rate limiting, and event routing.
    """

    def __init__(self, config: WebhookConfig, handler: WebhookHandler):
        """
        Initialize webhook server.

        Args:
            config: Server configuration
            handler: Event handler instance
        """
        self.config = config
        self.handler = handler
        self.app = web.Application(
            client_max_size=MAX_PAYLOAD_SIZE
        )
        self._setup_routes()
        if HAS_CORS:
            self._setup_cors()
        else:
            logger.warning("aiohttp_cors not installed, CORS support disabled")
        self._rate_limiter: Dict[str, List[float]] = {}

    def _setup_routes(self) -> None:
        """Configure server routes."""
        self.app.router.add_post('/webhook', self._handle_webhook)
        self.app.router.add_get('/health', self._health_check)
        self.app.router.add_get('/status', self._status_endpoint)

    def _setup_cors(self) -> None:
        """Configure CORS for web integrations."""
        if not HAS_CORS:
            return

        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
            )
        })

        for route in list(self.app.router.routes()):
            cors.add(route)

    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify webhook signature using HMAC.

        Args:
            payload: Request body bytes
            signature: GitHub signature header

        Returns:
            True if signature is valid
        """
        if not self.config.secret:
            return True  # No secret configured, skip validation

        expected = 'sha256=' + hmac.new(
            self.config.secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected, signature)

    def _check_rate_limit(self, client_ip: str) -> bool:
        """
        Check if client has exceeded rate limit.

        Args:
            client_ip: Client IP address

        Returns:
            True if within rate limit
        """
        import time
        now = time.time()
        minute_ago = now - 60

        # Clean old entries and count recent requests
        if client_ip not in self._rate_limiter:
            self._rate_limiter[client_ip] = []

        self._rate_limiter[client_ip] = [
            t for t in self._rate_limiter[client_ip]
            if t > minute_ago
        ]

        if len(self._rate_limiter[client_ip]) >= self.config.rate_limit:
            return False

        self._rate_limiter[client_ip].append(now)
        return True

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """
        Handle incoming webhook request.

        Args:
            request: Incoming HTTP request

        Returns:
            HTTP response
        """
        try:
            # Rate limiting
            client_ip = request.remote
            if not self._check_rate_limit(client_ip):
                logger.warning(f"Rate limit exceeded for {client_ip}")
                return web.Response(status=429, text="Rate limit exceeded")

            # Read and validate payload
            payload = await request.read()

            # Verify signature
            signature = request.headers.get(SIGNATURE_HEADER, '')
            if not self._verify_signature(payload, signature):
                logger.warning(f"Invalid signature from {client_ip}")
                return web.Response(status=401, text="Invalid signature")

            # Parse event type
            event_type_str = request.headers.get(EVENT_HEADER, '')
            try:
                event_type = EventType(event_type_str)
            except ValueError:
                logger.info(f"Unsupported event type: {event_type_str}")
                return web.Response(status=200, text="Event type not supported")

            # Check if event is allowed
            if event_type not in self.config.allowed_events:
                logger.debug(f"Event type {event_type} not in allowed list")
                return web.Response(status=200, text="Event filtered")

            # Parse payload
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON payload: {e}")
                return web.Response(status=400, text="Invalid JSON")

            # Create event object
            event = WebhookEvent(
                type=event_type,
                delivery_id=request.headers.get(DELIVERY_HEADER, ''),
                payload=data,
                headers=dict(request.headers)
            )

            # Process event asynchronously
            asyncio.create_task(self._process_event(event))

            return web.Response(status=200, text="OK")

        except Exception as e:
            logger.error(f"Webhook handling error: {e}", exc_info=True)
            return web.Response(status=500, text="Internal server error")

    async def _process_event(self, event: WebhookEvent) -> None:
        """
        Process webhook event asynchronously.

        Args:
            event: Webhook event to process
        """
        try:
            await self.handler.handle(event)
        except Exception as e:
            logger.error(f"Event processing error: {e}", exc_info=True)

    async def _health_check(self, request: web.Request) -> web.Response:
        """
        Health check endpoint.

        Returns:
            200 OK if server is healthy
        """
        return web.Response(text="OK")

    async def _status_endpoint(self, request: web.Request) -> web.Response:
        """
        Status endpoint with server statistics.

        Returns:
            JSON response with server status
        """
        status = {
            'status': 'running',
            'config': {
                'host': self.config.host,
                'port': self.config.port,
                'allowed_events': [e.value for e in self.config.allowed_events],
                'rate_limit': self.config.rate_limit,
            },
            'statistics': self.handler.get_statistics()
        }
        return web.json_response(status)

    async def start(self) -> None:
        """Start webhook server."""
        runner = web.AppRunner(self.app)
        await runner.setup()

        # Configure SSL if certificates provided
        ssl_context = None
        if self.config.ssl_cert and self.config.ssl_key:
            import ssl
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(
                str(self.config.ssl_cert),
                str(self.config.ssl_key)
            )

        site = web.TCPSite(
            runner,
            self.config.host,
            self.config.port,
            ssl_context=ssl_context
        )

        await site.start()

        protocol = 'https' if ssl_context else 'http'
        logger.info(
            f"Webhook server started at {protocol}://{self.config.host}:{self.config.port}/webhook"
        )

        # Keep server running
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await runner.cleanup()
            logger.info("Webhook server stopped")
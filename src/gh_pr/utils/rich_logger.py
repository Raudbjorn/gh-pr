"""
Universal Rich Logger for gh-pr
===============================

A comprehensive logging utility with rich formatting, timezone support,
and session tracking for the gh-pr application.

Features:
- Rich console formatting with colors and structured output
- Atlantic/Reykjavik timezone standardization
- Session tracking with unique UUIDs
- Stack trace capture with detailed context
- Thread and process information
- File logging with rotation
- Function tracing decorator
- Security features (masking sensitive environment variables)
"""

import logging
import logging.handlers
import os
import sys
import threading
import traceback
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pytz
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install as install_rich_traceback

# Install rich traceback handling globally
install_rich_traceback(show_locals=True)

# Configuration constants
DEFAULT_TIMEZONE = pytz.timezone('Atlantic/Reykjavik')
DEFAULT_LOG_LEVEL = logging.INFO
MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5

# Generate unique session ID for this process
SESSION_ID = str(uuid.uuid4())


class RichLogger:
    """
    Universal logger with rich formatting and comprehensive features.

    Provides structured logging with:
    - Rich console output
    - File logging with rotation
    - Session tracking
    - Security-aware environment variable masking
    - Thread and process information
    """

    def __init__(
        self,
        name: str = "gh-pr",
        level: int = DEFAULT_LOG_LEVEL,
        timezone: pytz.BaseTzInfo = DEFAULT_TIMEZONE,
        log_file: Optional[Union[str, Path]] = None,
        console_output: bool = True,
        file_output: bool = True
    ):
        """
        Initialize the RichLogger.

        Args:
            name: Logger name (typically module name)
            level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            timezone: Timezone for log timestamps
            log_file: Path to log file (optional)
            console_output: Enable console logging
            file_output: Enable file logging
        """
        self.name = name
        self.timezone = timezone
        self.session_id = SESSION_ID

        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # Prevent duplicate handlers
        if self.logger.handlers:
            self.logger.handlers.clear()

        # Setup console handler with rich formatting
        if console_output:
            self._setup_console_handler()

        # Setup file handler with rotation
        if file_output:
            self._setup_file_handler(log_file)

    def _setup_console_handler(self) -> None:
        """Setup rich console handler for colorized output."""
        console = Console(stderr=True)
        console_handler = RichHandler(
            console=console,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            markup=True
        )

        # Rich handler format
        console_format = "%(message)s"
        console_handler.setFormatter(logging.Formatter(console_format))

        self.logger.addHandler(console_handler)

    def _setup_file_handler(self, log_file: Optional[Union[str, Path]] = None) -> None:
        """Setup rotating file handler for persistent logging."""
        if log_file is None:
            # Default log file location
            log_dir = Path.home() / ".cache" / "gh-pr" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "gh-pr.log"

        # Rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=MAX_LOG_FILE_SIZE,
            backupCount=BACKUP_COUNT,
            encoding='utf-8'
        )

        # File format with full context
        file_format = (
            "%(asctime)s | %(levelname)8s | %(name)s | "
            f"PID:{os.getpid()} | TID:{threading.get_ident()} | "
            f"SID:{self.session_id[:8]} | %(message)s"
        )

        formatter = logging.Formatter(file_format)
        formatter.converter = lambda *args: datetime.now(self.timezone).timetuple()
        file_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)

    def _get_caller_info(self) -> Dict[str, Any]:
        """Get information about the calling function."""
        frame = sys._getframe(3)  # Go up the stack to the actual caller
        return {
            'filename': os.path.basename(frame.f_code.co_filename),
            'function': frame.f_code.co_name,
            'lineno': frame.f_lineno,
            'module': frame.f_globals.get('__name__', 'unknown')
        }

    def _mask_sensitive_env_vars(self, text: str) -> str:
        """
        Mask sensitive environment variables in log text.

        Args:
            text: Text that might contain sensitive information

        Returns:
            Text with sensitive values masked
        """
        sensitive_patterns = [
            'GH_TOKEN', 'GITHUB_TOKEN', 'TOKEN', 'PASSWORD', 'SECRET', 'KEY',
            'API_KEY', 'ACCESS_TOKEN', 'REFRESH_TOKEN', 'AUTH_TOKEN'
        ]

        masked_text = text
        for var in os.environ:
            if any(pattern in var.upper() for pattern in sensitive_patterns):
                value = os.environ[var]
                if value and len(value) > 4:
                    # Show first 4 chars and mask the rest
                    masked_value = value[:4] + '*' * (len(value) - 4)
                    masked_text = masked_text.replace(value, masked_value)

        return masked_text

    def _format_message(self, message: str, **kwargs) -> str:
        """Format message with caller info and security masking."""
        caller = self._get_caller_info()

        # Format the message with context
        formatted_msg = f"[{caller['filename']}:{caller['lineno']}] {caller['function']}() | {message}"

        # Add any additional context
        if kwargs:
            context_parts = [f"{k}={v}" for k, v in kwargs.items()]
            formatted_msg += f" | {', '.join(context_parts)}"

        # Apply security masking
        return self._mask_sensitive_env_vars(formatted_msg)

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message with context."""
        self.logger.debug(self._format_message(message, **kwargs))

    def info(self, message: str, **kwargs) -> None:
        """Log info message with context."""
        self.logger.info(self._format_message(message, **kwargs))

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message with context."""
        self.logger.warning(self._format_message(message, **kwargs))

    def error(self, message: str, **kwargs) -> None:
        """Log error message with context."""
        self.logger.error(self._format_message(message, **kwargs))

    def critical(self, message: str, **kwargs) -> None:
        """Log critical message with context."""
        self.logger.critical(self._format_message(message, **kwargs))

    def exception(self, message: str, **kwargs) -> None:
        """Log exception with full traceback."""
        exc_info = sys.exc_info()
        if exc_info[0] is not None:
            # Format the exception with rich traceback
            tb_lines = traceback.format_exception(*exc_info)
            tb_str = ''.join(tb_lines)
            full_message = f"{message}\n{tb_str}"
        else:
            full_message = message

        self.logger.error(self._format_message(full_message, **kwargs))

    def get_child(self, suffix: str) -> 'RichLogger':
        """Create a child logger with the same configuration."""
        child_name = f"{self.name}.{suffix}"
        child_logger = RichLogger(
            name=child_name,
            level=self.logger.level,
            timezone=self.timezone,
            console_output=False,  # Inherit from parent
            file_output=False      # Inherit from parent
        )
        return child_logger


def traced(logger: Optional[RichLogger] = None):
    """
    Decorator for automatic function entry/exit logging.

    Args:
        logger: RichLogger instance to use (optional)

    Returns:
        Decorated function with entry/exit logging
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Use provided logger or create a default one
            log = logger or get_logger(func.__module__)

            # Log function entry
            args_repr = [repr(a) for a in args[:3]]  # Limit to first 3 args
            kwargs_repr = [f"{k}={v!r}" for k, v in list(kwargs.items())[:3]]
            signature = ", ".join(args_repr + kwargs_repr)
            if len(args) > 3 or len(kwargs) > 3:
                signature += ", ..."

            log.debug(f"ENTER {func.__name__}({signature})")

            try:
                result = func(*args, **kwargs)
                log.debug(f"EXIT {func.__name__}() -> {type(result).__name__}")
                return result
            except Exception as e:
                log.error(f"EXCEPTION {func.__name__}() -> {e.__class__.__name__}: {e}")
                raise

        return wrapper
    return decorator


# Global logger registry
_loggers: Dict[str, RichLogger] = {}
_default_logger: Optional[RichLogger] = None


def get_logger(name: str = "gh-pr", **kwargs) -> RichLogger:
    """
    Get or create a logger instance.

    Args:
        name: Logger name
        **kwargs: Additional arguments for RichLogger

    Returns:
        RichLogger instance
    """
    global _loggers, _default_logger

    if name not in _loggers:
        _loggers[name] = RichLogger(name, **kwargs)

    # Set as default if it's the main logger
    if name == "gh-pr" and _default_logger is None:
        _default_logger = _loggers[name]

    return _loggers[name]


def get_default_logger() -> RichLogger:
    """Get the default gh-pr logger."""
    global _default_logger
    if _default_logger is None:
        _default_logger = get_logger("gh-pr")
    return _default_logger


def setup_logging(
    level: int = DEFAULT_LOG_LEVEL,
    log_file: Optional[Union[str, Path]] = None,
    console_output: bool = True,
    file_output: bool = True
) -> RichLogger:
    """
    Setup application-wide logging configuration.

    Args:
        level: Logging level
        log_file: Path to log file
        console_output: Enable console logging
        file_output: Enable file logging

    Returns:
        Configured main logger
    """
    return get_logger(
        "gh-pr",
        level=level,
        log_file=log_file,
        console_output=console_output,
        file_output=file_output
    )


# Convenience functions for quick logging
def debug(message: str, **kwargs) -> None:
    """Quick debug logging."""
    get_default_logger().debug(message, **kwargs)


def info(message: str, **kwargs) -> None:
    """Quick info logging."""
    get_default_logger().info(message, **kwargs)


def warning(message: str, **kwargs) -> None:
    """Quick warning logging."""
    get_default_logger().warning(message, **kwargs)


def error(message: str, **kwargs) -> None:
    """Quick error logging."""
    get_default_logger().error(message, **kwargs)


def critical(message: str, **kwargs) -> None:
    """Quick critical logging."""
    get_default_logger().critical(message, **kwargs)


def exception(message: str, **kwargs) -> None:
    """Quick exception logging."""
    get_default_logger().exception(message, **kwargs)
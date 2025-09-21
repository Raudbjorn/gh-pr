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

import inspect
import logging
import logging.handlers
import os
import re
import socket
import sys
import threading
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Optional, Union

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

# Pre-compiled regex patterns for performance optimization
SENSITIVE_ENV_PATTERNS = [
    'GH_TOKEN', 'GITHUB_TOKEN', 'TOKEN', 'PASSWORD', 'SECRET', 'KEY',
    'API_KEY', 'ACCESS_TOKEN', 'REFRESH_TOKEN', 'AUTH_TOKEN'
]


class TimezoneAwareFormatter(logging.Formatter):
    """Custom formatter that handles timezone-aware timestamps."""

    def __init__(self, fmt=None, datefmt=None, style='%', tz=None):
        """
        Initialize the timezone-aware formatter.

        Args:
            fmt: Log format string
            datefmt: Date format string
            style: Format style ('%', '{', '$')
            tz: Timezone for timestamp formatting
        """
        super().__init__(fmt, datefmt, style)
        self.tz = tz

    def formatTime(self, record, datefmt=None):  # noqa: N802
        """
        Format the timestamp with timezone awareness.

        Args:
            record: Log record
            datefmt: Date format string

        Returns:
            str: Formatted timestamp
        """
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if self.tz:
            dt = dt.astimezone(self.tz)
        s = dt.strftime(datefmt) if datefmt else dt.isoformat()
        return s


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
        file_output: bool = True,
        syslog_output: bool = False,
        syslog_address: Optional[tuple[str, int]] = None,
        syslog_facility: int = logging.handlers.SysLogHandler.LOG_USER
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
        self.console_output = console_output
        self.file_output = file_output
        self.syslog_output = syslog_output
        self.syslog_address = syslog_address
        self.syslog_facility = syslog_facility

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

        # Setup syslog handler
        if syslog_output:
            self._setup_syslog_handler()

    def _setup_console_handler(self) -> None:
        """
        Set up rich console handler for colorized output.

        Creates a RichHandler instance with full traceback support
        and local variable display. Outputs to stderr by default.

        Returns:
            None
        """
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
        """
        Set up rotating file handler for persistent logging.

        Creates a RotatingFileHandler with automatic rotation when
        the log file exceeds MAX_LOG_FILE_SIZE. Keeps BACKUP_COUNT
        number of backup files.

        Args:
            log_file: Path to log file. If None, uses default location
                     ~/.cache/gh-pr/logs/gh-pr.log

        Returns:
            None
        """
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

        class TimezoneAwareFormatter(logging.Formatter):
            def __init__(self, fmt=None, datefmt=None, style='%', tz=None):
                super().__init__(fmt, datefmt, style)
                self.tz = tz

            def formatTime(self, record, datefmt=None):  # noqa: N802
                dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
                if self.tz:
                    dt = dt.astimezone(self.tz)
                s = dt.strftime(datefmt) if datefmt else dt.isoformat()
                return s

        formatter = TimezoneAwareFormatter(file_format, tz=self.timezone)
        file_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)

    def _setup_syslog_handler(self) -> None:
        """
        Set up syslog handler for system logging integration.

        Creates a SysLogHandler that can send logs to local or remote
        syslog servers. Useful for centralized logging infrastructure.

        Returns:
            None

        Note:
            If syslog_address is None, attempts to use local syslog.
            On macOS/Linux, this is typically /dev/log or /var/run/syslog.
            On Windows, this will use UDP to localhost:514.
        """
        try:
            if self.syslog_address:
                # Remote syslog server
                handler = logging.handlers.SysLogHandler(
                    address=self.syslog_address,
                    facility=self.syslog_facility,
                    socktype=socket.SOCK_DGRAM
                )
            else:
                # Local syslog - let SysLogHandler determine the address
                handler = logging.handlers.SysLogHandler(
                    facility=self.syslog_facility
                )

            # Syslog format - simpler than file format
            syslog_format = (
                f"%(name)s[{os.getpid()}]: "
                "%(levelname)s - %(message)s"
            )

            handler.setFormatter(logging.Formatter(syslog_format))
            self.logger.addHandler(handler)
        except Exception as e:
            # If syslog setup fails, log a warning but don't crash
            if self.console_output or self.file_output:
                self.logger.warning(f"Failed to setup syslog handler: {e}")

    def _get_caller_info(self) -> dict[str, Any]:
        """
        Get information about the calling function.

        Walks the stack to find the first frame outside of the
        logging module, providing accurate caller context.

        Returns:
            dict: Contains 'filename', 'function', 'lineno', and 'module'
                 keys with information about the calling code.
        """
        # Walk the stack to find first frame outside of logging module
        current_file = inspect.getfile(inspect.currentframe())
        for frame_info in inspect.stack()[1:]:
            frame_file = frame_info.filename
            if frame_file != current_file and not frame_file.endswith('logging/__init__.py'):
                return {
                    'filename': os.path.basename(frame_info.filename),
                    'function': frame_info.function,
                    'lineno': frame_info.lineno,
                    'module': inspect.getmodulename(frame_info.filename) or 'unknown'
                }
        # Fallback if we can't find a proper frame - use last available frame
        stack = inspect.stack()
        if len(stack) > 1:
            frame_info = stack[-1]  # Use the outermost frame
            return {
                'filename': os.path.basename(frame_info.filename),
                'function': frame_info.function,
                'lineno': frame_info.lineno,
                'module': inspect.getmodulename(frame_info.filename) or 'unknown'
            }
        # Ultimate fallback
        return {
            'filename': 'unknown',
            'function': 'unknown',
            'lineno': 0,
            'module': 'unknown'
        }

    def _mask_sensitive_env_vars(self, text: str) -> str:
        """
        Mask sensitive environment variables in log text.

        Uses pre-compiled regex patterns for optimal performance and caches
        compiled patterns to avoid recompilation on every call.

        Args:
            text: Text that might contain sensitive information

        Returns:
            Text with sensitive values masked
        """
        if not hasattr(self, '_compiled_patterns'):
            self._compiled_patterns = {}

        masked_text = text
        for var, value in os.environ.items():
            if any(pattern in var.upper() for pattern in SENSITIVE_ENV_PATTERNS) and value and len(value) > 4:
                # Cache compiled patterns to avoid recompilation
                cache_key = f"{var}_{len(value)}"
                if cache_key not in self._compiled_patterns:
                    escaped_value = re.escape(value)
                    self._compiled_patterns[cache_key] = {
                        'standalone': re.compile(rf'\b{escaped_value}\b'),
                        'assignment': re.compile(rf'({re.escape(var)}=){escaped_value}'),
                        'masked_value': value[:4] + '*' * (len(value) - 4)
                    }

                patterns = self._compiled_patterns[cache_key]
                masked_value = patterns['masked_value']

                # Use compiled patterns for better performance
                def replacement(match, mv=masked_value):
                    return match.group(1) + mv

                masked_text = patterns['assignment'].sub(replacement, masked_text)
                masked_text = patterns['standalone'].sub(masked_value, masked_text)

        return masked_text

    def _format_message(self, message: str, **kwargs) -> str:
        """
        Format message with caller info and security masking.

        Combines the message with caller context information and
        applies security masking to prevent sensitive data leakage.

        Args:
            message: The log message to format
            **kwargs: Additional context key-value pairs to include

        Returns:
            str: Formatted message with context and masked sensitive data
        """
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
        """
        Log a debug-level message with context.

        Debug messages are typically used for detailed diagnostic
        information useful during development and troubleshooting.

        Args:
            message: The debug message to log
            **kwargs: Additional context key-value pairs

        Returns:
            None
        """
        self.logger.debug(self._format_message(message, **kwargs))

    def info(self, message: str, **kwargs) -> None:
        """
        Log an info-level message with context.

        Info messages indicate normal program flow and significant
        events that are not errors.

        Args:
            message: The informational message to log
            **kwargs: Additional context key-value pairs

        Returns:
            None
        """
        self.logger.info(self._format_message(message, **kwargs))

    def warning(self, message: str, **kwargs) -> None:
        """
        Log a warning-level message with context.

        Warning messages indicate potentially harmful situations
        that should be addressed but don't prevent program execution.

        Args:
            message: The warning message to log
            **kwargs: Additional context key-value pairs

        Returns:
            None
        """
        self.logger.warning(self._format_message(message, **kwargs))

    def error(self, message: str, **kwargs) -> None:
        """
        Log an error-level message with context.

        Error messages indicate error conditions that might still
        allow the application to continue running.

        Args:
            message: The error message to log
            **kwargs: Additional context key-value pairs

        Returns:
            None
        """
        self.logger.error(self._format_message(message, **kwargs))

    def critical(self, message: str, **kwargs) -> None:
        """
        Log a critical-level message with context.

        Critical messages indicate severe error conditions that
        will likely cause the program to abort.

        Args:
            message: The critical message to log
            **kwargs: Additional context key-value pairs

        Returns:
            None
        """
        self.logger.critical(self._format_message(message, **kwargs))

    def exception(self, message: str, **kwargs) -> None:
        """
        Log an exception with full traceback.

        This method should be called from within an exception handler
        to capture the current exception context. The rich handler will
        format the traceback with syntax highlighting and local variables.

        Args:
            message: The exception message to log
            **kwargs: Additional context key-value pairs

        Returns:
            None

        Note:
            Must be called from within an except block to capture
            the exception information.
        """
        # Let the rich handler format the exception with its superior formatting
        self.logger.error(self._format_message(message, **kwargs), exc_info=True)

    def get_child(self, suffix: str) -> 'RichLogger':
        """
        Create a child logger with the same configuration.

        The child logger inherits all output settings (console_output,
        file_output, syslog_output) from the parent logger.

        Args:
            suffix: String to append to parent logger name

        Returns:
            RichLogger: New child logger instance

        Example:
            >>> parent = RichLogger("myapp")
            >>> child = parent.get_child("module")
            >>> # child.name will be "myapp.module"
        """
        child_name = f"{self.name}.{suffix}"
        return RichLogger(
            name=child_name,
            level=self.logger.level,
            timezone=self.timezone,
            console_output=self.console_output,
            file_output=self.file_output,
            syslog_output=self.syslog_output,
            syslog_address=self.syslog_address,
            syslog_facility=self.syslog_facility
        )


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

            # Log function entry with secure argument representation
            def safe_repr(obj, max_len=50):
                """Create a safe, truncated representation of an object."""
                try:
                    repr_str = repr(obj)
                    if len(repr_str) > max_len:
                        repr_str = repr_str[:max_len-3] + "..."
                    # Apply security masking
                    return log._mask_sensitive_env_vars(repr_str)
                except Exception:
                    return f"<{type(obj).__name__}>"

            args_repr = [safe_repr(a) for a in args[:3]]  # Limit to first 3 args
            kwargs_repr = [f"{k}={safe_repr(v)}" for k, v in list(kwargs.items())[:3]]
            signature = ", ".join(args_repr + kwargs_repr)
            if len(args) > 3 or len(kwargs) > 3:
                signature += ", ..."

            log.debug(f"ENTER {func.__name__}({signature})")

            try:
                result = func(*args, **kwargs)
                log.debug(f"EXIT {func.__name__}() -> {type(result).__name__}")
                return result
            except Exception:
                log.exception(f"EXCEPTION in {func.__name__}()")
                raise

        return wrapper
    return decorator


# Global logger registry with thread safety
_loggers: dict[str, RichLogger] = {}
_default_logger: Optional[RichLogger] = None
_logger_lock = threading.Lock()


def get_logger(name: str = "gh-pr", **kwargs) -> RichLogger:
    """
    Get or create a logger instance (thread-safe).

    Args:
        name: Logger name
        **kwargs: Additional arguments for RichLogger

    Returns:
        RichLogger instance
    """
    global _loggers, _default_logger

    # Fast path: return existing logger without lock
    if name in _loggers:
        return _loggers[name]

    # Slow path: create new logger with lock
    with _logger_lock:
        # Double-check pattern
        if name not in _loggers:
            _loggers[name] = RichLogger(name, **kwargs)

        # Set as default if it's the main logger
        if name == "gh-pr" and _default_logger is None:
            _default_logger = _loggers[name]

        return _loggers[name]


def get_default_logger() -> RichLogger:
    """
    Get the default gh-pr logger instance.

    Retrieves the global default logger, creating it if it doesn't
    exist. Thread-safe through internal locking.

    Returns:
        RichLogger: The default logger instance
    """
    global _default_logger
    if _default_logger is None:
        _default_logger = get_logger("gh-pr")
    return _default_logger


def setup_logging(
    level: int = DEFAULT_LOG_LEVEL,
    log_file: Optional[Union[str, Path]] = None,
    console_output: bool = True,
    file_output: bool = True,
    syslog_output: bool = False,
    syslog_address: Optional[tuple[str, int]] = None,
    syslog_facility: int = logging.handlers.SysLogHandler.LOG_USER,
    timezone: Optional[pytz.BaseTzInfo] = None
) -> RichLogger:
    """
    Set up application-wide logging configuration.

    Configures the main application logger with specified output
    handlers and formatting options. This should typically be
    called once at application startup.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (None for default location)
        console_output: Enable rich console output to stderr
        file_output: Enable rotating file output
        syslog_output: Enable syslog output
        syslog_address: Tuple of (host, port) for remote syslog,
                       None for local syslog
        syslog_facility: Syslog facility code (default: LOG_USER)
        timezone: Timezone for timestamps (default: Atlantic/Reykjavik)

    Returns:
        RichLogger: Configured main logger instance

    Example:
        >>> logger = setup_logging(
        ...     level=logging.DEBUG,
        ...     syslog_output=True,
        ...     syslog_address=('localhost', 514)
        ... )
    """
    return get_logger(
        "gh-pr",
        level=level,
        log_file=log_file,
        console_output=console_output,
        file_output=file_output,
        syslog_output=syslog_output,
        syslog_address=syslog_address,
        syslog_facility=syslog_facility,
        timezone=timezone or DEFAULT_TIMEZONE
    )


# Convenience functions for quick logging
def debug(message: str, **kwargs) -> None:
    """
    Quick debug logging using the default logger.

    Convenience function for logging debug messages without
    needing to get a logger instance.

    Args:
        message: The debug message to log
        **kwargs: Additional context key-value pairs

    Returns:
        None
    """
    get_default_logger().debug(message, **kwargs)


def info(message: str, **kwargs) -> None:
    """
    Quick info logging using the default logger.

    Convenience function for logging informational messages
    without needing to get a logger instance.

    Args:
        message: The informational message to log
        **kwargs: Additional context key-value pairs

    Returns:
        None
    """
    get_default_logger().info(message, **kwargs)


def warning(message: str, **kwargs) -> None:
    """
    Quick warning logging using the default logger.

    Convenience function for logging warning messages without
    needing to get a logger instance.

    Args:
        message: The warning message to log
        **kwargs: Additional context key-value pairs

    Returns:
        None
    """
    get_default_logger().warning(message, **kwargs)


def error(message: str, **kwargs) -> None:
    """
    Quick error logging using the default logger.

    Convenience function for logging error messages without
    needing to get a logger instance.

    Args:
        message: The error message to log
        **kwargs: Additional context key-value pairs

    Returns:
        None
    """
    get_default_logger().error(message, **kwargs)


def critical(message: str, **kwargs) -> None:
    """
    Quick critical logging using the default logger.

    Convenience function for logging critical messages without
    needing to get a logger instance.

    Args:
        message: The critical message to log
        **kwargs: Additional context key-value pairs

    Returns:
        None
    """
    get_default_logger().critical(message, **kwargs)


def exception(message: str, **kwargs) -> None:
    """
    Quick exception logging.

    Note: This should be called from within an exception handler
    to properly capture the exception context.
    """
    get_default_logger().exception(message, **kwargs)

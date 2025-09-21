"""
Unit tests for the rich_logger module.

Tests cover all aspects of the RichLogger class including:
- Initialization and configuration
- Console, file, and syslog handlers
- Message formatting and security masking
- Child logger creation
- Thread safety
- Timezone handling
"""

import logging
import logging.handlers
import os
import socket
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import pytest
import pytz

from gh_pr.utils.rich_logger import (
    RichLogger,
    get_logger,
    get_default_logger,
    setup_logging,
    traced,
    debug,
    info,
    warning,
    error,
    critical,
    exception,
    DEFAULT_TIMEZONE,
    SESSION_ID,
)


class TestRichLoggerInitialization:
    """Test RichLogger initialization and configuration."""

    def test_default_initialization(self):
        """Test RichLogger with default parameters."""
        logger = RichLogger()

        assert logger.name == "gh-pr"
        assert logger.timezone == DEFAULT_TIMEZONE
        assert logger.session_id == SESSION_ID
        assert logger.console_output is True
        assert logger.file_output is True
        assert logger.syslog_output is False
        assert logger.logger.level == logging.INFO

    def test_custom_initialization(self):
        """Test RichLogger with custom parameters."""
        custom_tz = pytz.timezone("Europe/London")
        logger = RichLogger(
            name="test_logger",
            level=logging.DEBUG,
            timezone=custom_tz,
            console_output=False,
            file_output=False,
            syslog_output=True,
            syslog_address=("localhost", 514),
        )

        assert logger.name == "test_logger"
        assert logger.timezone == custom_tz
        assert logger.console_output is False
        assert logger.file_output is False
        assert logger.syslog_output is True
        assert logger.syslog_address == ("localhost", 514)
        assert logger.logger.level == logging.DEBUG

    def test_logger_handler_cleanup(self):
        """Test that existing handlers are cleared on initialization."""
        logger = RichLogger(name="test_cleanup")
        initial_handlers = len(logger.logger.handlers)

        # Create another logger with same name
        logger2 = RichLogger(name="test_cleanup")

        # Should have same number of handlers (old ones cleared)
        assert len(logger2.logger.handlers) == initial_handlers


class TestConsoleHandler:
    """Test console handler setup and behavior."""

    @patch("gh_pr.utils.rich_logger.Console")
    @patch("gh_pr.utils.rich_logger.RichHandler")
    def test_console_handler_setup(self, mock_rich_handler, mock_console):
        """Test console handler is properly configured."""
        logger = RichLogger(console_output=True, file_output=False)

        mock_console.assert_called_once_with(stderr=True)
        mock_rich_handler.assert_called_once_with(
            console=mock_console.return_value,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            markup=True
        )

        # Verify handler was added
        assert len(logger.logger.handlers) > 0

    def test_console_handler_disabled(self):
        """Test that console handler is not created when disabled."""
        with patch("gh_pr.utils.rich_logger.RichHandler") as mock_handler:
            logger = RichLogger(console_output=False, file_output=False)
            mock_handler.assert_not_called()


class TestFileHandler:
    """Test file handler setup and rotation."""

    def test_file_handler_default_location(self):
        """Test file handler uses default location when not specified."""
        with patch("gh_pr.utils.rich_logger.logging.handlers.RotatingFileHandler") as mock_handler:
            logger = RichLogger(console_output=False, file_output=True)

            # Check that default path was used
            call_args = mock_handler.call_args[0][0]
            assert ".cache/gh-pr/logs/gh-pr.log" in str(call_args)

    def test_file_handler_custom_location(self):
        """Test file handler with custom log file path."""
        with tempfile.NamedTemporaryFile(suffix=".log") as tmp_file:
            with patch("gh_pr.utils.rich_logger.logging.handlers.RotatingFileHandler") as mock_handler:
                logger = RichLogger(
                    console_output=False,
                    file_output=True,
                    log_file=tmp_file.name
                )

                mock_handler.assert_called_once_with(
                    tmp_file.name,
                    maxBytes=10 * 1024 * 1024,
                    backupCount=5,
                    encoding='utf-8'
                )

    def test_file_handler_timezone_formatter(self):
        """Test that file handler uses TimezoneAwareFormatter."""
        with tempfile.NamedTemporaryFile(suffix=".log") as tmp_file:
            logger = RichLogger(
                console_output=False,
                file_output=True,
                log_file=tmp_file.name,
                timezone=pytz.timezone("US/Eastern")
            )

            # Get the file handler
            file_handler = None
            for handler in logger.logger.handlers:
                if isinstance(handler, logging.handlers.RotatingFileHandler):
                    file_handler = handler
                    break

            assert file_handler is not None
            formatter = file_handler.formatter
            assert hasattr(formatter, 'tz')
            assert formatter.tz == pytz.timezone("US/Eastern")


class TestSyslogHandler:
    """Test syslog handler setup and configuration."""

    @patch("gh_pr.utils.rich_logger.logging.handlers.SysLogHandler")
    def test_syslog_handler_local(self, mock_syslog_handler):
        """Test local syslog handler setup."""
        logger = RichLogger(
            console_output=False,
            file_output=False,
            syslog_output=True,
            syslog_facility=logging.handlers.SysLogHandler.LOG_DAEMON
        )

        mock_syslog_handler.assert_called_once_with(
            facility=logging.handlers.SysLogHandler.LOG_DAEMON
        )

    @patch("gh_pr.utils.rich_logger.logging.handlers.SysLogHandler")
    def test_syslog_handler_remote(self, mock_syslog_handler):
        """Test remote syslog handler setup."""
        logger = RichLogger(
            console_output=False,
            file_output=False,
            syslog_output=True,
            syslog_address=("syslog.example.com", 514),
            syslog_facility=logging.handlers.SysLogHandler.LOG_USER
        )

        mock_syslog_handler.assert_called_once_with(
            address=("syslog.example.com", 514),
            facility=logging.handlers.SysLogHandler.LOG_USER,
            socktype=socket.SOCK_DGRAM
        )

    @patch("gh_pr.utils.rich_logger.logging.handlers.SysLogHandler")
    def test_syslog_handler_failure(self, mock_syslog_handler):
        """Test graceful handling of syslog setup failure."""
        mock_syslog_handler.side_effect = Exception("Syslog connection failed")

        # Should not crash even if syslog fails
        logger = RichLogger(
            console_output=True,
            file_output=False,
            syslog_output=True
        )

        # Logger should still be functional
        logger.info("Test message")


class TestMessageFormatting:
    """Test message formatting and context addition."""

    def test_format_message_basic(self):
        """Test basic message formatting with caller info."""
        logger = RichLogger(console_output=False, file_output=False)

        formatted = logger._format_message("Test message")

        # Should contain filename, line number, function name
        assert ".py:" in formatted
        assert "test_format_message_basic()" in formatted
        assert "Test message" in formatted

    def test_format_message_with_kwargs(self):
        """Test message formatting with additional context."""
        logger = RichLogger(console_output=False, file_output=False)

        formatted = logger._format_message(
            "Test message",
            user="john",
            action="login",
            status="success"
        )

        assert "Test message" in formatted
        assert "user=john" in formatted
        assert "action=login" in formatted
        assert "status=success" in formatted

    def test_get_caller_info(self):
        """Test caller information extraction."""
        logger = RichLogger(console_output=False, file_output=False)

        caller_info = logger._get_caller_info()

        assert 'filename' in caller_info
        assert 'function' in caller_info
        assert 'lineno' in caller_info
        assert 'module' in caller_info
        assert caller_info['function'] == 'test_get_caller_info'


class TestSecurityMasking:
    """Test sensitive environment variable masking."""

    def test_mask_sensitive_env_vars(self):
        """Test that sensitive environment variables are masked."""
        logger = RichLogger(console_output=False, file_output=False)

        # Set a test token
        test_token = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        with patch.dict(os.environ, {"GITHUB_TOKEN": test_token}):
            text = f"Using token {test_token} for authentication"
            masked = logger._mask_sensitive_env_vars(text)

            assert test_token not in masked
            assert "ghp_****" in masked

    def test_mask_environment_assignments(self):
        """Test masking of environment variable assignments."""
        logger = RichLogger(console_output=False, file_output=False)

        test_secret = "super_secret_value_12345"
        with patch.dict(os.environ, {"API_KEY": test_secret}):
            text = f"Set API_KEY={test_secret} in environment"
            masked = logger._mask_sensitive_env_vars(text)

            assert test_secret not in masked
            assert "API_KEY=supe****" in masked

    def test_mask_multiple_sensitive_vars(self):
        """Test masking multiple sensitive variables."""
        logger = RichLogger(console_output=False, file_output=False)

        with patch.dict(os.environ, {
            "GH_TOKEN": "token123456",
            "PASSWORD": "pass987654",
            "SECRET_KEY": "key111111"
        }):
            text = "Credentials: GH_TOKEN=token123456, PASSWORD=pass987654, SECRET_KEY=key111111"
            masked = logger._mask_sensitive_env_vars(text)

            assert "token123456" not in masked
            assert "pass987654" not in masked
            assert "key111111" not in masked
            assert "GH_TOKEN=toke****" in masked
            assert "PASSWORD=pass****" in masked
            assert "SECRET_KEY=key1****" in masked


class TestLoggingMethods:
    """Test all logging level methods."""

    @patch("gh_pr.utils.rich_logger.logging.Logger.debug")
    def test_debug_method(self, mock_debug):
        """Test debug logging method."""
        logger = RichLogger(console_output=False, file_output=False)
        logger.debug("Debug message", extra_field="value")

        mock_debug.assert_called_once()
        call_args = mock_debug.call_args[0][0]
        assert "Debug message" in call_args
        assert "extra_field=value" in call_args

    @patch("gh_pr.utils.rich_logger.logging.Logger.info")
    def test_info_method(self, mock_info):
        """Test info logging method."""
        logger = RichLogger(console_output=False, file_output=False)
        logger.info("Info message")

        mock_info.assert_called_once()
        assert "Info message" in mock_info.call_args[0][0]

    @patch("gh_pr.utils.rich_logger.logging.Logger.warning")
    def test_warning_method(self, mock_warning):
        """Test warning logging method."""
        logger = RichLogger(console_output=False, file_output=False)
        logger.warning("Warning message")

        mock_warning.assert_called_once()
        assert "Warning message" in mock_warning.call_args[0][0]

    @patch("gh_pr.utils.rich_logger.logging.Logger.error")
    def test_error_method(self, mock_error):
        """Test error logging method."""
        logger = RichLogger(console_output=False, file_output=False)
        logger.error("Error message")

        mock_error.assert_called_once()
        assert "Error message" in mock_error.call_args[0][0]

    @patch("gh_pr.utils.rich_logger.logging.Logger.critical")
    def test_critical_method(self, mock_critical):
        """Test critical logging method."""
        logger = RichLogger(console_output=False, file_output=False)
        logger.critical("Critical message")

        mock_critical.assert_called_once()
        assert "Critical message" in mock_critical.call_args[0][0]

    @patch("gh_pr.utils.rich_logger.logging.Logger.error")
    def test_exception_method(self, mock_error):
        """Test exception logging with traceback."""
        logger = RichLogger(console_output=False, file_output=False)

        try:
            raise ValueError("Test exception")
        except ValueError:
            logger.exception("Exception occurred")

        mock_error.assert_called_once()
        assert "Exception occurred" in mock_error.call_args[0][0]
        assert mock_error.call_args[1]["exc_info"] is True


class TestChildLogger:
    """Test child logger creation and inheritance."""

    def test_child_logger_creation(self):
        """Test creating a child logger."""
        parent = RichLogger(
            name="parent",
            level=logging.DEBUG,
            console_output=False,
            file_output=True,
            syslog_output=True,
            syslog_address=("localhost", 514)
        )

        child = parent.get_child("module")

        assert child.name == "parent.module"
        assert child.logger.level == logging.DEBUG
        assert child.console_output is False
        assert child.file_output is True
        assert child.syslog_output is True
        assert child.syslog_address == ("localhost", 514)
        assert child.timezone == parent.timezone

    def test_child_logger_hierarchy(self):
        """Test nested child logger creation."""
        root = RichLogger(name="root")
        child1 = root.get_child("child1")
        child2 = child1.get_child("child2")

        assert child2.name == "root.child1.child2"


class TestTracedDecorator:
    """Test the @traced decorator for function logging."""

    @patch("gh_pr.utils.rich_logger.get_logger")
    def test_traced_decorator_success(self, mock_get_logger):
        """Test traced decorator on successful function execution."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        @traced()
        def test_function(a, b, c=3):
            return a + b + c

        result = test_function(1, 2, c=4)

        assert result == 7

        # Check entry and exit logs
        calls = mock_logger.debug.call_args_list
        assert len(calls) == 2
        assert "ENTER test_function(1, 2, c=4)" in calls[0][0][0]
        assert "EXIT test_function() -> int" in calls[1][0][0]

    @patch("gh_pr.utils.rich_logger.get_logger")
    def test_traced_decorator_exception(self, mock_get_logger):
        """Test traced decorator on function exception."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        @traced()
        def test_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            test_function()

        # Check exception was logged
        mock_logger.exception.assert_called_once_with(
            "EXCEPTION in test_function()"
        )

    def test_traced_decorator_with_custom_logger(self):
        """Test traced decorator with custom logger."""
        custom_logger = MagicMock()

        @traced(logger=custom_logger)
        def test_function():
            return "result"

        result = test_function()

        assert result == "result"
        assert custom_logger.debug.call_count == 2


class TestGlobalLoggerRegistry:
    """Test global logger registry and thread safety."""

    def test_get_logger_singleton(self):
        """Test that get_logger returns the same instance."""
        logger1 = get_logger("test_singleton")
        logger2 = get_logger("test_singleton")

        assert logger1 is logger2

    def test_get_logger_different_names(self):
        """Test that different names return different loggers."""
        logger1 = get_logger("logger1")
        logger2 = get_logger("logger2")

        assert logger1 is not logger2
        assert logger1.name == "logger1"
        assert logger2.name == "logger2"

    def test_get_default_logger(self):
        """Test getting the default logger."""
        logger = get_default_logger()

        assert logger.name == "gh-pr"
        assert logger is get_default_logger()  # Should be same instance

    def test_thread_safety(self):
        """Test thread-safe logger creation."""
        loggers = []
        errors = []

        def create_logger(name):
            try:
                logger = get_logger(f"thread_logger_{name}")
                loggers.append(logger)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            thread = threading.Thread(target=create_logger, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert len(errors) == 0
        assert len(loggers) == 10

        # Check that same-named loggers are the same instance
        test_logger1 = get_logger("thread_logger_5")
        test_logger2 = get_logger("thread_logger_5")
        assert test_logger1 is test_logger2


class TestSetupLogging:
    """Test the setup_logging configuration function."""

    @patch("gh_pr.utils.rich_logger.get_logger")
    def test_setup_logging_basic(self, mock_get_logger):
        """Test basic setup_logging call."""
        setup_logging(
            level=logging.WARNING,
            console_output=False,
            file_output=True
        )

        mock_get_logger.assert_called_once_with(
            "gh-pr",
            level=logging.WARNING,
            log_file=None,
            console_output=False,
            file_output=True,
            syslog_output=False,
            syslog_address=None,
            syslog_facility=logging.handlers.SysLogHandler.LOG_USER,
            timezone=DEFAULT_TIMEZONE
        )

    @patch("gh_pr.utils.rich_logger.get_logger")
    def test_setup_logging_with_syslog(self, mock_get_logger):
        """Test setup_logging with syslog configuration."""
        custom_tz = pytz.timezone("US/Pacific")

        setup_logging(
            level=logging.DEBUG,
            syslog_output=True,
            syslog_address=("syslog.local", 1514),
            syslog_facility=logging.handlers.SysLogHandler.LOG_LOCAL0,
            timezone=custom_tz
        )

        mock_get_logger.assert_called_once()
        call_kwargs = mock_get_logger.call_args[1]
        assert call_kwargs["syslog_output"] is True
        assert call_kwargs["syslog_address"] == ("syslog.local", 1514)
        assert call_kwargs["syslog_facility"] == logging.handlers.SysLogHandler.LOG_LOCAL0
        assert call_kwargs["timezone"] == custom_tz


class TestConvenienceFunctions:
    """Test module-level convenience logging functions."""

    @patch("gh_pr.utils.rich_logger.get_default_logger")
    def test_debug_convenience(self, mock_get_default):
        """Test module-level debug function."""
        mock_logger = MagicMock()
        mock_get_default.return_value = mock_logger

        debug("Debug message", key="value")

        mock_logger.debug.assert_called_once_with("Debug message", key="value")

    @patch("gh_pr.utils.rich_logger.get_default_logger")
    def test_info_convenience(self, mock_get_default):
        """Test module-level info function."""
        mock_logger = MagicMock()
        mock_get_default.return_value = mock_logger

        info("Info message")

        mock_logger.info.assert_called_once_with("Info message")

    @patch("gh_pr.utils.rich_logger.get_default_logger")
    def test_warning_convenience(self, mock_get_default):
        """Test module-level warning function."""
        mock_logger = MagicMock()
        mock_get_default.return_value = mock_logger

        warning("Warning message")

        mock_logger.warning.assert_called_once_with("Warning message")

    @patch("gh_pr.utils.rich_logger.get_default_logger")
    def test_error_convenience(self, mock_get_default):
        """Test module-level error function."""
        mock_logger = MagicMock()
        mock_get_default.return_value = mock_logger

        error("Error message")

        mock_logger.error.assert_called_once_with("Error message")

    @patch("gh_pr.utils.rich_logger.get_default_logger")
    def test_critical_convenience(self, mock_get_default):
        """Test module-level critical function."""
        mock_logger = MagicMock()
        mock_get_default.return_value = mock_logger

        critical("Critical message")

        mock_logger.critical.assert_called_once_with("Critical message")

    @patch("gh_pr.utils.rich_logger.get_default_logger")
    def test_exception_convenience(self, mock_get_default):
        """Test module-level exception function."""
        mock_logger = MagicMock()
        mock_get_default.return_value = mock_logger

        exception("Exception message", details="error details")

        mock_logger.exception.assert_called_once_with(
            "Exception message",
            details="error details"
        )


class TestTimezoneHandling:
    """Test timezone handling in formatters."""

    def test_timezone_aware_formatter(self):
        """Test that TimezoneAwareFormatter handles timezones correctly."""
        with tempfile.NamedTemporaryFile(suffix=".log", mode='w+', delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            # Create logger with specific timezone
            eastern = pytz.timezone("US/Eastern")
            logger = RichLogger(
                name="tz_test",
                console_output=False,
                file_output=True,
                log_file=tmp_path,
                timezone=eastern
            )

            # Log a message
            logger.info("Timezone test message")

            # Read the log file
            with open(tmp_path, 'r') as f:
                log_content = f.read()

            # Should contain timestamp (we can't check exact time due to DST)
            assert "Timezone test message" in log_content
            # The log should have a timestamp
            assert ":" in log_content  # Time separator

        finally:
            # Clean up
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_different_timezone_formats(self):
        """Test logging with different timezone settings."""
        timezones = [
            pytz.UTC,
            pytz.timezone("Atlantic/Reykjavik"),
            pytz.timezone("Asia/Tokyo"),
            pytz.timezone("America/New_York"),
        ]

        for tz in timezones:
            logger = RichLogger(
                name=f"tz_test_{tz.zone}",
                console_output=False,
                file_output=False,
                timezone=tz
            )
            # Should not raise any errors
            assert logger.timezone == tz


class TestSessionTracking:
    """Test session ID tracking."""

    def test_session_id_consistency(self):
        """Test that session ID is consistent across loggers."""
        logger1 = RichLogger(name="logger1")
        logger2 = RichLogger(name="logger2")

        assert logger1.session_id == SESSION_ID
        assert logger2.session_id == SESSION_ID
        assert logger1.session_id == logger2.session_id

    def test_session_id_format(self):
        """Test that session ID is a valid UUID."""
        import uuid

        # Should be able to parse as UUID
        parsed = uuid.UUID(SESSION_ID)
        assert str(parsed) == SESSION_ID
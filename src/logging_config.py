"""Logging configuration for dbmcp MCP server.

CRITICAL: Never use stdout (print()) in MCP servers - it corrupts JSON-RPC messages.
Only use file logging and stderr. This module configures proper logging.
"""

import logging
import sys
from pathlib import Path

# Default log file location
DEFAULT_LOG_FILE = Path("dbmcp.log")


def setup_logging(
    log_file: Path | str | None = DEFAULT_LOG_FILE,
    level: int = logging.INFO,
    log_to_stderr: bool = True,
) -> logging.Logger:
    """Configure logging for the MCP server.

    Args:
        log_file: Path to log file. None disables file logging.
        level: Logging level (default: INFO)
        log_to_stderr: Whether to also log to stderr (default: True)

    Returns:
        Configured root logger for the application
    """
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Get root logger for our application
    logger = logging.getLogger("dbmcp")
    logger.setLevel(level)
    logger.handlers.clear()  # Remove any existing handlers

    # File handler (primary logging destination)
    if log_file is not None:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Stderr handler (safe for MCP - does not interfere with JSON-RPC on stdout)
    if log_to_stderr:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.WARNING)  # Only warnings and above to stderr
        stderr_handler.setFormatter(formatter)
        logger.addHandler(stderr_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(f"dbmcp.{name}")


# Credential filtering - ensure passwords are never logged
class CredentialFilter(logging.Filter):
    """Filter to redact sensitive credentials from log messages."""

    SENSITIVE_PATTERNS = [
        "password",
        "pwd",
        "secret",
        "token",
        "key",
        "credential",
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive information from log messages."""
        if hasattr(record, "msg") and isinstance(record.msg, str):
            msg_lower = record.msg.lower()
            for pattern in self.SENSITIVE_PATTERNS:
                if pattern in msg_lower:
                    # Check if this looks like credential logging
                    if "=" in record.msg or ":" in record.msg:
                        record.msg = f"[REDACTED - contains {pattern}]"
                        record.args = ()
                        break
        return True

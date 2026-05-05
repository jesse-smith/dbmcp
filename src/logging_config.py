"""Logging configuration for dbmcp MCP server.

CRITICAL: Never use stdout (print()) in MCP servers - it corrupts JSON-RPC messages.
Only use file logging and stderr. This module configures proper logging.

Logs are written to a centralized per-project location to avoid polluting every
working directory with a dbmcp.log file. Default path:

    ~/.dbmcp/logs/<cwd-basename>-<8char-hash>.log

The hash is derived from the absolute CWD path, so two projects that happen to
share the same directory name don't collide. Log files rotate at ~5MB with one
backup, capping total disk per project at ~10MB.
"""

import hashlib
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Rotation: ~5MB per file, 1 backup file → ~10MB total per project
_LOG_MAX_BYTES = 5_000_000
_LOG_BACKUP_COUNT = 1

# Legacy log file that used to be written in CWD. Kept for one-shot migration.
_LEGACY_LOG_FILE = Path("dbmcp.log")


def _compute_default_log_path(dir_override: Path | None = None) -> Path:
    """Compute the default log file path for the current working directory.

    Filename is `<cwd-basename>-<8hex>.log` where the 8-char hex is a blake2b
    digest of the absolute CWD path. Stable for the same directory across runs,
    distinct for different directories (even if they share a basename).

    Args:
        dir_override: Optional override for the log directory. Defaults to
            `~/.dbmcp/logs/`.

    Returns:
        Absolute path to the log file (parent directory may not yet exist).
    """
    base = dir_override if dir_override is not None else Path.home() / ".dbmcp" / "logs"
    cwd = Path.cwd().resolve()
    digest = hashlib.blake2b(str(cwd).encode("utf-8"), digest_size=4).hexdigest()
    return base / f"{cwd.name}-{digest}.log"


# TODO: remove after v2.1 — one-shot migration of legacy per-CWD log files.
def _migrate_legacy_log(new_path: Path) -> tuple[int | None, Exception | None]:
    """Move ./dbmcp.log contents into the centralized log, then delete it.

    No-op if the legacy file doesn't exist. Runs BEFORE the log handler is
    attached (so it can freely write to the target file), and the caller
    is expected to log the outcome afterward via the attached handler.

    Returns:
        (bytes_migrated, error). `(None, None)` if no legacy file existed.
        `(n, None)` on success. `(None, exc)` on failure.
    """
    if not _LEGACY_LOG_FILE.is_file():
        return (None, None)
    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_bytes = _LEGACY_LOG_FILE.read_bytes()
        with open(new_path, "ab") as dst:
            dst.write(legacy_bytes)
        _LEGACY_LOG_FILE.unlink()
        return (len(legacy_bytes), None)
    except Exception as e:
        return (None, e)


def setup_logging(
    log_dir: Path | str | None = None,
    level: int = logging.INFO,
    log_to_stderr: bool = True,
    log_to_file: bool = True,
) -> logging.Logger:
    """Configure logging for the MCP server.

    Args:
        log_dir: Override for the log directory. If None, uses
            `~/.dbmcp/logs/`. The log filename within this directory is
            derived from the current working directory.
        level: Logging level (default: INFO).
        log_to_stderr: Whether to also log WARNING+ to stderr (default: True).
        log_to_file: Whether to enable file logging (default: True). Disable
            for tests that don't want any file side effects.

    Returns:
        Configured root logger for the application.
    """
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger = logging.getLogger("dbmcp")
    logger.setLevel(level)
    logger.handlers.clear()

    migration_result: tuple[int | None, Exception | None] = (None, None)
    if log_to_file:
        dir_override = Path(log_dir) if isinstance(log_dir, str) else log_dir
        log_path = _compute_default_log_path(dir_override)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Migrate legacy CWD log file before the handler opens the target.
        migration_result = _migrate_legacy_log(log_path)

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=_LOG_MAX_BYTES,
            backupCount=_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    if log_to_stderr:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.WARNING)
        stderr_handler.setFormatter(formatter)
        logger.addHandler(stderr_handler)

    logger.propagate = False

    bytes_migrated, migration_error = migration_result
    if migration_error is not None:
        logger.warning("Legacy log migration failed (non-fatal): %s", migration_error)
    elif bytes_migrated is not None:
        logger.info(
            "Migrated legacy log file %s -> %s (%d bytes)",
            _LEGACY_LOG_FILE, _compute_default_log_path(
                Path(log_dir) if isinstance(log_dir, str) else log_dir,
            ), bytes_migrated,
        )

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module.

    Args:
        name: Module name (typically __name__).

    Returns:
        Logger instance.
    """
    return logging.getLogger(f"dbmcp.{name}")


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
                    if "=" in record.msg or ":" in record.msg:
                        record.msg = f"[REDACTED - contains {pattern}]"
                        record.args = ()
                        break
        return True

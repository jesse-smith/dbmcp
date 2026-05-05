"""Tests for centralized log path, rotation, and legacy migration."""

from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path

import pytest

from src.logging_config import (
    _LEGACY_LOG_FILE,
    _LOG_BACKUP_COUNT,
    _LOG_MAX_BYTES,
    _compute_default_log_path,
    setup_logging,
)

_FILENAME_RE = re.compile(r"^[^/]+-[0-9a-f]{8}\.log$")


@pytest.fixture(autouse=True)
def _isolate_home_and_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Path.home() and cwd to tmp_path so tests never touch the real home."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    fake_cwd = tmp_path / "work" / "myproject"
    fake_cwd.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.chdir(fake_cwd)
    return tmp_path


@pytest.fixture(autouse=True)
def _reset_dbmcp_logger():
    """Ensure each test starts with a clean dbmcp logger."""
    yield
    logger = logging.getLogger("dbmcp")
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)


def _hex8(s: str) -> re.Match | None:
    return re.fullmatch(r"[0-9a-f]{8}", s)


def test_default_path_uses_home_dbmcp_logs_and_hashed_basename():
    path = _compute_default_log_path()
    assert path.parent == Path.home() / ".dbmcp" / "logs"
    assert _FILENAME_RE.match(path.name), f"bad filename: {path.name}"
    # Basename prefix matches CWD basename
    assert path.name.startswith("myproject-")


def test_hash_stable_for_same_cwd():
    a = _compute_default_log_path()
    b = _compute_default_log_path()
    assert a == b


def test_hash_differs_for_different_cwds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    d1 = tmp_path / "a" / "dbmcp"
    d2 = tmp_path / "b" / "dbmcp"
    d1.mkdir(parents=True)
    d2.mkdir(parents=True)
    monkeypatch.chdir(d1)
    p1 = _compute_default_log_path()
    monkeypatch.chdir(d2)
    p2 = _compute_default_log_path()
    # Same basename, different hash → different filenames
    assert p1.name != p2.name
    assert p1.name.startswith("dbmcp-")
    assert p2.name.startswith("dbmcp-")


def test_dir_override_respected(tmp_path: Path):
    override = tmp_path / "custom-logs"
    path = _compute_default_log_path(dir_override=override)
    assert path.parent == override


def test_setup_logging_creates_dir_and_writes_file():
    logger = setup_logging(level=logging.INFO, log_to_stderr=False)
    logger.info("hello")
    for h in logger.handlers:
        h.flush()

    expected = _compute_default_log_path()
    assert expected.exists()
    content = expected.read_text(encoding="utf-8")
    assert "hello" in content


def test_setup_logging_with_custom_dir(tmp_path: Path):
    custom = tmp_path / "mylogs"
    logger = setup_logging(log_dir=custom, level=logging.INFO, log_to_stderr=False)
    logger.info("custom dir message")
    for h in logger.handlers:
        h.flush()

    logs = list(custom.glob("*.log"))
    assert len(logs) == 1
    assert "custom dir message" in logs[0].read_text(encoding="utf-8")


def test_setup_logging_no_file_when_disabled():
    logger = setup_logging(log_to_file=False, log_to_stderr=False)
    logger.info("ignored")
    # No FileHandler should be attached
    assert all(not isinstance(h, logging.FileHandler) for h in logger.handlers)


def test_migration_moves_legacy_log_and_deletes_it():
    legacy = _LEGACY_LOG_FILE
    legacy.write_text("old log line 1\nold log line 2\n", encoding="utf-8")
    assert legacy.exists()

    logger = setup_logging(level=logging.INFO, log_to_stderr=False)
    for h in logger.handlers:
        h.flush()

    # Legacy file is gone
    assert not legacy.exists()

    # Contents appended into new log
    new_path = _compute_default_log_path()
    content = new_path.read_text(encoding="utf-8")
    assert "old log line 1" in content
    assert "old log line 2" in content
    # Migration announcement landed in the new file
    assert "Migrated legacy log file" in content


def test_migration_idempotent_when_no_legacy_file():
    # No ./dbmcp.log exists — setup should succeed silently
    assert not _LEGACY_LOG_FILE.exists()
    logger = setup_logging(level=logging.INFO, log_to_stderr=False)
    for h in logger.handlers:
        h.flush()

    new_path = _compute_default_log_path()
    content = new_path.read_text(encoding="utf-8") if new_path.exists() else ""
    assert "Migrated legacy log file" not in content


def test_migration_swallows_errors(monkeypatch: pytest.MonkeyPatch):
    _LEGACY_LOG_FILE.write_text("some data", encoding="utf-8")

    # Force read_bytes to raise
    def boom(self):  # pragma: no cover - trivially exercised
        raise OSError("simulated read failure")

    monkeypatch.setattr(Path, "read_bytes", boom)

    # Must not raise
    logger = setup_logging(level=logging.INFO, log_to_stderr=False)
    assert logger is not None


def test_rotation_config_matches_spec():
    """Handler is configured with the documented rotation parameters."""
    logger = setup_logging(level=logging.INFO, log_to_stderr=False)
    file_handlers = [
        h for h in logger.handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)  # type: ignore[attr-defined]
    ]
    assert len(file_handlers) == 1
    h = file_handlers[0]
    assert h.maxBytes == _LOG_MAX_BYTES
    assert h.backupCount == _LOG_BACKUP_COUNT


def test_rotation_triggers_at_max_bytes():
    """Writing beyond maxBytes produces a .log.1 backup and caps the main file."""
    logger = setup_logging(level=logging.INFO, log_to_stderr=False)

    # Emit ~6MB of log data (> 5MB cap)
    blob = "x" * 10_000
    for _ in range(700):
        logger.info(blob)
    for h in logger.handlers:
        h.flush()

    new_path = _compute_default_log_path()
    backup = new_path.with_name(new_path.name + ".1")
    assert backup.exists(), "rotation backup file .log.1 not created"
    # Main file should be at or under cap (+ one line of slack for the final write)
    assert new_path.stat().st_size <= _LOG_MAX_BYTES + 10_100

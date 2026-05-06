"""Integration-style regression tests for connect_with_config(Databricks).

These tests lock in the fix for two bugs in
`ConnectionManager.connect_with_config` Databricks branch:

  Bug A: host/http_path/catalog/schema_name were not passed through
         `resolve_env_vars`, so `${VAR}` stayed literal.
  Bug B: The branch delegated to `connect_with_url`, which calls the dialect
         with `sqlalchemy_url=`, but `DatabricksDialect.create_engine` reads
         `host=`/`http_path=` kwargs and has no `sqlalchemy_url` handling.

We deliberately do NOT mock `DatabricksDialect` itself — only the innermost
engine-creation boundary — so Bug B (signature mismatch) is covered.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.config import DatabricksConnectionConfig
from src.db.connection import ConnectionManager
from src.db.dialects.databricks import DatabricksDialect


def _make_engine_spy():
    """Build an Engine-like MagicMock whose .connect() context manager works.

    Enough for `_test_connection(engine, start_time, dialect.name)` — which
    calls engine.connect() as a context manager and runs `SELECT 1` — to
    succeed without raising.
    """
    engine = MagicMock(name="Engine")
    conn = MagicMock(name="SQLAConnection")
    conn.execute.return_value = MagicMock(fetchone=lambda: (1,))
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = ctx
    return engine


def test_connect_with_config_resolves_env_vars_and_calls_dialect_with_kwargs(monkeypatch):
    """Databricks config with ${VAR} refs resolves env and calls dialect with real kwargs."""
    monkeypatch.setenv("DATABRICKS_HOST", "dbc-test.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/abc123")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-secret-xyz")

    cfg = DatabricksConnectionConfig(
        host="${DATABRICKS_HOST}",
        http_path="${DATABRICKS_HTTP_PATH}",
        token="${DATABRICKS_TOKEN}",
        catalog="my_catalog",
        schema_name="my_schema",
    )

    captured_kwargs: dict = {}

    def spy_create_engine(self, **kwargs):
        captured_kwargs.update(kwargs)
        return _make_engine_spy()

    # Patch at the class level so we're exercising the real DatabricksDialect
    # dispatch path (bug B coverage), but intercept the engine boundary only.
    monkeypatch.setattr(DatabricksDialect, "create_engine", spy_create_engine)
    # Neutralize _test_connection — engine is a MagicMock, no real DB round-trip.
    monkeypatch.setattr(
        ConnectionManager, "_test_connection",
        lambda self, engine, start_time, dialect_name: None,
    )

    manager = ConnectionManager()
    result = manager.connect_with_config(cfg, DatabricksDialect())

    assert captured_kwargs == {
        "host": "dbc-test.cloud.databricks.com",
        "http_path": "/sql/1.0/warehouses/abc123",
        "token": "dapi-secret-xyz",
        "catalog": "my_catalog",
        "schema": "my_schema",  # mapped from schema_name
    }
    # Lock Bug B: no URL-based call path.
    assert "sqlalchemy_url" not in captured_kwargs

    assert result.dialect_name == "databricks"
    assert result.connection_id  # non-empty


def test_connect_with_config_databricks_signature_matches_dialect(monkeypatch):
    """The kwargs the fix passes match the keys DatabricksDialect.create_engine reads.

    Guards against future drift: if the dialect signature changes without
    the caller being updated, this fails loudly.
    """
    # Patch sqlalchemy.create_engine inside the dialect module to a no-op,
    # so we don't actually try to build a real engine.
    import src.db.dialects.databricks as dbx_mod

    monkeypatch.setattr(
        dbx_mod, "sa_create_engine", lambda url, **kw: MagicMock(name="Engine")
    )
    # Also bypass the import-error guard in case databricks-sqlalchemy
    # isn't importable in this environment.
    monkeypatch.setattr(dbx_mod, "_databricks_import_error", None)

    dialect = DatabricksDialect()

    # The fix will call with exactly these keys.
    kwargs = {
        "host": "example.cloud.databricks.com",
        "http_path": "/sql/1.0/warehouses/x",
        "token": "tok",
        "catalog": "main",
        "schema": "default",
    }
    # Must not raise "Missing required parameter".
    engine = dialect.create_engine(**kwargs)
    assert engine is not None

    # Missing host should still raise ValueError — guards against the dialect
    # silently accepting anything, which would make Bug B invisible.
    with pytest.raises(ValueError, match="Missing required parameter"):
        dialect.create_engine(http_path="/x", token="t")

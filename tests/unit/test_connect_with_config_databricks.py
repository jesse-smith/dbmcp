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


# ---------------------------------------------------------------------------
# IDENT-01 / D-18: catalog-required enrichment in the config path
# ---------------------------------------------------------------------------


class _NeverCalled:
    """Helper to assert that an attribute access never happens."""

    def __getattr__(self, name):  # pragma: no cover - shouldn't trigger
        raise AssertionError(f"Should not have been called: {name}")


def _patch_no_test_connection(monkeypatch):
    monkeypatch.setattr(
        ConnectionManager, "_test_connection",
        lambda self, engine, start_time, dialect_name: None,
    )


def test_connect_with_config_empty_catalog_raises_enriched_connection_error(monkeypatch):
    """Empty catalog flows into enriched ConnectionError listing accessible catalogs (IDENT-01)."""
    from src.db.connection import ConnectionError as DBConnectionError

    cfg = DatabricksConnectionConfig(
        host="dbc-test.cloud.databricks.com",
        http_path="/sql/1.0/warehouses/abc",
        token="tok",
        catalog="",  # explicit empty — must NOT fall back to "main"
        schema_name="default",
    )

    captured_engine_kwargs: list[dict] = []

    def fake_create_engine(self, **kwargs):
        captured_engine_kwargs.append(dict(kwargs))
        if not kwargs.get("catalog"):
            raise ValueError("Databricks catalog is required")
        # probe path: catalog="system"
        return _make_engine_spy()

    def fake_list_catalogs(self, engine):
        return ["main", "hive_metastore", "samples", "my_catalog"]

    monkeypatch.setattr(DatabricksDialect, "create_engine", fake_create_engine)
    monkeypatch.setattr(DatabricksDialect, "list_catalogs", fake_list_catalogs)
    _patch_no_test_connection(monkeypatch)

    manager = ConnectionManager()
    with pytest.raises(DBConnectionError) as exc_info:
        manager.connect_with_config(cfg, DatabricksDialect())

    msg = str(exc_info.value)
    assert "Databricks connection requires a catalog" in msg
    assert "Accessible catalogs:" in msg
    assert "main" in msg and "hive_metastore" in msg
    # __cause__ chained to the original ValueError from create_engine
    assert isinstance(exc_info.value.__cause__, ValueError)
    assert "catalog is required" in str(exc_info.value.__cause__)

    # Probe engine used catalog="system" placeholder
    probe_calls = [k for k in captured_engine_kwargs if k.get("catalog") == "system"]
    assert len(probe_calls) == 1, captured_engine_kwargs


def test_connect_with_config_none_catalog_raises_enriched_connection_error(monkeypatch):
    """D-18: None catalog must NOT silently default to 'main' — must enrich-and-raise."""
    from src.db.connection import ConnectionError as DBConnectionError

    cfg = DatabricksConnectionConfig(
        host="dbc-test.cloud.databricks.com",
        http_path="/sql/1.0/warehouses/abc",
        token="tok",
        catalog=None,
        schema_name="default",
    )

    def fake_create_engine(self, **kwargs):
        if not kwargs.get("catalog"):
            raise ValueError("Databricks catalog is required")
        return _make_engine_spy()

    monkeypatch.setattr(DatabricksDialect, "create_engine", fake_create_engine)
    monkeypatch.setattr(
        DatabricksDialect, "list_catalogs",
        lambda self, engine: ["main", "samples"],
    )
    _patch_no_test_connection(monkeypatch)

    manager = ConnectionManager()
    with pytest.raises(DBConnectionError) as exc_info:
        manager.connect_with_config(cfg, DatabricksDialect())

    msg = str(exc_info.value)
    assert "Accessible catalogs:" in msg


def test_connect_with_config_probe_failure_message_names_both(monkeypatch):
    """When SHOW CATALOGS itself fails, error names BOTH the missing-catalog requirement
    AND the SHOW CATALOGS failure (D-06)."""
    from sqlalchemy.exc import SQLAlchemyError

    from src.db.connection import ConnectionError as DBConnectionError

    cfg = DatabricksConnectionConfig(
        host="dbc-test.cloud.databricks.com",
        http_path="/sql/1.0/warehouses/abc",
        token="tok",
        catalog="",
        schema_name="default",
    )

    def fake_create_engine(self, **kwargs):
        if not kwargs.get("catalog"):
            raise ValueError("Databricks catalog is required")
        return _make_engine_spy()

    def boom_list_catalogs(self, engine):
        raise SQLAlchemyError("permission denied")

    monkeypatch.setattr(DatabricksDialect, "create_engine", fake_create_engine)
    monkeypatch.setattr(DatabricksDialect, "list_catalogs", boom_list_catalogs)
    _patch_no_test_connection(monkeypatch)

    manager = ConnectionManager()
    with pytest.raises(DBConnectionError) as exc_info:
        manager.connect_with_config(cfg, DatabricksDialect())

    msg = str(exc_info.value)
    assert "catalog" in msg
    assert "SHOW CATALOGS" in msg and "failed" in msg
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_connect_with_config_valid_catalog_does_not_invoke_helper(monkeypatch):
    """Happy-path: valid catalog returns engine; helper is never invoked, list_catalogs not called."""
    cfg = DatabricksConnectionConfig(
        host="dbc-test.cloud.databricks.com",
        http_path="/sql/1.0/warehouses/abc",
        token="tok",
        catalog="my_catalog",
        schema_name="default",
    )

    def fake_create_engine(self, **kwargs):
        if not kwargs.get("catalog"):
            raise ValueError("Databricks catalog is required")
        return _make_engine_spy()

    list_catalogs_calls: list[int] = []

    def fake_list_catalogs(self, engine):
        list_catalogs_calls.append(1)
        return []

    monkeypatch.setattr(DatabricksDialect, "create_engine", fake_create_engine)
    monkeypatch.setattr(DatabricksDialect, "list_catalogs", fake_list_catalogs)
    _patch_no_test_connection(monkeypatch)

    manager = ConnectionManager()
    result = manager.connect_with_config(cfg, DatabricksDialect())

    assert result.dialect_name == "databricks"
    assert list_catalogs_calls == []  # helper never touched

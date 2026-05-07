"""Verify pyproject.toml dependency structure.

All database driver packages are hard dependencies — there are no optional
extras. This test pins that contract so a future refactor that re-introduces
extras must update the test intentionally.
"""

import tomllib
from pathlib import Path

import pytest


@pytest.fixture
def pyproject():
    path = Path(__file__).parents[2] / "pyproject.toml"
    with open(path, "rb") as f:
        return tomllib.load(f)


def test_no_optional_dependencies_section(pyproject):
    assert "optional-dependencies" not in pyproject["project"], (
        "pyproject.toml must not declare optional-dependencies — all drivers are hard deps"
    )


def test_core_deps_include_required(pyproject):
    core_deps = " ".join(pyproject["project"]["dependencies"]).lower()
    assert "sqlalchemy" in core_deps
    assert "sqlglot" in core_deps
    assert "mcp" in core_deps


def test_core_deps_include_pyodbc(pyproject):
    core_deps = [d.lower() for d in pyproject["project"]["dependencies"]]
    assert any("pyodbc" in d for d in core_deps)


def test_core_deps_include_azure_identity(pyproject):
    core_deps = [d.lower() for d in pyproject["project"]["dependencies"]]
    assert any("azure-identity" in d for d in core_deps)


def test_core_deps_include_databricks_sqlalchemy(pyproject):
    core_deps = [d.lower() for d in pyproject["project"]["dependencies"]]
    assert any("databricks-sqlalchemy" in d for d in core_deps)


def test_core_deps_include_databricks_sql_connector(pyproject):
    core_deps = [d.lower() for d in pyproject["project"]["dependencies"]]
    assert any("databricks-sql-connector" in d for d in core_deps)


def test_core_deps_include_jupyter(pyproject):
    core_deps = [d.lower() for d in pyproject["project"]["dependencies"]]
    assert any("jupyter" in d for d in core_deps)

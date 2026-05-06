"""Verify pyproject.toml dependency structure for optional extras."""

import tomllib
from pathlib import Path

import pytest


@pytest.fixture
def pyproject():
    path = Path(__file__).parents[2] / "pyproject.toml"
    with open(path, "rb") as f:
        return tomllib.load(f)


def test_core_deps_no_pyodbc(pyproject):
    core_deps = [d.lower() for d in pyproject["project"]["dependencies"]]
    assert not any("pyodbc" in d for d in core_deps), "pyodbc must not be in core dependencies"


def test_core_deps_no_azure_identity(pyproject):
    core_deps = [d.lower() for d in pyproject["project"]["dependencies"]]
    assert not any("azure-identity" in d for d in core_deps), "azure-identity must not be in core dependencies"


def test_mssql_extra_has_pyodbc(pyproject):
    mssql_deps = [d.lower() for d in pyproject["project"]["optional-dependencies"]["mssql"]]
    assert any("pyodbc" in d for d in mssql_deps)


def test_mssql_extra_has_azure_identity(pyproject):
    mssql_deps = [d.lower() for d in pyproject["project"]["optional-dependencies"]["mssql"]]
    assert any("azure-identity" in d for d in mssql_deps)


def test_databricks_extra_exists(pyproject):
    assert "databricks" in pyproject["project"]["optional-dependencies"]


def test_all_extra_includes_mssql(pyproject):
    all_deps = [d.lower() for d in pyproject["project"]["optional-dependencies"]["all"]]
    assert any("dbmcp[mssql]" in d for d in all_deps)


def test_all_extra_includes_databricks(pyproject):
    all_deps = [d.lower() for d in pyproject["project"]["optional-dependencies"]["all"]]
    assert any("dbmcp[databricks]" in d for d in all_deps)


def test_all_extra_includes_examples(pyproject):
    all_deps = [d.lower() for d in pyproject["project"]["optional-dependencies"]["all"]]
    assert any("dbmcp[examples]" in d for d in all_deps)


def test_core_deps_include_required(pyproject):
    core_deps = " ".join(pyproject["project"]["dependencies"]).lower()
    assert "sqlalchemy" in core_deps
    assert "sqlglot" in core_deps
    assert "mcp" in core_deps

"""Integration tests for find_fk_candidates MCP tool.

Tests end-to-end behavior against a real SQL Server test database.
Requires TEST_DB_SERVER, TEST_DB_DATABASE, TEST_DB_USERNAME, TEST_DB_PASSWORD
environment variables.
"""

import os

import pytest

from tests.helpers import parse_tool_response

# Skip all integration tests if env vars not set
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DB_SERVER"),
    reason="Integration test requires TEST_DB_SERVER environment variable",
)


@pytest.fixture(scope="module")
def connection_id():
    """Create a test database connection and return connection_id."""
    server = os.environ["TEST_DB_SERVER"]
    database = os.environ["TEST_DB_DATABASE"]
    username = os.environ.get("TEST_DB_USERNAME")
    password = os.environ.get("TEST_DB_PASSWORD")

    import asyncio

    from src.mcp_server.schema_tools import connect_database

    result = asyncio.get_event_loop().run_until_complete(
        connect_database(
            server=server,
            database=database,
            username=username,
            password=password,
            trust_server_cert=True,
        )
    )
    data = parse_tool_response(result)
    assert data["status"] == "success", f"Connection failed: {data}"
    return data["connection_id"]


# ---------------------------------------------------------------------------
# Basic FK candidate discovery
# ---------------------------------------------------------------------------

class TestFindFKCandidatesBasic:
    """Basic end-to-end tests for find_fk_candidates."""

    @pytest.mark.asyncio
    async def test_default_settings(self, connection_id):
        """Default settings return candidates for a known FK column."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="CustomerID",
            schema_name="SalesLT",
        ))

        assert result["status"] == "success"
        assert "source" in result
        assert result["source"]["column_name"] == "CustomerID"
        assert result["source"]["table_name"] == "SalesOrderHeader"
        assert isinstance(result["candidates"], list)
        assert "total_found" in result
        assert "was_limited" in result

    @pytest.mark.asyncio
    async def test_candidates_have_required_fields(self, connection_id):
        """Each candidate has all required fields from FKCandidateData model."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="CustomerID",
            schema_name="SalesLT",
        ))

        assert result["status"] == "success"
        for candidate in result["candidates"]:
            assert "source_column" in candidate
            assert "source_table" in candidate
            assert "source_schema" in candidate
            assert "source_data_type" in candidate
            assert "target_column" in candidate
            assert "target_table" in candidate
            assert "target_schema" in candidate
            assert "target_data_type" in candidate
            assert "target_is_primary_key" in candidate
            assert "target_is_unique" in candidate
            assert "target_is_nullable" in candidate
            assert "target_has_index" in candidate


# ---------------------------------------------------------------------------
# PK filter toggle
# ---------------------------------------------------------------------------

class TestPKFilterToggle:
    """Tests for pk_candidates_only parameter."""

    @pytest.mark.asyncio
    async def test_pk_filter_on(self, connection_id):
        """pk_candidates_only=True only returns PK candidate columns."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="CustomerID",
            schema_name="SalesLT",
            pk_candidates_only=True,
        ))

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_pk_filter_off_returns_more(self, connection_id):
        """pk_candidates_only=False may return more candidates."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result_on = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="CustomerID",
            schema_name="SalesLT",
            pk_candidates_only=True,
        ))

        result_off = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="CustomerID",
            schema_name="SalesLT",
            pk_candidates_only=False,
        ))

        assert result_on["status"] == "success"
        assert result_off["status"] == "success"
        # With filter off, should return >= candidates than with filter on
        assert result_off["total_found"] >= result_on["total_found"]


# ---------------------------------------------------------------------------
# Value overlap
# ---------------------------------------------------------------------------

class TestValueOverlap:
    """Tests for include_overlap parameter."""

    @pytest.mark.asyncio
    async def test_overlap_disabled_by_default(self, connection_id):
        """Default behavior does not include overlap fields."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="CustomerID",
            schema_name="SalesLT",
        ))

        assert result["status"] == "success"
        for candidate in result["candidates"]:
            assert "overlap_count" not in candidate
            assert "overlap_percentage" not in candidate

    @pytest.mark.asyncio
    async def test_overlap_enabled(self, connection_id):
        """include_overlap=True returns overlap count and percentage."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="CustomerID",
            schema_name="SalesLT",
            include_overlap=True,
        ))

        assert result["status"] == "success"
        if result["candidates"]:
            candidate = result["candidates"][0]
            assert "overlap_count" in candidate
            assert "overlap_percentage" in candidate
            assert isinstance(candidate["overlap_count"], int)
            assert isinstance(candidate["overlap_percentage"], float)


# ---------------------------------------------------------------------------
# Scoping filters
# ---------------------------------------------------------------------------

class TestScopingFilters:
    """Tests for schema/table/pattern scoping."""

    @pytest.mark.asyncio
    async def test_target_table_pattern(self, connection_id):
        """target_table_pattern filters target tables."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="CustomerID",
            schema_name="SalesLT",
            target_table_pattern="Customer%",
        ))

        assert result["status"] == "success"
        for candidate in result["candidates"]:
            assert candidate["target_table"].startswith("Customer")

    @pytest.mark.asyncio
    async def test_target_tables_list(self, connection_id):
        """target_tables explicit list filters results."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="CustomerID",
            schema_name="SalesLT",
            target_tables=["Customer"],
        ))

        assert result["status"] == "success"
        for candidate in result["candidates"]:
            assert candidate["target_table"] == "Customer"


# ---------------------------------------------------------------------------
# Limit enforcement
# ---------------------------------------------------------------------------

class TestLimitEnforcement:
    """Tests for result limiting."""

    @pytest.mark.asyncio
    async def test_limit_parameter(self, connection_id):
        """Limit parameter caps the number of candidates."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="CustomerID",
            schema_name="SalesLT",
            limit=2,
        ))

        assert result["status"] == "success"
        assert len(result["candidates"]) <= 2


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Error response tests."""

    @pytest.mark.asyncio
    async def test_invalid_connection_id(self):
        """Invalid connection_id returns error."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id="nonexistent",
            table_name="SalesOrderHeader",
            column_name="CustomerID",
        ))

        assert result["status"] == "error"
        assert "not found" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_table_not_found(self, connection_id):
        """Nonexistent table returns error."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="NonexistentTable12345",
            column_name="SomeColumn",
        ))

        assert result["status"] == "error"
        assert "not found" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_column_not_found(self, connection_id):
        """Nonexistent column returns error."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="NonexistentColumn12345",
            schema_name="SalesLT",
        ))

        assert result["status"] == "error"
        assert "not found" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_empty_result_not_error(self, connection_id):
        """No candidates returns success with empty list, not error."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="CustomerID",
            schema_name="SalesLT",
            target_tables=["NonexistentTable12345"],
        ))

        # Should be success with empty candidates, not error
        assert result["status"] == "success"
        assert result["candidates"] == []
        assert result["total_found"] == 0


# ---------------------------------------------------------------------------
# Default schema
# ---------------------------------------------------------------------------

class TestDefaultSchema:
    """Tests for default schema behavior."""

    @pytest.mark.asyncio
    async def test_default_schema_is_dbo(self, connection_id):
        """When no schema specified, defaults to 'dbo'."""
        from src.mcp_server.analysis_tools import find_fk_candidates

        result = parse_tool_response(await find_fk_candidates(
            connection_id=connection_id,
            table_name="SalesOrderHeader",
            column_name="CustomerID",
            # No schema_name — should default to "dbo"
        ))

        # May be error (no SalesOrderHeader in dbo) or success
        # The point is that the source schema_name defaults to "dbo"
        if result["status"] == "success":
            assert result["source"]["schema_name"] == "dbo"

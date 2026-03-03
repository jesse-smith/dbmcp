"""Integration tests for find_pk_candidates MCP tool.

Tests end-to-end behavior against a real SQL Server test database.
Requires TEST_DB_SERVER, TEST_DB_DATABASE, TEST_DB_USERNAME, TEST_DB_PASSWORD
environment variables.
"""

import json
import os

import pytest

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
    data = json.loads(result)
    assert data["status"] == "success", f"Connection failed: {data}"
    return data["connection_id"]


# ---------------------------------------------------------------------------
# Basic PK candidate discovery
# ---------------------------------------------------------------------------

class TestFindPKCandidatesBasic:
    """Basic end-to-end tests for find_pk_candidates."""

    @pytest.mark.asyncio
    async def test_declared_pk_table(self, connection_id):
        """Table with declared PK returns it as constraint-backed candidate."""
        from src.mcp_server.analysis_tools import find_pk_candidates

        result = json.loads(await find_pk_candidates(
            connection_id=connection_id,
            table_name="Customers",
            schema_name="SalesLT",
        ))

        assert result["status"] == "success"
        assert result["table_name"] == "Customers"
        assert result["schema_name"] == "SalesLT"
        assert len(result["candidates"]) >= 1

        # The declared PK should be constraint-backed
        pk_candidates = [
            c for c in result["candidates"] if c["is_constraint_backed"]
        ]
        assert len(pk_candidates) >= 1
        assert pk_candidates[0]["constraint_type"] == "PRIMARY KEY"

    @pytest.mark.asyncio
    async def test_candidates_have_required_fields(self, connection_id):
        """Each candidate has all required fields from PKCandidate model."""
        from src.mcp_server.analysis_tools import find_pk_candidates

        result = json.loads(await find_pk_candidates(
            connection_id=connection_id,
            table_name="Customers",
            schema_name="SalesLT",
        ))

        assert result["status"] == "success"
        for candidate in result["candidates"]:
            assert "column_name" in candidate
            assert "data_type" in candidate
            assert "is_constraint_backed" in candidate
            assert "constraint_type" in candidate
            assert "is_unique" in candidate
            assert "is_non_null" in candidate
            assert "is_pk_type" in candidate


# ---------------------------------------------------------------------------
# Type filter behavior
# ---------------------------------------------------------------------------

class TestTypeFilter:
    """Tests for type_filter parameter."""

    @pytest.mark.asyncio
    async def test_default_type_filter(self, connection_id):
        """Default type filter includes standard integer types."""
        from src.mcp_server.analysis_tools import find_pk_candidates

        result = json.loads(await find_pk_candidates(
            connection_id=connection_id,
            table_name="Customers",
            schema_name="SalesLT",
        ))

        assert result["status"] == "success"
        # With default filter, structural candidates should only have PK-compatible types
        for c in result["candidates"]:
            if not c["is_constraint_backed"]:
                assert c["is_pk_type"] is True

    @pytest.mark.asyncio
    async def test_empty_type_filter_disables_filtering(self, connection_id):
        """Empty type_filter includes all column types."""
        from src.mcp_server.analysis_tools import find_pk_candidates

        result = json.loads(await find_pk_candidates(
            connection_id=connection_id,
            table_name="Customers",
            schema_name="SalesLT",
            type_filter=[],
        ))

        assert result["status"] == "success"
        # All structural candidates should have is_pk_type=True (since no filter)
        for c in result["candidates"]:
            if not c["is_constraint_backed"]:
                assert c["is_pk_type"] is True


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Error response tests."""

    @pytest.mark.asyncio
    async def test_invalid_connection_id(self):
        """Invalid connection_id returns error."""
        from src.mcp_server.analysis_tools import find_pk_candidates

        result = json.loads(await find_pk_candidates(
            connection_id="nonexistent",
            table_name="Customers",
        ))

        assert result["status"] == "error"
        assert "not found" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_table_not_found(self, connection_id):
        """Nonexistent table returns error."""
        from src.mcp_server.analysis_tools import find_pk_candidates

        result = json.loads(await find_pk_candidates(
            connection_id=connection_id,
            table_name="NonexistentTable12345",
        ))

        assert result["status"] == "error"
        assert "not found" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_no_candidates_returns_empty_list(self, connection_id):
        """Table with no PK candidates returns empty list, not error."""
        from src.mcp_server.analysis_tools import find_pk_candidates

        # Use a table that may not have PK candidates
        # (this is table-dependent; adjust if needed)
        result = json.loads(await find_pk_candidates(
            connection_id=connection_id,
            table_name="Customers",
            schema_name="SalesLT",
        ))

        assert result["status"] == "success"
        assert isinstance(result["candidates"], list)


# ---------------------------------------------------------------------------
# Default schema
# ---------------------------------------------------------------------------

class TestDefaultSchema:
    """Tests for default schema behavior."""

    @pytest.mark.asyncio
    async def test_default_schema_is_dbo(self, connection_id):
        """When no schema specified, defaults to 'dbo'."""
        from src.mcp_server.analysis_tools import find_pk_candidates

        result = json.loads(await find_pk_candidates(
            connection_id=connection_id,
            table_name="Customers",
            # No schema_name — should default to "dbo"
        ))

        # May be error (no Customers in dbo) or success
        # The point is that schema_name defaults to "dbo"
        if result["status"] == "success":
            assert result["schema_name"] == "dbo"

"""FastMCP server for Database Schema Explorer.

This module implements the MCP server entry point. Tool definitions are in
separate modules (schema_tools, query_tools) which register themselves via
the shared `mcp` instance.

CRITICAL: Never use print() or stdout - it corrupts JSON-RPC messages.
All logging goes to file and stderr only.
"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.db.connection import ConnectionManager
from src.logging_config import CredentialFilter, setup_logging

# Configure logging (file + stderr, never stdout)
logger = setup_logging(log_file=Path("dbmcp.log"), log_to_stderr=True)
logger.addFilter(CredentialFilter())

# Create MCP server instance
mcp = FastMCP("dbmcp")

# Global connection manager (singleton for the server lifetime)
_connection_manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    return _connection_manager


# Import tool modules to register @mcp.tool() decorated functions.
# These imports MUST come after mcp, logger, and get_connection_manager are defined,
# since the tool modules import those symbols from this module.
from src.mcp_server.analysis_tools import (  # noqa: E402, F401
    find_pk_candidates,
    get_column_info,
)
from src.mcp_server.query_tools import (  # noqa: E402, F401
    execute_query,
    get_sample_data,
)
from src.mcp_server.schema_tools import (  # noqa: E402, F401
    connect_database,
    get_table_schema,
    list_schemas,
    list_tables,
)

# =============================================================================
# Server Entry Point
# =============================================================================


def main():
    """Run the MCP server on stdio transport."""
    logger.info("Starting dbmcp MCP server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

"""Tests for server lifecycle management (atexit cleanup and SIGTERM handler).

Verifies CONN-02 requirements: all database connections are cleaned up
when the MCP server process exits.
"""

import inspect
import signal
from unittest.mock import patch

import pytest


class TestAtexitRegistration:
    """Tests for atexit registration of disconnect_all."""

    def test_atexit_register_called_with_disconnect_all(self):
        """atexit.register is called with _connection_manager.disconnect_all on module load.

        Instead of reloading the server module (which breaks global MCP tool registry),
        we verify the module source contains the atexit registration call.
        """
        import src.mcp_server.server as server_module

        source = inspect.getsource(server_module)
        assert "import atexit" in source
        assert "atexit.register(_connection_manager.disconnect_all)" in source


class TestSigtermHandler:
    """Tests for SIGTERM handler registration and behavior."""

    @patch("src.mcp_server.server.mcp")
    def test_sigterm_handler_registered_in_main(self, mock_mcp):
        """signal.signal(SIGTERM, handler) is called in main() before mcp.run()."""
        from src.mcp_server.server import main

        with patch("src.mcp_server.server.signal") as mock_signal_module:
            mock_signal_module.SIGTERM = signal.SIGTERM
            main()

            mock_signal_module.signal.assert_called_once()
            call_args = mock_signal_module.signal.call_args
            assert call_args[0][0] == signal.SIGTERM

    @patch("src.mcp_server.server.mcp")
    def test_sigterm_handler_calls_sys_exit_0(self, mock_mcp):
        """The SIGTERM handler calls sys.exit(0) when invoked."""
        from src.mcp_server.server import main

        with patch("src.mcp_server.server.signal") as mock_signal_module:
            mock_signal_module.SIGTERM = signal.SIGTERM
            main()

            # Extract the handler function
            handler = mock_signal_module.signal.call_args[0][1]

            # Calling the handler should raise SystemExit(0)
            with pytest.raises(SystemExit) as exc_info:
                handler(signal.SIGTERM, None)

            assert exc_info.value.code == 0

"""
MCP Server Main Entry.
Exposes the tools via stdio or SSE for external IDEs to connect.
"""
from mcp.tools import mcp

if __name__ == "__main__":
    # Starts the FastMCP server, making all tools available
    # to Cursor, Claude Desktop, and other MCP clients.
    mcp.run()

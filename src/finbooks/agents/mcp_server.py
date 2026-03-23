"""MCP server factory — dispatches to the correct tool set based on mode.

Usage:
    server = create_server("fixed")   # or "hybrid"
    options = ClaudeAgentOptions(mcp_servers={"finbooks": server}, ...)
"""

from __future__ import annotations

from claude_agent_sdk import create_sdk_mcp_server

from finbooks.agents.output_tools import OUTPUT_TOOLS


def create_server(mode: str):
    """Return a McpSdkServerConfig with the tool set for *mode*.

    fixed  — extract_pdf, get_books_data, compare_statement + shared output tools
    hybrid — read_pdf_raw, read_books_raw, python_repl + shared output tools
    """
    if mode == "fixed":
        from finbooks.agents.modes.fixed import TOOLS
        all_tools = TOOLS + OUTPUT_TOOLS
    else:
        from finbooks.agents.modes.hybrid import TOOLS
        all_tools = TOOLS + OUTPUT_TOOLS

    return create_sdk_mcp_server(
        name="finbooks-validator",
        version="0.1.0",
        tools=all_tools,
    )

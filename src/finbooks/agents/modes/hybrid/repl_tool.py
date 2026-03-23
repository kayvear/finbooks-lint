"""Hybrid-mode python_repl tool — sandboxed code execution for the agent.

WHY THIS EXISTS
---------------
In hybrid mode the agent doesn't call a pre-built ``compare_statement`` tool.
Instead it receives raw data from both sides (via read_pdf_raw / read_books_raw)
and writes its own Python comparison code.  The comparison logic lives in the
agent's prompt context, not in our source tree — so it can evolve with the
prompt without a code deploy.

HOW IT WORKS
------------
A shared ``_namespace`` dict persists for the lifetime of one validation run
(created fresh in ``reset_namespace()`` before each PDF).  The agent can call
``python_repl`` multiple times and state accumulates across calls — exactly
like an interactive Python session.

The agent's typical call sequence:
    1. python_repl("import json; extracted = json.loads(<pdf_json_string>)")
    2. python_repl("import json; books = json.loads(<books_json_string>)")
    3. python_repl(
           "breaks = []\n"
           "for row in extracted['sections']['positions']['rows']:\n"
           "    ...\n"
           "result = breaks"
       )
    4. write_break_report(json.dumps(result), customer_id, period)

The tool captures stdout and the ``result`` variable.  The agent reads both
in the tool response to verify its code ran correctly.

SANDBOXING NOTE
---------------
The exec runs in the shared namespace with no import restrictions.  This is
intentional for a local development project — the agent may need ``json``,
``math``, etc.  If this tool were deployed in a multi-tenant environment,
add an allow-list for builtins.
"""

from __future__ import annotations

import contextlib
import io
from typing import Any

from claude_agent_sdk import tool

# Shared execution namespace — persists across python_repl calls within one run.
# Reset via reset_namespace() before each new PDF validation.
_namespace: dict[str, Any] = {}


def reset_namespace() -> None:
    """Clear the execution namespace.  Call once before each validation run."""
    _namespace.clear()


@tool(
    name="python_repl",
    description=(
        "Execute Python code in a persistent session. "
        "State (variables, imports) accumulates across calls. "
        "Assign your final list of break dicts to the variable 'result'. "
        "stdout and the value of 'result' are returned after each call."
    ),
    input_schema={"code": str},
)
async def python_repl(args: dict[str, Any]) -> dict[str, Any]:
    stdout_capture = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_capture):
            exec(args["code"], _namespace)  # noqa: S102  (exec is the point here)
        output = stdout_capture.getvalue()
        result = _namespace.get("result")
        response = output
        if result is not None:
            import json as _json
            try:
                result_json = _json.dumps(result)
                response += f"\nRESULT_JSON: {result_json}"
            except Exception:
                response += f"\nresult = {result!r}"
        if not response.strip():
            response = "(no output)"
        return {"content": [{"type": "text", "text": response}]}
    except Exception as exc:
        output = stdout_capture.getvalue()
        error_text = f"{output}\nError: {type(exc).__name__}: {exc}"
        return {"content": [{"type": "text", "text": error_text}], "is_error": True}

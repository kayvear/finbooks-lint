from finbooks.agents.modes.hybrid.io_tools import read_pdf_raw, read_books_raw
from finbooks.agents.modes.hybrid.repl_tool import python_repl

IO_TOOLS = [read_pdf_raw, read_books_raw]
TOOLS = IO_TOOLS + [python_repl]

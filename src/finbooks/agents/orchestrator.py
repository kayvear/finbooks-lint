"""Orchestrator — deterministic fan-out over all PDFs.

run(pdf_paths, mode) → list[ComparisonResult]

The orchestrator is a plain Python function (not a Claude agent).  It calls
run_validation_agent() for each PDF sequentially, collects the results, then
writes the combined JSON report and audit memo PDF.

Sequential processing is intentional: it keeps logs readable and avoids
concurrent Anthropic API calls.  Comment out the loop and uncomment the
asyncio.gather line to enable parallel processing if needed.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import anyio
from rich.console import Console
from rich.progress import Progress

from finbooks.agents.validation_agent import run_validation_agent
from finbooks.comparison.models import ComparisonResult
from finbooks.storage.paths import StoragePaths
from finbooks.validation.reports.audit_memo import AuditMemo
from finbooks.validation.reports.break_report import write_csv, write_json

console = Console()


async def _orchestrate(pdf_paths: list[Path], mode: str) -> list[ComparisonResult]:
    results: list[ComparisonResult] = []

    with Progress(console=console) as progress:
        task = progress.add_task(f"Agents [{mode}]...", total=len(pdf_paths))
        for pdf_path in pdf_paths:
            result = await run_validation_agent(pdf_path, mode)
            results.append(result)

            # Write per-customer CSV immediately (same as direct pipeline)
            csv_path = StoragePaths.break_csv(result.customer_id)
            write_csv(result.breaks, csv_path)

            progress.advance(task)
            n = len(result.breaks)
            color = "red" if n else "green"
            console.print(
                f"  [{color}]{'BREAKS' if n else 'CLEAN'}[/{color}] "
                f"{pdf_path.name} — {n} break(s)"
            )

    # Combined outputs
    write_json(results, StoragePaths.all_breaks_json())
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    AuditMemo().render(results, StoragePaths.audit_memo_pdf(run_id))

    return results


def run(pdf_paths: list[Path], mode: str) -> list[ComparisonResult]:
    """Synchronous entry point — runs the async orchestrator via anyio."""
    return anyio.run(_orchestrate, pdf_paths, mode)


async def run_async(pdf_paths: list[Path], mode: str) -> list[ComparisonResult]:
    """Async entry point for callers already inside an event loop."""
    return await _orchestrate(pdf_paths, mode)

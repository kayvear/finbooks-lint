"""
Validate PDF statements against books & records data (Phase 2a — no agents).

Usage:
    # Validate clean PDFs against clean books
    python scripts/validate_statements.py

    # Validate injected PDFs (from data/statements_injected/) against clean books
    python scripts/validate_statements.py --injected

    # Validate a specific PDF
    python scripts/validate_statements.py --pdf data/statements/<file>.pdf

    # Use a custom raw data directory (e.g. dirty parquet for books-side injection)
    python scripts/validate_statements.py --raw-dir data/raw_injected

Pipeline per PDF:
    1. Extract structured data from the PDF (pdfplumber; Claude vision as fallback)
    2. Retrieve books snapshot from parquet for the same customer + period
    3. Compare both sides → produce list[Break]
    4. Write per-customer CSV to data/validation/breaks_{customer_id}.csv
    5. After all customers: write combined JSON + narrative audit memo PDF
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from finbooks.comparison.books_retriever import BooksRetriever
from finbooks.comparison.comparator import StatementComparator
from finbooks.comparison.models import ComparisonResult
from finbooks.extraction.pdf_extractor import PdfExtractor, _period_from_filename
from finbooks.extraction.vision_extractor import VisionExtractor
from finbooks.storage.paths import StoragePaths
from finbooks.validation.reports.audit_memo import AuditMemo
from finbooks.validation.reports.break_report import write_csv, write_json

console = Console()

# Confidence threshold below which we fall back to vision extraction
_FALLBACK_THRESHOLD = 0.7


def validate_pdf(
    pdf_path: Path,
    retriever: BooksRetriever,
    comparator: StatementComparator,
    pdf_extractor: PdfExtractor,
    vision_extractor: VisionExtractor | None,
) -> ComparisonResult:
    """Run the full extraction → comparison pipeline for one PDF.

    Falls back to vision extraction if pdfplumber confidence is low.
    """
    # Derive customer_id from filename: {customer_id}_{period}.pdf
    stem = pdf_path.stem
    parts = stem.rsplit("_", 1)
    customer_id = parts[0] if len(parts) == 2 else stem
    period = parts[-1] if len(parts) == 2 else "unknown"

    # ── Extract ───────────────────────────────────────────────────────────────
    extracted = pdf_extractor.extract(pdf_path, customer_id)

    if extracted.confidence < _FALLBACK_THRESHOLD and vision_extractor is not None:
        console.print(
            f"    [yellow]Low confidence ({extracted.confidence:.2f}) — "
            f"switching to vision extractor[/yellow]"
        )
        extracted = vision_extractor.extract(pdf_path, customer_id)

    # ── Books snapshot ────────────────────────────────────────────────────────
    books = retriever.get_snapshot(customer_id, period)

    # ── Compare ───────────────────────────────────────────────────────────────
    return comparator.compare(extracted, books)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate PDF statements against books data."
    )
    parser.add_argument(
        "--injected", action="store_true",
        help="Read PDFs from data/statements_injected/ instead of data/statements/.",
    )
    parser.add_argument(
        "--pdf", type=str, default=None,
        help="Validate a single PDF file (overrides --injected).",
    )
    parser.add_argument(
        "--raw-dir", type=str, default=None,
        help="Custom raw parquet directory (default: data/raw/).",
    )
    parser.add_argument(
        "--no-vision", action="store_true",
        help="Disable Claude vision fallback (useful when ANTHROPIC_API_KEY is not set).",
    )
    args = parser.parse_args()

    # ── Determine PDF source ──────────────────────────────────────────────────
    if args.pdf:
        pdf_files = [Path(args.pdf)]
    elif args.injected:
        pdf_dir = StoragePaths.statements_injected
        if not pdf_dir.exists():
            console.print(
                f"[red]Injected statements directory not found:[/red] {pdf_dir}\n"
                "Run: python scripts/generate_statements.py --inject"
            )
            return
        pdf_files = sorted(pdf_dir.glob("*.pdf"))
    else:
        pdf_dir = StoragePaths.statements
        pdf_files = sorted(pdf_dir.glob("*.pdf"))

    if not pdf_files:
        console.print("[red]No PDF files found.[/red] Generate statements first.")
        return

    # ── Determine books source ────────────────────────────────────────────────
    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    if raw_dir and not raw_dir.exists():
        console.print(f"[red]Raw data directory not found:[/red] {raw_dir}")
        return

    # Check parquet files exist
    check_dir = raw_dir or StoragePaths.raw
    for fname in ("customers.parquet", "accounts.parquet", "positions.parquet"):
        if not (check_dir / fname).exists():
            console.print(
                f"[red]Missing:[/red] {check_dir / fname}\n"
                "Run: python scripts/generate_data.py"
            )
            return

    # ── Setup pipeline components ─────────────────────────────────────────────
    pdf_extractor = PdfExtractor(fallback_threshold=_FALLBACK_THRESHOLD)
    vision_extractor: VisionExtractor | None = None
    if not args.no_vision:
        try:
            import anthropic  # noqa: F401
            vision_extractor = VisionExtractor()
        except ImportError:
            console.print("[yellow]anthropic not installed — vision fallback disabled.[/yellow]")

    retriever = BooksRetriever(raw_dir=raw_dir)
    comparator = StatementComparator()

    StoragePaths.validation.mkdir(parents=True, exist_ok=True)

    # ── Run validation ────────────────────────────────────────────────────────
    console.print(f"\n[bold]Finbooks-Lint — Statement Validator[/bold]")
    console.print(f"PDFs:  {len(pdf_files)} file(s)")
    console.print(f"Books: {check_dir}\n")

    all_results: list[ComparisonResult] = []

    with Progress(console=console) as progress:
        task = progress.add_task("Validating...", total=len(pdf_files))
        for pdf_path in pdf_files:
            result = validate_pdf(
                pdf_path, retriever, comparator,
                pdf_extractor, vision_extractor,
            )
            all_results.append(result)

            # Write per-customer CSV immediately
            csv_path = StoragePaths.break_csv(result.customer_id)
            write_csv(result.breaks, csv_path)

            progress.advance(task)
            break_count = len(result.breaks)
            color = "red" if break_count > 0 else "green"
            console.print(
                f"  [{color}]{'BREAKS' if break_count else 'CLEAN'}[/{color}] "
                f"{pdf_path.name} — {break_count} break(s)"
            )

    # ── Write combined outputs ────────────────────────────────────────────────
    json_path = StoragePaths.all_breaks_json()
    write_json(all_results, json_path)
    console.print(f"\n[green]JSON report:[/green]  {json_path}")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    memo_path = StoragePaths.audit_memo_pdf(run_id)
    memo = AuditMemo()
    memo.render(all_results, memo_path)
    console.print(f"[green]Audit memo:[/green]   {memo_path}")

    # ── Console summary ───────────────────────────────────────────────────────
    total_breaks = sum(len(r.breaks) for r in all_results)
    console.print(f"\n[bold]Total breaks found:[/bold] {total_breaks}")

    if total_breaks > 0:
        table = Table(title="Breaks by Type", show_header=True, header_style="bold")
        table.add_column("Error Type", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("High", justify="right", style="red")
        table.add_column("Medium", justify="right", style="yellow")
        table.add_column("Low", justify="right", style="green")

        from collections import Counter
        from finbooks.comparison.models import BreakSeverity
        from finbooks.discrepancies.schema import ErrorType

        all_breaks = [b for r in all_results for b in r.breaks]
        by_type = Counter(b.break_type for b in all_breaks)

        for err_type in ErrorType:
            count = by_type.get(err_type, 0)
            if count == 0:
                continue
            type_breaks = [b for b in all_breaks if b.break_type == err_type]
            h = sum(1 for b in type_breaks if b.severity == BreakSeverity.HIGH)
            m = sum(1 for b in type_breaks if b.severity == BreakSeverity.MEDIUM)
            lo = sum(1 for b in type_breaks if b.severity == BreakSeverity.LOW)
            table.add_row(err_type.value, str(count), str(h), str(m), str(lo))

        console.print(table)

    console.print(f"\n[bold green]Done.[/bold green]")


if __name__ == "__main__":
    main()

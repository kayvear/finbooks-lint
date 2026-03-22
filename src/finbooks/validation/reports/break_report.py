"""Structured break report writers — CSV (per customer) and JSON (all customers)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from finbooks.comparison.models import Break, ComparisonResult


_CSV_FIELDS = [
    "break_id", "customer_id", "period",
    "break_type", "section", "field",
    "pdf_value", "books_value", "delta",
    "severity", "description",
]


def write_csv(breaks: list[Break], output_path: Path) -> None:
    """Write *breaks* to a CSV file at *output_path*.

    Creates parent directories if needed.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for b in breaks:
            row = b.model_dump()
            row["break_type"] = b.break_type.value
            row["severity"] = b.severity.value
            writer.writerow(row)


def write_json(results: list[ComparisonResult], output_path: Path) -> None:
    """Write all *results* to a single JSON file at *output_path*.

    The JSON structure is::

        {
          "total_breaks": N,
          "customers": [
            {
              "customer_id": "...",
              "period": "...",
              "break_count": N,
              "highest_severity": "...",
              "breaks": [...]
            }
          ]
        }
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_breaks = [b for r in results for b in r.breaks]
    payload = {
        "total_breaks": len(all_breaks),
        "customers": [
            {
                "customer_id": r.customer_id,
                "period": r.period,
                "break_count": len(r.breaks),
                "highest_severity": r.highest_severity.value if r.highest_severity else None,
                "breaks": [
                    {
                        **b.model_dump(),
                        "break_type": b.break_type.value,
                        "severity": b.severity.value,
                    }
                    for b in r.breaks
                ],
            }
            for r in results
        ],
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

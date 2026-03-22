"""Load a discrepancy spec from a YAML file."""

from pathlib import Path

import yaml

from finbooks.discrepancies.schema import DiscrepancySpec


def load_spec(path: Path | str) -> DiscrepancySpec:
    """Parse *path* (YAML) → :class:`DiscrepancySpec`.

    Raises ``FileNotFoundError`` if the file doesn't exist.
    Raises ``ValueError`` if the YAML is malformed or fails Pydantic validation.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Discrepancy spec not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected a YAML mapping at the root of {path}")

    return DiscrepancySpec.model_validate(raw)

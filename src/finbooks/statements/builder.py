from pathlib import Path

from finbooks.models.statement import StatementData
from finbooks.statements.statement import CustomerStatement


class StatementBuilder:
    """Renders a CustomerStatement PDF from StatementData and writes it to disk."""

    def __init__(self, institution_name: str = "Financial Services, Inc.") -> None:
        self.institution_name = institution_name

    def build(self, data: StatementData, output_path: Path) -> Path:
        """Render the statement PDF and save to output_path. Returns the path."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        pdf = CustomerStatement(institution_name=self.institution_name)
        pdf.build(data)
        pdf.output(str(output_path))

        return output_path

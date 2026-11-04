"""Collect and render the summary printed to stderr after anonymizing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

PDPA_NOTE = "Output is pseudonymized test data — still handle under PDPA s.37."


@dataclass
class TableStats:
    rows: int = 0
    cells: int = 0
    truncated_rows: int = 0


@dataclass
class Report:
    profile: str
    tables: dict[str, TableStats] = field(default_factory=dict)
    missing_columns: set[tuple[str, str]] = field(default_factory=set)
    suspicious_columns: set[tuple[str, str]] = field(default_factory=set)
    bytes_in: int = 0
    seconds: float = 0.0

    def stats(self, table: str) -> TableStats:
        """Return the counters for ``table``, creating them on first use."""
        return self.tables.setdefault(table, TableStats())

    def render(self, console: "Console") -> None:
        """Print the run summary; the last line is always the PDPA reminder."""
        from rich.markup import escape
        from rich.table import Table

        console.print(f"[bold]Profile:[/bold] {escape(self.profile)}")

        if self.bytes_in or self.seconds:
            mebibytes = self.bytes_in / (1024 * 1024)
            if self.seconds > 0:
                rate = mebibytes / self.seconds
                console.print(
                    f"{mebibytes:.1f} MiB in {self.seconds:.1f}s ({rate:.1f} MiB/s)"
                )
            else:
                console.print(f"{mebibytes:.1f} MiB")

        if self.tables:
            table = Table(title="Tables", box=None, pad_edge=False)
            table.add_column("table")
            table.add_column("rows", justify="right")
            table.add_column("cells", justify="right")
            table.add_column("truncated", justify="right")
            for name in sorted(self.tables):
                stats = self.tables[name]
                table.add_row(
                    escape(name),
                    str(stats.rows),
                    str(stats.cells),
                    str(stats.truncated_rows),
                )
            console.print(table)

        if self.missing_columns:
            columns = ", ".join(
                f"{table}.{column}" for table, column in sorted(self.missing_columns)
            )
            console.print(
                "[yellow]Profile columns missing from the dump:[/yellow] "
                + escape(columns)
            )

        if self.suspicious_columns:
            columns = ", ".join(
                f"{table}.{column}" for table, column in sorted(self.suspicious_columns)
            )
            console.print(
                "[yellow]Columns that look like personal data but have no rule:"
                "[/yellow] " + escape(columns)
            )

        console.print(PDPA_NOTE, markup=False)

"""
output/formatter.py
Formats the ranked component list for display or export.

Each entry in the ranked list is a tuple:
    (rank: int, qualified_name: str, weight: float)

Supported formats: table (default), csv, json.
"""

from __future__ import annotations
import csv
import io
import json


RankedEntry = tuple[int, str, float]


def format_output(
    ranked: list[RankedEntry],
    fmt: str = "table",
    top: int | None = None,
) -> str:
    """
    Render the ranked list as a human-readable or machine-readable string.

    Parameters
    ----------
    ranked:
        Sorted list of (rank, qualified_name, weight) tuples.
    fmt:
        One of "table", "csv", "json".
    top:
        If provided, only the first `top` entries are included.
    """
    data = ranked[:top] if top is not None else ranked

    if fmt == "table":
        return _format_table(data)
    if fmt == "csv":
        return _format_csv(data)
    if fmt == "json":
        return _format_json(data)
    raise ValueError(f"Unknown output format '{fmt}'. Choose: table, csv, json")


def _format_table(data: list[RankedEntry]) -> str:
    try:
        from tabulate import tabulate
        rows = [(rank, name, f"{weight:.8f}") for rank, name, weight in data]
        return tabulate(
            rows,
            headers=["Rank", "Component", "Weight"],
            tablefmt="grid",
        )
    except ImportError:
        # Fallback: plain aligned text
        lines = [f"{'Rank':>6}  {'Weight':>12}  Component"]
        lines.append("-" * 80)
        for rank, name, weight in data:
            lines.append(f"{rank:>6}  {weight:>12.8f}  {name}")
        return "\n".join(lines)


def _format_csv(data: list[RankedEntry]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["rank", "qualified_name", "weight"])
    for rank, name, weight in data:
        writer.writerow([rank, name, f"{weight:.10f}"])
    return buf.getvalue()


def _format_json(data: list[RankedEntry]) -> str:
    entries = [
        {"rank": rank, "qualified_name": name, "weight": round(weight, 10)}
        for rank, name, weight in data
    ]
    return json.dumps(entries, indent=2)

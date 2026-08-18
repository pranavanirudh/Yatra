"""Shared fixtures.

**On the numbers in this file.** The counts written here are contract fixtures:
they exist to exercise the loader's validation logic and they never leave
``tmp_path``. They are not observations, they are not derived from any published
figure, and no code path carries them into ``data/``, ``results/`` or the README.

The project's rule is that observations are never generated. That rule is about
claims concerning how many people visited a shrine. Asserting that a CSV with a
missing month raises ``ContractViolation`` is a claim about a parser. See
docs/claude_code_brief.md section 4 for where the line sits and why.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

SOURCE_ID = "fixture_source"

VALID_SOURCE = {
    SOURCE_ID: {
        "publisher": "Fixture Publisher",
        "title": "Contract test fixture, not a real source",
        "url": "https://example.invalid/fixture",
        "accessed": "2026-08-18",
    }
}


def write_dataset(
    directory: Path,
    monthly: dict[str, int] | None = None,
    annual: dict[int, int] | None = None,
    sources: dict | None = None,
    monthly_source: str = SOURCE_ID,
) -> Path:
    """Write a three-file dataset into ``directory``. Returns the directory."""
    directory.mkdir(parents=True, exist_ok=True)

    if monthly is None:
        monthly = two_clean_years()
    if annual is None:
        annual = {year: sum(v for k, v in monthly.items() if k.startswith(str(year)))
                  for year in sorted({int(k[:4]) for k in monthly})}
    if sources is None:
        sources = VALID_SOURCE

    lines = ["month,pilgrims,source_id"]
    lines += [f"{month},{count},{monthly_source}" for month, count in monthly.items()]
    (directory / "monthly.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    lines = ["year,pilgrims,source_id"]
    lines += [f"{year},{count},{monthly_source}" for year, count in annual.items()]
    (directory / "annual.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    (directory / "sources.yaml").write_text(yaml.safe_dump(sources), encoding="utf-8")
    return directory


def two_clean_years(start_year: int = 2000) -> dict[str, int]:
    """Twenty-four contiguous months whose annual sums are exact by construction."""
    return {
        f"{year}-{month:02d}": 1000 + month
        for year in (start_year, start_year + 1)
        for month in range(1, 13)
    }


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    return write_dataset(tmp_path / "raw")

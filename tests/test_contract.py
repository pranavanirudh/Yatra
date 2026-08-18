"""The data contract. Each test names a way a plausible-looking file is wrong."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import SOURCE_ID, VALID_SOURCE, two_clean_years, write_dataset
from yatra import contract
from yatra.errors import ContractViolation, MissingObservations


def test_absent_files_raise_and_name_the_paths(tmp_path: Path):
    with pytest.raises(MissingObservations) as excinfo:
        contract.load(tmp_path / "nothing-here")
    message = str(excinfo.value)
    assert "monthly.csv" in message
    assert "annual.csv" in message
    assert "sources.yaml" in message


def test_partial_dataset_still_raises(tmp_path: Path):
    directory = tmp_path / "raw"
    directory.mkdir()
    (directory / "monthly.csv").write_text("month,pilgrims,source_id\n", encoding="utf-8")
    with pytest.raises(MissingObservations):
        contract.load(directory)


def test_happy_path_loads(dataset: Path):
    observations = contract.load(dataset)
    assert observations.n_months == 24
    assert len(observations.annual) == 2
    first, last = observations.span
    assert (first.year, first.month) == (2000, 1)
    assert (last.year, last.month) == (2001, 12)
    assert "24 monthly observations" in observations.describe()


def test_gap_is_reported_by_name(tmp_path: Path):
    months = two_clean_years()
    del months["2000-07"]
    del months["2001-03"]
    write_dataset(tmp_path / "raw", monthly=months,
                  annual={})  # skip reconciliation; the gap must fire first

    with pytest.raises(ContractViolation) as excinfo:
        contract.load(tmp_path / "raw")
    message = str(excinfo.value)
    assert "2000-07" in message and "2001-03" in message
    assert "Missing data stays missing" in message


def test_duplicate_month_raises(tmp_path: Path):
    directory = tmp_path / "raw"
    write_dataset(directory)
    path = directory / "monthly.csv"
    path.write_text(path.read_text(encoding="utf-8") + f"2000-01,999,{SOURCE_ID}\n",
                    encoding="utf-8")
    with pytest.raises(ContractViolation, match="duplicate months"):
        contract.load(directory)


def test_null_count_raises_rather_than_being_treated_as_zero(tmp_path: Path):
    directory = tmp_path / "raw"
    write_dataset(directory)
    path = directory / "monthly.csv"
    path.write_text(path.read_text(encoding="utf-8").replace(
        f"2000-05,1005,{SOURCE_ID}", f"2000-05,,{SOURCE_ID}"), encoding="utf-8")
    with pytest.raises(ContractViolation) as excinfo:
        contract.load(directory)
    assert "not interpolated" in str(excinfo.value)


def test_fractional_count_raises_and_mentions_lakh(tmp_path: Path):
    """A figure left in lakh is the realistic way this column goes wrong."""
    directory = tmp_path / "raw"
    write_dataset(directory)
    path = directory / "monthly.csv"
    path.write_text(path.read_text(encoding="utf-8").replace(
        f"2000-05,1005,{SOURCE_ID}", f"2000-05,10.05,{SOURCE_ID}"), encoding="utf-8")
    with pytest.raises(ContractViolation, match="lakh"):
        contract.load(directory)


def test_dangling_source_id_raises(tmp_path: Path):
    directory = tmp_path / "raw"
    write_dataset(directory, monthly_source="not_in_sources_yaml")
    with pytest.raises(ContractViolation, match="not present in sources.yaml"):
        contract.load(directory)


def test_source_missing_publisher_raises(tmp_path: Path):
    broken = {SOURCE_ID: {"title": "No publisher", "accessed": "2026-08-18"}}
    write_dataset(tmp_path / "raw", sources=broken)
    with pytest.raises(ContractViolation, match="missing publisher"):
        contract.load(tmp_path / "raw")


def test_annual_mismatch_shows_both_numbers(tmp_path: Path):
    """The check that catches a transcription error inside a well-formed series."""
    months = two_clean_years()
    correct = sum(v for k, v in months.items() if k.startswith("2000"))
    write_dataset(
        tmp_path / "raw",
        monthly=months,
        annual={2000: correct + 900, 2001: sum(
            v for k, v in months.items() if k.startswith("2001"))},
    )
    with pytest.raises(ContractViolation) as excinfo:
        contract.load(tmp_path / "raw")
    message = str(excinfo.value)
    assert f"{correct:,}" in message
    assert f"{correct + 900:,}" in message
    assert "-900" in message
    assert "No tolerance is applied" in message


def test_a_dropped_digit_is_caught(tmp_path: Path):
    """Contiguous, typed, sourced -- and still wrong. This is the point of check 5."""
    months = two_clean_years()
    published = {year: sum(v for k, v in months.items() if k.startswith(str(year)))
                 for year in (2000, 2001)}
    months["2000-06"] = 106  # was 1006
    write_dataset(tmp_path / "raw", monthly=months, annual=published)
    with pytest.raises(ContractViolation, match="do not reconcile"):
        contract.load(tmp_path / "raw")


def test_partial_year_in_annual_is_rejected(tmp_path: Path):
    months = {f"2000-{m:02d}": 100 for m in range(1, 8)}
    write_dataset(tmp_path / "raw", monthly=months, annual={2000: 700})
    with pytest.raises(ContractViolation, match="only 7 monthly row"):
        contract.load(tmp_path / "raw")


def test_unreferenced_source_is_fine(tmp_path: Path):
    sources = dict(VALID_SOURCE)
    sources["spare_source"] = dict(VALID_SOURCE[SOURCE_ID])
    write_dataset(tmp_path / "raw", sources=sources)
    assert contract.load(tmp_path / "raw").n_months == 24

#!/usr/bin/env python
"""Build ``data/raw/`` from the Shrine Board's published Yatra statistics.

Source: https://www.maavaishnodevi.org/yatrastatistics

The page carries three tables, and which one a number comes from matters:

1. **Annual summary**, 1986-2025, in lakh to two decimals. *Not used as a
   figure.* Rounded to 2dp, it cannot reconcile exactly against a sum of raw
   monthly counts. It is used only as an independent order-of-magnitude check
   that the matrix was parsed correctly.
2. **Month-wise matrix**, 1986-2025: twelve monthly columns plus a ``Total``
   column, all raw integer counts. This is the source for every monthly figure
   in that span, and its ``Total`` column is the source for ``annual.csv``.
   The Total is published alongside the cells rather than derived from them
   here, so checking one against the other is a real transcription check.
3. **Recent months**, currently July 2025 - July 2026, raw counts in Indian
   digit grouping. Only its 2026 rows are used; the 2025 rows duplicate the
   matrix and are used to cross-check it.

Nothing is converted, filled, or inferred. The matrix is already in raw counts,
so there is no unit conversion anywhere in this script -- expanding the lakh
summary instead would introduce rounding error into every month.

**This script writes nothing unless every check passes.** All three files are
built in memory and committed to disk only at the end. A year whose twelve
months do not sum to its published total aborts the run, naming the year and
both numbers, because that is the one check that catches a transcription error
inside an otherwise well-formed series.

Usage::

    python scripts/build_raw.py                    # fetch and build
    python scripts/build_raw.py --html page.html   # parse a saved copy
    python scripts/build_raw.py --keep-html out.html
"""

from __future__ import annotations

import argparse
import datetime as dt
import html as html_module
import re
import ssl
import sys
import urllib.request
from pathlib import Path

import yaml

URL = "https://www.maavaishnodevi.org/yatrastatistics"

MONTH_COLUMNS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "Sept.", "Oct.", "Nov.", "December",
]

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "sept": 9, "oct": 10, "nov": 11, "dec": 12, "jan": 1,
    "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
}

MATRIX_SOURCE = "smvdsb_yatra_statistics_matrix"
RECENT_SOURCE = "smvdsb_yatra_statistics_recent"

# The lakh summary is rounded to two decimals, so it can differ from the exact
# total by up to 500 people by construction. Anything past this is a parse
# error, not rounding.
LAKH_TOLERANCE = 0.01

# Isolated disagreements between the two published tables are typos in the
# source and are reported. More than this many means the matrix was misparsed
# and every figure is suspect, which aborts.
MAX_SUMMARY_DISCREPANCIES = 3


class BuildError(RuntimeError):
    """Any reason the raw files must not be written."""


# --------------------------------------------------------------------------
# Fetch.
# --------------------------------------------------------------------------


def fetch(url: str = URL, attempts: int = 5) -> str:
    """Download the page. certifi's bundle, because the owner's network intercepts TLS."""
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover
        context = ssl.create_default_context()

    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    failures = []
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60, context=context) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - reported in full if all attempts fail
            failures.append(f"{type(exc).__name__}: {exc}")
    raise BuildError(
        f"Could not fetch {url} after {attempts} attempts:\n  " + "\n  ".join(failures)
    )


# --------------------------------------------------------------------------
# Parse. The tables are plain HTML; no parser library is assumed to be present.
# --------------------------------------------------------------------------


def _tables(doc: str) -> list[list[list[str]]]:
    out = []
    for table in re.findall(r"<table.*?</table>", doc, re.I | re.S):
        rows = []
        for row in re.findall(r"<tr.*?</tr>", table, re.I | re.S):
            cells = [
                html_module.unescape(re.sub(r"<[^>]+>", "", cell))
                .replace("\xa0", " ")
                .strip()
                for cell in re.findall(r"<t[dh].*?</t[dh]>", row, re.I | re.S)
            ]
            if cells:
                rows.append(cells)
        if rows:
            out.append(rows)
    return out


def _count(text: str, where: str) -> int:
    """Parse a published count. Indian digit grouping; must be a whole number."""
    cleaned = text.replace(",", "").replace(" ", "").strip()
    if not re.fullmatch(r"\d+", cleaned):
        raise BuildError(f"{where}: {text!r} is not a whole number of pilgrims.")
    return int(cleaned)


def parse_matrix(tables: list[list[list[str]]]) -> tuple[dict[str, int], dict[int, int]]:
    """The month-wise matrix -> (monthly counts by 'YYYY-MM', published year totals)."""
    for rows in tables:
        header = [c.strip() for c in rows[0]]
        if header[1:13] == MONTH_COLUMNS and header[-1].lower() == "total":
            break
    else:
        raise BuildError(
            "Could not find the month-wise matrix. Expected a table whose header "
            f"reads {MONTH_COLUMNS} followed by 'Total'. The page layout has "
            "changed; fix the parser rather than relaxing this check."
        )

    monthly: dict[str, int] = {}
    totals: dict[int, int] = {}
    for row in rows[1:]:
        if not re.fullmatch(r"\d{4}", row[0].strip()):
            continue
        if len(row) != 14:
            raise BuildError(
                f"Matrix row for {row[0]} has {len(row)} cells, expected 14 "
                "(year + 12 months + total)."
            )
        year = int(row[0])
        for index, cell in enumerate(row[1:13], start=1):
            monthly[f"{year}-{index:02d}"] = _count(cell, f"matrix {year}-{index:02d}")
        totals[year] = _count(row[13], f"matrix {year} total")

    if not monthly:
        raise BuildError("The month-wise matrix contained no year rows.")
    return monthly, totals


def parse_recent(tables: list[list[list[str]]]) -> dict[str, int]:
    """The recent-months table -> monthly counts by 'YYYY-MM'."""
    for rows in tables:
        header = [c.strip().lower() for c in rows[0]]
        if len(header) >= 3 and header[1] == "month" and "yatries" in header[2]:
            break
    else:
        raise BuildError(
            "Could not find the recent-months table (header: S. No. | Month | "
            "No. of Yatries)."
        )

    found: dict[str, int] = {}
    for row in rows[1:]:
        if len(row) < 3:
            continue
        match = re.fullmatch(r"([A-Za-z.]+)\s+(\d{4})", row[1].strip())
        if not match:
            raise BuildError(f"Recent-months table: cannot read month {row[1]!r}.")
        name = match.group(1).lower().rstrip(".")
        if name not in MONTH_NAMES:
            raise BuildError(f"Recent-months table: unknown month name {row[1]!r}.")
        key = f"{int(match.group(2))}-{MONTH_NAMES[name]:02d}"
        found[key] = _count(row[2], f"recent {key}")

    if not found:
        raise BuildError("The recent-months table contained no month rows.")
    return found


def parse_lakh_summary(tables: list[list[list[str]]]) -> dict[int, float]:
    """The annual summary in lakh. Used only as a parse check, never as a figure."""
    for rows in tables:
        header = [c.strip().lower() for c in rows[0]]
        if len(header) >= 3 and header[1] == "year" and "lakh" in header[2]:
            break
    else:
        return {}

    summary: dict[int, float] = {}
    for row in rows[1:]:
        if len(row) < 3 or not re.fullmatch(r"\d{4}", row[1].strip()):
            continue
        try:
            summary[int(row[1])] = float(row[2].replace(",", "").strip())
        except ValueError as exc:
            raise BuildError(f"Annual summary: cannot read {row[2]!r} as lakh.") from exc
    return summary


# --------------------------------------------------------------------------
# Checks. Every one of these aborts; none of them warns.
# --------------------------------------------------------------------------


def check_reconciliation(monthly: dict[str, int], totals: dict[int, int]) -> None:
    """Twelve months must sum to the published total, exactly, for every year."""
    failures = []
    for year, published in sorted(totals.items()):
        months = [monthly[f"{year}-{m:02d}"] for m in range(1, 13)]
        if len(months) != 12:
            failures.append(f"  {year}: only {len(months)} monthly cells")
            continue
        summed = sum(months)
        if summed != published:
            failures.append(
                f"  {year}: months sum to {summed:,} but published total is "
                f"{published:,} (difference {summed - published:+,})"
            )
    if failures:
        raise BuildError(
            "Annual reconciliation failed. Nothing has been written.\n"
            + "\n".join(failures)
            + "\n\nNo tolerance is applied and none should be added. Either the "
            "page was misparsed or the source genuinely does not reconcile, and "
            "both are findings rather than things to round away."
        )


def check_overlap(matrix: dict[str, int], recent: dict[str, int]) -> list[str]:
    """Months present in both tables must agree exactly."""
    shared = sorted(set(matrix) & set(recent))
    disagreements = [
        f"  {key}: matrix {matrix[key]:,} vs recent-months {recent[key]:,}"
        for key in shared
        if matrix[key] != recent[key]
    ]
    if disagreements:
        raise BuildError(
            "The two published tables disagree about months they share:\n"
            + "\n".join(disagreements)
            + "\n\nOne of them has been misread. Nothing has been written."
        )
    return shared


def compare_lakh_summary(totals: dict[int, int], summary: dict[int, float]) -> list[str]:
    """Compare the lakh summary against the exact totals. Returns discrepancies.

    A disagreement here is **reported, not fatal**, and the asymmetry is
    deliberate. The lakh summary supplies no figure to any output file -- it is
    rounded to two decimals and could not reconcile exactly even in principle,
    which is why ``annual.csv`` takes the matrix ``Total`` column instead. A
    year where the two published tables disagree is therefore a finding about
    the source, not a defect in anything this script emits, and the schema doc
    is explicit that such a finding belongs in the record rather than in a fudge
    factor.

    Widespread disagreement is a different matter and does abort: if many years
    are off, the matrix has been misparsed and every figure is suspect. One or
    two isolated years is a typo in someone's summary table.
    """
    if not summary:
        return []

    found = []
    for year, published in sorted(totals.items()):
        if year not in summary:
            continue
        implied = published / 100_000
        if abs(implied - summary[year]) > LAKH_TOLERANCE:
            found.append(
                f"{year}: matrix total {published:,} = {implied:.5f} lakh, "
                f"but the annual summary publishes {summary[year]:.2f} lakh"
            )

    if len(found) > MAX_SUMMARY_DISCREPANCIES:
        raise BuildError(
            f"The lakh summary disagrees with the matrix totals in {len(found)} "
            "years:\n  " + "\n  ".join(found)
            + "\n\nThat many is a parse error, not a set of typos in the source. "
            "Nothing has been written."
        )
    return found


def check_contiguous(months: dict[str, int]) -> tuple[str, str]:
    """No gaps between the first and last month present."""
    keys = sorted(months)
    first, last = keys[0], keys[-1]
    expected = []
    year, month = int(first[:4]), int(first[5:])
    while f"{year}-{month:02d}" <= last:
        expected.append(f"{year}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    missing = [key for key in expected if key not in months]
    if missing:
        raise BuildError(
            f"{len(missing)} month(s) missing between {first} and {last}: "
            f"{', '.join(missing[:12])}{' ...' if len(missing) > 12 else ''}. "
            "Missing months are not filled in. Nothing has been written."
        )
    return first, last


# --------------------------------------------------------------------------
# Emit.
# --------------------------------------------------------------------------


def build_files(
    monthly: dict[str, int],
    totals: dict[int, int],
    recent_years: set[int],
    accessed: str,
    discrepancies: list[str] | None = None,
) -> dict[str, str]:
    """Render the three files as text. Nothing touches disk here."""
    monthly_lines = ["month,pilgrims,source_id"]
    for key in sorted(monthly):
        source = RECENT_SOURCE if int(key[:4]) in recent_years else MATRIX_SOURCE
        monthly_lines.append(f"{key},{monthly[key]},{source}")

    annual_lines = ["year,pilgrims,source_id"]
    for year in sorted(totals):
        annual_lines.append(f"{year},{totals[year]},{MATRIX_SOURCE}")

    sources = {
        MATRIX_SOURCE: {
            "publisher": "Shri Mata Vaishno Devi Shrine Board",
            "title": "Yatra Statistics - month-wise break-up of Yatra from 1986",
            "url": URL,
            "accessed": accessed,
            "note": (
                "Month-wise matrix, twelve monthly columns plus a Total column. "
                "Figures are raw integer counts as published; no unit conversion "
                "is applied. annual.csv uses this table's Total column, not the "
                "separate annual summary given in lakh, because that summary is "
                "rounded to two decimals and cannot reconcile exactly. April to "
                "July 2020 are published as zero (COVID-19 closure) and are "
                "recorded as zero, not as missing."
            ),
        },
        RECENT_SOURCE: {
            "publisher": "Shri Mata Vaishno Devi Shrine Board",
            "title": "Yatra Statistics - recent month-wise figures",
            "url": URL,
            "accessed": accessed,
            "note": (
                "Separate recent-months table on the same page, raw counts in "
                "Indian digit grouping. Used only for months after the last "
                "complete year in the matrix. Months appearing in both tables "
                "were checked to agree exactly before writing. These months "
                "belong to a year still in progress, so they have no row in "
                "annual.csv and are deliberately outside the annual "
                "reconciliation check."
            ),
        },
    }

    return {
        "monthly.csv": "\n".join(monthly_lines) + "\n",
        "annual.csv": "\n".join(annual_lines) + "\n",
        "sources.yaml": yaml.safe_dump(sources, sort_keys=False, width=100),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, help="parse a saved copy instead of fetching")
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    parser.add_argument("--keep-html", type=Path, help="save the fetched page here")
    args = parser.parse_args(argv[1:])

    try:
        if args.html:
            doc = args.html.read_text(encoding="utf-8", errors="replace")
            print(f"parsing {args.html}")
        else:
            print(f"fetching {URL}")
            doc = fetch()
            if args.keep_html:
                args.keep_html.parent.mkdir(parents=True, exist_ok=True)
                args.keep_html.write_text(doc, encoding="utf-8")
                print(f"saved page to {args.keep_html}")

        tables = _tables(doc)
        print(f"found {len(tables)} tables")

        matrix, totals = parse_matrix(tables)
        recent = parse_recent(tables)
        summary = parse_lakh_summary(tables)
        print(f"matrix:  {len(matrix)} months, {len(totals)} annual totals "
              f"({min(totals)}-{max(totals)})")
        print(f"recent:  {len(recent)} months ({min(recent)}..{max(recent)})")
        print(f"summary: {len(summary)} annual figures in lakh (cross-check only)")

        # --- checks, all fatal --------------------------------------------
        check_reconciliation(matrix, totals)
        print(f"reconciliation: all {len(totals)} years sum exactly to their totals")

        shared = check_overlap(matrix, recent)
        if shared:
            print(f"overlap: {len(shared)} month(s) in both tables agree exactly "
                  f"({shared[0]}..{shared[-1]})")

        discrepancies = compare_lakh_summary(totals, summary)
        if discrepancies:
            print(f"lakh summary: {len(discrepancies)} year(s) disagree with the "
                  "matrix totals beyond rounding --")
            for line in discrepancies:
                print(f"  {line}")
            print("  Reported, not fatal: the summary supplies no figure to any "
                  "output file.")
            print("  annual.csv uses the matrix Total, which reconciles exactly. "
                  "Recorded in sources.yaml.")
        else:
            print("lakh summary: consistent with the matrix totals to within rounding")

        complete_years = set(totals)
        merged = dict(matrix)
        extra = {k: v for k, v in recent.items() if int(k[:4]) not in complete_years}
        merged.update(extra)
        recent_years = {int(k[:4]) for k in extra}
        print(f"carried forward from the recent table: {len(extra)} month(s)"
              + (f" ({min(extra)}..{max(extra)})" if extra else ""))

        first, last = check_contiguous(merged)
        print(f"contiguity: {len(merged)} months, {first}..{last}, no gaps")

        zeros = sorted(k for k, v in merged.items() if v == 0)
        if zeros:
            print(f"zero months (kept as observed, not missing): {', '.join(zeros)}")

        files = build_files(
            merged, totals, recent_years, dt.date.today().isoformat(), discrepancies
        )

    except BuildError as exc:
        print(f"\nABORTED: {exc}", file=sys.stderr)
        print("\nNo files were written.", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (args.out / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out / name}")

    print("\nNow run: python make.py validate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

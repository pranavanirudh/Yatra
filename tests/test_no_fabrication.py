"""Structural guards on the "never generate observations" constraint.

A rule enforced only by intention decays. These tests check the properties that
make the rule true of the code rather than of the author's memory: there is no
sample dataset in the repository, the loader has no generative path, and the
README's numbers cannot be typed by hand.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest
import yaml

from yatra import contract, report
from yatra.errors import MissingObservations

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "yatra"


def test_every_observation_traces_to_a_real_citation():
    """Nothing may sit in data/raw whose provenance cannot be followed.

    This test used to assert that ``data/raw`` held no CSVs at all, which was
    the right guard while the directory was empty: the only thing that could
    have appeared there was a sample. Real observations landed on 2026-08-18
    (built by ``scripts/build_raw.py`` from the Shrine Board's published
    statistics), so that form of the check now fires on exactly the situation
    the project wants.

    The intent it was protecting is unchanged and is what is asserted here
    instead: a figure in this repository must be traceable to a published
    source. A fabricated series would have to arrive with a fabricated citation
    to get past this, which is a much harder thing to do by accident -- and
    accident is what the guard is for.
    """
    raw = ROOT / "data" / "raw"
    if not raw.exists():
        return

    csvs = sorted(p.name for p in raw.glob("*.csv"))
    if not csvs:
        return

    sources_path = raw / "sources.yaml"
    assert sources_path.exists(), (
        f"data/raw holds {csvs} but no sources.yaml. Observations without "
        "citations are indistinguishable from invented ones."
    )
    sources = yaml.safe_load(sources_path.read_text(encoding="utf-8")) or {}
    assert sources, "data/raw/sources.yaml is empty."

    placeholder = re.compile(r"example\.(invalid|com)|CHANGE[ -]ME|localhost|TODO", re.I)
    for identifier, entry in sources.items():
        for field in ("publisher", "title", "url", "accessed"):
            value = str(entry.get(field, "")).strip()
            assert value, f"source '{identifier}' is missing '{field}'."
            assert not placeholder.search(value), (
                f"source '{identifier}' has a placeholder {field}: {value!r}. "
                "A fixture citation on real-looking data is how a sample gets "
                "mistaken for a measurement."
            )

    # And the citations must actually cover the data, not merely exist.
    used = set()
    for name in csvs:
        frame = pd.read_csv(raw / name)
        assert "source_id" in frame.columns, f"{name} has no source_id column."
        used |= set(frame["source_id"].dropna().unique())
    dangling = sorted(used - set(sources))
    assert not dangling, f"source_id(s) used but never defined: {dangling}."


def test_loader_has_no_generative_vocabulary():
    """Catches a fill/impute/synthesise path being added to the contract module."""
    text = (SRC / "contract.py").read_text(encoding="utf-8")
    for forbidden in ("fillna(", "interpolate(", "ffill(", "bfill(", "resample("):
        assert forbidden not in text, (
            f"contract.py contains '{forbidden}'. The loader must not be able to "
            "manufacture an observation, even accidentally."
        )


def test_loader_raises_rather_than_returning_empty(tmp_path: Path):
    with pytest.raises(MissingObservations):
        contract.load(tmp_path)


def test_report_refuses_to_render_without_metrics(tmp_path: Path):
    """No placeholder tables. Absent results must read as absent."""
    with pytest.raises(FileNotFoundError):
        report.render(tmp_path / "metrics.csv")


#: Every region of the README that report.py owns and rewrites wholesale. The
#: lead is the first screen; the other is the results section. Both carry
#: numbers, and neither may be hand-typed.
GENERATED_REGIONS = (
    (report.LEAD_BEGIN, report.LEAD_END),
    (report.BEGIN, report.END),
)


def _strip_generated(text: str) -> str:
    """README text with every generated region removed.

    Raises rather than skipping a region whose markers are absent: a silently
    unstripped block would make the prose test below pass by having nothing
    left to object to, which is the opposite of what it is for.
    """
    for begin, end in GENERATED_REGIONS:
        if begin not in text or end not in text:
            raise AssertionError(f"README is missing the {begin} / {end} markers.")
        head, _, rest = text.partition(begin)
        _, _, tail = rest.partition(end)
        text = head + tail
    return text


def test_readme_has_the_generated_markers():
    """Both generated regions are present and correctly ordered."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for begin, end in GENERATED_REGIONS:
        assert begin in text and end in text, f"README lacks {begin} / {end}"
        assert text.index(begin) < text.index(end), f"{end} precedes {begin}"

    # The lead is the first screen, so it must come before the results section.
    assert text.index(report.LEAD_END) < text.index(report.BEGIN), (
        "The lead block must precede the results block. A visitor reads the "
        "first screen first, and that is the point of generating it separately."
    )


def test_the_readme_lead_is_generated_not_typed():
    """The committed first screen must equal what report.py renders now.

    This is what makes "the headline table is covered by the generator" true
    rather than aspirational. Hand-editing a rank into the lead -- the single
    most quoted and least re-checked block in the repository -- fails here.
    """
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    _, _, rest = text.partition(report.LEAD_BEGIN)
    committed, _, _ = rest.partition(report.LEAD_END)

    assert committed.strip() == report.render_lead().strip(), (
        "README's lead block differs from report.render_lead(). Run "
        "`make report` rather than editing the first screen by hand."
    )


def test_the_lead_and_the_results_section_show_the_same_ranks():
    """One rank table, rendered twice, never two tables that can disagree.

    The first screen and the results section both show the clean-versus-shock
    leaderboard. If they were rendered independently, an edit to one would
    leave a visitor reading ranks the results section contradicts further down.
    """
    lead = report.render_lead()
    body = report.render()

    rows = [line for line in lead.splitlines() if line.startswith("| `")]
    assert rows, "The lead block contains no model rows."
    for row in rows:
        assert row in body, (
            f"Lead row {row!r} does not appear in the results section. The two "
            "renderings have drifted; both must come from report._rank_table."
        )


def test_hand_written_readme_prose_contains_no_statistics():
    """Every number in the README must trace to a row in metrics.csv.

    The mechanism is that report.py owns the generated regions -- the first
    screen and the results section. This test guards the other half: that
    nobody types a result into the prose around them. Prose outside every
    marker pair may not contain a decimal number or a thousands-grouped
    integer, which is what a MASE, a correlation or a forecast count looks like.
    """
    import re

    text = (ROOT / "README.md").read_text(encoding="utf-8")
    prose = _strip_generated(text)

    pattern = re.compile(r"(?<![\w.])(\d+\.\d+|\d{1,3}(?:,\d{3})+)(?![\w])")
    offenders = pattern.findall(prose)
    assert not offenders, (
        f"Numbers found in hand-written README prose: {offenders}. Results belong "
        "inside the generated block, where they trace to metrics.csv."
    )


def test_shock_config_is_not_importable_as_a_model_feature():
    """Shock windows are labels. No model module may read them.

    A model that could see the declared windows would be reading the answer key,
    and would post a spectacular score that meant nothing.
    """
    # Matched against code, not prose. These modules are entitled to *discuss*
    # regimes in a docstring -- metrics.py has to explain why one MASE
    # denominator is what makes the per-regime tables comparable. What they may
    # not do is import the module or read the config.
    references = re.compile(
        r"^\s*(?:from\s+\.?\S*\s+)?import\s+.*\bregimes\b"    # any import of it
        r"|\bregimes\s*\."                                     # any attribute use
        r"|\bShockWindow\b"
        r"|\bshocks\.yaml\b",
        re.MULTILINE,
    )
    for module in ("models.py", "metrics.py"):
        text = (SRC / module).read_text(encoding="utf-8")
        found = references.findall(text)
        assert not found, (
            f"{module} references the regimes module ({found}). Shock windows "
            "are evaluation labels and must not reach a model."
        )


def test_the_docs_index_names_every_document():
    """`docs/README.md` must list every file in `docs/`, with no dead entries.

    This project keeps superseded reasoning rather than deleting it, which only
    works if a reader can tell a live decision from a retired one. The index is
    what carries that distinction, so a document missing from it is a document
    read as current by default -- the same failure as a builder missing from
    `ui.BUILDERS` or a name missing from `NEEDS_CALENDAR`, and just as quiet.

    Checked both ways. An unindexed file is an undated verdict; an indexed file
    that no longer exists is a broken promise in the one page that exists to
    say what is here.
    """
    index = ROOT / "docs" / "README.md"
    text = index.read_text(encoding="utf-8")

    linked = {
        m.group(1)
        for m in re.finditer(r"\[[^\]]*\]\(([^)#][^)]*?)\)", text)
        if not m.group(1).startswith(("http", "mailto", "../"))
    }
    on_disk = {p.name for p in (ROOT / "docs").glob("*.md")} - {index.name}

    missing = sorted(on_disk - linked)
    assert not missing, (
        f"docs/ holds {missing}, which docs/README.md does not index. Add each "
        "with a status, or a reader takes it as current by default."
    )

    dangling = sorted(link for link in linked if not (index.parent / link).exists())
    assert not dangling, f"docs/README.md links to missing files: {dangling}."


def test_every_indexed_document_carries_a_status():
    """The status column is the point of the index; a blank one is worse than none.

    An entry with a link and no status tells a reader the file exists and
    nothing about whether to believe it, which is the question the index was
    written to answer.
    """
    text = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    rows = [
        line for line in text.splitlines()
        if line.startswith("| [") and "](" in line
    ]
    assert rows, "docs/README.md has no table rows; the index is not a table."

    for row in rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert len(cells) >= 3, f"Index row is malformed: {row!r}"
        assert cells[1], f"Index row has an empty status column: {row!r}"

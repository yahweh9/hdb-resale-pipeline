"""Generated tables in FINDINGS.md: filled from the edition, never retyped by hand."""

import json

import pandas as pd
import pytest

import edition
import render_findings


@pytest.fixture
def root(tmp_path):
    """A minimal edition on disk: a stamp and the MRT mart."""
    pd.DataFrame({
        "band_order": [1, 4],
        "mrt_band": ["0-400m", "over 1.2km"],
        "sales": [77650, 18128],
        "median_price_psm": [5568.0, 5104.0],
        "premium_vs_farthest_pct": [9.1, 0.0],
    }).to_csv(tmp_path / "mart_mrt_premium_by_band.csv", index=False)
    (tmp_path / edition.STAMP_FILE).write_text(json.dumps({
        "data_through": "2026-09", "sales": 240074,
        "published_on": "2026-09-14", "tables": ["mart_mrt_premium_by_band"],
    }), encoding="utf-8")
    return tmp_path


DOC = """# Findings

<!-- edition -->
stale stamp
<!-- /edition -->

Prose before, written by a person.

<!-- table: mrt_premium_by_band -->
| stale | table |
<!-- /table -->

Prose after, also written by a person.
"""


def test_a_table_marker_is_filled_from_the_published_mart(root):
    out = render_findings.render(DOC, root)

    assert "| 0-400m | 77,650 | S$5,568 | +9.1% |" in out
    assert "| over 1.2km | 18,128 | S$5,104 | +0.0% |" in out
    assert "stale | table" not in out


def test_the_edition_marker_carries_the_data_cut(root):
    out = render_findings.render(DOC, root)

    assert "through **Sep 2026** (240,074 sales)" in out
    assert "published **14 Sep 2026**" in out
    assert "stale stamp" not in out


def test_prose_outside_the_markers_is_never_touched(root):
    out = render_findings.render(DOC, root)

    assert "Prose before, written by a person." in out
    assert "Prose after, also written by a person." in out
    assert out.startswith("# Findings\n")


def test_rendering_twice_changes_nothing(root):
    # This is what makes --check possible: a rendered document is a fixed point.
    once = render_findings.render(DOC, root)

    assert render_findings.render(once, root) == once


def test_an_unknown_table_name_fails_loudly(root):
    with pytest.raises(ValueError, match="no_such_table"):
        render_findings.render("<!-- table: no_such_table -->\n<!-- /table -->\n", root)


def test_an_unclosed_marker_fails_rather_than_eating_the_document(root):
    # Left unchecked, a missing close marker would swallow everything after it.
    with pytest.raises(ValueError, match="unclosed"):
        render_findings.render("<!-- table: mrt_premium_by_band -->\nthe rest of the doc\n", root)

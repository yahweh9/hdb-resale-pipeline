"""Fill the generated tables in FINDINGS.md from the published edition.

FINDINGS.md is prose written by a person, with tables that are not. Each generated
table sits between markers:

    <!-- table: mrt_premium_by_band -->
    ...replaced on every render...
    <!-- /table -->

and the data-cut stamp between <!-- edition --> and <!-- /edition -->. Everything
outside the markers is left byte for byte, including numbers quoted inside sentences,
which stay hand-written and get re-read whenever an edition is refreshed.

    python render_findings.py           # rewrite FINDINGS.md from published/
    python render_findings.py --check   # exit 1 if FINDINGS.md is out of date (CI)
"""

import argparse
import datetime as dt
import re
import sys

import edition

FINDINGS = "FINDINGS.md"


def _count(v):
    return f"{v:,.0f}"


def _sgd(v):
    return f"S${v:,.0f}"


def _pct(v):
    return f"{v:+.1f}%"


def _index(v):
    return f"{v:.1f}"


def col(name, fmt):
    """A cell that formats one column of the row."""
    return lambda row: fmt(row[name])


def interval(low, high, fmt=_pct):
    """A cell showing a 95% interval from two columns."""
    return lambda row: f"{fmt(row[low])} to {fmt(row[high])}"


def _term(term):
    return lambda df: df[df["term"] == term]


_MODEL_VS_NAIVE = [
    ("Sales", col("sales", _count)),
    ("Naive (group-by)", col("naive_pct", _pct)),
    ("Model (like for like)", col("model_pct", _pct)),
    ("95% interval", interval("model_ci_low_pct", "model_ci_high_pct")),
]

# Marker name -> the published mart it reads, an optional row filter, and its columns as
# (header, cell) pairs. Headers and number formats live here, not in the mart: the mart
# stays plain numbers any tool can read, and the document decides how a reader sees them.
# The mart's own row order is kept, so ordering is decided once, in SQL.
TABLES = {
    "mrt_premium_by_band": {
        "mart": "mart_mrt_premium_by_band",
        "columns": [
            ("Distance to MRT", col("mrt_band", str)),
            ("Sales", col("sales", _count)),
            ("Median psm", col("median_price_psm", _sgd)),
            ("vs over 1.2km", col("premium_vs_farthest_pct", _pct)),
        ],
    },
    "mrt_model_vs_naive": {
        "mart": "mart_model_vs_naive",
        "rows": _term("mrt_band"),
        "columns": [("Distance to MRT", col("level", str))] + _MODEL_VS_NAIVE,
    },
    "lease_model_vs_naive": {
        "mart": "mart_model_vs_naive",
        "rows": _term("lease_band"),
        "columns": [("Lease remaining (years)", col("level", str))] + _MODEL_VS_NAIVE,
    },
    "mrt_premium_by_year": {
        "mart": "mart_effects_by_year",
        "rows": lambda df: df[df["level"] == "0-400m"],
        "columns": [
            ("Year", col("calendar_year", str)),
            ("0-400m vs over 1.2km", col("effect_pct", _pct)),
            ("95% interval", interval("ci_low_pct", "ci_high_pct")),
        ],
    },
    "price_index_by_year": {
        "mart": "mart_price_index",
        "rows": lambda df: df[df["is_year_end"]],
        "columns": [
            ("Month", col("month", str)),
            ("Median psm index", col("naive_index", _index)),
            ("Quality-adjusted index", col("hedonic_index", _index)),
            ("95% interval", interval("hedonic_ci_low", "hedonic_ci_high", _index)),
        ],
    },
}

OPEN = re.compile(r"<!-- (?:table: [\w-]+|edition) -->")
BLOCK = re.compile(
    r"<!-- (?:table: (?P<name>[\w-]+)|(?P<edition>edition)) -->\n"
    r"(?P<body>.*?)"
    r"<!-- /(?P<close>table|edition) -->",
    re.S,
)


def _markdown_table(name, root):
    if name not in TABLES:
        raise ValueError(f"FINDINGS.md asks for an unknown table: {name}")
    spec = TABLES[name]
    table = edition.read_table(spec["mart"], root)
    rows = spec.get("rows", lambda df: df)(table).to_dict("records")
    columns = spec["columns"]

    lines = [
        "| " + " | ".join(header for header, _ in columns) + " |",
        "|" + "---|" * len(columns),
    ]
    lines += ["| " + " | ".join(cell(row) for _, cell in columns) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def _stamp_line(root):
    stamp = edition.read_stamp(root)
    through = dt.datetime.strptime(stamp["data_through"], "%Y-%m")
    published = dt.date.fromisoformat(stamp["published_on"])
    return (
        f"**Data cut:** resale transactions through **{through:%b %Y}** "
        f"({stamp['sales']:,} sales) · published **{published.day} {published:%b %Y}**\n"
    )


def render(text, root=edition.EDITION_DIR):
    """Return `text` with every marker block refilled from the edition at `root`."""
    blocks = list(BLOCK.finditer(text))

    # A close marker missing from one block lets the non-greedy match run on to the
    # NEXT block's close, swallowing an opening marker on the way. Counting openings
    # against complete blocks catches that before any prose is overwritten.
    if len(OPEN.findall(text)) != len(blocks):
        raise ValueError("FINDINGS.md has an unclosed marker")

    out, pos = [], 0
    for m in blocks:
        kind = "edition" if m["edition"] else "table"
        if m["close"] != kind:
            raise ValueError(f"FINDINGS.md has an unclosed marker: <!-- {kind} --> closed by /{m['close']}")
        body = _stamp_line(root) if m["edition"] else _markdown_table(m["name"], root)
        opening = "<!-- edition -->" if m["edition"] else f"<!-- table: {m['name']} -->"
        out += [text[pos:m.start()], f"{opening}\n{body}<!-- /{kind} -->"]
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if FINDINGS.md does not match the edition; write nothing.")
    args = parser.parse_args()

    with open(FINDINGS, encoding="utf-8") as f:
        current = f.read()
    rendered = render(current)

    if args.check:
        if rendered != current:
            print("FINDINGS.md is out of date with published/. Run: python render_findings.py")
            sys.exit(1)
        print("FINDINGS.md matches the published edition.")
        return

    if rendered != current:
        with open(FINDINGS, "w", encoding="utf-8") as f:
            f.write(rendered)
        print("FINDINGS.md updated from the published edition.")
    else:
        print("FINDINGS.md already matches the published edition.")


if __name__ == "__main__":
    main()

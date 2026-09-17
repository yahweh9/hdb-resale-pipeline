"""Fill the generated tables in FINDINGS.md and README.md from the published edition.

Both documents are prose written by a person, with tables that are not. Each generated
table sits between markers:

    <!-- table: mrt_premium_by_band -->
    ...replaced on every render...
    <!-- /table -->

and the data-cut stamp between <!-- edition --> and <!-- /edition -->. Everything
outside the markers is left byte for byte, including numbers quoted inside sentences,
which stay hand-written and get re-read whenever an edition is refreshed.

    python -m publish.render_findings           # rewrite both documents from published/
    python -m publish.render_findings --check   # exit 1 if either is out of date (CI)
"""

import argparse
import datetime as dt
import re
import sys

from publish import edition

# The README carries the edition stamp too, so its headline numbers never float free of
# the data cut they came from.
DOCUMENTS = ["FINDINGS.md", "README.md"]


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
    ("Simple comparison", col("naive_pct", _pct)),
    ("Like for like", col("model_pct", _pct)),
    ("95% range", interval("model_ci_low_pct", "model_ci_high_pct")),
]

def _share(v):
    return f"{v:.1f}%"


VERDICTS = ["above", "below", "in line", "not enough sales"]

_FAIR_VALUE = [
    ("Block", col("address", str)),
    ("Town", col("town", str)),
    ("Sales", col("sales", _count)),
    ("Vs expected price", col("premium_pct", _pct)),
    ("95% range", interval("ci_low_pct", "ci_high_pct")),
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
            ("Median price per sqm", col("median_price_psm", _sgd)),
            ("Vs over 1.2km", col("premium_vs_farthest_pct", _pct)),
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
        "columns": [("Lease left (years)", col("level", str))] + _MODEL_VS_NAIVE,
    },
    "mrt_premium_by_year": {
        "mart": "mart_effects_by_year",
        "rows": lambda df: df[df["level"] == "0-400m"],
        "columns": [
            ("Year", col("calendar_year", str)),
            ("Within 400m vs over 1.2km, like for like", col("effect_pct", _pct)),
            ("95% range", interval("ci_low_pct", "ci_high_pct")),
        ],
    },
    "model_validation": {
        "mart": "mart_model_validation",
        "columns": [
            ("Year", col("scope", str)),
            ("Sales it hadn't seen", col("test_sales", _count)),
            ("Model: typical miss", col("model_median_error_pct", _share)),
            ("Simple guess: typical miss", col("baseline_median_error_pct", _share)),
            ("Model: within 10%", col("model_within_10pct", _share)),
            ("Simple guess: within 10%", col("baseline_within_10pct", _share)),
        ],
    },
    "fair_value_verdicts": {
        "mart": "mart_block_fair_value",
        "rows": lambda df: (
            df.groupby("verdict").agg(blocks=("block_key", "size"), sales=("sales", "sum"))
            .reset_index().sort_values("verdict", key=lambda v: v.map(VERDICTS.index))
        ),
        "columns": [
            ("Verdict", col("verdict", str)),
            ("Blocks", col("blocks", _count)),
            ("Sales in those blocks", col("sales", _count)),
        ],
    },
    "fair_value_above": {
        "mart": "mart_block_fair_value",
        "rows": lambda df: df[df["verdict"] == "above"].nlargest(10, "premium_pct"),
        "columns": _FAIR_VALUE,
    },
    "fair_value_below": {
        "mart": "mart_block_fair_value",
        "rows": lambda df: df[df["verdict"] == "below"].nsmallest(10, "premium_pct"),
        "columns": _FAIR_VALUE,
    },
    "cbd_gradient": {
        "mart": "mart_cbd_gradient",
        "columns": [
            ("Km from the CBD", col("km_from_cbd", str)),
            ("Median price per sqm", col("median_price_psm", _sgd)),
            ("Sales", col("sales", _count)),
        ],
    },
    "mrt_premium_by_cbd_ring": {
        "mart": "mart_mrt_premium_by_cbd_ring",
        "columns": [
            ("Distance from the CBD", col("cbd_ring", str)),
            ("Within 400m of MRT", col("near_mrt_psm", _sgd)),
            ("Further away", col("not_near_psm", _sgd)),
            ("Difference", col("premium_pct", _pct)),
        ],
    },
    "storey_naive": {
        "mart": "mart_storey_premium",
        "rows": lambda df: df.dropna(subset=["naive_4room_psm"]),
        "columns": [
            ("Floor level", col("floor_tier", str)),
            ("Median price per sqm (4-room)", col("naive_4room_psm", _sgd)),
            ("Vs a low floor", col("naive_premium_pct", _pct)),
        ],
    },
    "storey_controlled": {
        "mart": "mart_storey_premium",
        "rows": lambda df: df.dropna(subset=["controlled_multiplier"]),
        "columns": [
            ("Floor level", col("floor_tier", str)),
            ("Price vs a low floor (1.00 = same)", col("controlled_multiplier", lambda v: f"{v:.2f}")),
            ("Groups compared", col("comparison_cells", _count)),
        ],
    },
    "lease_naive_4room": {
        "mart": "mart_lease_4room",
        # Dearest first: the finding is where "under 50" lands in this order.
        "rows": lambda df: df.sort_values("median_price_psm", ascending=False),
        "columns": [
            ("Lease left (years)", col("lease_band", str)),
            ("Median price per sqm", col("median_price_psm", _sgd)),
            ("Sales", col("sales", _count)),
        ],
    },
    "lease_confound_4room": {
        "mart": "mart_lease_4room",
        "columns": [
            ("Lease left (years)", col("lease_band", str)),
            ("Typical distance to the CBD", col("median_km_to_cbd", lambda v: f"{v:.1f} km")),
            ("% in mature estates", col("pct_mature", lambda v: f"{v:.0f}%")),
            ("Sales", col("sales", _count)),
        ],
    },
    "price_by_year": {
        "mart": "mart_price_by_year",
        "columns": [
            ("Year", col("calendar_year", str)),
            ("Median price per sqm", col("median_price_psm", _sgd)),
            ("Sales", col("sales", _count)),
            ("Mature estates", col("mature_psm", _sgd)),
            ("Non-mature estates", col("non_mature_psm", _sgd)),
            ("How much more mature estates cost", col("maturity_gap_pct", _share)),
        ],
    },
    "large_flat_share": {
        "mart": "mart_large_flat_share",
        "columns": [
            ("Region", col("region", str)),
            ("2017", col("share_2017", _share)),
            ("2021", col("share_2021", _share)),
            ("Latest year", col("share_latest", _share)),
            ("Change since 2017", col("change_pts", lambda v: f"{v:+.1f} pts")),
        ],
    },
    "price_index_by_year": {
        "mart": "mart_price_index",
        "rows": lambda df: df[df["is_year_end"]],
        "columns": [
            ("Month", col("month", str)),
            ("Median price (Jan 2017 = 100)", col("naive_index", _index)),
            ("Like for like (Jan 2017 = 100)", col("hedonic_index", _index)),
            ("95% range", interval("hedonic_ci_low", "hedonic_ci_high", _index)),
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
        raise ValueError(f"The document asks for an unknown table: {name}")
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
        raise ValueError("The document has an unclosed marker")

    out, pos = [], 0
    for m in blocks:
        kind = "edition" if m["edition"] else "table"
        if m["close"] != kind:
            raise ValueError(f"The document has an unclosed marker: <!-- {kind} --> closed by /{m['close']}")
        body = _stamp_line(root) if m["edition"] else _markdown_table(m["name"], root)
        opening = "<!-- edition -->" if m["edition"] else f"<!-- table: {m['name']} -->"
        out += [text[pos:m.start()], f"{opening}\n{body}<!-- /{kind} -->"]
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if a document does not match the edition; write nothing.")
    args = parser.parse_args()

    stale = []
    for path in DOCUMENTS:
        with open(path, encoding="utf-8") as f:
            current = f.read()
        rendered = render(current)

        if rendered == current:
            print(f"{path} matches the published edition.")
        elif args.check:
            print(f"{path} is out of date with published/.")
            stale.append(path)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(rendered)
            print(f"{path} updated from the published edition.")

    # Every document is checked before failing, so one run names all the stale ones.
    if stale:
        print("Run: python -m publish.render_findings")
        sys.exit(1)


if __name__ == "__main__":
    main()

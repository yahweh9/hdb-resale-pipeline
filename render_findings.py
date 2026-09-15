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


# Marker name -> (published mart, [(column, header, formatter), ...]). Headers and
# number formats live here, not in the mart: the mart stays plain numbers any tool can
# read, and the document decides how a reader sees them.
TABLES = {
    "mrt_premium_by_band": (
        "mart_mrt_premium_by_band",
        [
            ("mrt_band", "Distance to MRT", str),
            ("sales", "Sales", _count),
            ("median_price_psm", "Median psm", _sgd),
            ("premium_vs_farthest_pct", "vs over 1.2km", _pct),
        ],
    ),
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
    mart, columns = TABLES[name]
    rows = edition.read_table(mart, root).to_dict("records")

    lines = [
        "| " + " | ".join(header for _, header, _ in columns) + " |",
        "|" + "---|" * len(columns),
    ]
    lines += ["| " + " | ".join(fmt(row[col]) for col, _, fmt in columns) + " |" for row in rows]
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

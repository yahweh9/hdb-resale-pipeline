"""Explore, with nothing filtered, must say exactly what the published marts say.

The descriptive figures exist twice -- in SQL, as marts, and in pandas, in explore.py,
so the Explore page can follow its filters. Two implementations of one definition drift
apart quietly: a threshold changed in one place, a band edge in another. This recomputes
each figure from an edition's sales and compares it with that edition's mart, and exits
1 on any difference beyond the mart's own rounding.

    python check_explore_parity.py                                 # the committed edition
    python check_explore_parity.py --edition data/fixture/published   # CI
"""

import argparse
import sys

import edition
import explore

# (mart, explore function, key column, {compared column: tolerance}). Tolerances are the
# marts' rounding: medians to whole dollars, percentages to 0.1, multipliers to 0.001.
CHECKS = [
    ("mart_cbd_gradient", explore.cbd_gradient, "km_from_cbd",
     {"sales": 0, "median_price_psm": 0.5}),
    ("mart_mrt_premium_by_band", explore.mrt_premium_by_band, "mrt_band",
     {"sales": 0, "median_price_psm": 0.5, "premium_vs_farthest_pct": 0.051}),
    ("mart_storey_premium", explore.storey_multiplier, "floor_tier",
     {"controlled_multiplier": 0.00051, "comparison_cells": 0}),
]


def compare(mart, computed, key, tolerances):
    """Every disagreement between a mart and its explore twin, as readable strings."""
    columns = list(tolerances)
    # Rows the mart has no value for (e.g. a tier with no controlled comparison) are not
    # claims, so they are not compared.
    published = mart.dropna(subset=columns)[[key] + columns].set_index(key)
    recomputed = computed.dropna(subset=columns)[[key] + columns].set_index(key)

    problems = []
    for missing in sorted(set(published.index) ^ set(recomputed.index), key=str):
        side = "the mart" if missing in published.index else "explore.py"
        problems.append(f"{key}={missing}: only in {side}")
    for row in sorted(set(published.index) & set(recomputed.index), key=str):
        for column, tolerance in tolerances.items():
            a, b = float(published.at[row, column]), float(recomputed.at[row, column])
            if abs(a - b) > tolerance:
                problems.append(f"{key}={row}, {column}: mart {a} vs explore {b}")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--edition", default=edition.EDITION_DIR)
    args = parser.parse_args()

    sales = edition.read_sales(args.edition)
    failed = False
    for mart_name, function, key, tolerances in CHECKS:
        problems = compare(edition.read_table(mart_name, args.edition), function(sales), key, tolerances)
        print(f"{mart_name}: {'OK' if not problems else f'{len(problems)} difference(s)'}")
        for problem in problems:
            print(f"  {problem}")
        failed = failed or bool(problems)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

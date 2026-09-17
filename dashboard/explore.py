"""The Explore page's maths: the descriptive figures, recomputed under any filter.

Published figures come from marts and never move. These are their exploratory twins:
the same definitions in pandas, so they can follow the sidebar. Each returns the same
columns as the mart it mirrors, so one chart function draws both, and
dashboard/check_parity.py proves that with nothing filtered the two agree.

Bands are read from the sales, never re-derived: dim_block classifies MRT bands once,
on the unrounded distance.
"""

import numpy as np
import pandas as pd

TIER_ORDER = ["Low (1-4)", "Mid (5-9)", "High (10-19)", "Ultra-High (20+)"]


def filter_sales(sales, years, flat_types=(), regions=(), towns=()):
    """Sales in the inclusive year range; an empty selection means no filter."""
    first, last = years
    out = sales[sales["calendar_year"].between(first, last)]
    for column, chosen in (("flat_type", flat_types), ("region", regions), ("town", towns)):
        if len(chosen):
            out = out[out[column].isin(chosen)]
    return out


def price_trend(sales, min_sales=10):
    """Median price per sqm by month and flat type. A month with fewer than `min_sales`
    of a type is dropped: its "median" is one or two flats bouncing around."""
    trend = (sales.groupby(["transaction_month", "flat_type"], as_index=False)
             .agg(median_price_psm=("price_psm", "median"), sales=("price_psm", "size")))
    return trend[trend["sales"] >= min_sales].reset_index(drop=True)


def volume(sales):
    return sales.groupby("transaction_month", as_index=False).agg(sales=("price_psm", "size"))


def cbd_gradient(sales, min_sales=200):
    """Median price per sqm by whole kilometre from the CBD. Mirrors mart_cbd_gradient."""
    rings = (sales.dropna(subset=["dist_to_cbd_km"])
             .assign(km_from_cbd=lambda d: np.floor(d["dist_to_cbd_km"]).astype(int))
             .groupby("km_from_cbd", as_index=False)
             .agg(sales=("price_psm", "size"), median_price_psm=("price_psm", "median")))
    return rings[rings["sales"] >= min_sales].reset_index(drop=True)


def mrt_premium_by_band(sales):
    """Median price per sqm by published MRT band, and each band's premium over the
    farthest band (over 1.2km). Mirrors mart_mrt_premium_by_band: with no sales that far
    out under the current filters, there is nothing to measure a premium against."""
    bands = (sales.dropna(subset=["mrt_band"])
             .groupby(["mrt_band_order", "mrt_band"], as_index=False)
             .agg(sales=("price_psm", "size"), median_price_psm=("price_psm", "median"))
             .rename(columns={"mrt_band_order": "band_order"})
             .sort_values("band_order", ignore_index=True))
    farthest_rows = bands.loc[bands["band_order"] == 4, "median_price_psm"]
    farthest = farthest_rows.iloc[0] if len(farthest_rows) else np.nan
    return bands.assign(premium_vs_farthest_pct=100 * (bands["median_price_psm"] / farthest - 1))


def town_ranking(sales):
    """Median price per sqm by town, dearest first."""
    return (sales.groupby(["town", "is_mature_estate"], as_index=False)
            .agg(sales=("price_psm", "size"), median_price_psm=("price_psm", "median"))
            .sort_values("median_price_psm", ascending=False, ignore_index=True))


def storey_multiplier(sales, min_cell=15):
    """Each floor tier against Low floors in the same town, flat type and year, averaged
    over every comparison with `min_cell`+ sales on both sides. Mirrors the controlled
    columns of mart_storey_premium."""
    keys = ["town", "flat_type", "calendar_year"]
    cells = (sales.groupby(keys + ["floor_tier"], as_index=False)
             .agg(psm=("price_psm", "median"), n=("price_psm", "size")))
    cells = cells[cells["n"] >= min_cell]
    low = cells[cells["floor_tier"] == "Low (1-4)"][keys + ["psm"]].rename(columns={"psm": "low_psm"})
    joined = cells.merge(low, on=keys)
    if joined.empty:
        return pd.DataFrame(columns=["floor_tier", "controlled_multiplier", "comparison_cells"])
    joined["ratio"] = joined["psm"] / joined["low_psm"]
    out = (joined.groupby("floor_tier", as_index=False)
           .agg(controlled_multiplier=("ratio", "mean"), comparison_cells=("ratio", "size")))
    order = out["floor_tier"].map({tier: i for i, tier in enumerate(TIER_ORDER)})
    return out.assign(_order=order).sort_values("_order").drop(columns="_order").reset_index(drop=True)


def town_summary(sales):
    """The numbers behind the charts, so no identity is carried by colour alone."""
    return (sales.groupby(["town", "is_mature_estate"], as_index=False)
            .agg(transactions=("resale_price", "size"),
                 median_price=("resale_price", "median"),
                 median_psm=("price_psm", "median"),
                 median_mrt_km=("dist_to_nearest_mrt_km", "median"),
                 median_cbd_km=("dist_to_cbd_km", "median"))
            .sort_values("median_psm", ascending=False, ignore_index=True))

"""The Explore page's maths: filter-aware descriptive figures on tiny hand-built sales.

Each function must return the same columns as the published mart it mirrors, so the
dashboard draws both with one chart; check_explore_parity.py proves the numbers agree
when nothing is filtered.
"""

import pandas as pd
import pytest

import explore


def sales(rows):
    """Sales with sensible defaults, overridden per row."""
    base = {
        "transaction_month": pd.Timestamp("2020-01-01"), "calendar_year": 2020,
        "town": "BEDOK", "region": "East", "is_mature_estate": True,
        "flat_type": "4 ROOM", "floor_tier": "Low (1-4)",
        "dist_to_nearest_mrt_km": 0.3, "mrt_band": "0-400m", "mrt_band_order": 1,
        "dist_to_cbd_km": 10.5, "is_near_mrt": True,
        "resale_price": 500000.0, "price_psm": 5000.0, "floor_area_sqm": 100.0,
        "remaining_lease_months": 900,
    }
    return pd.DataFrame([{**base, **row} for row in rows])


def repeat(n, **row):
    return [row] * n


def test_empty_selections_mean_everything():
    df = sales([{"town": "BEDOK"}, {"town": "YISHUN"}])

    assert len(explore.filter_sales(df, years=(2017, 2026))) == 2


def test_filters_combine_and_the_year_range_is_inclusive():
    df = sales([
        {"calendar_year": 2019, "town": "BEDOK"},
        {"calendar_year": 2020, "town": "BEDOK", "flat_type": "3 ROOM"},
        {"calendar_year": 2021, "town": "BEDOK"},
        {"calendar_year": 2021, "town": "YISHUN"},
    ])

    out = explore.filter_sales(df, years=(2020, 2021), flat_types=["4 ROOM"], towns=["BEDOK"])

    assert out["calendar_year"].tolist() == [2021]


def test_price_trend_drops_months_too_thin_to_have_a_median():
    df = sales(repeat(10, flat_type="4 ROOM") + repeat(3, flat_type="1 ROOM"))

    trend = explore.price_trend(df)

    assert trend["flat_type"].tolist() == ["4 ROOM"]
    assert list(trend.columns) == ["transaction_month", "flat_type", "median_price_psm", "sales"]


def test_cbd_gradient_floors_to_whole_kilometres_and_drops_thin_rings():
    df = sales(repeat(200, dist_to_cbd_km=4.99, price_psm=6000.0)
               + repeat(199, dist_to_cbd_km=5.0, price_psm=5000.0))

    gradient = explore.cbd_gradient(df)

    assert gradient.to_dict("records") == [{"km_from_cbd": 4, "sales": 200, "median_price_psm": 6000.0}]


def test_mrt_premium_uses_the_published_band_never_the_distance():
    # 0.403km rounds to "0.40 km" but was classified 400-800m on the exact distance.
    # Re-deriving the band here from the rounded column would move it.
    df = sales([
        {"dist_to_nearest_mrt_km": 0.40, "mrt_band": "400-800m", "mrt_band_order": 2, "price_psm": 5500.0},
        {"dist_to_nearest_mrt_km": 2.0, "mrt_band": "over 1.2km", "mrt_band_order": 4, "price_psm": 5000.0},
    ])

    bands = explore.mrt_premium_by_band(df).set_index("mrt_band")

    assert bands.loc["400-800m", "premium_vs_farthest_pct"] == pytest.approx(10.0)
    assert "0-400m" not in bands.index


def test_storey_multiplier_compares_only_within_town_type_and_year():
    df = sales(
        repeat(15, floor_tier="Low (1-4)", price_psm=5000.0)
        + repeat(15, floor_tier="Ultra-High (20+)", price_psm=7500.0)
        # A dear town's tall block with no Low floors beside it: no comparison, no effect.
        + repeat(15, town="BISHAN", floor_tier="Ultra-High (20+)", price_psm=20000.0)
        # Too few sales for a cell.
        + repeat(14, town="YISHUN", floor_tier="Low (1-4)", price_psm=1.0)
    )

    storey = explore.storey_multiplier(df).set_index("floor_tier")

    assert storey.loc["Ultra-High (20+)", "controlled_multiplier"] == pytest.approx(1.5)
    assert storey.loc["Ultra-High (20+)", "comparison_cells"] == 1


def test_town_ranking_is_dearest_first():
    df = sales([{"town": "YISHUN", "price_psm": 4000.0}, {"town": "BISHAN", "price_psm": 6000.0}])

    assert explore.town_ranking(df)["town"].tolist() == ["BISHAN", "YISHUN"]

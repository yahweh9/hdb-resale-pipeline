"""Planted-answer tests for the hedonic model.

A synthetic market is built with effects we choose, and the model has to hand them
back. This is the only kind of test that proves the model measures what it says it
measures: one that runs cleanly and reports a lease effect with the sign flipped would
pass every smoke test there is.

The market is confounded on purpose. Short leases are made more common in the dearest
town -- the trap finding 4 in FINDINGS.md fell into -- so recovering the lease effect
means the model really is holding town constant, not just fitting a clean dataset.
"""

import numpy as np
import pandas as pd
import pytest

import hedonic

TOWNS = {"EAST": np.log(0.92), "MID": 0.0, "WEST": np.log(1.08)}
MRT = {"0-400m": np.log(1.10), "400-800m": np.log(1.04), "800m-1.2km": 0.0, "over 1.2km": 0.0}
LEASE = {"under 50": np.log(0.85), "50-60": np.log(0.90), "60-70": np.log(0.93),
         "70-80": np.log(0.96), "80-90": np.log(0.98), "90+": 0.0}
FLOOR = {"Low (1-4)": 0.0, "Mid (5-9)": 0.03, "High (10-19)": 0.08, "Ultra-High (20+)": 0.30}
FLAT = {"3 ROOM": 0.05, "4 ROOM": 0.0, "5 ROOM": -0.03}
def month_labels(n):
    return [f"{2017 + i // 12}-{i % 12 + 1:02d}" for i in range(n)]


def market(seed=0, n_blocks=400, sales_per_block=8, drop=None, n_months=24):
    """Synthetic sales with known effects. `drop` = (term, level) removes that level."""
    MONTHS = month_labels(n_months)
    rng = np.random.default_rng(seed)

    def pick(options, size, p=None):
        keys = np.array(list(options))
        return keys[rng.choice(len(keys), size=size, p=p)]

    # Block attributes: every sale in a block shares its town, station band and lease.
    town = pick(TOWNS, n_blocks)
    mrt = pick(MRT, n_blocks)
    # The confound: WEST, the dearest town, has three times the share of short leases.
    short = rng.random(n_blocks) < np.where(town == "WEST", 3 / 8, 1 / 6)
    lease = np.where(short, "under 50", pick([k for k in LEASE if k != "under 50"], n_blocks))
    block_shock = rng.normal(0, 0.02, n_blocks)

    n = n_blocks * sales_per_block
    b = np.repeat(np.arange(n_blocks), sales_per_block)
    floor, flat = pick(FLOOR, n), pick(FLAT, n)
    month_i = rng.integers(len(MONTHS), size=n)

    def lookup(effects, levels):
        return pd.Series(levels).map(effects).to_numpy()

    log_psm = (np.log(5000) + lookup(TOWNS, town[b]) + lookup(MRT, mrt[b])
               + lookup(LEASE, lease[b]) + lookup(FLOOR, floor) + lookup(FLAT, flat)
               + 0.005 * month_i + block_shock[b] + rng.normal(0, 0.03, n))
    sales = pd.DataFrame({
        "block_key": [f"b{i}" for i in b], "town": town[b], "mrt_band": mrt[b],
        "lease_band": lease[b], "floor_tier": floor, "flat_type": flat,
        "transaction_month": np.array(MONTHS)[month_i], "price_psm": np.exp(log_psm),
    })
    if drop:
        term, level = drop
        sales = sales[sales[term] != level]
    return sales


@pytest.fixture(scope="module")
def fit():
    return hedonic.fit_hedonic(market())


def effect(coefs, term, level):
    return coefs.set_index(["term", "level"]).loc[(term, level)]


@pytest.mark.parametrize("term, level, planted", [
    ("mrt_band", "0-400m", MRT["0-400m"]),
    ("mrt_band", "400-800m", MRT["400-800m"]),
    ("lease_band", "under 50", LEASE["under 50"]),
    ("lease_band", "70-80", LEASE["70-80"]),
    ("floor_tier", "Ultra-High (20+)", FLOOR["Ultra-High (20+)"]),
    ("flat_type", "3 ROOM", FLAT["3 ROOM"]),
])
def test_planted_effects_come_back(fit, term, level, planted):
    assert effect(fit, term, level)["effect_pct"] == pytest.approx(100 * np.expm1(planted), abs=1.5)


def test_the_lease_effect_survives_the_town_confound(fit):
    # Short leases cluster in the dearest town. A model that failed to hold town
    # constant would report them as barely cheaper, or dearer -- finding 4's reversal.
    assert effect(fit, "lease_band", "under 50")["effect_pct"] < -12


def test_town_effects_are_relative_to_the_average_town(fit):
    towns = fit[fit["term"] == "town"]
    centred = {t: v - np.mean(list(TOWNS.values())) for t, v in TOWNS.items()}

    assert towns["estimate"].mean() == pytest.approx(0, abs=1e-9)
    assert not towns["is_reference"].any()
    for town, planted in centred.items():
        assert effect(fit, "town", town)["effect_pct"] == pytest.approx(100 * np.expm1(planted), abs=1.5)


def test_each_other_term_has_exactly_one_zero_effect_reference(fit):
    refs = fit[fit["is_reference"]]

    assert sorted(refs["term"]) == sorted(["mrt_band", "lease_band", "floor_tier", "flat_type", "month"])
    assert (refs["estimate"] == 0).all()
    assert set(refs["level"]) >= {"over 1.2km", "90+", "Low (1-4)", "4 ROOM", "2017-01"}


def test_the_month_terms_track_the_planted_trend(fit):
    # 0.5% a month for 23 months after the reference month.
    assert effect(fit, "month", "2018-12")["estimate"] == pytest.approx(0.005 * 23, abs=0.015)


def test_a_design_wider_than_127_columns_keeps_every_month():
    # The real warehouse has 117 months, ~160 columns in all. Category codes come back
    # as int8 (up to 127 categories), and column arithmetic on them wrapped past 127:
    # every month from Mar 2024 was written into the wrong column and fitted as zero.
    # 24 months never reached the edge. 120 months stays int8 and crosses it.
    coefs = hedonic.fit_hedonic(market(n_blocks=800, n_months=120))
    months = coefs[coefs["term"] == "month"].set_index("level")

    assert len(months) == 120
    assert months.loc["2026-12", "estimate"] == pytest.approx(0.005 * 119, abs=0.03)


def test_every_interval_contains_its_estimate_and_has_width(fit):
    free = fit[~fit["is_reference"]]

    assert (free["std_error"] > 0).all()
    assert (free["ci_low_pct"] < free["effect_pct"]).all()
    assert (free["effect_pct"] < free["ci_high_pct"]).all()


def test_sales_counts_add_up_to_the_input(fit):
    n = len(market())
    for term, rows in fit.groupby("term"):
        assert rows["sales"].sum() == n, term


def test_a_rank_deficient_design_fails_instead_of_returning_arbitrary_numbers():
    # If every block's station band is fixed by its town, the model cannot tell town
    # from station apart. statsmodels would fit anyway -- with a warning nobody reads
    # and coefficients that are one arbitrary solution among infinitely many.
    sales = market()
    sales["mrt_band"] = sales["town"].map({"EAST": "0-400m", "MID": "400-800m", "WEST": "over 1.2km"})

    with pytest.raises(ValueError, match="rank"):
        hedonic.fit_hedonic(sales)


def test_an_empty_band_is_left_out_rather_than_crashing():
    coefs = hedonic.fit_hedonic(market(drop=("lease_band", "under 50")))

    lease = coefs[coefs["term"] == "lease_band"]
    assert "under 50" not in set(lease["level"])
    assert len(lease) == 5


def test_a_missing_reference_falls_back_to_the_most_common_level():
    coefs = hedonic.fit_hedonic(market(drop=("mrt_band", "over 1.2km")))

    mrt = coefs[coefs["term"] == "mrt_band"]
    assert mrt["is_reference"].sum() == 1
    assert "over 1.2km" not in set(mrt["level"])

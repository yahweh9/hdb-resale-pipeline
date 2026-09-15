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

from synthetic import FLAT, FLOOR, LEASE, MRT, TOWNS, market


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


# --- One fit per calendar year ------------------------------------------------------


def test_fitting_by_year_recovers_the_effect_in_every_year():
    # 24 months spans 2017 and 2018; each year gets its own fit and its own answer.
    coefs = hedonic.fit_by_year(market(n_blocks=800))

    assert sorted(coefs["calendar_year"].unique()) == [2017, 2018]
    for year, fit in coefs.groupby("calendar_year"):
        assert effect(fit, "mrt_band", "0-400m")["effect_pct"] == pytest.approx(
            100 * np.expm1(MRT["0-400m"]), abs=2.5
        ), year


def test_each_year_is_measured_against_its_own_first_month():
    coefs = hedonic.fit_by_year(market(n_blocks=800))
    refs = coefs[(coefs["term"] == "month") & coefs["is_reference"]]

    assert dict(zip(refs["calendar_year"], refs["level"])) == {2017: "2017-01", 2018: "2018-01"}


def test_a_year_too_thin_to_identify_is_skipped_not_guessed():
    sales = market(n_blocks=800)
    thin = pd.concat([sales[sales["transaction_month"] < "2018"],
                      sales[sales["transaction_month"] >= "2018"].head(10)])

    coefs = hedonic.fit_by_year(thin)

    assert sorted(coefs["calendar_year"].unique()) == [2017]


# --- Prediction ---------------------------------------------------------------------


def test_predictions_land_within_the_planted_noise():
    sales = market()
    model = hedonic.fit(sales)

    misses = np.log(sales["price_psm"].to_numpy()) - hedonic.predict(model, sales)

    # Sale noise sd 0.03 plus block shock sd 0.02: a typical miss is ~0.03 in log points.
    assert np.median(np.abs(misses)) < 0.04
    assert abs(np.mean(misses)) < 0.005


def test_a_level_the_fit_never_saw_cannot_be_predicted():
    model = hedonic.fit(market())
    unseen = market().head(3).assign(town=["EAST", "NOWHERE", "WEST"])

    predicted = hedonic.predict(model, unseen)

    assert np.isnan(predicted[1])
    assert not np.isnan(predicted[[0, 2]]).any()

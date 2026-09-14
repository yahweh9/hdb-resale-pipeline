"""Validation and fair value, tested on a market where we know the right answer.

Validation has to show the model beating a lazy guess on blocks it never saw -- if it
cannot do that on a market built to its own assumptions, it certainly cannot on real
sales. Fair value has to find the blocks we planted premiums on, and refuse a verdict
where there are too few sales to give one.
"""

import numpy as np
import pandas as pd
import pytest

import valuation
from synthetic import market


# --- Validation ---------------------------------------------------------------------


def test_the_holdout_is_a_fixed_fifth_of_blocks():
    blocks = pd.Series([f"b{i}" for i in range(1000)] * 3)  # repeated, as sales are

    first = valuation.holdout_blocks(blocks)
    again = valuation.holdout_blocks(blocks.sample(frac=1, random_state=7))

    assert first == again  # same blocks whatever order the sales arrive in
    assert len(first) == 200


@pytest.fixture(scope="module")
def validation():
    return valuation.validate(market(n_blocks=1000)).set_index("scope")


def test_one_row_per_year_and_one_for_all_years(validation):
    assert list(validation.index) == ["2017", "2018", "All years"]


def test_about_a_fifth_of_sales_are_tested(validation):
    share = validation.loc["All years", "test_sales"] / len(market(n_blocks=1000))

    assert 0.15 < share < 0.25


def test_the_model_beats_the_lazy_baseline_on_unseen_blocks(validation):
    # The baseline knows town and flat type; the model also knows the station band, the
    # lease, the storey and the month, all of which carry planted effects.
    overall = validation.loc["All years"]

    assert overall["model_median_error_pct"] < overall["baseline_median_error_pct"]
    assert overall["model_within_10pct"] > overall["baseline_within_10pct"]


# --- Fair value ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def planted():
    # Block 0 sells 15% above what its attributes justify, block 1 15% below.
    return market(n_blocks=300, sales_per_block=40, n_months=48,
                  block_effects={0: np.log(1.15), 1: np.log(0.85)})


@pytest.fixture(scope="module")
def verdicts(planted):
    return valuation.fair_value(planted).set_index("block_key")


def test_a_planted_premium_is_found(verdicts):
    assert verdicts.loc["b0", "verdict"] == "above"
    assert verdicts.loc["b0", "premium_pct"] == pytest.approx(15, abs=4)


def test_a_planted_discount_is_found(verdicts):
    assert verdicts.loc["b1", "verdict"] == "below"
    assert verdicts.loc["b1", "premium_pct"] == pytest.approx(-15, abs=4)


def test_only_the_last_36_months_count(planted, verdicts):
    # 48 months run Jan 2017 to Dec 2020, so the window opens in Jan 2018.
    b0 = planted[planted["block_key"] == "b0"]

    assert verdicts.loc["b0", "sales"] == (b0["transaction_month"] >= "2018-01").sum()
    assert (verdicts["window_start"] == "2018-01").all()


def test_a_thin_block_gets_no_verdict(planted):
    thin = pd.concat([planted[planted["block_key"] != "b2"],
                      planted[planted["block_key"] == "b2"].tail(5)])

    verdicts = valuation.fair_value(thin).set_index("block_key")

    assert verdicts.loc["b2", "verdict"] == "not enough sales"


def test_every_verdict_follows_the_rules(verdicts):
    judged = verdicts[verdicts["verdict"].isin(["above", "below"])]

    assert (judged["sales"] >= valuation.MIN_SALES).all()
    assert ((judged["ci_low_pct"] > 0) | (judged["ci_high_pct"] < 0)).all()
    assert set(verdicts["verdict"]) <= {"above", "below", "in line", "not enough sales"}

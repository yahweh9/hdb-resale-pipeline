"""Two uses of the hedonic model that need it to predict, not just to explain.

validate: does the model price flats it has never seen better than a lazy guess? Each
year is fitted on 80% of blocks and asked to price the other 20%, next to a baseline
that guesses the median price per sqm for the town and flat type. Blocks are held out
whole, because a block's own sales share everything the model cannot see: holding out
single sales would let the model peek at the answer through the block's other sales.

fair_value: which blocks sell above or below what their attributes justify? Each sale
in the last 36 months is compared with its own year's fit, and a block gets a verdict
only when it has enough sales and they agree.

Like pricing/hedonic.py, this is plain pandas and numpy so pytest can test it against planted
answers; the dbt Python models only move data in and out.
"""

import numpy as np
import pandas as pd
from scipy import stats

from pricing import hedonic

SEED = 2017
HOLDOUT_SHARE = 0.2
WINDOW_MONTHS = 36
MIN_SALES = 10


def holdout_blocks(block_keys, share=HOLDOUT_SHARE, seed=SEED):
    """The set of blocks held out for testing: a fixed share, the same on every run.

    Sorted before sampling, so the answer depends only on which blocks exist, never on
    the order their sales happened to arrive in.
    """
    blocks = np.array(sorted(pd.unique(block_keys)))
    rng = np.random.default_rng(seed)
    return set(rng.choice(blocks, size=round(len(blocks) * share), replace=False))


def _years(sales):
    return sales["transaction_month"].str[:4].astype(int)


def validate(sales):
    """Out-of-sample accuracy per year and across all years, model against baseline.

    Both methods are scored on the same sales: those the model can price (every level
    seen in training) and the baseline can price (the town and flat type sold in the
    training blocks that year). A year too thin to fit is skipped.
    """
    years = _years(sales)
    is_test = sales["block_key"].isin(holdout_blocks(sales["block_key"]))

    scored = []
    for year in sorted(years.unique()):
        train, test = sales[(years == year) & ~is_test], sales[(years == year) & is_test]
        try:
            model = hedonic.fit(train)
        except hedonic.RankDeficientError:
            continue

        medians = (train.groupby(["town", "flat_type"])["price_psm"].median()
                   .rename("baseline_psm").reset_index())
        test = test.merge(medians, on=["town", "flat_type"], how="left")
        scored.append(pd.DataFrame({
            "scope": str(year),
            "actual": test["price_psm"].to_numpy(),
            "model": np.exp(hedonic.predict(model, test)),
            "baseline": test["baseline_psm"].to_numpy(),
        }))

    if not scored:
        return _empty_validation()
    scored = pd.concat(scored, ignore_index=True).dropna()
    rows = [_score(scope, group) for scope, group in scored.groupby("scope", sort=True)]
    rows.append(_score("All years", scored))
    return pd.DataFrame(rows)


def _score(scope, scored):
    model_error = (scored["model"] / scored["actual"] - 1).abs()
    baseline_error = (scored["baseline"] / scored["actual"] - 1).abs()
    return {
        "scope": scope,
        "test_sales": int(len(scored)),
        "model_median_error_pct": 100 * model_error.median(),
        "baseline_median_error_pct": 100 * baseline_error.median(),
        "model_within_10pct": 100 * (model_error <= 0.10).mean(),
        "baseline_within_10pct": 100 * (baseline_error <= 0.10).mean(),
    }


def _empty_validation():
    # Typed, so dbt-duckdb can still create the table when no year could be fitted.
    return pd.DataFrame({
        "scope": pd.Series(dtype="object"), "test_sales": pd.Series(dtype="int64"),
        "model_median_error_pct": pd.Series(dtype="float64"),
        "baseline_median_error_pct": pd.Series(dtype="float64"),
        "model_within_10pct": pd.Series(dtype="float64"),
        "baseline_within_10pct": pd.Series(dtype="float64"),
    })


def _window_start(last_month, months=WINDOW_MONTHS):
    """The first month of the `months`-month window ending at `last_month`, inclusive."""
    index = int(last_month[:4]) * 12 + int(last_month[5:7]) - 1 - (months - 1)
    return f"{index // 12}-{index % 12 + 1:02d}"


def fair_value(sales):
    """Each block's typical premium over what the model predicts, with a verdict.

    Every sale in the window is compared with the fit for ITS OWN year, fitted on all of
    that year's sales, so a 2024 sale is judged against 2024 prices and a stale average
    cannot make a fast-rising town look overpriced.

    premium_pct is the block's mean residual as a percentage, with a 95% t interval
    (t, not normal: a block with 10 sales has a wide interval and should look it).
    """
    window_start = _window_start(sales["transaction_month"].max())
    years = _years(sales)
    in_window = sales["transaction_month"] >= window_start

    residuals = []
    for year in sorted(years[in_window].unique()):
        try:
            model = hedonic.fit(sales[years == year])
        except hedonic.RankDeficientError:
            continue
        judged = sales[in_window & (years == year)]
        residuals.append(pd.DataFrame({
            "block_key": judged["block_key"].to_numpy(),
            "residual": np.log(judged["price_psm"].to_numpy()) - hedonic.predict(model, judged),
        }))

    if not residuals:
        return _empty_fair_value()
    residuals = pd.concat(residuals, ignore_index=True).dropna()
    blocks = residuals.groupby("block_key")["residual"].agg(["count", "mean", "std"]).reset_index()

    n = blocks["count"].to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        half_width = stats.t.ppf(0.975, n - 1) * blocks["std"].to_numpy() / np.sqrt(n)
    low, high = blocks["mean"] - half_width, blocks["mean"] + half_width

    verdict = np.select(
        [n < MIN_SALES, low > 0, high < 0],
        ["not enough sales", "above", "below"],
        default="in line",
    )
    return pd.DataFrame({
        "block_key": blocks["block_key"],
        "sales": n.astype("int64"),
        "premium_pct": 100 * np.expm1(blocks["mean"]),
        "ci_low_pct": 100 * np.expm1(low),
        "ci_high_pct": 100 * np.expm1(high),
        "verdict": verdict,
        "window_start": window_start,
        "window_end": sales["transaction_month"].max(),
    })


def _empty_fair_value():
    return pd.DataFrame({
        "block_key": pd.Series(dtype="object"), "sales": pd.Series(dtype="int64"),
        "premium_pct": pd.Series(dtype="float64"), "ci_low_pct": pd.Series(dtype="float64"),
        "ci_high_pct": pd.Series(dtype="float64"), "verdict": pd.Series(dtype="object"),
        "window_start": pd.Series(dtype="object"), "window_end": pd.Series(dtype="object"),
    })

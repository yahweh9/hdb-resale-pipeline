"""The hedonic pricing model: every effect estimated at once, each holding the rest constant.

    log(price_psm) ~ town + mrt_band + lease_band + floor_tier + flat_type + month

A GROUP BY estimates one effect while the others move freely in the background, which
is how finding 4 in FINDINGS.md came out backwards. Fitting them together is what turns
"flats near stations sell for 7.2% more" into "being near a station is worth X%, in the
same town, with the same lease, storey, flat type and month."

This module is plain pandas, numpy and statsmodels, with no dbt and no warehouse, so the
planted-answer tests in tests/python/test_hedonic.py can prove it recovers known effects
before the dbt Python model runs it on real sales.
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm

TERMS = ["town", "mrt_band", "lease_band", "floor_tier", "flat_type", "month"]

# The level every other level in a term is compared against. Month's reference is the
# earliest month in the data; town has none -- see _town_contrasts.
REFERENCES = {
    "mrt_band": "over 1.2km",
    "lease_band": "90+",
    "floor_tier": "Low (1-4)",
    "flat_type": "4 ROOM",
}

# Normal critical value. Cluster-robust errors in statsmodels use the normal, not t.
Z95 = 1.959964


class RankDeficientError(ValueError):
    """The data cannot tell two terms apart, so no coefficient in the fit means anything."""


def _reference(values, term):
    """The reference level for a term, falling back when the preferred one has no sales.

    A thin slice -- a single year of the fixture, say -- can lack the preferred level
    entirely. Falling back to the most common level keeps the fit alive, and the output
    flags which level was used, so nothing is silently reinterpreted.
    """
    counts = values.value_counts()
    if term == "month":
        return min(counts.index)
    if REFERENCES.get(term) in counts.index:
        return REFERENCES[term]
    return sorted(counts.index, key=lambda level: (-counts[level], level))[0]


def fit_hedonic(sales):
    """Fit the model to `sales` and return one row per level of every term.

    Input columns: block_key, town, mrt_band, lease_band, floor_tier, flat_type,
    transaction_month ('YYYY-MM') and price_psm.

    Output columns: term, level, is_reference, sales, estimate (log points), std_error,
    effect_pct, ci_low_pct, ci_high_pct. A level with no sales does not appear.
    """
    df = sales.rename(columns={"transaction_month": "month"}).reset_index(drop=True)
    n = len(df)

    # Design matrix built by index, not by patsy or get_dummies: 240k rows x ~150
    # columns of float64 is already ~300MB, and this makes exactly one copy of it.
    layout = []  # (term, levels, reference, first column index)
    width = 1    # column 0 is the intercept
    for term in TERMS:
        reference = _reference(df[term], term)
        levels = [reference] + sorted(set(df[term]) - {reference})
        layout.append((term, levels, reference, width))
        width += len(levels) - 1

    X = np.zeros((n, width))
    X[:, 0] = 1.0
    for term, levels, _, start in layout:
        # int64 on purpose: pandas hands back int8 codes for up to 127 levels, and
        # `start + code` in int8 wraps past 127 -- which put every month from Mar 2024
        # into the wrong column once the design grew past 127 columns.
        codes = pd.Categorical(df[term], categories=levels).codes.astype(np.int64)
        free = codes > 0
        X[np.flatnonzero(free), start + codes[free] - 1] = 1.0

    y = np.log(df["price_psm"].to_numpy(dtype=float))
    # Sales in the same block share everything the model cannot see -- the same view,
    # the same upkeep, the same neighbours. Clustering by block stops 40 sales from one
    # block counting as 40 independent pieces of evidence.
    groups = pd.factorize(df["block_key"])[0]
    result = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
    # A rank-deficient design still "fits": statsmodels warns and returns one arbitrary
    # solution among infinitely many. That is how an int8 overflow once zeroed 31 month
    # columns and produced a plausible-looking table. Wrong numbers must not be quiet.
    if result.model.rank < width:
        raise RankDeficientError(
            f"Design matrix is rank-deficient ({result.model.rank} of {width} columns "
            "independent): two terms cannot be told apart in this data."
        )
    params, cov = np.asarray(result.params), np.asarray(result.cov_params())

    rows = []
    for term, levels, reference, start in layout:
        counts = df[term].value_counts()
        contrasts = _town_contrasts(levels, start, width) if term == "town" else None
        for i, level in enumerate(levels):
            if contrasts is not None:
                c = contrasts[i]
            elif i == 0:
                c = None
            else:
                c = np.zeros(width)
                c[start + i - 1] = 1.0

            estimate = 0.0 if c is None else float(c @ params)
            std_error = 0.0 if c is None else float(np.sqrt(c @ cov @ c))
            rows.append({
                "term": term,
                "level": level,
                "is_reference": term != "town" and level == reference,
                "sales": int(counts[level]),
                "estimate": estimate,
                "std_error": std_error,
                "effect_pct": 100 * np.expm1(estimate),
                "ci_low_pct": 100 * np.expm1(estimate - Z95 * std_error),
                "ci_high_pct": 100 * np.expm1(estimate + Z95 * std_error),
            })
    return pd.DataFrame(rows)


def fit_by_year(sales):
    """The same model fitted separately to each calendar year, stacked with a year column.

    One all-years fit assumes every effect held still for a decade; the mature-estate gap
    alone went 23% -> 6% -> 11% (finding 5). A fit per year lets the effects move. Each
    year's months are measured against that year's own first month.

    A year the data cannot identify -- too few sales for the number of terms, as in the
    CI fixture -- is skipped rather than fitted to arbitrary numbers. Whether a year
    SHOULD have been fitted is a question about the data, so the dbt build asks it, not
    this function.
    """
    years = sales["transaction_month"].str[:4].astype(int)
    fits = []
    for year in sorted(years.unique()):
        try:
            coefs = fit_hedonic(sales[years == year])
        except RankDeficientError:
            continue
        fits.append(coefs.assign(calendar_year=year))
    if not fits:
        return pd.DataFrame(columns=["calendar_year", "term", "level", "is_reference", "sales",
                                     "estimate", "std_error", "effect_pct", "ci_low_pct",
                                     "ci_high_pct"])
    stacked = pd.concat(fits, ignore_index=True)
    return stacked[["calendar_year"] + [c for c in stacked.columns if c != "calendar_year"]]


def _town_contrasts(levels, start, width):
    """Each town against the average town, rather than against one arbitrary town.

    The fit itself needs a reference town (the first level). Its coefficients are then
    re-expressed as deviations from their mean across all towns, reference included, via
    linear contrasts -- so the standard errors carry through the re-centring correctly,
    not just the point estimates.
    """
    k = len(levels)
    mean = np.zeros(width)
    mean[start:start + k - 1] = 1.0 / k
    contrasts = []
    for i in range(k):
        c = -mean.copy()
        if i > 0:
            c[start + i - 1] += 1.0
        contrasts.append(c)
    return contrasts

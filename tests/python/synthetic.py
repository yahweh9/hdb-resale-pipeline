"""A synthetic HDB market with effects we choose, shared by the model's tests.

Every test that needs to know the right answer builds its data here: towns, station
bands, lease bands, storeys and flat types each carry a planted effect, prices trend
0.5% a month, and every block has a random shock shared by its sales.

The market is confounded on purpose. Short leases are more common in the dearest town
-- the trap finding 4 in FINDINGS.md fell into.
"""

import numpy as np
import pandas as pd

TOWNS = {"EAST": np.log(0.92), "MID": 0.0, "WEST": np.log(1.08)}
MRT = {"0-400m": np.log(1.10), "400-800m": np.log(1.04), "800m-1.2km": 0.0, "over 1.2km": 0.0}
LEASE = {"under 50": np.log(0.85), "50-60": np.log(0.90), "60-70": np.log(0.93),
         "70-80": np.log(0.96), "80-90": np.log(0.98), "90+": 0.0}
FLOOR = {"Low (1-4)": 0.0, "Mid (5-9)": 0.03, "High (10-19)": 0.08, "Ultra-High (20+)": 0.30}
FLAT = {"3 ROOM": 0.05, "4 ROOM": 0.0, "5 ROOM": -0.03}


def month_labels(n):
    return [f"{2017 + i // 12}-{i % 12 + 1:02d}" for i in range(n)]


def market(seed=0, n_blocks=400, sales_per_block=8, drop=None, n_months=24, block_effects=None):
    """Synthetic sales with known effects.

    `drop` = (term, level) removes that level. `block_effects` = {block index: log effect}
    plants a premium or discount on specific blocks, on top of their random shock --
    the thing fair value is supposed to find.
    """
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
    for index, planted in (block_effects or {}).items():
        block_shock[index] += planted

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

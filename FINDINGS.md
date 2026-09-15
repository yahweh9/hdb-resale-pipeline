# Findings

What 240,074 HDB resale transactions say, and — more carefully — what they do not.

<!-- edition -->
**Data cut:** resale transactions through **Sep 2026** (240,074 sales) · published **14 Sep 2026**
<!-- /edition -->

This is the analysis document. [README.md](README.md) is about the pipeline that
produces the data; this is about what came out of it. Every figure here is
reproducible from the warehouse `dbt build` creates, and the query behind each one is
a single join across the gold star schema.

---

## Method, and how to read the numbers

- **Medians, never means.** The price distribution has a long right tail; a mean is
  dragged by a handful of maisonettes and penthouses.
- **Price per square metre, not price.** A 5-room flat is not expensive because it is
  expensive, it is expensive because it is large. Normalising by area is what makes
  towns and flat types comparable at all.
- **2026 is nine months** (Jan–Sep, 18,007 sales), not a full year. Any 2026-vs-2025
  comparison here is partial-year against full-year, which seasonality alone can move.
- **Sample sizes are quoted throughout.** Two of the findings below rest on subsets
  small enough to matter.
- Source: [data.gov.sg](https://data.gov.sg) resale flat prices, Jan 2017 – Sep 2026.
  Station locations from Wikidata; block coordinates geocoded via OneMap.

**The honest frame for everything below:** these are `GROUP BY` results. Location,
lease, storey, flat type and age all correlate with one another, and a group-by
estimates one effect at a time while the others move freely in the background. Where
that changes an answer, it is said so explicitly — in one case it reverses it.

---

## 1. The CBD premium is real, and it stops at about 5km

Median price per square metre, by 1km ring from the CBD (1.2839, 103.8515):

| km | median psm | | km | median psm |
|---|---|---|---|---|
| 1 | S$8,889 | | 10 | S$5,198 |
| 2 | S$7,416 | | 11 | S$5,529 |
| 3 | S$6,660 | | 12 | S$5,393 |
| 4 | S$6,517 | | 13 | S$5,137 |
| 5 | S$5,981 | | 14 | S$5,376 |
| 6 | S$5,917 | | 15 | S$5,187 |
| 7 | S$6,182 | | 16 | S$4,615 |
| 8 | S$5,672 | | 17 | S$4,694 |
| 9 | S$5,411 | | 19 | S$4,314 |

Three regimes, not one gradient:

- **1–5km: steep decay.** Down 33% over four kilometres.
- **5–15km: a plateau.** Down only 13% over ten kilometres, and it *oscillates* — 7km
  is dearer than 6km, 11km dearer than 10km, 14km dearer than 13km. Distance has
  stopped explaining price.
- **Past 16km: a second cliff**, into the far North and West.

The non-monotonicity in the middle band is the finding. Inside the plateau, which
town you are in matters more than how far out it is: Queenstown and Jurong East sit at
similar radii and price differently. A model that treats distance-to-CBD as a single
linear term will fit the centre and misprice everything from 5 to 15km, which is
where most of Singapore's public housing is.

**What this can't tell you:** why the plateau exists. Regional centres, MRT line
geometry, estate age and BTO vintage all vary across it and none is isolated here.

---

## 2. The MRT premium is not one number — it is four

Flats within 400m of a station sell at a **7.2% premium** overall (S$5,568 vs
S$5,194 per sqm, n = 78,682 and 161,391). By distance band, against the farthest:

<!-- table: mrt_premium_by_band -->
| Distance to MRT | Sales | Median psm | vs over 1.2km |
|---|---|---|---|
| 0-400m | 78,682 | S$5,568 | +10.1% |
| 400-800m | 99,886 | S$5,288 | +4.6% |
| 800m-1.2km | 43,601 | S$5,000 | -1.1% |
| over 1.2km | 17,905 | S$5,055 | +0.0% |
<!-- /table -->

Almost all of the difference sits inside 800m; beyond that the bands are within about
1% of each other. That headline is close to meaningless on its own, though, because
station proximity is entangled with CBD proximity. Splitting by ring:

| Distance from CBD | Near MRT | Not near | Premium |
|---|---|---|---|
| under 5km | S$7,504 | S$6,394 | **+17.4%** |
| 5–10km | S$6,098 | S$5,650 | **+7.9%** |
| 10–15km | S$5,375 | S$5,247 | **+2.4%** |
| 15km+ | S$5,000 | S$4,743 | **+5.4%** |

The premium is **more than seven times larger in the centre than at 10–15km**, and the
aggregate 7.2% is an artefact of mixing them.

This runs against intuition — you would expect a station to be worth *more* on the
periphery, where the alternatives are worse. One reading is that in the centre a
station is bundled with everything else that is central, so the 17.4% is measuring the
bundle rather than the station. That reading is untested here.

**What this can't tell you:** whether any of these figures is the value of the station
itself. Even within a ring, near-station blocks differ from far ones in age, estate
type and amenity density. Every number in this table remains an upper bound.

---

## 3. The storey premium is real, and a third of it is the postcode

Comparing floor tiers directly, for 4-room flats:

| Tier | Median psm | Naive premium |
|---|---|---|
| Low (1–4) | S$5,000 | — |
| Mid (5–9) | S$5,288 | +5.8% |
| High (10–19) | S$5,739 | +14.8% |
| Ultra-High (20+) | S$9,140 | **+82.8%** |

An 83% premium for a high floor is not credible, and it is not what is happening.
Blocks tall enough to have a 20th storey are newer and concentrated in expensive
places, so a raw comparison credits the storey with the neighbourhood.

Comparing each tier only against **low floors in the same town, the same flat type and
the same year** (189 such comparison cells for the top tier, minimum 15 sales per
cell):

| Tier | Controlled multiplier |
|---|---|
| Low (1–4) | 1.000 |
| Mid (5–9) | 1.052 |
| High (10–19) | 1.118 |
| Ultra-High (20+) | **1.513** |

**The 20+ premium falls from 83% to 51%.** Around a third of the apparent storey
effect was location and vintage. The remaining 51% is large, consistent across cells,
and survives the control.

**What this can't tell you:** the controls are coarse — town, not block. Within a town,
tall blocks still differ systematically from short ones.

---

## 4. Lease decay comes out backwards, and that is the most useful result here

Every buyer in Singapore knows a shorter lease should mean a cheaper flat. The data,
grouped naively for 4-room flats, says otherwise:

| Remaining lease | Median psm | Sales |
|---|---|---|
| 90+ years | S$6,129 | 30,271 |
| **under 50 years** | **S$5,945** | **638** |
| 70–90 years | S$5,336 | 37,522 |
| 50–70 years | S$4,911 | 33,602 |

The shortest leases come **second most expensive**, above two bands with far more
lease left. Taken at face value this says lease decay does not exist, which is false.

It is a confound, and it is measurable:

| Remaining lease | Median km to CBD | % in mature estates | Sales |
|---|---|---|---|
| under 50 years | **6.2 km** | **93%** | 638 |
| 50–70 years | 12.2 km | 54% | 33,602 |
| 70–90 years | 14.2 km | 30% | 37,522 |
| 90+ years | 14.2 km | 25% | 30,271 |

Flats with under 50 years left sit **less than half as far from the CBD** as every
other band, and 93% of them are in mature estates. They are the oldest flats in
Singapore, and the oldest estates are the central ones. The five towns supplying most
of those 638 sales are Toa Payoh, Bukit Merah, Kallang/Whampoa, Queenstown and Marine
Parade — every one of them central and mature.

**Location is worth more than the lease is losing.** The lease effect is real; this
grouping simply cannot see it, because the variable that would reveal it is almost
perfectly correlated with the one hiding it.

This is included because it is the clearest demonstration in the project of why a
dashboard needs a document beside it. The chart would have been correct, legible, and
would have led a reader to exactly the wrong conclusion.

**What this can't tell you:** the size of the true lease effect. Separating it needs
a model that holds location constant — see [What would settle this](#what-would-settle-this).

---

## 5. Prices rose 52%, almost all of it after 2020

Median price per square metre, all flat types:

| Year | Median psm | Sales | | Year | Median psm | Sales |
|---|---|---|---|---|---|---|
| 2017 | S$4,282 | 20,509 | | 2022 | S$5,373 | 26,720 |
| 2018 | S$4,209 | 21,561 | | 2023 | S$5,709 | 25,754 |
| 2019 | S$4,176 | 22,186 | | 2024 | S$6,098 | 27,832 |
| 2020 | S$4,356 | 23,333 | | 2025 | S$6,500 | 25,085 |
| 2021 | S$4,916 | 29,087 | | 2026* | S$6,478 | 18,007 |

<sub>*nine months</sub>

The shape matters more than the total. **2017–2019 was flat and slightly declining.**
The entire 52% rise happened from 2020 onward, with the sharpest single jump in 2021
(+12.8%), alongside the highest transaction volume in the series.

Alongside it, the gap between mature and non-mature estates **collapsed and then
partially recovered**:

| Year | Mature | Non-mature | Gap |
|---|---|---|---|
| 2017 | S$4,851 | S$3,944 | 23.0% |
| 2019 | S$4,592 | S$3,893 | 17.9% |
| 2021 | S$5,188 | S$4,756 | 9.1% |
| 2023 | S$5,923 | S$5,579 | **6.2%** |
| 2026 | S$6,920 | S$6,211 | 11.4% |

Non-mature estates rose faster through the boom, compressing a 23% premium to 6% by
2023, before it widened again. Because this is a *ratio*, it partly controls for the
market-wide rise — whatever drove prices up drove both sides up.

**What this can't tell you:** anything causal. This period contains a pandemic, a
construction shutdown that delayed BTO completions, an interest-rate cycle and several
rounds of cooling measures. None of them is in this dataset.

---

## 6. A hypothesis that was tested and did not hold

**Hypothesis:** as prices rose, demand would shift toward larger flats in the cheaper
North and West, while central buyers moved to smaller units — a regional divergence.

Share of each region's sales that are 5-room, Executive or Multi-Generation:

| Region | 2017 | 2021 | 2026 | Change |
|---|---|---|---|---|
| Central | 22.9% | 23.6% | 17.6% | −5.3 pts |
| East | 37.6% | 39.2% | 35.0% | −2.6 pts |
| North | 33.5% | 36.8% | 31.5% | −2.0 pts |
| North-East | 34.3% | 36.1% | 30.5% | −3.8 pts |
| West | 34.2% | 38.3% | 33.4% | −0.8 pts |

**Not supported.** Every region moves in the same direction — up to 2021, down by 2026
— and the largest fall is in Central, the opposite of the prediction. There is no
regional divergence to find.

What is there instead is uniform: the share of large-flat sales fell everywhere as
prices rose. That is consistent with an affordability constraint acting market-wide
rather than a regional preference shift, though this data cannot distinguish
constrained buyers from changed tastes.

A negative result is reported here because it was tested. The alternative — running
five hypotheses and publishing the three that worked — is how analysis becomes
decoration.

---

## What would settle this

Every caveat above has the same shape: a `GROUP BY` estimates one effect while the
others move freely. The standard answer is a **hedonic pricing model** — estimate all
of them at once, so each coefficient is read holding the rest constant:

```
log(price_psm) ~ dist_to_cbd + dist_to_mrt + remaining_lease
               + floor_tier + flat_type + town + time
```

That is what turns "flats near stations sell for 7.2% more" into "station proximity is
worth X%, holding distance to the CBD, lease and storey constant" — a claim that
survives being questioned. The gold star schema is already the feature table for it:
`fact_resale_txn` joined to its four dimensions is one query from a design matrix.

**It has not been built.** Saying what the data cannot currently support is more useful
than an extra chart.

---

## Limitations

**No repeat-sales index is possible from this source.** The dataset carries no unit
identifier — there is no way to tell that the same flat sold in 2018 and again in 2024.
Repeat-sales indices (the method behind Case-Shiller) control for property quality
automatically by comparing a home to *itself*, which is exactly what would fix most of
the confounds above. That option is closed here, and no amount of modelling reopens it.

**No forecasting.** Nine years of history cannot support a ten-year projection, and
this series is driven by policy — cooling measures, BTO supply, grants, income
ceilings — which are decisions, not processes. Nothing in the 2017–2020 data predicts
the 2021 inflection. A forecast chart would look authoritative and mean nothing.

**Coverage.** Resale transactions only: no BTO prices, no rentals, no private market.
HDB housing is where the large majority of Singapore residents live, but conclusions
here do not generalise to the private market, which is priced differently and is not
in this dataset.

**Geocoding.** All 9,744 block addresses resolved via OneMap with zero failures, so
there is no spatial coverage gap. Distances are great-circle, not walking routes — a
block 400m from a station across an expressway is not 400m on foot.

**Lease parsing.** `remaining_lease` arrives in two formats in the same column
(`'61 years 04 months'` and a bare number of years). Both are parsed to integer months;
a range test in the dbt build fails the pipeline if any value falls outside 0–1,188.

---

*Generated tables come from the committed edition in `published/`, stamped at the top
of this page. Reproduce with `python ingest_hdb.py --full && dbt build`, then
`python publish_edition.py && python render_findings.py`.*

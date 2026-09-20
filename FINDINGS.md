# Findings

What 240,074 HDB resale sales say about flat prices, and what they can't tell us.

<!-- edition -->
**Data cut:** resale transactions through **Sep 2026** (240,074 sales) · published **14 Sep 2026**
<!-- /edition -->

[README.md](README.md) is the overview, and [docs/ENGINEERING.md](docs/ENGINEERING.md)
explains how the data is collected and processed. Every table on this page is filled
in automatically from the same published numbers the dashboard uses, so the two can't
disagree.

---

## How to read the numbers

- Prices are per square metre, not per flat. A 5-room flat costs more mostly because
  it's bigger, so dividing by floor area compares flats of different sizes fairly.
- Figures are medians, meaning the middle sale. A handful of very expensive flats can
  drag an average up, but they barely move the median.
- 2026 is only nine months (January to September, 18,007 sales), so comparing it with
  full years needs care.
- Sample sizes are shown, so you can see when a number rests on only a few hundred
  sales.
- Sources: [data.gov.sg](https://data.gov.sg) resale flat prices, Jan 2017 to Sep 2026.
  MRT station locations from Wikidata; block locations from OneMap.

**Two kinds of comparison.** Most tables are *simple comparisons*: group the sales and
take the median. They're easy to understand but can mislead, because location, lease,
floor and flat type all move together. So for findings 2 to 5 I also show a
*like-for-like* comparison from a pricing model, which compares flats that are the same
in everything except the thing being measured. [The model, in plain
English](#the-model-in-plain-english) explains how it works.

**Ranges.** Model results come with a "95% range". Read it as the model saying: my best
guess is +19%, and I'm confident the real answer is between +18% and +20%.

---

## 1. Flats nearer the city centre cost more, but the effect fades after about 5km

Median price per square metre, by distance from the CBD, in 1km rings:

<!-- table: cbd_gradient -->
| Km from the CBD | Median price per sqm | Sales |
|---|---|---|
| 1 | S$8,889 | 1,558 |
| 2 | S$7,416 | 4,538 |
| 3 | S$6,660 | 4,025 |
| 4 | S$6,517 | 10,119 |
| 5 | S$5,981 | 7,563 |
| 6 | S$5,917 | 8,782 |
| 7 | S$6,182 | 6,676 |
| 8 | S$5,672 | 7,830 |
| 9 | S$5,411 | 13,751 |
| 10 | S$5,198 | 16,511 |
| 11 | S$5,529 | 10,386 |
| 12 | S$5,393 | 20,586 |
| 13 | S$5,137 | 22,666 |
| 14 | S$5,376 | 32,674 |
| 15 | S$5,187 | 20,565 |
| 16 | S$4,615 | 13,667 |
| 17 | S$4,694 | 12,264 |
| 18 | S$4,777 | 19,205 |
| 19 | S$4,314 | 6,410 |
<!-- /table -->

- Within 5km, prices drop fast: down about a third over four kilometres.
- From 5 to 15km they barely change, down only 13% over ten kilometres, and they zigzag:
  7km is pricier than 6km, and 11km pricier than 10km. In this band, *which town* a flat
  is in matters more than how far out it is.
- Past 16km there's a second drop, into the far north and west.

Most HDB flats are in that 5 to 15km middle band, so a simple "further out means
cheaper" rule would get most of Singapore wrong.

**What this can't tell me:** *why* the middle band is so flat. Regional centres, MRT
lines and the age of estates all vary across it, and I haven't separated them.

---

## 2. Living near an MRT station is worth more than it first looks

A simple comparison says flats within 400m of a station sell for **7.2% more** per
square metre than flats further away (S$5,568 against S$5,194, from 78,682 and 161,391
sales). Split into distance bands and compared with flats over 1.2km away:

<!-- table: mrt_premium_by_band -->
| Distance to MRT | Sales | Median price per sqm | Vs over 1.2km |
|---|---|---|---|
| 0-400m | 78,682 | S$5,568 | +10.1% |
| 400-800m | 99,886 | S$5,288 | +4.6% |
| 800m-1.2km | 43,601 | S$5,000 | -1.1% |
| over 1.2km | 17,905 | S$5,055 | +0.0% |
<!-- /table -->

Almost all of the difference is within 800m. But this simple view mixes two things up,
because being near a station is tangled up with being near the city centre. Splitting
by distance from the CBD:

<!-- table: mrt_premium_by_cbd_ring -->
| Distance from the CBD | Within 400m of MRT | Further away | Difference |
|---|---|---|---|
| under 5km | S$7,504 | S$6,394 | +17.4% |
| 5-10km | S$6,098 | S$5,650 | +7.9% |
| 10-15km | S$5,375 | S$5,247 | +2.4% |
| 15km+ | S$5,000 | S$4,743 | +5.4% |
<!-- /table -->

Near the centre, the station premium is more than seven times bigger than at 10 to
15km. I expected the opposite: surely a station matters more out in the suburbs, where
there are fewer alternatives? My best guess is that near the centre, "near a station"
also means "near everything else", so the 17.4% is paying for the whole package rather
than the station alone. I haven't tested that.

Comparing like with like, the pricing model uses flats in the same town, with the same
lease, floor, flat type and month of sale:

<!-- table: mrt_model_vs_naive -->
| Distance to MRT | Sales | Simple comparison | Like for like | 95% range |
|---|---|---|---|---|
| 0-400m | 78,682 | +10.1% | +18.9% | +18.1% to +19.8% |
| 400-800m | 99,886 | +4.6% | +12.9% | +12.1% to +13.6% |
| 800m-1.2km | 43,601 | -1.1% | +7.6% | +6.9% to +8.3% |
| over 1.2km | 17,905 | +0.0% | +0.0% | +0.0% to +0.0% |
<!-- /table -->

Like for like, being within 400m of a station is worth about 19%, roughly double the
simple comparison, and the premium keeps shrinking with distance. That means the
flats far from stations had other things going for them (a better town, more lease
left, a higher floor) which the simple comparison wrongly credited to distance.

The premium has also changed over time:

<!-- table: mrt_premium_by_year -->
| Year | Within 400m vs over 1.2km, like for like | 95% range |
|---|---|---|
| 2017 | +21.9% | +20.6% to +23.2% |
| 2018 | +24.4% | +22.9% to +25.9% |
| 2019 | +24.6% | +23.0% to +26.1% |
| 2020 | +22.6% | +21.2% to +24.1% |
| 2021 | +20.1% | +18.7% to +21.4% |
| 2022 | +16.9% | +15.8% to +18.0% |
| 2023 | +14.9% | +13.9% to +16.0% |
| 2024 | +14.1% | +13.1% to +15.2% |
| 2025 | +16.7% | +15.6% to +17.8% |
| 2026 | +17.3% | +16.2% to +18.4% |
<!-- /table -->

**What this can't tell me:** whether this is the value of the station itself. Blocks
near a station might also be near more shops or have better walking routes, which the
model can't see. Distances are straight lines, not walking routes.

---

## 3. High floors cost more, but much less than they seem to

For 4-room flats, comparing floor levels directly:

<!-- table: storey_naive -->
| Floor level | Median price per sqm (4-room) | Vs a low floor |
|---|---|---|
| Low (1-4) | S$5,000 | +0.0% |
| Mid (5-9) | S$5,288 | +5.8% |
| High (10-19) | S$5,739 | +14.8% |
| Ultra-High (20+) | S$9,140 | +82.8% |
<!-- /table -->

An 83% premium for a high floor isn't believable. Blocks tall enough to have a 20th
floor tend to be newer and in pricier places, so a simple comparison gives the floor
credit for the neighbourhood.

A fairer comparison sets each floor level against low floors in the same town, flat
type and year (189 such groups for the top floors, each with at least 15 sales):

<!-- table: storey_controlled -->
| Floor level | Price vs a low floor (1.00 = same) | Groups compared |
|---|---|---|
| Low (1-4) | 1.00 | 888 |
| Mid (5-9) | 1.05 | 741 |
| High (10-19) | 1.12 | 832 |
| Ultra-High (20+) | 1.51 | 189 |
<!-- /table -->

That brings the 20+ floor premium down from 83% to 51%. About a third of the gap was
really about location.

Holding the lease constant as well, most of the rest disappears. Tall blocks are also
newer: 82% of sales on the 20th floor or above have 80 or more years of lease left,
against 26% of sales on low floors. The pricing model, which also compares flats with
the same lease and MRT distance, puts 20+ floors at about 20% above a low floor (95% range
19.5% to 21.4%), high floors (10 to 19) at about 8%, and mid floors (5 to 9) at about
4%. Height is still worth something, just well under half of what the town
comparison suggested.

**What this can't tell me:** views, block design and upkeep. Those differ between tall
and short blocks too, and some of that may still be counted as "floor".

---

## 4. Older flats looked more expensive, until I compared like with like

Everyone in Singapore knows a shorter lease should mean a cheaper flat. But when I
grouped 4-room flats by how many years of lease they had left, the data seemed to say
otherwise:

<!-- table: lease_naive_4room -->
| Lease left (years) | Median price per sqm | Sales |
|---|---|---|
| 80-90 | S$6,413 | 16,150 |
| 90+ | S$6,129 | 30,271 |
| under 50 | S$5,945 | 638 |
| 50-60 | S$5,357 | 10,220 |
| 70-80 | S$4,946 | 21,372 |
| 60-70 | S$4,709 | 23,382 |
<!-- /table -->

Flats with under 50 years left came out third most expensive, ahead of three groups
with more lease left, and 80 to 90 year leases even beat 90+. Taken at face value, that
says a shrinking lease doesn't lower the price at all, which isn't true.

The explanation is *where* those older flats are:

<!-- table: lease_confound_4room -->
| Lease left (years) | Typical distance to the CBD | % in mature estates | Sales |
|---|---|---|---|
| under 50 | 6.2 km | 93% | 638 |
| 50-60 | 10.0 km | 76% | 10,220 |
| 60-70 | 13.6 km | 45% | 23,382 |
| 70-80 | 14.7 km | 29% | 21,372 |
| 80-90 | 13.2 km | 31% | 16,150 |
| 90+ | 14.2 km | 25% | 30,271 |
<!-- /table -->

Flats with under 50 years left sit less than half as far from the CBD as any group with
60 or more years left, and 93% of them are in mature estates. The pattern is
steady: going from 70 to 80 years left down to under 50, the typical distance to the CBD
falls from 14.7km to 6.2km, and the share in mature estates rises from 29% to 93%. The
oldest flats are in the oldest estates, and the oldest estates are the central ones. The
five towns with most of those 638 sales are Toa Payoh, Bukit Merah, Kallang/Whampoa,
Queenstown and Marine Parade, all of them central and mature.

The location is worth more than the lease is losing. The effect of the lease is real;
this simple grouping just can't see it.

This is my favourite result in the project, because it shows why a chart needs an
explanation beside it. The chart would have been accurate and easy to read, and it
would have led readers to exactly the wrong conclusion.

Comparing like with like, the lease effect shows up. The model uses flats in the same
town and MRT distance band, with the same floor, flat type and month. It covers all
flat types, so its simple-comparison column differs from the 4-room tables above:

<!-- table: lease_model_vs_naive -->
| Lease left (years) | Sales | Simple comparison | Like for like | 95% range |
|---|---|---|---|---|
| under 50 | 7,700 | -14.3% | -42.7% | -43.4% to -42.0% |
| 50-60 | 38,132 | -15.1% | -33.0% | -33.5% to -32.5% |
| 60-70 | 57,538 | -24.1% | -26.1% | -26.5% to -25.6% |
| 70-80 | 50,125 | -21.8% | -20.5% | -20.9% to -20.1% |
| 80-90 | 32,224 | -9.0% | -10.1% | -10.6% to -9.6% |
| 90+ | 54,355 | +0.0% | +0.0% | +0.0% to +0.0% |
<!-- /table -->

Like for like, value falls at every step as the lease runs down, to about 43% below a
flat with 90+ years left. The simple comparison put the shortest leases only 14%
below.

**What this can't tell me:** the lease separately from the age of the building.
Remaining lease and age are the same clock read in opposite directions, so each number
is the combined price of an older flat with less lease left.

---

## 5. Prices rose by more than half, almost all of it after 2020

Median price per square metre, all flat types:

<!-- table: price_by_year -->
| Year | Median price per sqm | Sales | Mature estates | Non-mature estates | How much more mature estates cost |
|---|---|---|---|---|---|
| 2017 | S$4,282 | 20,509 | S$4,851 | S$3,944 | 23.0% |
| 2018 | S$4,209 | 21,561 | S$4,749 | S$3,859 | 23.1% |
| 2019 | S$4,176 | 22,186 | S$4,592 | S$3,893 | 17.9% |
| 2020 | S$4,356 | 23,333 | S$4,623 | S$4,177 | 10.7% |
| 2021 | S$4,916 | 29,087 | S$5,188 | S$4,756 | 9.1% |
| 2022 | S$5,373 | 26,720 | S$5,672 | S$5,200 | 9.1% |
| 2023 | S$5,709 | 25,754 | S$5,923 | S$5,579 | 6.2% |
| 2024 | S$6,098 | 27,832 | S$6,388 | S$5,927 | 7.8% |
| 2025 | S$6,500 | 25,085 | S$6,864 | S$6,278 | 9.3% |
| 2026 | S$6,478 | 18,007 | S$6,920 | S$6,211 | 11.4% |
<!-- /table -->

<sub>2026 is nine months.</sub>

2017 to 2019 was flat, even slightly down. The whole 52% rise came from 2020
onwards, with the biggest single jump in 2021 (+12.8%), which was also the busiest year
for sales.

But a median can move just because *different kinds of flats* happened to sell that
year. The model tracks the price of the same kind of flat (same town, MRT distance,
lease, floor and flat type) month by month. Here is the last month of each year, with
January 2017 set to 100:

<!-- table: price_index_by_year -->
| Month | Median price (Jan 2017 = 100) | Like for like (Jan 2017 = 100) | 95% range |
|---|---|---|---|
| 2017-12 | 99.0 | 98.8 | 98.0 to 99.6 |
| 2018-12 | 97.3 | 98.1 | 97.2 to 99.0 |
| 2019-12 | 97.6 | 98.9 | 98.1 to 99.7 |
| 2020-12 | 106.6 | 105.3 | 104.4 to 106.1 |
| 2021-12 | 119.9 | 119.4 | 118.5 to 120.3 |
| 2022-12 | 130.1 | 131.5 | 130.5 to 132.5 |
| 2023-12 | 135.5 | 138.1 | 137.0 to 139.2 |
| 2024-12 | 148.2 | 153.8 | 152.6 to 155.1 |
| 2025-12 | 151.1 | 157.1 | 155.8 to 158.3 |
| 2026-09 | 149.0 | 157.5 | 155.8 to 159.3 |
<!-- /table -->

Like for like, prices rose about 57% by September 2026, and they kept rising through
2026. The median's pause in 2026 came from which flats sold, not from what flats were
worth.

The gap between mature and non-mature estates (the last column of the first table)
shrank and then partly recovered. Non-mature estates rose faster during the boom,
squeezing the mature-estate premium from 23% to 6% by 2023, before it widened again.
Because it's a ratio between the two, it's less affected by the overall rise in prices.

**What this can't tell me:** why. This period includes a pandemic, delayed BTO
completions, changing interest rates and several rounds of cooling measures, and none of
those are in this dataset.

---

## 6. An idea I tested that turned out to be wrong

My idea: as prices rose, buyers in the cheaper north and west would move to bigger
flats, while buyers in central areas would move to smaller ones.

Share of each region's sales that are large flats (5-room, Executive or
Multi-Generation):

<!-- table: large_flat_share -->
| Region | 2017 | 2021 | Latest year | Change since 2017 |
|---|---|---|---|---|
| Central | 22.9% | 23.6% | 17.6% | -5.3 pts |
| East | 37.6% | 39.2% | 35.0% | -2.6 pts |
| North | 33.5% | 36.8% | 31.5% | -2.0 pts |
| North-East | 34.3% | 36.1% | 30.5% | -3.8 pts |
| West | 34.2% | 38.3% | 33.4% | -0.8 pts |
<!-- /table -->

It didn't hold. Every region moved the same way, up until 2021 and down since, and the
biggest drop was in the central region, the opposite of what I predicted.

What the data shows instead is that large-flat sales fell *everywhere* as prices rose.
That fits with buyers across the island being stretched by affordability, though this
data can't tell "couldn't afford a bigger flat" apart from "didn't want one".

I've kept this in because I tested it. Only reporting the ideas that worked would make
the analysis look better than it really is.

---

## 7. Which blocks sell for more (or less) than expected

First, I had to check the model is actually good at pricing flats. For each year, it
learned from 80% of blocks and then priced the sales in the other 20%, which it had
never seen. I compared it with a simple guess: the median price per square metre for
that town and flat type.

<!-- table: model_validation -->
| Year | Sales it hadn't seen | Model: typical miss | Simple guess: typical miss | Model: within 10% | Simple guess: within 10% |
|---|---|---|---|---|---|
| 2017 | 4,126 | 6.5% | 7.9% | 70.1% | 59.4% |
| 2018 | 4,294 | 6.8% | 8.2% | 67.6% | 57.6% |
| 2019 | 4,213 | 7.0% | 9.0% | 66.8% | 53.7% |
| 2020 | 4,393 | 6.5% | 9.4% | 70.1% | 52.2% |
| 2021 | 5,417 | 6.2% | 9.3% | 71.1% | 53.3% |
| 2022 | 5,008 | 5.5% | 8.7% | 76.7% | 56.2% |
| 2023 | 5,012 | 5.1% | 8.3% | 78.7% | 57.8% |
| 2024 | 5,442 | 5.3% | 8.2% | 78.2% | 57.5% |
| 2025 | 5,004 | 5.6% | 8.6% | 76.7% | 55.9% |
| 2026 | 3,507 | 6.0% | 9.5% | 72.7% | 52.2% |
| All years | 46,416 | 6.0% | 8.7% | 73.2% | 55.6% |
<!-- /table -->

The model prices a typical sale in an unseen block within about 6%, against about 9%
for the simple guess, and it does better in every year. An automatic check fails
the build if that ever stops being true.

Then I compared every sale from the last 36 months with the model's expected price, and
averaged the difference for each block. A block only gets a verdict if it has at least
10 sales and its whole 95% range sits above zero or below zero:

<!-- table: fair_value_verdicts -->
| Verdict | Blocks | Sales in those blocks |
|---|---|---|
| above | 793 | 13,836 |
| below | 1,008 | 15,817 |
| in line | 886 | 12,770 |
| not enough sales | 6,782 | 34,822 |
<!-- /table -->

Blocks selling furthest above what their features would suggest:

<!-- table: fair_value_above -->
| Block | Town | Sales | Vs expected price | 95% range |
|---|---|---|---|---|
| 87 ZION RD | BUKIT MERAH | 10 | +34.8% | +31.0% to +38.8% |
| 182 JELEBU RD | BUKIT PANJANG | 12 | +31.9% | +23.0% to +41.4% |
| 13 CANTONMENT CL | BUKIT MERAH | 12 | +28.9% | +24.7% to +33.3% |
| 183 JELEBU RD | BUKIT PANJANG | 10 | +28.0% | +21.4% to +35.0% |
| 12 CANTONMENT CL | BUKIT MERAH | 14 | +27.5% | +22.7% to +32.5% |
| 11 CANTONMENT CL | BUKIT MERAH | 11 | +25.8% | +21.9% to +29.8% |
| 277D COMPASSVALE LINK | SENGKANG | 10 | +25.3% | +21.9% to +28.7% |
| 154B BEDOK STH RD | BEDOK | 11 | +25.0% | +18.9% to +31.5% |
| 238 HOUGANG AVE 1 | HOUGANG | 13 | +24.6% | +20.9% to +28.4% |
| 122 YUAN CHING RD | JURONG WEST | 12 | +24.6% | +20.0% to +29.3% |
<!-- /table -->

Furthest below:

<!-- table: fair_value_below -->
| Block | Town | Sales | Vs expected price | 95% range |
|---|---|---|---|---|
| 989A JURONG WEST ST 93 | JURONG WEST | 14 | -23.6% | -25.5% to -21.8% |
| 987A JURONG WEST ST 93 | JURONG WEST | 11 | -21.0% | -23.5% to -18.4% |
| 677C JURONG WEST ST 64 | JURONG WEST | 10 | -20.9% | -24.2% to -17.3% |
| 662 BUFFALO RD | CENTRAL AREA | 10 | -20.6% | -24.2% to -16.9% |
| 21 EUNOS CRES | GEYLANG | 14 | -19.8% | -23.2% to -16.1% |
| 22 SIN MING RD | BISHAN | 14 | -19.2% | -21.5% to -16.9% |
| 24 SIN MING RD | BISHAN | 10 | -19.0% | -21.8% to -16.0% |
| 41 SIMS DR | GEYLANG | 13 | -19.0% | -21.7% to -16.3% |
| 51 LOR 6 TOA PAYOH | TOA PAYOH | 20 | -18.6% | -21.0% to -16.1% |
| 91 LOR 3 TOA PAYOH | TOA PAYOH | 14 | -18.6% | -22.1% to -15.0% |
<!-- /table -->

**What this can't tell me:** why. A block's premium is everything about it the model
doesn't measure: the flat design (the model doesn't know about premium or DBSS designs),
the exact age of the block, the views, the upkeep, a new mall next door. "Above" means
buyers pay more than the block's measured features explain. It doesn't mean the block
is overpriced.

---

## The model, in plain English

Simple comparisons change one thing at a time while everything else shifts in the
background. The fix is a *hedonic pricing model*, which prices a flat by adding up
what each of its features is worth. It's the same idea as working out what
cheese adds to a burger's price by looking at lots of burgers with different toppings.

Mine estimates all of these at once, so each result holds the others constant:

```
log(price per sqm) ~ town + MRT distance band + lease band + floor level + flat type + month
```

- Using the log of the price means results come out as percentages ("19% more") rather
  than fixed dollar amounts, because a station adds more dollars to an expensive flat
  than to a cheap one.
- Distance and lease are grouped into bands, like 0 to 400m or 60 to 70 years, so the
  effects don't have to follow a straight line.
- Distance to the CBD is left out. Almost all of it (96.8%) is already explained by
  which town a flat is in, so the model can't separate the two.
- Sales in the same block are treated as related rather than independent, so the model
  doesn't become overconfident. The technical term is "clustered standard errors".
- The code is tested before it touches real data: it has to find effects that were
  deliberately planted in made-up data.

The code is in [pricing/hedonic.py](pricing/hedonic.py). The model turns "flats near stations sell for
7.2% more" into "being within 400m of a station is worth about 19%, for a flat in the
same town, with the same lease, floor, flat type and month". It does still assume each
effect is the same everywhere, so a station counts for the same in Bishan as in
Woodlands.

---

## What this data can't tell you

**Whether the same flat sold twice.** The dataset has no ID for individual flats, so
there's no way to see that one flat sold in 2018 and again in 2024. Comparing a flat
with itself would be the best way to measure price changes, but this data doesn't allow
it.

**The future.** I don't make forecasts. Nine years of history isn't enough, and HDB
prices depend heavily on government policy (cooling measures, BTO supply, grants), which
are decisions rather than patterns. Nothing in the 2017 to 2020 data predicted the jump
in 2021.

**Other kinds of housing.** This covers HDB resale flats only: no new BTO flats, no
rentals and no private property, so the results don't carry over to private housing.

**Walking distance.** Every block address was matched to a map location (all 9,744,
with none missing), but distances are straight lines. A block 400m from a station across
an expressway is not a 400m walk.

**Lease details.** The remaining lease arrives in two different formats in the raw data.
Both are converted to months, and an automatic check stops the pipeline if any value
looks impossible.

---

*The tables on this page are generated from the published numbers in `published/`,
dated at the top. To rebuild everything from scratch, see
[Running it](docs/ENGINEERING.md#running-it).*

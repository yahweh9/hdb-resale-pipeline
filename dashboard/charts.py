"""Chart builders for the dashboard, fed by published marts or dashboard/explore.py alike.

Every builder takes a tidy frame with the marts' column names, so the Findings page and
the Explore page draw a figure with the same function -- the only difference between
them is where the numbers came from.
"""

import altair as alt
import pandas as pd

FLAT_TYPE_ORDER = ["1 ROOM", "2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM",
                   "EXECUTIVE", "MULTI GENERATION"]
FLOOR_ORDER = ["Low (1-4)", "Mid (5-9)", "High (10-19)", "Ultra-High (20+)"]

# Categorical slots, dark-mode steps, in fixed order. Assigned by slot and never
# cycled, so a flat type keeps its colour when a filter changes the series count.
# Validated against surface #1a1a19: worst adjacent CVD dE 8.4, normal-vision 19.3,
# all seven >= 3:1 contrast.
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9"]

SURFACE = "#1a1a19"
PRIMARY = SERIES[0]
INK = "#ffffff"
INK_MUTED = "#c3c2b7"
GRID = "#383835"


def style(chart):
    """Recessive chrome, ink-coloured text, no chart-junk borders.

    Text never wears a series colour: the mark carries identity, the label stays in ink.
    Grid lines sit close to the surface so the data is the only thing with contrast.
    """
    return (
        chart.configure_view(strokeWidth=0, fill=SURFACE)
        .configure_axis(
            labelColor=INK_MUTED, titleColor=INK_MUTED,
            labelFontSize=11, titleFontSize=11, titleFontWeight="normal",
            gridColor=GRID, gridOpacity=0.5, domainColor=GRID, tickColor=GRID,
        )
        .configure_legend(
            labelColor=INK_MUTED, titleColor=INK_MUTED,
            labelFontSize=11, titleFontSize=11, titleFontWeight="normal",
            symbolStrokeWidth=3,
        )
        .configure_axisY(domain=False, ticks=False)
    )


def _maturity(frame):
    return frame.assign(estate=frame["is_mature_estate"].map({True: "Mature", False: "Non-mature"}))


def price_trend(trend):
    """Median price by month, split by flat type. Each type keeps its OWN colour slot:
    the colour follows the flat type, not its position in whatever survived a filter."""
    present = [t for t in FLAT_TYPE_ORDER if t in set(trend["flat_type"])]
    colors = [SERIES[FLAT_TYPE_ORDER.index(t)] for t in present]
    return style(
        alt.Chart(trend)
        .mark_line(strokeWidth=2, interpolate="monotone")
        .encode(
            x=alt.X("transaction_month:T", title=None),
            y=alt.Y("median_price_psm:Q", title="Median price per sqm (SGD)",
                    axis=alt.Axis(format="~s"), scale=alt.Scale(zero=False)),
            color=alt.Color("flat_type:N", title="Flat type", sort=present,
                            scale=alt.Scale(domain=present, range=colors)),
            tooltip=[
                alt.Tooltip("transaction_month:T", title="Month", format="%b %Y"),
                alt.Tooltip("flat_type:N", title="Type"),
                alt.Tooltip("median_price_psm:Q", title="Median psm", format="$,.0f"),
                alt.Tooltip("sales:Q", title="Sales", format=","),
            ],
        )
        .properties(height=320)
    )


def town_ranking(ranked):
    """Median price per sqm by town. Colour carries estate maturity, a second attribute
    the bar length cannot show, and is not re-assigned when a filter drops towns."""
    return style(
        alt.Chart(_maturity(ranked))
        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4, height={"band": 0.8})
        .encode(
            x=alt.X("median_price_psm:Q", title="Median price per sqm (SGD)"),
            y=alt.Y("town:N", sort="-x", title=None),
            color=alt.Color("estate:N", title="Estate",
                            scale=alt.Scale(domain=["Mature", "Non-mature"], range=SERIES[:2])),
            tooltip=[
                alt.Tooltip("town:N", title="Town"),
                alt.Tooltip("estate:N", title="Estate"),
                alt.Tooltip("median_price_psm:Q", title="Median psm", format="$,.0f"),
                alt.Tooltip("sales:Q", title="Sales", format=","),
            ],
        )
        .properties(height=560)
    )


def town_effect(towns):
    """The model's town premium over the average town, with its 95% interval.

    Unlike the median ranking, this holds the housing stock constant, so a town is not
    credited with the lease, storey or station access of the flats that happen to sell.
    """
    towns = _maturity(towns)
    base = alt.Chart(towns).encode(
        y=alt.Y("town:N", sort=alt.EncodingSortField("model_effect_pct", order="descending"), title=None),
    )
    bars = base.mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4, height={"band": 0.8}).encode(
        x=alt.X("model_effect_pct:Q", title="vs the average town, like for like (%)"),
        color=alt.Color("estate:N", title="Estate",
                        scale=alt.Scale(domain=["Mature", "Non-mature"], range=SERIES[:2])),
        tooltip=[
            alt.Tooltip("town:N", title="Town"),
            alt.Tooltip("model_effect_pct:Q", title="Effect (%)", format="+.1f"),
            alt.Tooltip("model_ci_low_pct:Q", title="95% low", format="+.1f"),
            alt.Tooltip("model_ci_high_pct:Q", title="95% high", format="+.1f"),
            alt.Tooltip("median_price_psm:Q", title="Median psm", format="$,.0f"),
        ],
    )
    whiskers = base.mark_rule(color=INK_MUTED, strokeWidth=1).encode(
        x="model_ci_low_pct:Q", x2="model_ci_high_pct:Q",
    )
    return style((bars + whiskers).properties(height=560))


def cbd_gradient(gradient):
    """Median price per sqm by 1km ring from the CBD. Per kilometre, because the shape is
    the finding: steep decay to about 5km, then a plateau that oscillates. One series, so
    no legend; points drawn because each is a real aggregate, not an interpolation."""
    base = alt.Chart(gradient).encode(
        x=alt.X("km_from_cbd:Q", title="Kilometres from CBD", axis=alt.Axis(tickMinStep=2)),
        y=alt.Y("median_price_psm:Q", title="Median price per sqm (SGD)", scale=alt.Scale(zero=False)),
        tooltip=[
            alt.Tooltip("km_from_cbd:Q", title="Distance (km)"),
            alt.Tooltip("median_price_psm:Q", title="Median psm", format="$,.0f"),
            alt.Tooltip("sales:Q", title="Sales", format=","),
        ],
    )
    return style(
        (base.mark_line(strokeWidth=2, color=PRIMARY, interpolate="monotone")
         + base.mark_point(size=64, filled=True, color=PRIMARY, stroke=SURFACE, strokeWidth=2))
        .properties(height=300)
    )


def mrt_premium(bands):
    """Median price per sqm by distance band to the nearest station. One hue, not a ramp:
    the x-axis already carries the order and the bar length the value."""
    order = bands.sort_values("band_order")["mrt_band"].tolist()
    return style(
        alt.Chart(bands)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color=PRIMARY, width={"band": 0.75})
        .encode(
            x=alt.X("mrt_band:N", title="Distance to nearest MRT/LRT", sort=order,
                    axis=alt.Axis(labelAngle=0)),
            y=alt.Y("median_price_psm:Q", title="Median price per sqm (SGD)", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("mrt_band:N", title="Distance"),
                alt.Tooltip("median_price_psm:Q", title="Median psm", format="$,.0f"),
                alt.Tooltip("premium_vs_farthest_pct:Q", title="vs over 1.2km (%)", format="+.1f"),
                alt.Tooltip("sales:Q", title="Sales", format=","),
            ],
        )
        .properties(height=280)
    )


def storey_multiplier(storey):
    """Each tier against Low floors in the same town, flat type and year. Four marks, so
    every one is labelled directly."""
    storey = storey.dropna(subset=["controlled_multiplier"])
    bars = alt.Chart(storey).mark_bar(
        cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color=PRIMARY, width={"band": 0.7}
    ).encode(
        x=alt.X("floor_tier:N", title=None, sort=FLOOR_ORDER, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("controlled_multiplier:Q", title="x the price of a low floor", scale=alt.Scale(zero=False)),
        tooltip=[
            alt.Tooltip("floor_tier:N", title="Tier"),
            alt.Tooltip("controlled_multiplier:Q", title="Multiplier", format=".3f"),
            alt.Tooltip("comparison_cells:Q", title="Comparisons"),
        ],
    )
    labels = bars.mark_text(dy=-8, color=INK, fontSize=11).encode(
        text=alt.Text("controlled_multiplier:Q", format=".2f")
    )
    return style((bars + labels).properties(height=280))


def volume(counts):
    """Transactions per month. Context for the price charts, not a headline: a muted fill
    at half their height, because volume explains confidence in the medians."""
    return style(
        alt.Chart(counts)
        .mark_area(color=PRIMARY, opacity=0.35, line={"color": PRIMARY, "strokeWidth": 2},
                   interpolate="monotone")
        .encode(
            x=alt.X("transaction_month:T", title=None),
            y=alt.Y("sales:Q", title="Transactions"),
            tooltip=[
                alt.Tooltip("transaction_month:T", title="Month", format="%b %Y"),
                alt.Tooltip("sales:Q", title="Sales", format=","),
            ],
        )
        .properties(height=180)
    )


def price_index(index):
    """Quality-adjusted price index against the median. Two series in fixed slots; the
    model's line carries its 95% interval as a band. Where the lines part, the mix of
    flats sold moved, not their prices."""
    index = index.assign(month=pd.to_datetime(index["month"]))
    domain = ["Quality-adjusted (model)", "Median price per sqm"]
    lines = index.melt(
        id_vars=["month"], value_vars=["hedonic_index", "naive_index"],
        var_name="series", value_name="index",
    ).replace({"series": {"hedonic_index": domain[0], "naive_index": domain[1]}})

    band = alt.Chart(index).mark_area(color=PRIMARY, opacity=0.25).encode(
        x=alt.X("month:T", title=None),
        y=alt.Y("hedonic_ci_low:Q", title="Index, Jan 2017 = 100", scale=alt.Scale(zero=False)),
        y2="hedonic_ci_high:Q",
    )
    line = alt.Chart(lines).mark_line(strokeWidth=2, interpolate="monotone").encode(
        x="month:T",
        y="index:Q",
        color=alt.Color("series:N", title=None, sort=domain,
                        scale=alt.Scale(domain=domain, range=SERIES[:2]),
                        legend=alt.Legend(orient="top")),
        tooltip=[
            alt.Tooltip("month:T", title="Month", format="%b %Y"),
            alt.Tooltip("series:N", title="Index"),
            alt.Tooltip("index:Q", title="Value", format=".1f"),
        ],
    )
    return style((band + line).properties(height=300))


def effects_over_time(effects):
    """The station premium and the short-lease discount, refitted each year, with 95%
    intervals as rules -- the two findings the model overturned, so their stability matters."""
    picks = {"0-400m": "Within 400m of MRT (vs over 1.2km)",
             "under 50": "Under 50 years lease (vs 90+)"}
    rows = effects[effects["level"].isin(picks)].assign(series=lambda d: d["level"].map(picks))
    domain = list(picks.values())
    color = alt.Color("series:N", title=None, sort=domain,
                      scale=alt.Scale(domain=domain, range=SERIES[:2]),
                      legend=alt.Legend(orient="top", labelLimit=320))
    base = alt.Chart(rows).encode(
        x=alt.X("calendar_year:O", title=None, axis=alt.Axis(labelAngle=0)),
        color=color,
    )
    rules = base.mark_rule(strokeWidth=2, opacity=0.5).encode(
        y=alt.Y("ci_low_pct:Q", title="Effect on price per sqm (%)"), y2="ci_high_pct:Q",
    )
    points = base.mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=48, filled=True)).encode(
        y="effect_pct:Q",
        tooltip=[
            alt.Tooltip("calendar_year:O", title="Year"),
            alt.Tooltip("series:N", title="Effect"),
            alt.Tooltip("effect_pct:Q", title="Effect (%)", format="+.1f"),
            alt.Tooltip("ci_low_pct:Q", title="95% low", format="+.1f"),
            alt.Tooltip("ci_high_pct:Q", title="95% high", format="+.1f"),
        ],
    )
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=GRID, strokeWidth=1).encode(y="y:Q")
    return style((zero + rules + points).properties(height=280))

"""Chart builders for the dashboard, fed by published marts or dashboard/explore.py alike.

Every builder takes a tidy frame with the marts' column names, so the Findings page and
the Explore page draw a figure with the same function -- the only difference between
them is where the numbers came from.

Colours were checked with the dataviz palette validator against the white card surface:
the two-series pair clears every categorical check, and the flat-type ramp is a five-step
selection of the blue ramp whose neighbours stay far enough apart to read.
"""

import altair as alt
import pandas as pd

FLAT_TYPE_ORDER = ["1 ROOM", "2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM",
                   "EXECUTIVE", "MULTI GENERATION"]
FLOOR_ORDER = ["Low (1-4)", "Mid (5-9)", "High (10-19)", "Ultra-High (20+)"]

SURFACE = "#ffffff"
INK = "#18181b"
INK_2 = "#52525b"
INK_MUTED = "#71717a"
GRID = "#efeff1"
BASELINE = "#d4d4d8"

# Two categorical slots, in fixed order: blue then orange. Worst CVD dE 24.7, normal
# vision 33.6, both >= 3:1 on white.
SERIES = ["#2a78d6", "#eb6834"]
PRIMARY = SERIES[0]

# Flat types are ordered by size, so they take one hue, light to dark. Five steps is the
# most the blue ramp can hold with every neighbour distinct; 1-room and multi-generation
# flats sell about once a month, too rarely for a monthly median, so they are not drawn.
FLAT_TYPE_RAMP = {
    "2 ROOM": "#86b6ef",
    "3 ROOM": "#5598e7",
    "4 ROOM": "#2a78d6",
    "5 ROOM": "#1c5cab",
    "EXECUTIVE": "#104281",
}

SANS = "Geist, ui-sans-serif, system-ui, sans-serif"
MONO = "Geist Mono, ui-monospace, monospace"
BAR = 24  # px: bars never fill their slot, and never pass the 24px cap


def style(chart):
    """Recessive chrome: hairline grid, muted mono tick labels, ink-coloured text.

    Text never wears a series colour: the mark carries identity, the label stays in ink.
    """
    return (
        chart.configure(font=SANS, background=SURFACE)
        .configure_view(strokeWidth=0, fill=SURFACE)
        .configure_axis(
            labelFont=MONO, labelColor=INK_MUTED, labelFontSize=11, labelPadding=6,
            titleFont=SANS, titleColor=INK_2, titleFontSize=12, titleFontWeight=500, titlePadding=10,
            gridColor=GRID, gridWidth=1, domainColor=BASELINE, tickColor=BASELINE, tickSize=4,
        )
        .configure_axisY(domain=False, ticks=False)
        .configure_legend(
            orient="top", direction="horizontal", labelFont=SANS, labelColor=INK_2, labelFontSize=12,
            titleFont=SANS, titleColor=INK_MUTED, titleFontSize=11, titleFontWeight=500,
            symbolStrokeWidth=2, symbolSize=110, labelLimit=320,
        )
        .configure_text(font=SANS)
    )


def _category_axis(**kwargs):
    """Axis for words rather than numbers: sans, not mono."""
    return alt.Axis(labelFont=SANS, labelColor=INK_2, labelFontSize=12, **kwargs)


def _year_axis():
    return alt.Axis(format="%Y", tickCount={"interval": "year", "step": 2})


def _maturity(frame):
    return frame.assign(estate=frame["is_mature_estate"].map({True: "Mature", False: "Non-mature"}))


def _estate_color():
    return alt.Color("estate:N", title="Estate",
                     scale=alt.Scale(domain=["Mature", "Non-mature"], range=SERIES))


def _crosshair(data, field, x, y, tooltip, color=None):
    """Hover layer for line and area charts: a hairline rule at the nearest x, ringed
    points on every series there, and a tooltip. The invisible selectors are the hit
    target, so the reader never has to land on a 2px line."""
    nearest = alt.selection_point(nearest=True, on="pointerover", fields=[field], empty=False,
                                  clear="pointerout")
    selectors = alt.Chart(data).mark_point(size=600, opacity=0).encode(x=x, tooltip=tooltip).add_params(nearest)
    rule = alt.Chart(data).mark_rule(color=BASELINE, strokeWidth=1).encode(x=x).transform_filter(nearest)
    encoding = {"x": x, "y": y, "tooltip": tooltip,
                "opacity": alt.condition(nearest, alt.value(1), alt.value(0))}
    if color is not None:
        encoding["color"] = color
    points = alt.Chart(data).mark_point(size=70, filled=True, stroke=SURFACE, strokeWidth=2).encode(**encoding)
    return [selectors, rule, points]


def _end_labels(frame, x, x_field, y_field, series, fmt):
    """The latest value beside each line's end, in ink: the legend names the series, the
    label gives the number the reader came for."""
    last = frame.sort_values(x_field).groupby(series, as_index=False).tail(1)
    return alt.Chart(last).mark_text(align="left", dx=10, color=INK_2, fontSize=12, fontWeight=500).encode(
        x=x, y=f"{y_field}:Q", text=alt.Text(f"{y_field}:Q", format=fmt),
    )


def price_trend(trend, height=320):
    """Median price by month, one line per flat type, lightest for the smallest. Each type
    keeps its own shade: the colour follows the flat type, not what survived a filter."""
    present = [t for t in FLAT_TYPE_RAMP if t in set(trend["flat_type"])]
    data = trend[trend["flat_type"].isin(present)]
    color = alt.Color("flat_type:N", title="Flat type", sort=present,
                      scale=alt.Scale(domain=present, range=[FLAT_TYPE_RAMP[t] for t in present]))
    x = alt.X("transaction_month:T", title=None, axis=_year_axis())
    y = alt.Y("median_price_psm:Q", title="Median price per sqm (S$)",
              axis=alt.Axis(format=",.0f"), scale=alt.Scale(zero=False))
    tooltip = [
        alt.Tooltip("transaction_month:T", title="Month", format="%b %Y"),
        alt.Tooltip("flat_type:N", title="Flat type"),
        alt.Tooltip("median_price_psm:Q", title="Median per sqm", format="$,.0f"),
        alt.Tooltip("sales:Q", title="Sales", format=","),
    ]
    line = alt.Chart(data).mark_line(strokeWidth=2, interpolate="monotone", strokeCap="round").encode(
        x=x, y=y, color=color)
    return style(alt.layer(line, *_crosshair(data, "transaction_month", x, y, tooltip, color))
                 .properties(height=height))


def town_ranking(ranked, height=None):
    """Median price per sqm by town. Colour carries estate maturity, a second attribute
    the bar length cannot show, and is not re-assigned when a filter drops towns."""
    height = height or max(240, 23 * len(ranked))
    return style(
        alt.Chart(_maturity(ranked))
        .mark_bar(cornerRadiusEnd=4, size=13)
        .encode(
            x=alt.X("median_price_psm:Q", title="Median price per sqm (S$)", axis=alt.Axis(format=",.0f")),
            y=alt.Y("town:N", sort="-x", title=None, axis=_category_axis()),
            color=_estate_color(),
            tooltip=[
                alt.Tooltip("town:N", title="Town"),
                alt.Tooltip("estate:N", title="Estate"),
                alt.Tooltip("median_price_psm:Q", title="Median per sqm", format="$,.0f"),
                alt.Tooltip("sales:Q", title="Sales", format=","),
            ],
        )
        .properties(height=height)
    )


def town_effect(towns, height=None):
    """The model's town premium over the average town, with its 95% range.

    Unlike the median ranking, this holds the housing stock constant, so a town is not
    credited with the lease, storey or station access of the flats that happen to sell.
    """
    towns = _maturity(towns)
    height = height or max(240, 23 * len(towns))
    y = alt.Y("town:N", sort=alt.EncodingSortField("model_effect_pct", order="descending"),
              title=None, axis=_category_axis())
    bars = alt.Chart(towns).mark_bar(cornerRadiusEnd=4, size=13).encode(
        x=alt.X("model_effect_pct:Q", title="Vs the average town (%)"),
        y=y,
        color=_estate_color(),
        tooltip=[
            alt.Tooltip("town:N", title="Town"),
            alt.Tooltip("model_effect_pct:Q", title="Effect (%)", format="+.1f"),
            alt.Tooltip("model_ci_low_pct:Q", title="95% range from", format="+.1f"),
            alt.Tooltip("model_ci_high_pct:Q", title="95% range to", format="+.1f"),
            alt.Tooltip("median_price_psm:Q", title="Median per sqm", format="$,.0f"),
        ],
    )
    whiskers = alt.Chart(towns).mark_rule(color=INK_MUTED, strokeWidth=1).encode(
        x="model_ci_low_pct:Q", x2="model_ci_high_pct:Q", y=y,
    )
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=BASELINE, strokeWidth=1).encode(x="x:Q")
    return style(alt.layer(zero, bars, whiskers).properties(height=height))


def cbd_gradient(gradient, height=250):
    """Median price per sqm by 1km ring from the CBD. Per kilometre, because the shape is
    the finding: steep decay to about 5km, then a plateau. One series, so no legend."""
    x = alt.X("km_from_cbd:Q", title="Kilometres from the CBD", axis=alt.Axis(tickMinStep=2))
    y = alt.Y("median_price_psm:Q", title="Median price per sqm (S$)",
              axis=alt.Axis(format=",.0f"), scale=alt.Scale(zero=False))
    tooltip = [
        alt.Tooltip("km_from_cbd:Q", title="Distance (km)"),
        alt.Tooltip("median_price_psm:Q", title="Median per sqm", format="$,.0f"),
        alt.Tooltip("sales:Q", title="Sales", format=","),
    ]
    line = alt.Chart(gradient).mark_line(strokeWidth=2, color=PRIMARY, interpolate="monotone").encode(x=x, y=y)
    dots = alt.Chart(gradient).mark_point(size=64, filled=True, color=PRIMARY, stroke=SURFACE,
                                          strokeWidth=2, opacity=1).encode(x=x, y=y)
    return style(alt.layer(line, dots, *_crosshair(gradient, "km_from_cbd", x, y, tooltip))
                 .properties(height=height))


def mrt_premium(bands, height=230):
    """Median price per sqm by distance band to the nearest station, bars from zero. The
    label on each cap is the band against flats over 1.2km away -- the number the chart
    is about."""
    order = bands.sort_values("band_order")["mrt_band"].tolist()
    base = alt.Chart(bands).encode(
        x=alt.X("mrt_band:N", title="Distance to the nearest MRT or LRT station", sort=order,
                axis=_category_axis(labelAngle=0)),
        y=alt.Y("median_price_psm:Q", title="Median price per sqm (S$)", axis=alt.Axis(format=",.0f")),
    )
    bars = base.mark_bar(cornerRadiusEnd=4, size=BAR, color=PRIMARY).encode(
        tooltip=[
            alt.Tooltip("mrt_band:N", title="Distance"),
            alt.Tooltip("median_price_psm:Q", title="Median per sqm", format="$,.0f"),
            alt.Tooltip("premium_vs_farthest_pct:Q", title="Vs over 1.2km (%)", format="+.1f"),
            alt.Tooltip("sales:Q", title="Sales", format=","),
        ],
    )
    labels = base.mark_text(dy=-9, color=INK_2, fontSize=12, fontWeight=500).transform_calculate(
        label="datum.band_order == 4 ? 'reference' : format(datum.premium_vs_farthest_pct, '+.1f') + '%'"
    ).encode(text="label:N")
    return style(alt.layer(bars, labels).properties(height=height))


def storey_multiplier(storey, height=280):
    """Each floor level against low floors in the same town, flat type and year, bars
    from zero. Four marks, so every one is labelled."""
    storey = storey.dropna(subset=["controlled_multiplier"])
    base = alt.Chart(storey).encode(
        x=alt.X("floor_tier:N", title=None, sort=FLOOR_ORDER, axis=_category_axis(
            labelAngle=0, labelExpr="[split(datum.label, ' (')[0], '(' + split(datum.label, ' (')[1]]",
            labelLineHeight=15)),
        y=alt.Y("controlled_multiplier:Q", title="Times the price of a low floor"),
    )
    bars = base.mark_bar(cornerRadiusEnd=4, size=BAR, color=PRIMARY).encode(
        tooltip=[
            alt.Tooltip("floor_tier:N", title="Floor level"),
            alt.Tooltip("controlled_multiplier:Q", title="Times a low floor", format=".3f"),
            alt.Tooltip("comparison_cells:Q", title="Groups compared", format=","),
        ],
    )
    labels = base.mark_text(dy=-9, color=INK_2, fontSize=12, fontWeight=500).encode(
        text=alt.Text("controlled_multiplier:Q", format=".2f"),
    )
    return style(alt.layer(bars, labels).properties(height=height))


def volume(counts, height=320):
    """Sales per month: how many sales each monthly median rests on. A 10% wash under a
    2px line, because it is context for the price charts, not a headline."""
    x = alt.X("transaction_month:T", title=None, axis=_year_axis())
    y = alt.Y("sales:Q", title="Sales per month", axis=alt.Axis(format=",.0f"))
    tooltip = [
        alt.Tooltip("transaction_month:T", title="Month", format="%b %Y"),
        alt.Tooltip("sales:Q", title="Sales", format=","),
    ]
    area = alt.Chart(counts).mark_area(color=PRIMARY, opacity=0.1, interpolate="monotone").encode(x=x, y=y)
    line = alt.Chart(counts).mark_line(color=PRIMARY, strokeWidth=2, interpolate="monotone").encode(x=x, y=y)
    return style(alt.layer(area, line, *_crosshair(counts, "transaction_month", x, y, tooltip))
                 .properties(height=height))


def price_index(index, height=300):
    """Like-for-like price index against the median. Two series in fixed slots; the
    model's line carries its 95% range as a wash. Where the lines part, the mix of flats
    sold moved, not their prices."""
    index = index.assign(month=pd.to_datetime(index["month"]))
    domain = ["Like for like (model)", "Median price per sqm"]
    lines = index.melt(
        id_vars=["month"], value_vars=["hedonic_index", "naive_index"],
        var_name="series", value_name="index",
    ).replace({"series": {"hedonic_index": domain[0], "naive_index": domain[1]}})
    color = alt.Color("series:N", title=None, sort=domain, scale=alt.Scale(domain=domain, range=SERIES))
    x = alt.X("month:T", title=None, axis=_year_axis())
    y = alt.Y("index:Q", title="Index, Jan 2017 = 100", scale=alt.Scale(zero=False))
    tooltip = [
        alt.Tooltip("month:T", title="Month", format="%b %Y"),
        alt.Tooltip("series:N", title="Index"),
        alt.Tooltip("index:Q", title="Value", format=".1f"),
    ]
    band = alt.Chart(index).mark_area(color=PRIMARY, opacity=0.12).encode(
        x=x, y=alt.Y("hedonic_ci_low:Q", title="Index, Jan 2017 = 100", scale=alt.Scale(zero=False)),
        y2="hedonic_ci_high:Q",
    )
    line = alt.Chart(lines).mark_line(strokeWidth=2, interpolate="monotone").encode(x=x, y=y, color=color)
    ends = _end_labels(lines, x, "month", "index", "series", ".1f")
    return style(
        alt.layer(band, line, ends, *_crosshair(lines, "month", x, y, tooltip, color))
        .properties(height=height, padding={"right": 48})
    )


def effects_over_time(effects, height=300):
    """The station premium and the short-lease discount, refitted each year, with 95%
    ranges as bars -- the two findings the model overturned, so their stability matters."""
    picks = {"0-400m": "Within 400m of MRT (vs over 1.2km)",
             "under 50": "Under 50 years of lease (vs 90+)"}
    rows = effects[effects["level"].isin(picks)].assign(series=lambda d: d["level"].map(picks))
    domain = list(picks.values())
    color = alt.Color("series:N", title=None, sort=domain, scale=alt.Scale(domain=domain, range=SERIES),
                      legend=alt.Legend(direction="vertical"))
    x = alt.X("calendar_year:O", title=None,
              axis=alt.Axis(labelAngle=0, labelExpr="datum.value % 2 == 1 ? datum.label : ''"))
    y = alt.Y("effect_pct:Q", title="Effect on price per sqm (%)")
    tooltip = [
        alt.Tooltip("calendar_year:O", title="Year"),
        alt.Tooltip("series:N", title="Effect"),
        alt.Tooltip("effect_pct:Q", title="Effect (%)", format="+.1f"),
        alt.Tooltip("ci_low_pct:Q", title="95% range from", format="+.1f"),
        alt.Tooltip("ci_high_pct:Q", title="95% range to", format="+.1f"),
    ]
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=BASELINE, strokeWidth=1).encode(y="y:Q")
    # The ranges carry no legend of their own, so the legend swatches take the solid dots.
    range_color = alt.Color("series:N", sort=domain, scale=alt.Scale(domain=domain, range=SERIES), legend=None)
    ranges = alt.Chart(rows).mark_rule(strokeWidth=2, opacity=0.35).encode(
        x=x, y=alt.Y("ci_low_pct:Q", title="Effect on price per sqm (%)"), y2="ci_high_pct:Q", color=range_color,
    )
    line = alt.Chart(rows).mark_line(strokeWidth=2).encode(x=x, y=y, color=color)
    dots = alt.Chart(rows).mark_point(size=64, filled=True, stroke=SURFACE, strokeWidth=2, opacity=1).encode(
        x=x, y=y, color=color, tooltip=tooltip)
    ends = _end_labels(rows, x, "calendar_year", "effect_pct", "series", "+.1f")
    return style(alt.layer(zero, ranges, line, dots, ends).properties(height=height, padding={"right": 52}))

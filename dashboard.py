"""Streamlit dashboard over the published edition.

Reads published/ -- never the warehouse, never bronze, never the API. The edition is
what publish_edition.py exported from the gold star and the marts, stamped with its
data cut, so this page shows exactly the numbers FINDINGS.md quotes and runs on a host
that has never seen the pipeline.

Two kinds of figure live here. Published figures come straight from a mart and ignore
the sidebar: they are the numbers the findings stand behind. Exploratory figures are
recomputed from every sale under whatever filters are chosen.

    streamlit run dashboard.py
"""

import os

import altair as alt
import pandas as pd
import streamlit as st

import edition

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

    Text never wears a series colour: the mark carries identity, the label stays
    in ink. Grid lines sit close to the surface so the data is the only thing
    with contrast.
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


@st.cache_data(show_spinner="Reading the edition...")
def load_sales():
    """Every sale, once. 240k rows is small enough to filter in memory."""
    return edition.read_sales()


@st.cache_data
def load_published():
    """The stamp and the published marts. Small, and never filtered."""
    return (
        edition.read_stamp(),
        edition.read_table("mart_mrt_premium_by_band"),
        edition.read_table("mart_price_index"),
        edition.read_table("mart_effects_by_year"),
        edition.read_table("mart_block_fair_value"),
    )


def price_index(index):
    """Quality-adjusted price index against the median, from the published mart.

    Two series in fixed slots, so a colour always means the same index. The model's line
    carries its 95% interval as a band; the median has no interval to show. Where the
    lines part, the mix of flats sold moved, not their prices.
    """
    index = index.assign(month=pd.to_datetime(index["month"]))
    lines = index.melt(
        id_vars=["month"], value_vars=["hedonic_index", "naive_index"],
        var_name="series", value_name="index",
    ).replace({"series": {"hedonic_index": "Quality-adjusted (model)",
                          "naive_index": "Median price per sqm"}})
    domain = ["Quality-adjusted (model)", "Median price per sqm"]

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
    """Two published effects, refitted each year: the station premium and the short-lease
    discount, each with its 95% interval as a rule.

    Chosen because they are the two findings the model overturned, so how stable they are
    matters. Fixed colour slots, labelled series, zero line for reference.
    """
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


def kpi_row(df):
    cols = st.columns(4)
    cols[0].metric("Transactions", f"{len(df):,}")
    cols[1].metric("Median price", f"S${df['resale_price'].median():,.0f}")
    cols[2].metric("Median price / sqm", f"S${df['price_psm'].median():,.0f}")
    cols[3].metric("Months covered", f"{df['transaction_month'].nunique():,}")


def price_trend(df):
    """Median price by month, split by flat type. Median, not mean: the tail is long.

    Months with fewer than 10 sales of a type are dropped. 1 ROOM has 88 sales in the
    whole dataset, so its monthly median is a single transaction bouncing around -- a
    line that reads as volatility when it is really just absence.
    """
    trend = (
        df.groupby(["transaction_month", "flat_type"], as_index=False)
        .agg(resale_price=("resale_price", "median"), n=("resale_price", "size"))
    )
    trend = trend[trend["n"] >= 10]

    # Legend lists only what is plotted, but each type keeps its OWN slot: the colour
    # follows the flat type, not its position in whatever survived the filter. Drop a
    # type and the others do not repaint.
    present = [t for t in FLAT_TYPE_ORDER if t in set(trend["flat_type"])]
    colors = [SERIES[FLAT_TYPE_ORDER.index(t)] for t in present]

    return style(
        alt.Chart(trend)
        .mark_line(strokeWidth=2, interpolate="monotone")
        .encode(
            x=alt.X("transaction_month:T", title=None),
            y=alt.Y("resale_price:Q", title="Median resale price (SGD)",
                    axis=alt.Axis(format="~s"), scale=alt.Scale(zero=False)),
            color=alt.Color(
                "flat_type:N", title="Flat type", sort=present,
                scale=alt.Scale(domain=present, range=colors),
            ),
            tooltip=[
                alt.Tooltip("transaction_month:T", title="Month", format="%b %Y"),
                alt.Tooltip("flat_type:N", title="Type"),
                alt.Tooltip("resale_price:Q", title="Median", format="$,.0f"),
                alt.Tooltip("n:Q", title="Sales", format=","),
            ],
        )
        .properties(height=320)
    )


def town_ranking(df):
    """Median price per sqm by town. Normalising by area is what makes towns comparable.

    Colour carries estate maturity, a second attribute the bar length cannot show.
    It is not redundant with the ranking, and it is not re-assigned when a filter
    changes which towns survive.
    """
    ranked = (
        df.groupby(["town", "is_mature_estate"], as_index=False)["price_psm"]
        .median()
        .sort_values("price_psm", ascending=False)
    )
    ranked["estate"] = ranked["is_mature_estate"].map({True: "Mature", False: "Non-mature"})
    return style(
        alt.Chart(ranked)
        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4, height={"band": 0.8})
        .encode(
            x=alt.X("price_psm:Q", title="Median price per sqm (SGD)"),
            y=alt.Y("town:N", sort="-x", title=None),
            color=alt.Color(
                "estate:N", title="Estate",
                scale=alt.Scale(domain=["Mature", "Non-mature"], range=SERIES[:2]),
            ),
            tooltip=[
                alt.Tooltip("town:N", title="Town"),
                alt.Tooltip("estate:N", title="Estate"),
                alt.Tooltip("price_psm:Q", title="Median psm", format="$,.0f"),
            ],
        )
        .properties(height=560)
    )


def cbd_gradient(df):
    """Median price per sqm by 1km ring from the CBD.

    Per kilometre rather than in wide bands, because the shape IS the finding: steep
    decay to about 5km, then a plateau that oscillates instead of falling. Wide bands
    smooth that away and the point disappears.

    One series, so no legend -- the title names it. Points are drawn because each is a
    real aggregate, not an interpolation.
    """
    rings = df.assign(km=df["dist_to_cbd_km"].astype(int))
    summary = rings.groupby("km", as_index=False).agg(
        price_psm=("price_psm", "median"), n=("price_psm", "size")
    )
    summary = summary[summary["n"] >= 200]
    base = alt.Chart(summary).encode(
        x=alt.X("km:Q", title="Kilometres from CBD", axis=alt.Axis(tickMinStep=2)),
        y=alt.Y("price_psm:Q", title="Median price per sqm (SGD)",
                scale=alt.Scale(zero=False)),
        tooltip=[
            alt.Tooltip("km:Q", title="Distance (km)"),
            alt.Tooltip("price_psm:Q", title="Median psm", format="$,.0f"),
            alt.Tooltip("n:Q", title="Sales", format=","),
        ],
    )
    return style(
        (base.mark_line(strokeWidth=2, color=PRIMARY, interpolate="monotone")
         + base.mark_point(size=64, filled=True, color=PRIMARY,
                           stroke=SURFACE, strokeWidth=2))
        .properties(height=300)
    )


def mrt_premium(bands):
    """Median price per sqm by distance to the nearest station, from the published mart.

    A published figure: it charts mart_mrt_premium_by_band as-is and ignores the
    sidebar, so it always matches the table in FINDINGS.md. The bands are defined once,
    in dim_block; this function never re-derives them.

    Banded rather than continuous: the row-level relationship is noisy, and 400m is
    the threshold HDB and URA use for walkability, so it is the cut people already
    reason in.

    One hue, not a ramp. The x-axis already carries the order and the bar length the
    value; colouring the bands by their own position would encode the same thing a
    third time.
    """
    order = bands.sort_values("band_order")["mrt_band"].tolist()
    return style(
        alt.Chart(bands)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4,
                  color=PRIMARY, width={"band": 0.75})
        .encode(
            x=alt.X("mrt_band:N", title="Distance to nearest MRT/LRT", sort=order,
                    axis=alt.Axis(labelAngle=0)),
            y=alt.Y("median_price_psm:Q", title="Median price per sqm (SGD)",
                    scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("mrt_band:N", title="Distance"),
                alt.Tooltip("median_price_psm:Q", title="Median psm", format="$,.0f"),
                alt.Tooltip("premium_vs_farthest_pct:Q", title="vs over 1.2km (%)", format="+.1f"),
                alt.Tooltip("sales:Q", title="Sales", format=","),
            ],
        )
        .properties(height=280)
    )


def floor_multiplier(df):
    """Storey premium, controlled for location, flat type and year.

    Uncontrolled this badly overstates: tall blocks are newer and sit in more
    expensive places, so a raw comparison credits the storey with the postcode.
    Comparing each tier only against Low floors in the SAME town, flat type and year
    cuts the 20+ premium from 83% to about 51%.
    """
    cells = (
        df.groupby(["town", "flat_type", "calendar_year", "floor_tier"], observed=True)
        .agg(psm=("price_psm", "median"), n=("price_psm", "size"))
        .reset_index()
    )
    cells = cells[cells["n"] >= 15]

    base = cells[cells["floor_tier"] == "Low (1-4)"][
        ["town", "flat_type", "calendar_year", "psm"]
    ].rename(columns={"psm": "base_psm"})

    joined = cells.merge(base, on=["town", "flat_type", "calendar_year"])
    if joined.empty:
        return None
    joined["multiplier"] = joined["psm"] / joined["base_psm"]

    summary = joined.groupby("floor_tier", as_index=False, observed=True).agg(
        multiplier=("multiplier", "mean"), cells=("multiplier", "size")
    )
    bars = alt.Chart(summary).mark_bar(
        cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color=PRIMARY, width={"band": 0.7}
    ).encode(
        x=alt.X("floor_tier:N", title=None, sort=FLOOR_ORDER, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("multiplier:Q", title="x the price of a low floor",
                scale=alt.Scale(zero=False)),
        tooltip=[
            alt.Tooltip("floor_tier:N", title="Tier"),
            alt.Tooltip("multiplier:Q", title="Multiplier", format=".3f"),
            alt.Tooltip("cells:Q", title="Comparisons"),
        ],
    )
    # Direct labels: four marks, so every one is labelled without crowding.
    labels = bars.mark_text(dy=-8, color=INK, fontSize=11).encode(
        text=alt.Text("multiplier:Q", format=".2f")
    )
    return style((bars + labels).properties(height=280))


def volume_chart(df):
    """Transaction counts per month. Context for the price charts, not a headline.

    Deliberately recessive -- a muted fill and half the height of the price series
    above it, because volume explains the confidence in those medians rather than
    competing with them.
    """
    volume = df.groupby("transaction_month", as_index=False).size()
    return style(
        alt.Chart(volume)
        .mark_area(color=PRIMARY, opacity=0.35, line={"color": PRIMARY, "strokeWidth": 2},
                   interpolate="monotone")
        .encode(
            x=alt.X("transaction_month:T", title=None),
            y=alt.Y("size:Q", title="Transactions"),
            tooltip=[
                alt.Tooltip("transaction_month:T", title="Month", format="%b %Y"),
                alt.Tooltip("size:Q", title="Sales", format=","),
            ],
        )
        .properties(height=180)
    )


def summary_table(df):
    """The numbers behind the charts, so identity is never colour-alone.

    An accessibility requirement rather than a nicety: a reader who cannot separate
    two hues, or who is printing this, still gets every value.
    """
    table = (
        df.groupby(["town", "is_mature_estate"], as_index=False)
        .agg(
            transactions=("resale_price", "size"),
            median_price=("resale_price", "median"),
            median_psm=("price_psm", "median"),
            median_mrt_km=("dist_to_nearest_mrt_km", "median"),
            median_cbd_km=("dist_to_cbd_km", "median"),
        )
        .sort_values("median_psm", ascending=False)
    )
    table["is_mature_estate"] = table["is_mature_estate"].map({True: "Mature", False: "Non-mature"})
    return table.rename(columns={
        "town": "Town", "is_mature_estate": "Estate", "transactions": "Sales",
        "median_price": "Median price", "median_psm": "Median psm",
        "median_mrt_km": "km to MRT", "median_cbd_km": "km to CBD",
    })


def main():
    st.set_page_config(page_title="HDB Resale Prices", page_icon="*", layout="wide")
    st.title("HDB resale prices")

    if not os.path.exists(os.path.join(edition.EDITION_DIR, edition.STAMP_FILE)):
        st.error(f"No published edition in {edition.EDITION_DIR}/. Publish one first:")
        st.code(
            """python ingest_hdb.py --full
dbt deps && dbt build
python publish_edition.py""",
            language="bash",
        )
        st.stop()

    df = load_sales()
    stamp, mrt_bands, index, effects, fair_value = load_published()

    with st.sidebar:
        st.header("Filters")

        years = sorted(df["calendar_year"].unique())
        first, last = st.select_slider("Year", options=years, value=(years[0], years[-1]))

        flat_types = st.multiselect(
            "Flat type",
            options=[t for t in FLAT_TYPE_ORDER if t in set(df["flat_type"])],
            default=[],
            help="Empty means all.",
        )
        regions = st.multiselect("Region", options=sorted(df["region"].unique()), default=[])
        towns = st.multiselect("Town", options=sorted(df["town"].unique()), default=[])

    filtered = df[df["calendar_year"].between(first, last)]
    if flat_types:
        filtered = filtered[filtered["flat_type"].isin(flat_types)]
    if regions:
        filtered = filtered[filtered["region"].isin(regions)]
    if towns:
        filtered = filtered[filtered["town"].isin(towns)]

    if filtered.empty:
        st.warning("No transactions match those filters.")
        st.stop()

    kpi_row(filtered)
    st.divider()

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Median price over time")
        st.altair_chart(price_trend(filtered), use_container_width=True)

        st.subheader("Prices like for like")
        st.altair_chart(price_index(index), use_container_width=True)
        st.caption(
            "Published figure, unaffected by the filters. The model prices the same flat "
            "-- same town, MRT band, lease band, storey and flat type -- each month. Where "
            "the lines part, the mix of flats sold changed, not their prices."
        )

        st.subheader("The CBD premium, and where it stops")
        st.altair_chart(cbd_gradient(filtered), use_container_width=True)
        st.caption(
            "Steep decay to about 5km, then a plateau that oscillates rather than "
            "falls. Past ~5km, distance to the CBD stops explaining price and the "
            "town itself takes over."
        )

        st.subheader("MRT proximity premium")
        st.altair_chart(mrt_premium(mrt_bands), use_container_width=True)
        st.caption(
            "Published figure: every sale in the edition, unaffected by the filters. "
            "Naive, not controlled -- station proximity is entangled with distance "
            "to the CBD (see FINDINGS.md, finding 2)."
        )

        st.subheader("How the model's effects moved")
        st.altair_chart(effects_over_time(effects), use_container_width=True)
        st.caption(
            "Published figure: the hedonic model refitted on each calendar year, holding "
            "town, the other band, storey, flat type and month constant. Bars are 95% "
            "intervals. 2026 is nine months."
        )

        st.subheader("Transaction volume")
        st.altair_chart(volume_chart(filtered), use_container_width=True)

    with right:
        st.subheader("Price per sqm by town")
        st.altair_chart(town_ranking(filtered), use_container_width=True)

        st.subheader("Storey premium, controlled")
        chart = floor_multiplier(filtered)
        if chart is None:
            st.info("Not enough comparable sales in this selection.")
        else:
            st.altair_chart(chart, use_container_width=True)
            st.caption(
                "Each tier against low floors in the same town, flat type and year. "
                "Uncontrolled, the 20+ premium looks like 83%; most of that is which "
                "blocks happen to be tall."
            )

    st.divider()

    st.subheader("Blocks that sell above or below what their attributes justify")
    judged = fair_value[fair_value["verdict"].isin(["above", "below"])]
    if towns:
        # Narrowing to chosen towns only selects rows; every verdict was computed on all
        # sales, so the town filter never changes a block's number.
        judged = judged[judged["town"].isin(towns)]
    st.dataframe(
        judged[["address", "town", "verdict", "premium_pct", "ci_low_pct", "ci_high_pct", "sales"]]
        .rename(columns={"address": "Block", "town": "Town", "verdict": "Verdict",
                         "premium_pct": "vs model (%)", "ci_low_pct": "95% low (%)",
                         "ci_high_pct": "95% high (%)", "sales": "Sales"}),
        use_container_width=True, hide_index=True,
    )
    window = f"{fair_value['window_start'].iloc[0]} to {fair_value['window_end'].iloc[0]}" if len(fair_value) else ""
    st.caption(
        f"Published figure. Sales {window}, each against its own year's model. A verdict "
        "needs 10+ sales and a 95% interval clear of zero; the Town filter narrows the list "
        "but never changes a number. A premium is whatever the model cannot see -- flat "
        "design, block age within a lease band, views -- not a sign of overpricing."
    )

    with st.expander("View the numbers as a table"):
        st.dataframe(
            summary_table(filtered),
            use_container_width=True, hide_index=True,
            column_config={
                "Median price": st.column_config.NumberColumn(format="$%d"),
                "Median psm": st.column_config.NumberColumn(format="$%d"),
                "km to MRT": st.column_config.NumberColumn(format="%.2f"),
                "km to CBD": st.column_config.NumberColumn(format="%.2f"),
            },
        )

    st.caption(
        f"Edition: {stamp['sales']:,} transactions, "
        f"{df['transaction_month'].min():%b %Y} to {df['transaction_month'].max():%b %Y}, "
        f"published {stamp['published_on']}. "
        "Source: data.gov.sg."
    )


if __name__ == "__main__":
    main()

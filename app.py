"""Streamlit dashboard over the published edition, in two pages.

Findings shows published figures only: every number comes straight from a mart in
published/, the same numbers FINDINGS.md quotes, and nothing on the page can change them.
Explore recomputes the descriptive figures from every sale under whatever filters are
chosen, through dashboard/explore.py; with nothing filtered it matches the marts, and
dashboard/check_parity.py proves it in CI.

Reads published/ -- never the warehouse, never the API -- so it runs on a host that has
never seen the pipeline. The look lives in dashboard/theme.py; this file only says what
is on each page.

    streamlit run app.py
"""

import os

import streamlit as st

from dashboard import charts, explore, theme
from publish import edition


@st.cache_data(show_spinner=False)
def load_sales():
    """Every sale, once. 240k rows is small enough to filter in memory."""
    return edition.read_sales()


@st.cache_data(show_spinner=False)
def load_table(name):
    return edition.read_table(name)


@st.cache_data(show_spinner=False)
def load_stamp():
    return edition.read_stamp()


def show(chart):
    st.altair_chart(chart, use_container_width=True, theme=None)


# --- Findings -----------------------------------------------------------------------


def findings_page():
    theme.apply()
    stamp = load_stamp()
    index = load_table("mart_price_index")
    validation = load_table("mart_model_validation").set_index("scope")
    model_vs_naive = load_table("mart_model_vs_naive")

    theme.header(
        "Findings",
        f"What {stamp['sales']:,} resale sales say about flat prices",
        "Published figures only. The charts compare flats like for like, or say plainly when "
        "they don't, and nothing here can be filtered, so the page always matches the write-up. "
        "To slice the data yourself, open Explore.",
        theme.edition_aside(stamp, "Every number on this page matches FINDINGS.md."),
    )

    hero = ("Like-for-like prices since Jan 2017", "Not published", "", "")
    if len(index):
        last = index.iloc[-1]
        hero = (
            "Like-for-like prices since Jan 2017",
            f"{last['hedonic_index'] - 100:+.1f}%",
            f"The median price per sqm rose {last['naive_index'] - 100:.1f}% over the same months. "
            "The gap is the mix of flats that sold.",
            theme.sparkline(index["hedonic_index"], "Like-for-like price index, January 2017 to the latest month"),
        )
    others = []
    near = model_vs_naive[(model_vs_naive["term"] == "mrt_band") & (model_vs_naive["level"] == "0-400m")]
    if len(near):
        row = near.iloc[0]
        others.append((
            "Living within 400m of an MRT station",
            f"{row['model_pct']:+.1f}%",
            f"Like for like, against flats over 1.2km away. A simple comparison says {row['naive_pct']:+.1f}%.",
        ))
    if "All years" in validation.index:
        overall = validation.loc["All years"]
        others.append((
            "Typical miss on blocks the model never saw",
            f"{overall['model_median_error_pct']:.1f}%",
            f"Against {overall['baseline_median_error_pct']:.1f}% for a simple guess from the town and flat type.",
        ))
    theme.tiles(hero, others)

    left, right = st.columns([1.6, 1], gap="large")
    with left:
        with theme.card():
            show(charts.price_index(index))
        theme.card_label(
            "Prices like for like",
            "The model prices the same kind of flat each month: same town, lease, floor, flat type "
            "and distance to MRT. Where the two lines part, the mix of flats that sold changed, not "
            "their value. The shaded band is the 95% range.",
        )
    with right:
        with theme.card():
            show(charts.effects_over_time(load_table("mart_effects_by_year")))
        theme.card_label(
            "How the model's effects moved",
            "Both effects refitted on each calendar year, with bars for the 95% range. "
            "2026 is nine months.",
        )

    left, right = st.columns([1, 1.6], gap="large")
    with left:
        with theme.card():
            show(charts.town_effect(load_table("mart_town_ranking")))
        theme.card_label(
            "Town premiums, like for like",
            "Each town against the average town, for flats with the same lease, floor, flat type "
            "and distance to MRT. The thin lines show the 95% range.",
        )
    with right:
        with theme.card():
            show(charts.cbd_gradient(load_table("mart_cbd_gradient")))
        theme.card_label(
            "Distance to the CBD",
            "Median price per sqm by 1km ring. Prices fall fast for the first 5km, then barely "
            "change until about 15km, where which town a flat is in matters more.",
        )
        with theme.card():
            show(charts.mrt_premium(load_table("mart_mrt_premium_by_band")))
        theme.card_label(
            "Distance to MRT, before comparing like with like",
            "Simple medians by distance band; each label is that band against flats over 1.2km "
            "away. Like for like, the premium within 400m is roughly double.",
        )

    left, right = st.columns([1.6, 1], gap="large")
    with left:
        fair_value_card(load_table("mart_block_fair_value"))
    with right:
        with theme.card():
            show(charts.storey_multiplier(load_table("mart_storey_premium")))
        theme.card_label(
            "Floor level, within the same town",
            "Each floor level against low floors in the same town, flat type and year. Lease isn't "
            "held constant here; the model, which does, puts 20+ floors about 20% above a low floor.",
        )

    theme.footnote(f"{theme.edition_line(stamp)}. Source: data.gov.sg. The numbers behind every chart are in FINDINGS.md.")


def fair_value_card(fair_value):
    judged = fair_value[fair_value["verdict"].isin(["above", "below"])]
    with theme.card():
        towns = st.multiselect("Filter by town", sorted(judged["town"].unique()), default=[],
                               placeholder="All towns",
                               help="Narrows the list. It never changes a number.")
        if towns:
            judged = judged[judged["town"].isin(towns)]
        # The sign says above or below, so the verdict needs no column of its own.
        shown = judged.assign(
            vs=judged["premium_pct"].map("{:+.1f}%".format),
            range=judged["ci_low_pct"].map("{:+.1f}".format) + " to " + judged["ci_high_pct"].map("{:+.1f}%".format),
        )
        st.dataframe(
            shown[["address", "town", "vs", "range", "sales"]]
            .rename(columns={"address": "Block", "town": "Town", "vs": "Vs expected",
                             "range": "95% range", "sales": "Sales"}),
            use_container_width=True, hide_index=True, height=330,
        )
    window = ""
    if len(fair_value):
        window = (f"Sales from {theme.month_name(fair_value['window_start'].iloc[0])} to "
                  f"{theme.month_name(fair_value['window_end'].iloc[0])}, each against its own year's model. ")
    theme.card_label(
        "Blocks that sell above (+) or below (-) what the model expects",
        f"{window}A block needs 10 or more sales and a 95% range clear of zero to be listed. The "
        "difference is whatever the model can't see, like views or flat design, not a sign of overpricing.",
    )


# --- Explore ------------------------------------------------------------------------


def explore_page():
    theme.apply()

    # A skeleton only on the first load of a session: afterwards the sales are cached,
    # and flashing placeholders on every filter change would be worse than none.
    loading = st.empty()
    if not st.session_state.get("sales_loaded"):
        loading.markdown(theme.skeleton(), unsafe_allow_html=True)
    df = load_sales()
    st.session_state["sales_loaded"] = True
    loading.empty()

    with st.sidebar:
        st.header("Filters")
        years = sorted(df["calendar_year"].unique())
        year_range = st.select_slider("Year", options=years, value=(years[0], years[-1]))
        flat_types = st.multiselect(
            "Flat type", [t for t in charts.FLAT_TYPE_ORDER if t in set(df["flat_type"])],
            default=[], placeholder="All flat types",
        )
        regions = st.multiselect("Region", sorted(df["region"].unique()), default=[], placeholder="All regions")
        towns = st.multiselect("Town", sorted(df["town"].unique()), default=[], placeholder="All towns")

    filtered = explore.filter_sales(df, year_range, flat_types, regions, towns)

    chips = [f"{year_range[0]} to {year_range[1]}" if year_range[0] != year_range[1] else str(year_range[0])]
    chips += _chip_list(flat_types, "All flat types")
    chips += _chip_list(regions, "All regions")
    chips += _chip_list(towns, "All towns")
    theme.header(
        "Explore",
        "Explore the sales yourself",
        "Simple comparisons, recalculated from every sale under the filters in the sidebar. "
        "Good for looking around; for figures you can quote, use Findings.",
        theme.filter_aside(chips, f"{len(filtered):,} of {len(df):,} sales match."),
    )

    if filtered.empty:
        theme.empty_state(
            "No sales match these filters",
            "Try a wider year range, or clear one of the flat type, region or town filters in the sidebar.",
        )
        st.stop()

    monthly = filtered.groupby("transaction_month")["price_psm"].median()
    months = sorted(filtered["transaction_month"].unique())
    theme.tiles(
        (
            "Median price per sqm",
            f"S${filtered['price_psm'].median():,.0f}",
            f"From {len(filtered):,} sales. The line is the median for each month.",
            theme.sparkline(monthly.tolist(), "Median price per sqm by month for the selected sales"),
        ),
        [
            ("Median price", f"S${filtered['resale_price'].median():,.0f}",
             "Half the flats in this selection sold for more, half for less."),
            ("Months covered", f"{len(months):,}",
             f"{theme.month_name(months[0])} to {theme.month_name(months[-1])}."),
        ],
    )

    left, right = st.columns([1.6, 1], gap="large")
    with left:
        with theme.card():
            show(charts.price_trend(explore.price_trend(filtered)))
        theme.card_label(
            "Median price over time",
            "Median price per sqm each month, one line per flat type, lightest for the smallest. "
            "1-room and multi-generation flats sell about once a month, too rarely for a monthly "
            "median, so they're left off.",
        )
    with right:
        with theme.card():
            show(charts.volume(explore.volume(filtered)))
        theme.card_label("Sales each month", "How many sales each monthly median rests on.")

    left, right = st.columns([1, 1.6], gap="large")
    with left:
        with theme.card():
            show(charts.town_ranking(explore.town_ranking(filtered)))
        theme.card_label(
            "Price per sqm by town",
            "Simple medians, coloured by estate type. These aren't like for like: Findings has the "
            "town premiums that are.",
        )
    with right:
        with theme.card():
            show(charts.cbd_gradient(explore.cbd_gradient(filtered)))
        theme.card_label("Distance to the CBD", "Median price per sqm by 1km ring from the CBD.")
        with theme.card():
            show(charts.mrt_premium(explore.mrt_premium_by_band(filtered)))
        theme.card_label(
            "Distance to MRT",
            "Median price per sqm by distance band; each label is that band against flats over 1.2km away.",
        )

    left, right = st.columns([1.6, 1], gap="large")
    with left:
        table = explore.town_summary(filtered)
        table["is_mature_estate"] = table["is_mature_estate"].map({True: "Mature", False: "Non-mature"})
        with theme.card():
            st.dataframe(
                table.rename(columns={
                    "town": "Town", "is_mature_estate": "Estate", "transactions": "Sales",
                    "median_price": "Median price", "median_psm": "Median per sqm",
                    "median_mrt_km": "Km to MRT", "median_cbd_km": "Km to CBD",
                }),
                use_container_width=True, hide_index=True, height=330,
                column_config={
                    "Median price": st.column_config.NumberColumn(format="S$%d"),
                    "Median per sqm": st.column_config.NumberColumn(format="S$%d"),
                    "Km to MRT": st.column_config.NumberColumn(format="%.2f"),
                    "Km to CBD": st.column_config.NumberColumn(format="%.2f"),
                },
            )
        theme.card_label("The numbers, by town", "The figures behind these charts for each town in your selection.")
    with right:
        storey = explore.storey_multiplier(filtered)
        if storey.dropna(subset=["controlled_multiplier"]).empty:
            theme.empty_state(
                "Not enough comparable sales",
                "Floor levels are compared within the same town, flat type and year. Widen the filters to see them.",
            )
        else:
            with theme.card():
                show(charts.storey_multiplier(storey))
            theme.card_label(
                "Floor level, within the same town",
                "Each floor level against low floors in the same town, flat type and year.",
            )

    theme.footnote(f"{theme.edition_line(load_stamp())}. Source: data.gov.sg.")


def _chip_list(chosen, everything):
    if not chosen:
        return [everything]
    if len(chosen) <= 3:
        return list(chosen)
    return list(chosen[:3]) + [f"+{len(chosen) - 3} more"]


def main():
    st.set_page_config(page_title="HDB resale prices", page_icon=":material/apartment:", layout="wide")

    if not os.path.exists(os.path.join(edition.EDITION_DIR, edition.STAMP_FILE)):
        theme.apply()
        theme.error_state(
            "No published numbers to show",
            f"The dashboard reads the {edition.EDITION_DIR}/ folder, and it isn't there. "
            "Build it from the data, from the repository root:",
        )
        st.code("python -m ingest.hdb_resale --full\ndbt deps && dbt build\npython -m publish.build_edition",
                language="bash")
        st.stop()

    st.navigation([
        st.Page(findings_page, title="Findings", icon=":material/insights:", default=True),
        st.Page(explore_page, title="Explore", icon=":material/tune:"),
    ]).run()


if __name__ == "__main__":
    main()

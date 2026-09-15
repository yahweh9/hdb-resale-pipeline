"""Streamlit dashboard over the published edition, in two pages.

Findings shows published figures only: every number comes straight from a mart in
published/, the same numbers FINDINGS.md quotes, and nothing on the page can change them.
Explore recomputes the descriptive figures from every sale under whatever filters are
chosen, through explore.py; with nothing filtered it matches the marts, and
check_explore_parity.py proves it in CI.

Reads published/ -- never the warehouse, never the API -- so it runs on a host that has
never seen the pipeline.

    streamlit run dashboard.py
"""

import os

import streamlit as st

import charts
import edition
import explore


@st.cache_data(show_spinner="Reading the edition...")
def load_sales():
    """Every sale, once. 240k rows is small enough to filter in memory."""
    return edition.read_sales()


@st.cache_data
def load_table(name):
    return edition.read_table(name)


@st.cache_data
def load_stamp():
    return edition.read_stamp()


def edition_caption(stamp):
    st.caption(
        f"Edition: {stamp['sales']:,} transactions through {stamp['data_through']}, "
        f"published {stamp['published_on']}. Source: data.gov.sg."
    )


# --- Findings -----------------------------------------------------------------------


def findings_page():
    stamp = load_stamp()
    index = load_table("mart_price_index")
    validation = load_table("mart_model_validation").set_index("scope")

    st.title("HDB resale prices: findings")
    st.caption(
        "Published figures. Every number here comes from the committed edition and matches "
        "FINDINGS.md; nothing on this page filters or recomputes it. For your own cuts, "
        "use Explore."
    )

    cols = st.columns(4)
    cols[0].metric("Transactions", f"{stamp['sales']:,}")
    if len(index):
        cols[1].metric("Prices since Jan 2017, like for like", f"{index['hedonic_index'].iloc[-1] - 100:+.1f}%")
    if "All years" in validation.index:
        overall = validation.loc["All years"]
        cols[2].metric("Model's typical miss, unseen blocks", f"{overall['model_median_error_pct']:.1f}%")
        cols[3].metric("Town x flat type guess's miss", f"{overall['baseline_median_error_pct']:.1f}%")
    st.divider()

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Prices like for like")
        st.altair_chart(charts.price_index(index), use_container_width=True)
        st.caption(
            "The model prices the same flat -- same town, MRT band, lease band, storey and "
            "flat type -- each month. Where the lines part, the mix of flats sold changed, "
            "not their prices."
        )

        st.subheader("MRT proximity, before controls")
        st.altair_chart(charts.mrt_premium(load_table("mart_mrt_premium_by_band")), use_container_width=True)
        st.caption(
            "Naive medians. Station proximity is entangled with everything else about a "
            "location; the model's like-for-like premium is roughly double (FINDINGS.md, finding 2)."
        )

        st.subheader("How the model's effects moved")
        st.altair_chart(charts.effects_over_time(load_table("mart_effects_by_year")), use_container_width=True)
        st.caption(
            "The model refitted on each calendar year. Bars are 95% intervals. 2026 is nine months."
        )

        st.subheader("The CBD premium, and where it stops")
        st.altair_chart(charts.cbd_gradient(load_table("mart_cbd_gradient")), use_container_width=True)
        st.caption(
            "Steep decay to about 5km, then a plateau that oscillates rather than falls. Past "
            "~5km, distance to the CBD stops explaining price and the town itself takes over."
        )

    with right:
        st.subheader("Town premiums, like for like")
        st.altair_chart(charts.town_effect(load_table("mart_town_ranking")), use_container_width=True)
        st.caption(
            "Each town against the average town, holding MRT band, lease band, storey, flat "
            "type and month constant. Whiskers are 95% intervals."
        )

        st.subheader("Storey premium, town-controlled")
        st.altair_chart(charts.storey_multiplier(load_table("mart_storey_premium")), use_container_width=True)
        st.caption(
            "Each tier against low floors in the same town, flat type and year. This does "
            "not hold lease constant, and tall blocks are newer: the model, which does, puts "
            "20+ storeys far lower."
        )

    st.divider()
    fair_value_section(load_table("mart_block_fair_value"))
    edition_caption(stamp)


def fair_value_section(fair_value):
    st.subheader("Blocks that sell above or below what their attributes justify")
    judged = fair_value[fair_value["verdict"].isin(["above", "below"])]
    towns = st.multiselect("Show towns", sorted(judged["town"].unique()), default=[],
                           help="Empty means all. Narrows the list; never changes a number.")
    if towns:
        judged = judged[judged["town"].isin(towns)]
    st.dataframe(
        judged[["address", "town", "verdict", "premium_pct", "ci_low_pct", "ci_high_pct", "sales"]]
        .rename(columns={"address": "Block", "town": "Town", "verdict": "Verdict",
                         "premium_pct": "vs model (%)", "ci_low_pct": "95% low (%)",
                         "ci_high_pct": "95% high (%)", "sales": "Sales"}),
        use_container_width=True, hide_index=True,
    )
    if len(fair_value):
        st.caption(
            f"Sales {fair_value['window_start'].iloc[0]} to {fair_value['window_end'].iloc[0]}, "
            "each against its own year's model. A verdict needs 10+ sales and a 95% interval "
            "clear of zero. A premium is whatever the model cannot see -- flat design, block "
            "age within a lease band, views -- not a sign of overpricing."
        )


# --- Explore ------------------------------------------------------------------------


def explore_page():
    df = load_sales()

    with st.sidebar:
        st.header("Filters")
        years = sorted(df["calendar_year"].unique())
        year_range = st.select_slider("Year", options=years, value=(years[0], years[-1]))
        flat_types = st.multiselect(
            "Flat type", [t for t in charts.FLAT_TYPE_ORDER if t in set(df["flat_type"])],
            default=[], help="Empty means all.",
        )
        regions = st.multiselect("Region", sorted(df["region"].unique()), default=[])
        towns = st.multiselect("Town", sorted(df["town"].unique()), default=[])

    filtered = explore.filter_sales(df, year_range, flat_types, regions, towns)

    st.title("HDB resale prices: explore")
    st.caption(
        "Exploratory figures, recomputed from every sale under the filters on the left. "
        "Naive group-bys, not the model: useful for looking, not for quoting."
    )
    if filtered.empty:
        st.warning("No transactions match those filters.")
        st.stop()

    cols = st.columns(4)
    cols[0].metric("Transactions", f"{len(filtered):,}")
    cols[1].metric("Median price", f"S${filtered['resale_price'].median():,.0f}")
    cols[2].metric("Median price / sqm", f"S${filtered['price_psm'].median():,.0f}")
    cols[3].metric("Months covered", f"{filtered['transaction_month'].nunique():,}")
    st.divider()

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Median price over time")
        st.altair_chart(charts.price_trend(explore.price_trend(filtered)), use_container_width=True)

        st.subheader("Distance to the CBD")
        st.altair_chart(charts.cbd_gradient(explore.cbd_gradient(filtered)), use_container_width=True)

        st.subheader("Distance to MRT")
        st.altair_chart(charts.mrt_premium(explore.mrt_premium_by_band(filtered)), use_container_width=True)

        st.subheader("Transaction volume")
        st.altair_chart(charts.volume(explore.volume(filtered)), use_container_width=True)

    with right:
        st.subheader("Price per sqm by town")
        st.altair_chart(charts.town_ranking(explore.town_ranking(filtered)), use_container_width=True)

        st.subheader("Storey premium, town-controlled")
        storey = explore.storey_multiplier(filtered)
        if storey.empty:
            st.info("Not enough comparable sales in this selection.")
        else:
            st.altair_chart(charts.storey_multiplier(storey), use_container_width=True)

    st.divider()
    with st.expander("View the numbers as a table"):
        table = explore.town_summary(filtered)
        table["is_mature_estate"] = table["is_mature_estate"].map({True: "Mature", False: "Non-mature"})
        st.dataframe(
            table.rename(columns={
                "town": "Town", "is_mature_estate": "Estate", "transactions": "Sales",
                "median_price": "Median price", "median_psm": "Median psm",
                "median_mrt_km": "km to MRT", "median_cbd_km": "km to CBD",
            }),
            use_container_width=True, hide_index=True,
            column_config={
                "Median price": st.column_config.NumberColumn(format="$%d"),
                "Median psm": st.column_config.NumberColumn(format="$%d"),
                "km to MRT": st.column_config.NumberColumn(format="%.2f"),
                "km to CBD": st.column_config.NumberColumn(format="%.2f"),
            },
        )
    edition_caption(load_stamp())


def main():
    st.set_page_config(page_title="HDB Resale Prices", page_icon="*", layout="wide")

    if not os.path.exists(os.path.join(edition.EDITION_DIR, edition.STAMP_FILE)):
        st.error(f"No published edition in {edition.EDITION_DIR}/. Publish one first:")
        st.code("python ingest_hdb.py --full\ndbt deps && dbt build\npython publish_edition.py",
                language="bash")
        st.stop()

    st.navigation([
        st.Page(findings_page, title="Findings", default=True),
        st.Page(explore_page, title="Explore"),
    ]).run()


if __name__ == "__main__":
    main()

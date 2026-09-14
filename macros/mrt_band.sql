{#
    The one definition of the MRT distance bands. The mart uses it now and the hedonic
    model's input will use it in slice 2, so a band edge can only ever change in one
    place.

    Upper edges are inclusive to match dim_block.is_near_mrt (<= 0.4): "0-400m" and
    "near MRT" must count exactly the same blocks, or the dashboard and the findings
    quote two different near-station premiums. The two thinnest ranges are merged:
    over 2km has ~520 sales, too few to stand as a band of its own.
#}

{% macro mrt_band_order(dist_km) -%}
    case
        when {{ dist_km }} is null then null
        when {{ dist_km }} <= 0.4 then 1
        when {{ dist_km }} <= 0.8 then 2
        when {{ dist_km }} <= 1.2 then 3
        else 4
    end
{%- endmacro %}

{% macro mrt_band_label(dist_km) -%}
    case
        when {{ dist_km }} is null then null
        when {{ dist_km }} <= 0.4 then '0-400m'
        when {{ dist_km }} <= 0.8 then '400-800m'
        when {{ dist_km }} <= 1.2 then '800m-1.2km'
        else 'over 1.2km'
    end
{%- endmacro %}

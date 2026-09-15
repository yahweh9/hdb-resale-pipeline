{#
    The one definition of the MRT distance bands, applied once in dim_block so every
    consumer (the marts now, the hedonic model in slice 2) reads the same band.

    Upper edges are inclusive: 400m exactly is near. is_near_mrt is defined as band 1,
    so "0-400m" and "near MRT" always count the same blocks. Pass the UNROUNDED
    distance -- banding a rounded one moves blocks across edges. The two thinnest
    ranges are merged: over 2km has ~520 sales, too few to stand as a band of its own.
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

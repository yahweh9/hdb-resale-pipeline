{#
    Great-circle distance in kilometres between two lat/lon pairs.

    A macro rather than repeated arithmetic because it is used twice in dim_block --
    distance to the CBD and distance to the nearest station -- and the formula is
    exactly the kind of thing that gets subtly mistyped the second time.

    Earth radius 6371 km. Accurate to well under the width of an HDB block at this
    scale, which is all the precision the question needs.
#}
{% macro haversine_km(lat1, lon1, lat2, lon2) -%}
    6371 * 2 * asin(sqrt(
        pow(sin(radians({{ lat2 }} - {{ lat1 }}) / 2), 2)
        + cos(radians({{ lat1 }})) * cos(radians({{ lat2 }}))
        * pow(sin(radians({{ lon2 }} - {{ lon1 }}) / 2), 2)
    ))
{%- endmacro %}

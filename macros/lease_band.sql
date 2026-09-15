{#
    The one definition of the lease bands, in whole years of lease remaining at sale.

    Lower edges are inclusive: "50-60" means at least 50 years and under 60, which is
    how people say it -- a flat with 59 years 11 months left has "59 years". Months,
    not years, go in, because silver parses remaining_lease to integer months. Under
    40 years has only ~55 sales, so it is folded into "under 50".
#}

{% macro lease_band(remaining_lease_months) -%}
    case
        when {{ remaining_lease_months }} is null then null
        when {{ remaining_lease_months }} < 600  then 'under 50'
        when {{ remaining_lease_months }} < 720  then '50-60'
        when {{ remaining_lease_months }} < 840  then '60-70'
        when {{ remaining_lease_months }} < 960  then '70-80'
        when {{ remaining_lease_months }} < 1080 then '80-90'
        else '90+'
    end
{%- endmacro %}

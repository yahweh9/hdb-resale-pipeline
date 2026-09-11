{#
    dbt's default appends the custom schema to the target schema, which would give
    main_silver and main_gold. The layer names are the point here, so use them
    verbatim: silver.silver_hdb_resale and gold.fact_resale_txn.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}

/*
    Grain: one row per transaction month. The fact has no finer date than the month
    data.gov.sg publishes, so a day-grain calendar would be 30x the rows with every
    one of them unreferenced.
*/

with months as (

    select distinct transaction_month
    from {{ ref('silver_hdb_resale') }}

)

select
    cast(strftime(transaction_month, '%Y%m') as integer) as date_key,
    transaction_month,
    strftime(transaction_month, '%Y-%m')                as year_month,
    cast(year(transaction_month) as integer)            as calendar_year,
    cast(quarter(transaction_month) as integer)         as calendar_quarter,
    cast(month(transaction_month) as integer)           as month_of_year,
    monthname(transaction_month)                        as month_name
from months

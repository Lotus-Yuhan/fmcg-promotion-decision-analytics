# Customer 360 and RFM Data Dictionary

## Purpose and grain

`customer_360` contains one row per observed household. It combines full-store
shopping behaviour, beverage behaviour, RFM scores and the partial anonymised
demographics supplied by the current official Complete Journey release.

The household-level table is generated locally at
`data/local_exports/customer_360.csv` and is excluded from Git. Public outputs
are limited to aggregate segment summaries and quality checks.

## Core fields

| Field | Definition |
|---|---|
| `household_key` | Anonymous household identifier supplied by the dataset. |
| `observation_end_day` | Maximum transaction day in the full dataset. |
| `first_purchase_day` | First observed purchase day for the household. |
| `last_purchase_day` | Last observed purchase day for the household. |
| `recency_days` | Observation end day minus last purchase day; lower is more recent. |
| `frequency_baskets` | Count of distinct observed baskets. |
| `monetary_value` | Sum of observed full-store sales value. |
| `active_weeks` | Number of weeks containing at least one basket. |
| `purchase_days` | Number of distinct days containing a purchase. |
| `avg_days_between_purchases` | Mean gap between consecutive purchase days. |
| `avg_basket_value` | Mean sales value per basket. |
| `discount_basket_rate` | Share of baskets containing a retail or coupon discount. |
| `coupon_basket_rate` | Share of baskets containing a coupon discount. |
| `unique_products` | Number of distinct products purchased. |
| `department_breadth` | Number of distinct departments purchased from. |
| `category_breadth` | Number of distinct commodity descriptions purchased from. |
| `beverage_spend` | Observed sales value from the defined beverage scope. |
| `beverage_basket_penetration` | Beverage baskets divided by all baskets. |
| `beverage_promo_share` | Beverage revenue on observed promotion divided by beverage revenue. |

## RFM scoring

Each RFM component receives a score from 1 to 5 based on the household
distribution:

- Recency: lower values receive higher scores.
- Frequency: higher basket counts receive higher scores.
- Monetary: higher observed sales receive higher scores.

Tied values receive the same percentile rank. `rfm_score` concatenates the
three scores; for example, `555` is highly recent, frequent and high-spending.

## Behavioural interpretation

`promotion_oriented_flag` identifies households in the top quartile of
discount-basket rate that also shop at least as frequently as the median
household. This is an observed behavioural proxy, not proof of underlying price
sensitivity and not a causal promotion effect.

## Limitations

- Households are frequent shoppers at one retailer and are not a representative
  population sample.
- Transactions outside the retailer are unobserved.
- RFM thresholds are relative to this dataset and observation window.
- Demographics cover only part of the household panel and several variables are
  anonymised as classification codes in the current official release.
- Customer personas are descriptive targeting aids, not causal treatment rules.

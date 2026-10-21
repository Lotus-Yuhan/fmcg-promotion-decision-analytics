# Cohort Retention Method

## Business purpose

Cohort analysis separates customer-base composition from lifecycle behaviour.
It asks whether households with a similar first observed purchase period remain
active and continue generating revenue as the observation window progresses.

## Cohort definition

The dataset contains relative day numbers rather than real calendar dates.
`src/cohort_retention.py` therefore assigns each transaction to a fixed 30-day
period:

```text
activity_period = floor((day - 1) / 30)
```

A household's `cohort_period` is its first observed activity period, and
`cohort_age` is the number of 30-day periods since that first observed period.

These are **observed first-purchase cohorts**, not verified acquisition cohorts.
Purchases before the dataset begins are unavailable, so cohort P00 is explicitly
flagged as left-censored. Later cohorts may also contain previously existing but
temporarily inactive customers.

## Metrics

### Customer retention rate

```text
active households at cohort age / households in the cohort
```

Age-zero retention must equal 100%. Cells that are observable but have no
activity are recorded as zero. Future cells beyond the end of the dataset are
left missing and are never treated as churn.

### Revenue retention index

```text
cohort revenue at cohort age / cohort revenue at age zero
```

The index can exceed 100% when retained households spend more than the cohort
did in its initial period. Age zero is usually a partial period because a
household can make its first observed purchase on any day within that 30-day
window. This mechanically depresses the denominator and can bias later revenue
indices upward. Changes can also reflect survivor composition. The output is
therefore labelled an **unadjusted revenue retention index** and must not be
described as organic growth, profit or a causal promotion effect.

## Comparability rule

All cohorts remain in the long output for auditability. Comparative matrices
and heatmaps display only cohorts containing at least 30 households. In this
dataset, nearly all households first appear in the first four periods, while
later cohort sizes are too small for stable comparison.

## Automated checks

The pipeline verifies:

- cohort sizes reconcile to the 2,500 observed households;
- age-zero customer retention equals 100%;
- active households never exceed cohort size;
- retention rates remain between zero and one;
- cohort ages are non-negative;
- cohort-period revenue reconciles to source transaction revenue;
- all observed 30-day periods are represented;
- small cohorts are flagged rather than silently excluded.

## Outputs

- `data/powerbi_exports/cohort_retention_long.csv`
- `outputs/tables/customer_retention_matrix.csv`
- `outputs/tables/revenue_retention_matrix.csv`
- `outputs/charts/cohort_customer_retention.png`
- `outputs/charts/cohort_revenue_retention.png`
- `outputs/validation/cohort_retention_quality.csv`

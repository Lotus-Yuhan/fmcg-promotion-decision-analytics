# Commercial Decision Layer

## Purpose

This layer converts customer, coupon, sales-contribution and matched-promotion
evidence into Power BI-ready decision tables. Every metric is labelled as one
of three evidence types:

- `observed_behavior`: directly aggregated from the supplied transactions,
  campaign or redemption data;
- `quasi_experimental_estimate`: derived from the matched promotion DiD; or
- `assumption_only_scenario`: calculated from user-editable cost, margin and
  scaling assumptions.

This separation prevents observed revenue, estimated incrementality and
hypothetical ROI from being presented as if they were the same fact.

## Coupon denominator correction

The 124,548 rows in `coupon.csv` are coupon-to-eligible-product mappings. They
are not 124,548 issued coupons. Dividing the 2,318 redemption transactions by
those mapping rows produces 1.86%, but that figure is not a valid redemption
rate.

The decision layer instead uses the 7,208 unique targeted
household-campaign pairs in `campaign_table` as the exposure denominator. Of
these, 889 contain at least one redemption, producing **12.33% target-household
redemption penetration**. All observed redemption household-campaign pairs
reconcile to a targeted pair.

Coupon UPCs are also usually mapped to many products: only 58 of 1,397
coupon-campaign pairs map uniquely to one product. Redemption is therefore not
forced into a product category when the underlying data do not support that
attribution.

## Customer targeting findings

The 1,584 targeted households are strongly concentrated among existing
high-value customers:

- **High-Value Frequent:** 1,092 targeted households, 6,131
  household-campaign exposures and 13.78% exposure-level redemption
  penetration;
- **Developing Occasional:** 481 targeted households, 1,065 exposures and
  4.13% penetration;
- **Dormant Low-Value:** only 11 targeted households and 12 exposures.

This is an observed targeting and redemption pattern, not a causal segment
response estimate. High-value households may redeem more because campaigns
were designed or delivered differently to them.

## Category decisions

Carbonated soft drinks account for 59.2% of observed beverage sales and juice
for 22.8%. They are the only categories with at least 30 matched events and
three products in the category-specific causal analysis:

- Carbonated soft drinks: +0.39 units per event, 95% CI +0.08 to +0.82.
- Juice: +0.27 units per event, 95% CI +0.02 to +0.53.

Both are labelled `prioritise_controlled_expansion_test`, not “scale without
limits”. Coffee, energy/sports drinks, other beverages, tea and water require
more causal evidence even when their descriptive promotion shares are high.

The SKU table deliberately labels lift as `descriptive_not_causal`. It can be
used to screen SKUs for a future controlled test, not to claim SKU-level
incrementality.

## ROI and budget scenarios

No reliable product cost, gross margin, execution cost or store-wide sales
coverage factor is available. The 243-row scenario table therefore varies:

- causal revenue effect case: lower 95% bound, point estimate and upper bound;
- panel-to-total-sales multiplier: 1, 10 or 25;
- assumed gross margin: 20%, 30% or 40%;
- assumed execution cost per event: $1, $5 or $10; and
- assumed test budget: $1,000, $2,500 or $5,000.

Every row is labelled `assumption_only_scenario`. The most useful output is the
break-even panel-to-total multiplier. For example, using the base causal
revenue estimate, 30% margin and $5 event cost requires a multiplier of about
30.5 merely to break even. This is a threshold for decision discussion, not a
forecast.

## Power BI-ready outputs

| File | Purpose |
|---|---|
| `decision_kpis.csv` | Executive cards with evidence labels and definitions |
| `coupon_campaign_performance.csv` | Campaign targeting and redemption penetration |
| `coupon_segment_performance.csv` | K-Means and RFM coupon response summaries |
| `category_decision_scorecard.csv` | Sales contribution plus reportable causal effects |
| `sku_sales_contribution.csv` | Descriptive SKU screening table |
| `roi_assumption_scenarios.csv` | User-filterable assumption grid |
| `commercial_decision_quality.csv` | Reconciliation and scope checks |

The household-level customer and matched-event files remain local and
Git-ignored.

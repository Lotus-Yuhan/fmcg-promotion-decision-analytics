# Matched Promotion Difference-in-Differences Method

## Decision question and estimand

This extension estimates the average same-week incremental units and revenue
associated with an isolated display or mailer exposure at the
product-store-week level. The treatment may co-occur with a price discount, so
the estimate represents the observed merchandising package rather than a pure
display-only mechanism.

The analysis is observational. Matching, pre-trend checks and placebo tests
make the comparison more credible, but they do not recreate random assignment.

## Eligible products and events

Products must have at least 200 observed units, sales in at least 10 stores and
sales in at least 30 weeks. This leaves 326 beverage SKUs.

An eligible treated event is one display/mailer week with:

- four preceding and four following weeks inside the observed promotion file;
- no other display/mailer exposure for that product-store pair in the complete
  nine-week window;
- at least two positive-sales weeks in the four-week pre-period; and
- at most one retained event per product-store pair.

The last rule prevents repeatedly treating the same unit as independent
evidence.

## Control construction and matching

For each event, control candidates are active product-store pairs in the same
beverage category. They must have no display/mailer exposure in the same
nine-week window and at least two positive-sales pre-period weeks.

Nearest-neighbour matching uses standardised Euclidean distance over:

- mean pre-period units and revenue;
- pre-period unit trend and number of positive weeks;
- average realised pre-period price; and
- units in each of weeks -4, -3, -2 and -1.

Matches with distance above 2.0 are removed as outside acceptable common
support. Exact same-product or same-store matches are identified in the audit
file, but most usable controls are different products within the same category.
The matching therefore balances observed demand history rather than claiming
product identity.

## Estimator and uncertainty

For event (i), the same-week unit effect is:

$$
\widehat{\tau}_i =
(Y_{i,T,0}-\bar{Y}_{i,T,pre})
-(Y_{i,C,0}-\bar{Y}_{i,C,pre}).
$$

The reported effect is the mean across matched events. Ninety-five-percent
confidence intervals use 1,000 bootstrap draws clustered by treated product so
events belonging to the same SKU are resampled together.

The event-study series subtracts the mean treated-control difference in weeks
-4 to -1 from each relative week. A separate product-level test examines the
difference in pre-period slopes. A pseudo-treatment at week -1, relative to
weeks -4 to -2, provides the pre-period placebo.

## Final sample and findings

The final common-support sample contains 423 events across 139 treated SKUs and
three beverage categories. All nine data and identification checks pass.

- Maximum absolute post-match standardised mean difference: **0.099**.
- Pre-trend slope test: **p = 0.442**.
- Pre-period placebo test: **p = 0.335**.
- Incremental units in the exposure week: **+0.36** per product-store event
  (95% cluster-bootstrap CI: **+0.14 to +0.65**).
- Incremental revenue in the exposure week: **+$0.55** per event
  (95% CI: **+$0.19 to +$0.98**).
- Relative estimates are approximately +45%, but the absolute effect is the
  more decision-useful measure because baseline product-store weekly volume is
  low.

The result is smaller but remains positive under stricter specifications. A
2.5%/97.5% winsorised mean is +0.25 units, while the 324 events with matching
distance at or below 1.0 produce +0.23 units (95% CI: +0.07 to +0.39).

The post-event confidence intervals cross zero. The data therefore support a
temporary same-week sales response, not a persistent sales increase.

Carbonated soft drinks and juice have enough matched events for separate
reporting; other categories are retained in the pooled estimate but suppressed
from the category chart when fewer than 30 events or three products are
available.

## Limitations and interpretation boundary

- Treatment is not randomly assigned; unobserved local merchandising or demand
  shocks can remain after matching.
- Most controls are same-category rather than the identical SKU, because
  high-volume products are often promoted across many stores at once.
- Missing weekly transactions are interpreted as zero observed purchases.
  Requiring pre-period activity reduces, but does not eliminate, the risk that
  a zero represents a temporary assortment or stock-availability issue.
- Display/mailer activity may be bundled with shelf discounts. The estimate is
  not a clean price-elasticity coefficient.
- The Complete Journey panel contains frequent-shopper households and is not a
  census of all store sales.
- Product cost and execution cost are unavailable. Revenue lift is not profit,
  and ROI must remain a scenario assumption.

These limitations mean the result should be described as a matched
quasi-experimental estimate with supportive diagnostics, not definitive proof
of causality.

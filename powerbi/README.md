# Power BI Portfolio Report

Open `FMCG.pbip` in Power BI Desktop. The report uses PBIP/PBIR + TMDL so the
semantic model and every report page are source controlled and reviewable.

## Pages

1. Executive Summary
2. Customer Growth & Segmentation
3. Promotion Incrementality
4. Budget Scenario Planner

## Refresh

The `DataFolderPath` Power Query parameter points to this repository's
`data/powerbi_exports` folder. If the repository moves, update that parameter in
Power BI Desktop, then choose **Refresh**.

## Evidence labels

- `observed_behavior`: descriptive customer, sales and coupon measures.
- `quasi_experimental_estimate`: matched Difference-in-Differences estimates.
- `assumption_only_scenario`: budget and ROI sensitivities using assumed costs,
  gross margin and panel-to-total multipliers.

Raw Dunnhumby files and household-level local analytical exports remain excluded
from redistribution under the repository data-use policy.

## Budget scenario definitions

The parameter slicers are disconnected, strict single-select dropdowns sorted by
numeric value. The saved selections are the defaults (labelled "Default"): Base
point estimate, 10x multiplier, 30% gross margin, $5 per event and $1,000
budget. If nothing is selected, the DAX measures fall back to the same defaults.

- `Events Funded = INT(Budget / Cost per Event)`
- `Projected Incremental Revenue = Events Funded * Panel Effect * Multiplier`
- `Net Contribution = Projected Incremental Revenue * Gross Margin - Budget`
- `ROI = Net Contribution / Budget`
- `Break-even Multiplier = Cost per Event / (Panel Effect * Gross Margin)`

With the defaults, 200 funded events produce $1,093.36 projected incremental
revenue, $328.01 gross profit, -$671.99 net contribution, -67.20% ROI and a
30.49x break-even multiplier.

## Metric definitions

- Coupon Redemption = redeemed targeted household-campaign pairs / all targeted
  household-campaign pairs (889 / 7,208 = 12.33%).
- Incremental Units per Event = event-week treated-control unit difference minus
  the mean treated-control difference across weeks -4 to -1, averaged over 423
  matched product-store events.
- High Value Revenue Share = High-Value Frequent segment observed whole-store
  revenue / observed whole-store revenue.
- Segment coupon redemption = redeemed household-campaign exposures / targeted
  household-campaign exposures within each segment. Dormant Low-Value has 12
  targeted exposures and zero observed redemptions.

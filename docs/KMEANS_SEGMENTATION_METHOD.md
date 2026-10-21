# K-Means Segmentation Method

## Purpose

K-Means provides a data-driven comparison to the rule-based RFM lifecycle
segments. The purpose is not to replace business judgement, but to test whether
households form repeatable behavioural groups when multiple Customer 360
features are considered together.

## Features

The model uses 11 behavioural features:

- recency, basket frequency and monetary value;
- average basket value, active weeks and average purchase gap;
- category breadth;
- discount-basket and coupon-basket rates;
- beverage basket penetration and beverage promotion share.

Continuous positive variables are winsorised at the 1st and 99th percentiles,
log-transformed and standardised. Rate variables are winsorised and
standardised without a log transform. Missing purchase gaps are median-imputed.

Demographics are deliberately excluded because they cover only 801 of 2,500
households and several fields are anonymised.

## Selecting K

Candidate solutions from K=2 through K=8 are compared using:

- silhouette score;
- Calinski-Harabasz score;
- Davies-Bouldin index;
- inertia;
- mean and minimum pairwise Adjusted Rand Index across five random seeds.

K=2 has the strongest silhouette score but provides only a broad engaged versus
low-engagement split. K=3 is selected as the business solution because it adds
an interpretable middle-engagement group while retaining near-perfect random-
seed stability. This trade-off is explicit rather than hidden.

## Stability

Two stability checks are reported:

1. Pairwise Adjusted Rand Index across seeds 11, 29, 47, 71 and 97.
2. Adjusted Rand Index between models independently fitted on the first 80% of
   the observation window and the full observation window for common households.

Random-seed stability is very high. Time-window stability is moderate, showing
that customer assignments evolve as more behaviour is observed. Cluster labels
should therefore be refreshed rather than treated as permanent traits.

## Business labels

Numeric cluster IDs are converted into labels from aggregate profiles:

- **High-Value Frequent:** highest mean monetary value and high frequency.
- **Dormant Low-Value:** longest recency and lowest engagement.
- **Developing Occasional:** middle-frequency and middle-value households.

Discount and promotion rates are similar across the three final clusters. The
model therefore does not support naming a cluster "price sensitive". Promotion-
oriented behaviour remains a separate observed proxy in Customer 360.

## Limitations

- K-Means assumes roughly spherical clusters under Euclidean distance.
- Results depend on feature definitions and the observation window.
- Internal cluster metrics do not prove commercial value or causal response.
- PCA is used only as a diagnostic projection and loses information.
- Labels describe observed behaviour, not fixed customer identities.

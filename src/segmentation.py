"""
segmentation.py — rule-based RFM + promo-behavior segmentation on beverage households.

Segments (priority order: ties broken by priority below):
  1. High-Value Beverage Buyers   — beverage_spend >= Q3 of beverage_spend
  2. Coupon-Driven Shoppers       — coupon_usage_rate >= 0.10 (coupons are rare; 10% is meaningful)
  3. Promo-Sensitive Shoppers     — promo_purchase_share >= 0.40
  4. Low-Engagement Shoppers      — everyone else

Priority: High-Value > Coupon-Driven > Promo-Sensitive > Low-Engagement.
Coupon-Driven ranks above Promo-Sensitive because coupon usage requires explicit opt-in
behaviour (clipping/scanning), making it a stronger, more actionable signal than receiving
a shelf discount passively.
"""

import pathlib
import numpy as np
import pandas as pd

PROCESSED_DIR = pathlib.Path(__file__).parent.parent / "data" / "processed"
POWERBI_DIR = pathlib.Path(__file__).parent.parent / "data" / "powerbi_exports"

PROMO_SHARE_THRESHOLD = 0.40
COUPON_RATE_THRESHOLD = 0.10


def compute_household_features() -> pd.DataFrame:
    """
    Compute per-household RFM + promo features using:
      - Full transactions (for total_spend, total_baskets, avg_basket_value, recency)
      - Beverage transactions parquet (pre-built with is_promo flags)
    Returns one row per household that transacted in beverages.
    """
    txn_full = pd.read_parquet(PROCESSED_DIR / "transactions.parquet")
    txn_bev = pd.read_parquet(PROCESSED_DIR / "beverage_transactions.parquet")

    # ── Full-basket metrics ──────────────────────────────────────────────────
    max_day_global = txn_full["day"].max()

    full_agg = (
        txn_full.groupby("household_key")
        .agg(
            total_spend=("sales_value", "sum"),
            total_baskets=("basket_id", "nunique"),
            last_day=("day", "max"),
        )
        .reset_index()
    )
    full_agg["avg_basket_value"] = full_agg["total_spend"] / full_agg["total_baskets"]
    full_agg["recency_days"] = max_day_global - full_agg["last_day"]
    full_agg = full_agg.drop(columns=["last_day"])

    # ── Beverage metrics ─────────────────────────────────────────────────────
    bev_basic = (
        txn_bev.groupby("household_key")
        .agg(
            beverage_spend=("sales_value", "sum"),
            beverage_units=("quantity", "sum"),
            beverage_baskets=("basket_id", "nunique"),
        )
        .reset_index()
    )

    # promo revenue within beverages
    bev_promo = (
        txn_bev[txn_bev["is_promo"]]
        .groupby("household_key")["sales_value"]
        .sum()
        .reset_index()
        .rename(columns={"sales_value": "beverage_promo_revenue"})
    )

    # coupon usage: baskets where coupon_disc < 0
    bev_coupon_baskets = (
        txn_bev[txn_bev["coupon_disc"].fillna(0) < 0]
        .groupby("household_key")["basket_id"]
        .nunique()
        .reset_index()
        .rename(columns={"basket_id": "coupon_baskets"})
    )

    # repeat purchase rate: fraction of bev baskets that are not the first
    # = (beverage_baskets - 1) / max(beverage_baskets - 1, 1)  — 0 for single-visit households
    # This equals (beverage_baskets - 1) / max(beverage_baskets - 1, 1) = 1 for multi-visit,
    # and 0 for single-visit. Simplify: repeat_purchase_rate = 0 if beverage_baskets == 1 else 1.
    # More nuanced: count how many baskets follow the first → beverage_baskets - 1,
    # divided by max(beverage_baskets - 1, 1).
    # For a household with N bev baskets: (N-1)/max(N-1,1).

    # ── Merge all beverage features ──────────────────────────────────────────
    bev_agg = bev_basic.merge(bev_promo, on="household_key", how="left")
    bev_agg = bev_agg.merge(bev_coupon_baskets, on="household_key", how="left")
    bev_agg["beverage_promo_revenue"] = bev_agg["beverage_promo_revenue"].fillna(0)
    bev_agg["coupon_baskets"] = bev_agg["coupon_baskets"].fillna(0).astype(int)

    bev_agg["promo_purchase_share"] = np.where(
        bev_agg["beverage_spend"] > 0,
        bev_agg["beverage_promo_revenue"] / bev_agg["beverage_spend"],
        0.0,
    )
    bev_agg["coupon_usage_rate"] = (
        bev_agg["coupon_baskets"] / bev_agg["beverage_baskets"].clip(lower=1)
    )
    # repeat_purchase_rate: fraction of possible repeat occasions that happened.
    # A household with N beverage baskets had N-1 opportunities to return after the first visit.
    # We scale by the study period (102 weeks) to express: what share of weeks did they buy bev?
    # = beverage_baskets / 102 (observed purchase frequency per week of study)
    # Capped at 1.0 to handle edge cases.
    STUDY_WEEKS = 102
    bev_agg["repeat_purchase_rate"] = (
        bev_agg["beverage_baskets"] / STUDY_WEEKS
    ).clip(upper=1.0)

    # ── Merge full + bev ─────────────────────────────────────────────────────
    features = bev_agg.merge(full_agg, on="household_key", how="left")

    features["beverage_basket_penetration"] = (
        features["beverage_baskets"] / features["total_baskets"].clip(lower=1)
    )

    # RFM aliases
    features["frequency"] = features["total_baskets"]
    features["monetary"] = features["beverage_spend"]

    return features.reset_index(drop=True)


def assign_segments(features: pd.DataFrame) -> pd.DataFrame:
    """
    Rule-based segmentation. Priority: High-Value > Coupon-Driven > Promo-Sensitive > Low-Engagement.
    """
    q3_bev_spend = features["beverage_spend"].quantile(0.75)

    high_value = features["beverage_spend"] >= q3_bev_spend
    coupon_driven = (~high_value) & (features["coupon_usage_rate"] >= COUPON_RATE_THRESHOLD)
    promo_sensitive = (~high_value) & (~coupon_driven) & (
        features["promo_purchase_share"] >= PROMO_SHARE_THRESHOLD
    )
    low_engagement = ~(high_value | coupon_driven | promo_sensitive)

    features = features.copy()
    features["segment"] = "Low-Engagement Shoppers"
    features.loc[promo_sensitive, "segment"] = "Promo-Sensitive Shoppers"
    features.loc[coupon_driven, "segment"] = "Coupon-Driven Shoppers"
    features.loc[high_value, "segment"] = "High-Value Beverage Buyers"

    return features


if __name__ == "__main__":
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Computing household features ===")
    features = compute_household_features()
    print(f"Households with beverage transactions: {len(features):,}")

    print("\n=== Assigning segments ===")
    segmented = assign_segments(features)

    seg_summary = (
        segmented.groupby("segment")
        .agg(
            household_count=("household_key", "count"),
            avg_beverage_spend=("beverage_spend", "mean"),
            avg_promo_share=("promo_purchase_share", "mean"),
            avg_repeat_rate=("repeat_purchase_rate", "mean"),
            total_beverage_spend=("beverage_spend", "sum"),
        )
        .reset_index()
    )
    total_bev = seg_summary["total_beverage_spend"].sum()
    seg_summary["beverage_revenue_share"] = seg_summary["total_beverage_spend"] / total_bev

    print("\nSegment summary:")
    print(seg_summary[[
        "segment", "household_count", "avg_beverage_spend",
        "avg_promo_share", "avg_repeat_rate", "beverage_revenue_share"
    ]].to_string(index=False))

    # ── Write outputs ─────────────────────────────────────────────────────────
    hhseg_path = PROCESSED_DIR / "household_segments.parquet"
    segmented.to_parquet(hhseg_path, index=False, engine="pyarrow")
    print(f"\nwrote {hhseg_path} ({len(segmented):,} rows)")

    # dim_households: merge demographics where available
    demo = pd.read_parquet(PROCESSED_DIR / "demographics.parquet")
    dim_hh = segmented.merge(demo, on="household_key", how="left")
    dim_hh_path = POWERBI_DIR / "dim_households.csv"
    dim_hh.to_csv(dim_hh_path, index=False)
    # The current official Complete Journey release anonymises several
    # demographic labels as classification_1, classification_2, etc., whereas
    # older releases exposed fields such as age_desc.  Measure coverage from
    # the source household keys instead of relying on one release-specific
    # demographic column.
    demo_households = set(demo["household_key"].dropna())
    demographic_coverage = dim_hh["household_key"].isin(demo_households).sum()
    print(f"wrote {dim_hh_path} ({len(dim_hh):,} rows, "
          f"{demographic_coverage:,} with demographics)")

    # household_segments summary CSV
    seg_csv_cols = [
        "segment", "household_count", "avg_beverage_spend",
        "avg_promo_share", "avg_repeat_rate",
    ]
    seg_csv_path = POWERBI_DIR / "household_segments.csv"
    seg_summary[seg_csv_cols].to_csv(seg_csv_path, index=False)
    print(f"wrote {seg_csv_path}")

"""
kpi_builder.py — 15+ KPI table and what-if scenario generator.

All KPIs are computed from real data. What-if scenarios are directional only
and are labelled as such in every output row.
"""

import pathlib
import numpy as np
import pandas as pd

PROCESSED_DIR = pathlib.Path(__file__).parent.parent / "data" / "processed"
POWERBI_DIR = pathlib.Path(__file__).parent.parent / "data" / "powerbi_exports"

# Discount levels for what-if grid
DISCOUNT_LEVELS = [0.0, 0.05, 0.10, 0.15, 0.20]
# Elasticity cap: never project more than 5x unit lift from a discount
MAX_LIFT_CAP = 5.0
WHATIF_NOTES = "Directional scenario only — not causal"


def compute_kpis() -> pd.DataFrame:
    """
    Returns long-form KPI table with columns:
    kpi_name, kpi_value, kpi_unit, kpi_category
    """
    txn_full = pd.read_parquet(PROCESSED_DIR / "transactions.parquet")
    bev_txn = pd.read_parquet(PROCESSED_DIR / "beverage_transactions.parquet")
    pp = pd.read_parquet(PROCESSED_DIR / "promotion_performance.parquet")
    coupon = pd.read_parquet(PROCESSED_DIR / "coupon.parquet")
    coupon_redempt = pd.read_parquet(PROCESSED_DIR / "coupon_redempt.parquet")
    seg = pd.read_parquet(PROCESSED_DIR / "household_segments.parquet")

    # ── Revenue KPIs ──────────────────────────────────────────────────────────
    total_revenue = txn_full["sales_value"].sum()
    bev_revenue = bev_txn["sales_value"].sum()
    bev_units = bev_txn["quantity"].sum()
    bev_avg_price = bev_txn["unit_price"].mean()  # mean of per-line unit prices

    promo_revenue = bev_txn.loc[bev_txn["is_promo"], "sales_value"].sum()
    non_promo_revenue = bev_txn.loc[~bev_txn["is_promo"], "sales_value"].sum()
    bev_promo_rev_pct = promo_revenue / bev_revenue * 100
    bev_non_promo_rev_pct = non_promo_revenue / bev_revenue * 100

    csd_revenue = bev_txn.loc[
        bev_txn["beverage_category"] == "Carbonated Soft Drinks", "sales_value"
    ].sum()
    csd_rev_share = csd_revenue / bev_revenue * 100

    # ── Promotion lift KPIs ───────────────────────────────────────────────────
    # Weighted mean: weight each product's lift by its units_sold
    lift_df = pp[
        pp["promotion_lift"].notna() & np.isfinite(pp["promotion_lift"])
    ].copy()
    # Use all products that have computable lift (not only qualified subset)
    weighted_mean_lift = np.average(
        lift_df["promotion_lift"],
        weights=lift_df["units_sold"].clip(lower=0.01),
    )
    median_lift = lift_df["promotion_lift"].median()

    # ── Customer KPIs ─────────────────────────────────────────────────────────
    # Coupon redemption rate: total redeemed / total distributed
    coupon_redemption_rate = len(coupon_redempt) / len(coupon) * 100

    # Basket metrics
    basket_full = (
        txn_full.groupby("basket_id")["sales_value"].sum()
    )
    avg_basket_value = basket_full.mean()

    bev_baskets = (
        bev_txn.groupby("basket_id")["sales_value"].sum()
    )
    avg_bev_basket_value = bev_baskets.mean()

    # Per-household metrics (households that bought beverages)
    hh_bev = (
        bev_txn.groupby("household_key")
        .agg(bev_spend=("sales_value", "sum"), bev_units=("quantity", "sum"))
        .reset_index()
    )
    bev_households = len(hh_bev)
    rev_per_hh = hh_bev["bev_spend"].mean()
    units_per_hh = hh_bev["bev_units"].mean()

    # Beverage repeat purchase rate: share of households who made >= 2 bev purchases
    bev_basket_counts = bev_txn.groupby("household_key")["basket_id"].nunique()
    bev_repeat_rate = (bev_basket_counts >= 2).mean() * 100

    # ── Segment KPIs ─────────────────────────────────────────────────────────
    total_seg_hh = len(seg)
    hv_share = (seg["segment"] == "High-Value Beverage Buyers").sum() / total_seg_hh * 100
    ps_share = (seg["segment"] == "Promo-Sensitive Shoppers").sum() / total_seg_hh * 100

    # ── Assemble KPI table ────────────────────────────────────────────────────
    rows = [
        # Revenue
        ("Total Revenue (All Categories)", total_revenue, "USD", "Revenue"),
        ("Beverage Revenue", bev_revenue, "USD", "Revenue"),
        ("Beverage Units Sold", bev_units, "units", "Revenue"),
        ("Beverage Avg Selling Price", bev_avg_price, "USD/unit", "Revenue"),
        ("Carbonated Soft Drinks Revenue Share of Beverages", csd_rev_share, "%", "Mix"),
        # Promo
        ("Beverage Promo Revenue %", bev_promo_rev_pct, "%", "Promo"),
        ("Beverage Non-Promo Revenue %", bev_non_promo_rev_pct, "%", "Promo"),
        ("Mean Promotion Lift (Beverages, Unit-Weighted)", weighted_mean_lift, "ratio", "Promo"),
        ("Median Promotion Lift (Beverages)", median_lift, "ratio", "Promo"),
        ("Coupon Redemption Rate", coupon_redemption_rate, "%", "Promo"),
        # Customer
        ("Beverage Repeat Purchase Rate (% of Households)", bev_repeat_rate, "%", "Customer"),
        ("Avg Basket Value (All Categories)", avg_basket_value, "USD", "Customer"),
        ("Avg Beverage Basket Value", avg_bev_basket_value, "USD", "Customer"),
        ("Revenue per Beverage Household", rev_per_hh, "USD", "Customer"),
        ("Units per Beverage Household", units_per_hh, "units", "Customer"),
        # Mix / Segments
        ("High-Value Customer Share (% of Beverage HHs)", hv_share, "%", "Customer"),
        ("Promo-Sensitive Customer Share (% of Beverage HHs)", ps_share, "%", "Customer"),
    ]

    kpi_df = pd.DataFrame(rows, columns=["kpi_name", "kpi_value", "kpi_unit", "kpi_category"])
    return kpi_df


def build_what_if_scenarios() -> pd.DataFrame:
    """
    Directional what-if scenarios for each beverage_category × discount_level × coupon.

    Elasticity proxy: from observed promo vs non-promo velocity ratio and
    effective discount pct within promo transactions.
    assumed_lift_factor = 1 + (discount_pct / observed_eff_disc_pct) * (obs_ratio - 1)
    Capped at MAX_LIFT_CAP.
    """
    bev_txn = pd.read_parquet(PROCESSED_DIR / "beverage_transactions.parquet")

    # ── Compute observed elasticity proxy per category ────────────────────────
    cat_promo = (
        bev_txn[bev_txn["is_promo"]]
        .groupby("beverage_category")
        .agg(
            promo_units=("quantity", "sum"),
            promo_revenue=("sales_value", "sum"),
            promo_discount_amount=("discount_amount", "sum"),
            promo_weeks=("week_no", "nunique"),
        )
        .reset_index()
    )

    cat_nonpromo = (
        bev_txn[~bev_txn["is_promo"]]
        .groupby("beverage_category")
        .agg(
            non_promo_units=("quantity", "sum"),
            non_promo_revenue=("sales_value", "sum"),
            non_promo_weeks=("week_no", "nunique"),
        )
        .reset_index()
    )

    cat = cat_promo.merge(cat_nonpromo, on="beverage_category", how="outer")
    cat = cat.fillna(0)

    cat["promo_velocity"] = cat["promo_units"] / cat["promo_weeks"].clip(lower=1)
    cat["non_promo_velocity"] = cat["non_promo_units"] / cat["non_promo_weeks"].clip(lower=1)

    # observed units ratio (promo velocity / non-promo velocity)
    cat["obs_units_ratio"] = np.where(
        cat["non_promo_velocity"] > 0,
        cat["promo_velocity"] / cat["non_promo_velocity"],
        1.0,
    )

    # gross revenue for promo baselines
    cat_baseline = (
        bev_txn.groupby("beverage_category")
        .agg(
            baseline_revenue=("sales_value", "sum"),
            baseline_units=("quantity", "sum"),
        )
        .reset_index()
    )
    cat = cat.merge(cat_baseline, on="beverage_category", how="left")

    # effective discount pct on promo transactions
    cat["eff_disc_pct"] = np.where(
        cat["promo_revenue"] > 0,
        cat["promo_discount_amount"] / (cat["promo_revenue"] + cat["promo_discount_amount"]),
        0.0,
    )
    # Clamp eff_disc_pct to [0.01, 0.50] to avoid division by near-zero
    cat["eff_disc_pct"] = cat["eff_disc_pct"].clip(lower=0.01, upper=0.50)

    # ── Build scenario grid ────────────────────────────────────────────────────
    scenarios = []
    scenario_id = 0

    for _, row in cat.iterrows():
        for disc_pct in DISCOUNT_LEVELS:
            for coupon_applied in [False, True]:
                effective_disc = disc_pct + (0.01 if coupon_applied else 0.0)
                coupon_volume_bump = 0.02 if coupon_applied else 0.0

                if disc_pct == 0 and not coupon_applied:
                    lift_factor = 1.0
                else:
                    # elasticity proxy
                    if row["obs_units_ratio"] > 1.0 and row["eff_disc_pct"] > 0:
                        lift_factor = 1.0 + (
                            disc_pct / row["eff_disc_pct"]
                        ) * (row["obs_units_ratio"] - 1.0)
                    else:
                        lift_factor = 1.0
                    lift_factor = min(lift_factor, MAX_LIFT_CAP)
                    lift_factor += coupon_volume_bump

                proj_units = row["baseline_units"] * lift_factor
                avg_price = (
                    row["baseline_revenue"] / row["baseline_units"]
                    if row["baseline_units"] > 0 else 0.0
                )
                net_price_factor = 1.0 - effective_disc
                proj_revenue = proj_units * avg_price * net_price_factor
                rev_delta_pct = (
                    (proj_revenue - row["baseline_revenue"]) / row["baseline_revenue"] * 100
                    if row["baseline_revenue"] > 0 else 0.0
                )

                scenarios.append({
                    "scenario_id": scenario_id,
                    "beverage_category": row["beverage_category"],
                    "discount_pct": disc_pct,
                    "coupon_applied": coupon_applied,
                    "baseline_revenue": round(row["baseline_revenue"], 2),
                    "baseline_units": int(row["baseline_units"]),
                    "projected_units": round(proj_units, 1),
                    "projected_revenue": round(proj_revenue, 2),
                    "revenue_delta_pct": round(rev_delta_pct, 2),
                    "notes_label": WHATIF_NOTES,
                })
                scenario_id += 1

    return pd.DataFrame(scenarios)


if __name__ == "__main__":
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Computing KPIs ===")
    kpi_df = compute_kpis()
    print(kpi_df.to_string(index=False))

    kpi_path = POWERBI_DIR / "commercial_kpis.csv"
    kpi_df.to_csv(kpi_path, index=False)
    print(f"\nwrote {kpi_path} ({len(kpi_df)} KPIs)")

    print("\n=== Building what-if scenarios ===")
    scenarios = build_what_if_scenarios()
    print(f"Total scenarios: {len(scenarios)}")
    print("\nSample (first 10 rows):")
    print(scenarios.head(10).to_string(index=False))

    whatif_path = POWERBI_DIR / "what_if_scenarios.csv"
    scenarios.to_csv(whatif_path, index=False)
    print(f"\nwrote {whatif_path} ({len(scenarios)} rows)")

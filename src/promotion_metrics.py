"""
promotion_metrics.py — promotion signal construction, lift calculation, and export.

Two independent promotion signals:
  Signal A (causal): display != 0 OR mailer != '0' — from causal_data.csv
  Signal B (discount): retail_disc < 0 OR coupon_disc < 0 OR coupon_match_disc < 0

is_promo = signal_a OR signal_b  (per transaction line)
"""

import pathlib
import numpy as np
import pandas as pd

from src.data_cleaning import load_causal

PROCESSED_DIR = pathlib.Path(__file__).parent.parent / "data" / "processed"
POWERBI_DIR = pathlib.Path(__file__).parent.parent / "data" / "powerbi_exports"

# Minimum observations required before a product enters the lift ranking
MIN_TOTAL_UNITS = 50
MIN_PROMO_WEEKS = 3
MIN_NON_PROMO_WEEKS = 3


def load_beverage_transactions() -> pd.DataFrame:
    """
    Inner-join full transactions to beverage_products on product_id.
    Adds: gross_revenue, discount_amount, unit_price.
    Drops rows with zero or null quantity (can't compute unit price).
    """
    txn = pd.read_parquet(PROCESSED_DIR / "transactions.parquet")
    bev = pd.read_parquet(PROCESSED_DIR / "beverage_products.parquet")

    txn_bev = txn.merge(bev[["product_id", "beverage_category"]], on="product_id", how="inner")

    txn_bev["gross_revenue"] = txn_bev["sales_value"]
    txn_bev["discount_amount"] = -(
        txn_bev["retail_disc"].fillna(0)
        + txn_bev["coupon_disc"].fillna(0)
        + txn_bev["coupon_match_disc"].fillna(0)
    )

    # unit_price: replace zero-quantity with NaN, then drop
    txn_bev["unit_price"] = np.where(
        txn_bev["quantity"] > 0,
        txn_bev["sales_value"] / txn_bev["quantity"],
        np.nan,
    )
    txn_bev = txn_bev.dropna(subset=["unit_price"]).copy()

    return txn_bev.reset_index(drop=True)


def attach_causal_flags(txns_bev: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join causal signals (display, mailer) to beverage transactions.
    Join key: (product_id, store_id, week_no).
    Adds: display_flag, mailer_flag, causal_promo.
    """
    bev_product_ids = set(txns_bev["product_id"].unique().tolist())

    causal = load_causal(product_ids=bev_product_ids)

    causal = causal.rename(columns={"display": "display_raw", "mailer": "mailer_raw"})
    causal = causal.drop_duplicates(subset=["product_id", "store_id", "week_no"])

    df = txns_bev.merge(
        causal[["product_id", "store_id", "week_no", "display_raw", "mailer_raw"]],
        on=["product_id", "store_id", "week_no"],
        how="left",
    )

    # Signal A: display != 0 OR mailer != '0'
    df["display_flag"] = df["display_raw"].fillna(0).astype(str).ne("0")
    df["mailer_flag"] = df["mailer_raw"].fillna("0").astype(str).ne("0")
    df["causal_promo"] = df["display_flag"] | df["mailer_flag"]

    df = df.drop(columns=["display_raw", "mailer_raw"])

    return df.reset_index(drop=True)


def compute_is_promo(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds is_promo boolean column.
    Signal B: any discount col is negative.
    is_promo = causal_promo OR signal_b.
    """
    signal_b = (
        (df["retail_disc"].fillna(0) < 0)
        | (df["coupon_disc"].fillna(0) < 0)
        | (df["coupon_match_disc"].fillna(0) < 0)
    )
    df = df.copy()
    df["is_promo"] = df["causal_promo"] | signal_b
    return df


def compute_product_promo_table(
    df: pd.DataFrame,
    min_total_units: int = MIN_TOTAL_UNITS,
    min_promo_weeks: int = MIN_PROMO_WEEKS,
    min_non_promo_weeks: int = MIN_NON_PROMO_WEEKS,
) -> pd.DataFrame:
    """
    Per-product promotion performance table with lift calculation.
    Lift is velocity-based: (promo_units / promo_weeks) / (non_promo_units / non_promo_weeks).
    Products with insufficient data are included but flagged — rank only on qualified rows.
    """
    bev = pd.read_parquet(PROCESSED_DIR / "beverage_products.parquet")

    agg = (
        df.groupby("product_id")
        .agg(
            total_revenue=("gross_revenue", "sum"),
            units_sold=("quantity", "sum"),
            avg_selling_price=("unit_price", "mean"),
            promo_revenue=("gross_revenue", lambda s: s[df.loc[s.index, "is_promo"]].sum()),
            non_promo_revenue=("gross_revenue", lambda s: s[~df.loc[s.index, "is_promo"]].sum()),
            promo_units=("quantity", lambda s: s[df.loc[s.index, "is_promo"]].sum()),
            non_promo_units=("quantity", lambda s: s[~df.loc[s.index, "is_promo"]].sum()),
        )
        .reset_index()
    )

    # Compute promo_weeks and non_promo_weeks per product
    promo_weeks_df = (
        df[df["is_promo"]]
        .groupby("product_id")["week_no"]
        .nunique()
        .reset_index()
        .rename(columns={"week_no": "promo_weeks"})
    )
    non_promo_weeks_df = (
        df[~df["is_promo"]]
        .groupby("product_id")["week_no"]
        .nunique()
        .reset_index()
        .rename(columns={"week_no": "non_promo_weeks"})
    )

    agg = agg.merge(promo_weeks_df, on="product_id", how="left")
    agg = agg.merge(non_promo_weeks_df, on="product_id", how="left")
    agg["promo_weeks"] = agg["promo_weeks"].fillna(0).astype(int)
    agg["non_promo_weeks"] = agg["non_promo_weeks"].fillna(0).astype(int)

    # Velocity and lift
    agg["promo_velocity"] = agg["promo_units"] / agg["promo_weeks"].clip(lower=1)
    agg["non_promo_velocity"] = agg["non_promo_units"] / agg["non_promo_weeks"].clip(lower=1)

    # Lift: NaN where non_promo_weeks == 0 (no baseline)
    agg["promotion_lift"] = np.where(
        agg["non_promo_weeks"] > 0,
        agg["promo_velocity"] / agg["non_promo_velocity"].replace(0, np.nan),
        np.nan,
    )

    # Join beverage_category
    agg = agg.merge(bev[["product_id", "beverage_category"]], on="product_id", how="left")

    # Category avg lift (exclude NaN and inf, use only qualified products for the mean)
    qualified_mask = (
        (agg["units_sold"] >= min_total_units)
        & (agg["promo_weeks"] >= min_promo_weeks)
        & (agg["non_promo_weeks"] >= min_non_promo_weeks)
    )
    lift_for_cat_avg = agg.loc[qualified_mask, ["beverage_category", "promotion_lift"]].copy()
    lift_for_cat_avg = lift_for_cat_avg[
        np.isfinite(lift_for_cat_avg["promotion_lift"])
    ]
    cat_avg_lift = (
        lift_for_cat_avg.groupby("beverage_category")["promotion_lift"]
        .mean()
        .reset_index()
        .rename(columns={"promotion_lift": "category_avg_lift"})
    )

    agg = agg.merge(cat_avg_lift, on="beverage_category", how="left")
    agg["lift_index_vs_category"] = agg["promotion_lift"] / agg["category_avg_lift"]

    return agg.reset_index(drop=True)


def _build_beverage_transactions_full() -> pd.DataFrame:
    """End-to-end: load → causal → is_promo. Returns fully-flagged beverage txn df."""
    txns_bev = load_beverage_transactions()
    txns_bev = attach_causal_flags(txns_bev)
    txns_bev = compute_is_promo(txns_bev)
    return txns_bev


if __name__ == "__main__":
    import sys

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Building beverage transactions with promo flags ===")
    df = _build_beverage_transactions_full()

    total_bev_revenue = df["gross_revenue"].sum()
    total_bev_units = df["quantity"].sum()
    promo_share = df["is_promo"].mean()

    print(f"Total beverage revenue:      ${total_bev_revenue:,.2f}")
    print(f"Total beverage units:        {total_bev_units:,}")
    print(f"Promo transaction share:     {promo_share:.1%}")
    print(f"Total beverage txn lines:    {len(df):,}")

    print("\n=== Computing product promo table ===")
    prod_table = compute_product_promo_table(df)

    # Qualified subset for ranking
    qualified = prod_table[
        (prod_table["units_sold"] >= MIN_TOTAL_UNITS)
        & (prod_table["promo_weeks"] >= MIN_PROMO_WEEKS)
        & (prod_table["non_promo_weeks"] >= MIN_NON_PROMO_WEEKS)
        & np.isfinite(prod_table["promotion_lift"].fillna(np.nan))
    ].copy()

    print(f"\nQualified products for lift ranking: {len(qualified):,} "
          f"(of {len(prod_table):,} total beverage SKUs with transactions)")

    print("\nTop 20 products by promotion_lift (qualified only):")
    top20 = qualified.nlargest(20, "promotion_lift")[
        ["product_id", "beverage_category", "promotion_lift",
         "lift_index_vs_category", "category_avg_lift",
         "promo_weeks", "non_promo_weeks", "units_sold", "total_revenue"]
    ]
    print(top20.to_string(index=False))

    # Threshold reporting
    q_lift = qualified.dropna(subset=["lift_index_vs_category"])
    q_lift = q_lift[np.isfinite(q_lift["lift_index_vs_category"])]
    top_lift_index = q_lift["lift_index_vs_category"].max() if len(q_lift) > 0 else np.nan
    count_2x = (q_lift["lift_index_vs_category"] >= 2.0).sum()
    count_24x = (q_lift["lift_index_vs_category"] >= 2.4).sum()

    print(f"\nTop lift_index_vs_category:          {top_lift_index:.3f}")
    print(f"Products >= 2.0x lift index:         {count_2x}")
    print(f"Products >= 2.4x lift index:         {count_24x}")

    if count_24x == 0:
        print("  NOTE: No product reached 2.4x category-avg lift index with "
              f"min_total_units={MIN_TOTAL_UNITS}, min_promo_weeks={MIN_PROMO_WEEKS}, "
              f"min_non_promo_weeks={MIN_NON_PROMO_WEEKS}.")

    # Write intermediates
    print("\n=== Writing outputs ===")
    bev_txn_path = PROCESSED_DIR / "beverage_transactions.parquet"
    df.to_parquet(bev_txn_path, index=False, engine="pyarrow")
    print(f"wrote {bev_txn_path} ({len(df):,} rows)")

    promo_path = PROCESSED_DIR / "promotion_performance.parquet"
    prod_table.to_parquet(promo_path, index=False, engine="pyarrow")
    print(f"wrote {promo_path} ({len(prod_table):,} rows)")

    csv_path = POWERBI_DIR / "promotion_performance.csv"
    prod_table.to_csv(csv_path, index=False)
    print(f"wrote {csv_path}")

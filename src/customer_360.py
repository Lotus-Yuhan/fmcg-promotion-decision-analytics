"""Build an independently developed Customer 360 table and RFM segments.

Row-level household outputs are written only to ignored local directories.
Committed outputs contain aggregate segment summaries and quality checks.

RFM definitions
---------------
Recency
    Days between a household's last observed purchase and the dataset end day.
Frequency
    Number of distinct baskets during the full observation window.
Monetary
    Total observed sales value across all baskets.

Promotion-oriented behaviour is an observational proxy based on the share of
baskets containing a retail or coupon discount. It must not be interpreted as
a causal estimate of price sensitivity.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd


ROOT_DIR = pathlib.Path(__file__).parent.parent
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
LOCAL_EXPORT_DIR = ROOT_DIR / "data" / "local_exports"
POWERBI_DIR = ROOT_DIR / "data" / "powerbi_exports"
VALIDATION_DIR = ROOT_DIR / "outputs" / "validation"

RFM_QUANTILES = 5


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide while returning zero when the denominator is zero."""
    result = np.divide(
        numerator.astype(float),
        denominator.astype(float),
        out=np.zeros(len(numerator), dtype=float),
        where=denominator.to_numpy() != 0,
    )
    return pd.Series(result, index=numerator.index)


def _quantile_score(series: pd.Series, higher_is_better: bool) -> pd.Series:
    """Return stable 1-5 quantile scores while preserving tied values."""
    percentile_rank = series.rank(method="average", pct=True)
    score = np.ceil(percentile_rank * RFM_QUANTILES).clip(1, RFM_QUANTILES)
    score = score.astype("int8")
    if not higher_is_better:
        score = (RFM_QUANTILES + 1 - score).astype("int8")
    return score


def _build_purchase_interval_features(transactions: pd.DataFrame) -> pd.DataFrame:
    """Calculate purchase-day counts and mean gaps between shopping days."""
    purchase_days = (
        transactions[["household_key", "day"]]
        .drop_duplicates()
        .sort_values(["household_key", "day"])
    )
    purchase_days["days_since_previous_purchase"] = (
        purchase_days.groupby("household_key")["day"].diff()
    )
    return (
        purchase_days.groupby("household_key")
        .agg(
            purchase_days=("day", "size"),
            avg_days_between_purchases=("days_since_previous_purchase", "mean"),
        )
        .reset_index()
    )


def build_customer_360(cutoff_day: int | None = None) -> pd.DataFrame:
    """Create one analytical row per observed household.

    ``cutoff_day`` supports time-window robustness checks. When supplied, only
    transactions observed on or before that relative day are used.
    """
    transactions = pd.read_parquet(PROCESSED_DIR / "transactions.parquet")
    products = pd.read_parquet(PROCESSED_DIR / "products.parquet")
    beverage = pd.read_parquet(PROCESSED_DIR / "beverage_transactions.parquet")
    demographics = pd.read_parquet(PROCESSED_DIR / "demographics.parquet")

    full_end_day = int(transactions["day"].max())
    if cutoff_day is not None:
        if cutoff_day < int(transactions["day"].min()) or cutoff_day > full_end_day:
            raise ValueError(
                f"cutoff_day must be within the observed range; received {cutoff_day}"
            )
        transactions = transactions.loc[transactions["day"] <= cutoff_day].copy()
        beverage = beverage.loc[beverage["day"] <= cutoff_day].copy()

    observation_end_day = int(transactions["day"].max())

    basket_level = (
        transactions.assign(
            has_discount=(
                (transactions["retail_disc"] < 0)
                | (transactions["coupon_disc"] < 0)
                | (transactions["coupon_match_disc"] < 0)
            ),
            has_coupon=(
                (transactions["coupon_disc"] < 0)
                | (transactions["coupon_match_disc"] < 0)
            ),
        )
        .groupby(["household_key", "basket_id"], as_index=False)
        .agg(
            basket_day=("day", "max"),
            basket_week=("week_no", "max"),
            basket_sales=("sales_value", "sum"),
            basket_units=("quantity", "sum"),
            basket_has_discount=("has_discount", "max"),
            basket_has_coupon=("has_coupon", "max"),
        )
    )

    customer = (
        basket_level.groupby("household_key")
        .agg(
            first_purchase_day=("basket_day", "min"),
            last_purchase_day=("basket_day", "max"),
            frequency_baskets=("basket_id", "size"),
            monetary_value=("basket_sales", "sum"),
            total_units=("basket_units", "sum"),
            active_weeks=("basket_week", "nunique"),
            avg_basket_value=("basket_sales", "mean"),
            median_basket_value=("basket_sales", "median"),
            discount_baskets=("basket_has_discount", "sum"),
            coupon_baskets=("basket_has_coupon", "sum"),
        )
        .reset_index()
    )
    customer["recency_days"] = observation_end_day - customer["last_purchase_day"]
    customer["observed_tenure_days"] = (
        customer["last_purchase_day"] - customer["first_purchase_day"] + 1
    )
    customer["discount_basket_rate"] = _safe_divide(
        customer["discount_baskets"], customer["frequency_baskets"]
    )
    customer["coupon_basket_rate"] = _safe_divide(
        customer["coupon_baskets"], customer["frequency_baskets"]
    )

    intervals = _build_purchase_interval_features(transactions)
    customer = customer.merge(intervals, on="household_key", how="left")

    household_products = transactions[["household_key", "product_id"]].drop_duplicates()
    category_features = (
        household_products.merge(
            products[["product_id", "department", "commodity_desc"]],
            on="product_id",
            how="left",
            validate="many_to_one",
        )
        .groupby("household_key")
        .agg(
            unique_products=("product_id", "nunique"),
            department_breadth=("department", "nunique"),
            category_breadth=("commodity_desc", "nunique"),
        )
        .reset_index()
    )
    customer = customer.merge(category_features, on="household_key", how="left")

    beverage_basic = (
        beverage.groupby("household_key")
        .agg(
            beverage_spend=("sales_value", "sum"),
            beverage_units=("quantity", "sum"),
            beverage_baskets=("basket_id", "nunique"),
        )
        .reset_index()
    )
    beverage_promo = (
        beverage.loc[beverage["is_promo"]]
        .groupby("household_key")["sales_value"]
        .sum()
        .rename("beverage_promo_revenue")
        .reset_index()
    )
    beverage_features = beverage_basic.merge(
        beverage_promo, on="household_key", how="left"
    )
    beverage_features["beverage_promo_revenue"] = beverage_features[
        "beverage_promo_revenue"
    ].fillna(0.0)

    customer = customer.merge(beverage_features, on="household_key", how="left")
    beverage_columns = [
        "beverage_spend",
        "beverage_units",
        "beverage_baskets",
        "beverage_promo_revenue",
    ]
    customer[beverage_columns] = customer[beverage_columns].fillna(0)
    customer["beverage_promo_share"] = _safe_divide(
        customer["beverage_promo_revenue"], customer["beverage_spend"]
    )
    customer["beverage_basket_penetration"] = _safe_divide(
        customer["beverage_baskets"], customer["frequency_baskets"]
    )

    customer["r_score"] = _quantile_score(
        customer["recency_days"], higher_is_better=False
    )
    customer["f_score"] = _quantile_score(
        customer["frequency_baskets"], higher_is_better=True
    )
    customer["m_score"] = _quantile_score(
        customer["monetary_value"], higher_is_better=True
    )
    customer["rfm_score"] = (
        customer["r_score"].astype(str)
        + customer["f_score"].astype(str)
        + customer["m_score"].astype(str)
    )
    customer["rfm_total"] = customer[["r_score", "f_score", "m_score"]].sum(axis=1)
    customer = assign_rfm_segments(customer)
    customer = assign_customer_personas(customer)

    customer = customer.merge(
        demographics, on="household_key", how="left", validate="one_to_one"
    )
    customer["has_demographics"] = customer[demographics.columns.difference(
        ["household_key"]
    )].notna().any(axis=1)

    customer.insert(1, "observation_end_day", observation_end_day)
    return customer.sort_values("household_key").reset_index(drop=True)


def assign_rfm_segments(customer: pd.DataFrame) -> pd.DataFrame:
    """Assign mutually exclusive, interpretable RFM lifecycle segments."""
    result = customer.copy()
    r, f, m = result["r_score"], result["f_score"], result["m_score"]

    result["rfm_segment"] = "Needs Attention"
    result.loc[(r <= 2) & (f <= 2), "rfm_segment"] = "Hibernating"
    result.loc[(r <= 2) & ((f >= 4) | (m >= 4)), "rfm_segment"] = (
        "At-Risk High-Value"
    )
    result.loc[(r >= 4) & (f <= 2), "rfm_segment"] = "New / Low-Frequency"
    result.loc[(r >= 4) & (f.between(2, 3)), "rfm_segment"] = "Promising"
    result.loc[(r >= 3) & (m >= 4), "rfm_segment"] = "Big Spenders"
    result.loc[(r >= 3) & (f >= 4) & (m >= 3), "rfm_segment"] = "Loyal"
    result.loc[(r >= 4) & (f >= 4) & (m >= 4), "rfm_segment"] = "Champions"
    return result


def assign_customer_personas(customer: pd.DataFrame) -> pd.DataFrame:
    """Add action-oriented personas using RFM and observed discount behaviour."""
    result = customer.copy()
    promo_threshold = result["discount_basket_rate"].quantile(0.75)

    result["high_value_flag"] = result["m_score"] >= 4
    result["low_frequency_flag"] = result["f_score"] <= 2
    result["promotion_oriented_flag"] = (
        (result["discount_basket_rate"] >= promo_threshold)
        & (result["frequency_baskets"] >= result["frequency_baskets"].median())
    )

    result["customer_persona"] = "Core Customers"
    result.loc[result["low_frequency_flag"], "customer_persona"] = (
        "Low-Frequency Customers"
    )
    result.loc[result["promotion_oriented_flag"], "customer_persona"] = (
        "Promotion-Oriented Customers"
    )
    result.loc[
        result["high_value_flag"] & (result["r_score"] <= 2),
        "customer_persona",
    ] = "High-Value At Risk"
    result.loc[
        result["high_value_flag"]
        & (result["f_score"] >= 4)
        & (result["r_score"] >= 3),
        "customer_persona",
    ] = "High-Value Loyal"
    return result


def build_segment_summary(customer: pd.DataFrame, group_column: str) -> pd.DataFrame:
    """Create a disclosure-safe aggregate summary for a segment field."""
    summary = (
        customer.groupby(group_column, dropna=False)
        .agg(
            household_count=("household_key", "size"),
            total_revenue=("monetary_value", "sum"),
            avg_recency_days=("recency_days", "mean"),
            avg_frequency_baskets=("frequency_baskets", "mean"),
            avg_monetary_value=("monetary_value", "mean"),
            avg_discount_basket_rate=("discount_basket_rate", "mean"),
            avg_coupon_basket_rate=("coupon_basket_rate", "mean"),
            total_beverage_spend=("beverage_spend", "sum"),
        )
        .reset_index()
    )
    summary["household_share"] = summary["household_count"] / len(customer)
    summary["revenue_share"] = summary["total_revenue"] / customer[
        "monetary_value"
    ].sum()
    summary = summary.round(
        {
            "total_revenue": 2,
            "avg_recency_days": 2,
            "avg_frequency_baskets": 2,
            "avg_monetary_value": 2,
            "avg_discount_basket_rate": 4,
            "avg_coupon_basket_rate": 4,
            "total_beverage_spend": 2,
            "household_share": 4,
            "revenue_share": 4,
        }
    )
    return summary.sort_values("total_revenue", ascending=False).reset_index(drop=True)


def validate_customer_360(customer: pd.DataFrame) -> pd.DataFrame:
    """Return machine-readable quality checks for the analytical table."""
    transactions = pd.read_parquet(
        PROCESSED_DIR / "transactions.parquet", columns=["household_key", "sales_value"]
    )
    source_households = int(transactions["household_key"].nunique())
    source_revenue = float(transactions["sales_value"].sum())
    customer_revenue = float(customer["monetary_value"].sum())

    checks = [
        ("row_count_matches_source_households", len(customer), source_households, len(customer) == source_households),
        ("household_key_is_unique", int(customer["household_key"].nunique()), len(customer), customer["household_key"].is_unique),
        ("household_key_missing_count", int(customer["household_key"].isna().sum()), 0, customer["household_key"].notna().all()),
        ("negative_recency_count", int((customer["recency_days"] < 0).sum()), 0, (customer["recency_days"] >= 0).all()),
        ("nonpositive_frequency_count", int((customer["frequency_baskets"] <= 0).sum()), 0, (customer["frequency_baskets"] > 0).all()),
        ("revenue_reconciliation_difference", round(customer_revenue - source_revenue, 6), 0, np.isclose(customer_revenue, source_revenue, atol=0.01)),
        ("rfm_segment_missing_count", int(customer["rfm_segment"].isna().sum()), 0, customer["rfm_segment"].notna().all()),
        ("demographic_household_coverage", int(customer["has_demographics"].sum()), "informational", True),
    ]
    return pd.DataFrame(
        checks, columns=["check_name", "observed_value", "expected_value", "passed"]
    )


def main() -> None:
    """Build local detail outputs and public aggregate artifacts."""
    print("=== Building Customer 360 ===")
    customer = build_customer_360()
    print(f"households: {len(customer):,}")
    print(f"columns:    {len(customer.columns):,}")

    quality = validate_customer_360(customer)
    print("\n=== Quality checks ===")
    print(quality.to_string(index=False))
    if not quality["passed"].all():
        failed = quality.loc[~quality["passed"], "check_name"].tolist()
        raise ValueError(f"Customer 360 validation failed: {failed}")

    rfm_summary = build_segment_summary(customer, "rfm_segment")
    persona_summary = build_segment_summary(customer, "customer_persona")

    LOCAL_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    parquet_path = PROCESSED_DIR / "customer_360.parquet"
    local_csv_path = LOCAL_EXPORT_DIR / "customer_360.csv"
    rfm_summary_path = POWERBI_DIR / "rfm_segment_summary.csv"
    persona_summary_path = POWERBI_DIR / "customer_persona_summary.csv"
    quality_path = VALIDATION_DIR / "customer_360_quality.csv"

    customer.to_parquet(parquet_path, index=False, engine="pyarrow")
    customer.to_csv(local_csv_path, index=False)
    rfm_summary.to_csv(rfm_summary_path, index=False)
    persona_summary.to_csv(persona_summary_path, index=False)
    quality.to_csv(quality_path, index=False)

    print("\n=== RFM segment summary ===")
    print(rfm_summary.to_string(index=False))
    print("\n=== Customer persona summary ===")
    print(persona_summary.to_string(index=False))
    print("\nWrote local household-level outputs:")
    print(f"  {parquet_path}")
    print(f"  {local_csv_path}")
    print("Wrote publishable aggregate outputs:")
    print(f"  {rfm_summary_path}")
    print(f"  {persona_summary_path}")
    print(f"  {quality_path}")


if __name__ == "__main__":
    main()

"""Observed first-purchase cohort retention for Complete Journey households.

The source data provide relative day numbers rather than calendar dates, so the
analysis uses fixed 30-day periods. Cohorts represent the first purchase
observed inside this dataset; they must not be described as verified customer
acquisition cohorts because purchases before the observation window are not
available.
"""

from __future__ import annotations

import pathlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT_DIR = pathlib.Path(__file__).parent.parent
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
POWERBI_DIR = ROOT_DIR / "data" / "powerbi_exports"
TABLE_DIR = ROOT_DIR / "outputs" / "tables"
CHART_DIR = ROOT_DIR / "outputs" / "charts"
VALIDATION_DIR = ROOT_DIR / "outputs" / "validation"

PERIOD_DAYS = 30
MIN_COMPARABLE_COHORT_SIZE = 30
DISPLAY_HORIZON = 12


def build_cohort_retention() -> tuple[pd.DataFrame, int, float]:
    """Build a complete observed cohort-age panel, including zero-activity cells."""
    transactions = pd.read_parquet(
        PROCESSED_DIR / "transactions.parquet",
        columns=["household_key", "basket_id", "day", "sales_value"],
    )
    transactions["activity_period"] = (
        (transactions["day"] - 1) // PERIOD_DAYS
    ).astype(int)
    maximum_period = int(transactions["activity_period"].max())
    source_revenue = float(transactions["sales_value"].sum())

    household_period = (
        transactions.groupby(["household_key", "activity_period"], as_index=False)
        .agg(
            period_revenue=("sales_value", "sum"),
            period_baskets=("basket_id", "nunique"),
        )
    )
    cohort_lookup = (
        household_period.groupby("household_key", as_index=False)["activity_period"]
        .min()
        .rename(columns={"activity_period": "cohort_period"})
    )
    household_period = household_period.merge(
        cohort_lookup, on="household_key", how="left", validate="many_to_one"
    )
    household_period["cohort_age"] = (
        household_period["activity_period"] - household_period["cohort_period"]
    )

    cohort_sizes = (
        cohort_lookup.groupby("cohort_period", as_index=False)
        .agg(cohort_size=("household_key", "nunique"))
    )
    observed = (
        household_period.groupby(["cohort_period", "cohort_age"], as_index=False)
        .agg(
            active_households=("household_key", "nunique"),
            cohort_period_revenue=("period_revenue", "sum"),
            cohort_period_baskets=("period_baskets", "sum"),
        )
    )

    # Build every observable cohort-age cell. Missing observed activity becomes
    # zero; ages beyond the dataset end are omitted rather than treated as churn.
    complete_cells = []
    for row in cohort_sizes.itertuples(index=False):
        max_age = maximum_period - int(row.cohort_period)
        complete_cells.extend(
            {
                "cohort_period": int(row.cohort_period),
                "cohort_age": cohort_age,
                "activity_period": int(row.cohort_period) + cohort_age,
                "max_observable_age": max_age,
            }
            for cohort_age in range(max_age + 1)
        )
    panel = pd.DataFrame(complete_cells)
    panel = panel.merge(
        cohort_sizes, on="cohort_period", how="left", validate="many_to_one"
    )
    panel = panel.merge(
        observed,
        on=["cohort_period", "cohort_age"],
        how="left",
        validate="one_to_one",
    )
    for column in [
        "active_households",
        "cohort_period_revenue",
        "cohort_period_baskets",
    ]:
        panel[column] = panel[column].fillna(0)

    initial_revenue = (
        panel.loc[panel["cohort_age"] == 0, ["cohort_period", "cohort_period_revenue"]]
        .rename(columns={"cohort_period_revenue": "cohort_initial_revenue"})
    )
    panel = panel.merge(
        initial_revenue, on="cohort_period", how="left", validate="many_to_one"
    )
    panel["customer_retention_rate"] = (
        panel["active_households"] / panel["cohort_size"]
    )
    panel["revenue_retention_index"] = np.divide(
        panel["cohort_period_revenue"],
        panel["cohort_initial_revenue"],
        out=np.zeros(len(panel), dtype=float),
        where=panel["cohort_initial_revenue"].to_numpy() != 0,
    )
    panel["left_censored_cohort"] = panel["cohort_period"] == 0
    panel["small_cohort_flag"] = (
        panel["cohort_size"] < MIN_COMPARABLE_COHORT_SIZE
    )
    panel["comparison_eligible"] = ~panel["small_cohort_flag"]
    panel["cohort_label"] = panel["cohort_period"].map(
        lambda value: f"P{int(value):02d}"
    )

    integer_columns = [
        "cohort_period",
        "cohort_age",
        "activity_period",
        "max_observable_age",
        "cohort_size",
        "active_households",
        "cohort_period_baskets",
    ]
    panel[integer_columns] = panel[integer_columns].astype(int)
    panel = panel.round(
        {
            "cohort_period_revenue": 2,
            "cohort_initial_revenue": 2,
            "customer_retention_rate": 4,
            "revenue_retention_index": 4,
        }
    )
    return panel.sort_values(["cohort_period", "cohort_age"]), maximum_period, source_revenue


def build_matrix(
    panel: pd.DataFrame, value_column: str, eligible_only: bool = False
) -> pd.DataFrame:
    """Pivot the long cohort panel while preserving unobservable cells as NaN."""
    data = panel
    if eligible_only:
        data = data.loc[data["comparison_eligible"]]
    matrix = data.pivot(
        index="cohort_label", columns="cohort_age", values=value_column
    )
    matrix.columns = [f"age_{int(column):02d}" for column in matrix.columns]
    return matrix.sort_index()


def validate_cohort_panel(
    panel: pd.DataFrame, source_revenue: float, expected_periods: int
) -> pd.DataFrame:
    """Return validation evidence for cohort construction and censoring rules."""
    cohort_once = panel.drop_duplicates("cohort_period")
    age_zero = panel.loc[panel["cohort_age"] == 0]
    panel_revenue = float(panel["cohort_period_revenue"].sum())
    checks = [
        (
            "cohort_sizes_reconcile_to_households",
            int(cohort_once["cohort_size"].sum()),
            2500,
            int(cohort_once["cohort_size"].sum()) == 2500,
        ),
        (
            "age_zero_retention_equals_one",
            float(age_zero["customer_retention_rate"].min()),
            1.0,
            np.allclose(age_zero["customer_retention_rate"], 1.0),
        ),
        (
            "active_households_not_above_cohort_size",
            int((panel["active_households"] > panel["cohort_size"]).sum()),
            0,
            (panel["active_households"] <= panel["cohort_size"]).all(),
        ),
        (
            "retention_rate_within_zero_one",
            int((~panel["customer_retention_rate"].between(0, 1)).sum()),
            0,
            panel["customer_retention_rate"].between(0, 1).all(),
        ),
        (
            "negative_cohort_age_count",
            int((panel["cohort_age"] < 0).sum()),
            0,
            (panel["cohort_age"] >= 0).all(),
        ),
        (
            "revenue_reconciliation_difference",
            round(panel_revenue - source_revenue, 6),
            0,
            np.isclose(panel_revenue, source_revenue, atol=0.01),
        ),
        (
            "observed_period_count",
            int(panel["activity_period"].nunique()),
            expected_periods,
            int(panel["activity_period"].nunique()) == expected_periods,
        ),
        (
            "comparison_eligible_cohort_count",
            int(cohort_once["comparison_eligible"].sum()),
            "informational",
            True,
        ),
        (
            "small_cohort_count",
            int(cohort_once["small_cohort_flag"].sum()),
            "informational",
            True,
        ),
    ]
    return pd.DataFrame(
        checks, columns=["check_name", "observed_value", "expected_value", "passed"]
    )


def write_heatmap(
    matrix: pd.DataFrame, title: str, output_path: pathlib.Path
) -> None:
    """Write an interview-ready retention heatmap for comparable cohorts."""
    display = matrix.iloc[:, : DISPLAY_HORIZON + 1]
    fig_width = max(10, 0.75 * len(display.columns))
    fig_height = max(4, 0.65 * len(display.index) + 2)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    sns.heatmap(
        display,
        annot=True,
        fmt=".0%",
        cmap="Blues",
        vmin=0,
        mask=display.isna(),
        linewidths=0.5,
        cbar_kws={"label": "Index / rate"},
        ax=ax,
    )
    ax.set_title(title, fontsize=14, weight="bold", pad=14)
    ax.set_xlabel("30-day periods since first observed purchase")
    ax.set_ylabel("First observed purchase cohort")
    fig.text(
        0.01,
        0.01,
        "Only cohorts with at least 30 households are shown. P00 is left-censored.",
        fontsize=9,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    """Build, validate and export cohort retention artifacts."""
    print("=== Building observed first-purchase cohorts ===")
    panel, maximum_period, source_revenue = build_cohort_retention()
    expected_periods = maximum_period + 1
    quality = validate_cohort_panel(panel, source_revenue, expected_periods)

    print(f"30-day periods: {expected_periods}")
    print(f"cohorts:        {panel['cohort_period'].nunique()}")
    print("\n=== Quality checks ===")
    print(quality.to_string(index=False))
    if not quality["passed"].all():
        failed = quality.loc[~quality["passed"], "check_name"].tolist()
        raise ValueError(f"Cohort retention validation failed: {failed}")

    customer_matrix = build_matrix(panel, "customer_retention_rate")
    revenue_matrix = build_matrix(panel, "revenue_retention_index")
    heatmap_panel = panel.loc[panel["comparison_eligible"]].copy()
    heatmap_panel["cohort_display"] = heatmap_panel.apply(
        lambda row: (
            f"{row['cohort_label']} (n={int(row['cohort_size'])}, left-censored)"
            if row["left_censored_cohort"]
            else f"{row['cohort_label']} (n={int(row['cohort_size'])})"
        ),
        axis=1,
    )
    comparable_customer_matrix = heatmap_panel.pivot(
        index="cohort_display", columns="cohort_age", values="customer_retention_rate"
    ).sort_index()
    comparable_customer_matrix.columns = [
        f"age_{int(column):02d}" for column in comparable_customer_matrix.columns
    ]
    comparable_revenue_matrix = build_matrix(
        panel, "revenue_retention_index", eligible_only=True
    )

    POWERBI_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    long_path = POWERBI_DIR / "cohort_retention_long.csv"
    overview_path = POWERBI_DIR / "cohort_overview.csv"
    customer_matrix_path = TABLE_DIR / "customer_retention_matrix.csv"
    revenue_matrix_path = TABLE_DIR / "revenue_retention_matrix.csv"
    quality_path = VALIDATION_DIR / "cohort_retention_quality.csv"
    customer_chart_path = CHART_DIR / "cohort_customer_retention.png"
    revenue_chart_path = CHART_DIR / "cohort_revenue_retention.png"

    panel.to_csv(long_path, index=False)
    customer_matrix.to_csv(customer_matrix_path)
    revenue_matrix.to_csv(revenue_matrix_path)
    quality.to_csv(quality_path, index=False)
    write_heatmap(
        comparable_customer_matrix,
        "Customer Retention by Observed First-Purchase Cohort",
        customer_chart_path,
    )
    write_heatmap(
        comparable_revenue_matrix,
        "Unadjusted Revenue Retention Index by Observed First-Purchase Cohort",
        revenue_chart_path,
    )

    cohort_overview = panel.loc[panel["cohort_age"] == 0, [
        "cohort_label",
        "cohort_size",
        "left_censored_cohort",
        "small_cohort_flag",
        "max_observable_age",
    ]].rename(columns={"max_observable_age": "overview_max_observable_age"})
    cohort_overview.to_csv(overview_path, index=False)
    print("\n=== Cohort overview ===")
    print(cohort_overview.to_string(index=False))
    print("\nWrote:")
    for path in [
        long_path,
        overview_path,
        customer_matrix_path,
        revenue_matrix_path,
        quality_path,
        customer_chart_path,
        revenue_chart_path,
    ]:
        print(f"  {path}")


if __name__ == "__main__":
    main()

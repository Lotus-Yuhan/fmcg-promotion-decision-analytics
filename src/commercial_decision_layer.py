"""Build Power BI-ready commercial decision tables with evidence labels.

Observed facts, quasi-experimental estimates and assumption-only scenarios are
kept separate so revenue lift is never presented as observed profit or ROI.
"""

from __future__ import annotations

import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = pathlib.Path(__file__).parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
POWERBI_DIR = ROOT / "data" / "powerbi_exports"
LOCAL_EXPORT_DIR = ROOT / "data" / "local_exports"
OUTPUT_DIR = ROOT / "outputs"
CHART_DIR = OUTPUT_DIR / "charts"
VALIDATION_DIR = OUTPUT_DIR / "validation"


def build_coupon_campaign_performance() -> tuple[pd.DataFrame, pd.DataFrame]:
    campaign_table = pd.read_parquet(PROCESSED_DIR / "campaign_table.parquet")
    campaign_desc = pd.read_parquet(PROCESSED_DIR / "campaign_desc.parquet")
    coupon = pd.read_parquet(PROCESSED_DIR / "coupon.parquet")
    redemption = pd.read_parquet(PROCESSED_DIR / "coupon_redempt.parquet")

    targets = campaign_table[
        ["campaign", "household_key", "description"]
    ].drop_duplicates(["campaign", "household_key"])
    redemption_pairs = (
        redemption.groupby(["campaign", "household_key"], observed=True)
        .agg(
            redemption_transactions=("coupon_upc", "size"),
            unique_coupons_redeemed=("coupon_upc", "nunique"),
            first_redemption_day=("day", "min"),
            last_redemption_day=("day", "max"),
        )
        .reset_index()
    )
    target_outcomes = targets.merge(
        redemption_pairs,
        on=["campaign", "household_key"],
        how="left",
        validate="one_to_one",
    )
    target_outcomes["redeemed_flag"] = target_outcomes[
        "redemption_transactions"
    ].notna()
    target_outcomes["redemption_transactions"] = target_outcomes[
        "redemption_transactions"
    ].fillna(0).astype(int)

    mapping = (
        coupon.groupby("campaign", observed=True)
        .agg(
            coupon_upcs_defined=("coupon_upc", "nunique"),
            coupon_product_mapping_rows=("product_id", "size"),
            coupon_products_covered=("product_id", "nunique"),
        )
        .reset_index()
    )
    campaign = (
        target_outcomes.groupby("campaign", observed=True)
        .agg(
            campaign_type=("description", "first"),
            targeted_households=("household_key", "nunique"),
            household_campaign_exposures=("household_key", "size"),
            redeeming_households=("redeemed_flag", "sum"),
            redemption_transactions=("redemption_transactions", "sum"),
        )
        .reset_index()
        .merge(
            campaign_desc[["campaign", "start_day", "end_day"]],
            on="campaign",
            how="left",
            validate="one_to_one",
        )
        .merge(mapping, on="campaign", how="left", validate="one_to_one")
    )
    campaign["campaign_duration_days"] = (
        campaign["end_day"] - campaign["start_day"] + 1
    )
    campaign["campaign_type"] = campaign["campaign_type"].str.replace(
        r"^Type([A-Z])$", r"Type \1", regex=True
    )
    campaign["target_household_redemption_penetration"] = (
        campaign["redeeming_households"] / campaign["targeted_households"]
    )
    campaign["redemption_transactions_per_100_targets"] = (
        100 * campaign["redemption_transactions"] / campaign["targeted_households"]
    )
    campaign["evidence_type"] = "observed_behavior"
    campaign["denominator_note"] = (
        "redeeming targeted households / unique targeted households"
    )
    return campaign.sort_values("campaign"), target_outcomes


def build_coupon_segment_performance(
    target_outcomes: pd.DataFrame,
) -> pd.DataFrame:
    profiles = pd.read_csv(LOCAL_EXPORT_DIR / "customer_360_kmeans.csv")
    profile_cols = ["household_key", "kmeans_segment", "rfm_segment"]
    data = target_outcomes.merge(
        profiles[profile_cols], on="household_key", how="left", validate="many_to_one"
    )
    rows = []
    for dimension in ["kmeans_segment", "rfm_segment"]:
        summary = (
            data.groupby(dimension, observed=True)
            .agg(
                targeted_households=("household_key", "nunique"),
                household_campaign_exposures=("household_key", "size"),
                redeemed_household_campaigns=("redeemed_flag", "sum"),
                redemption_transactions=("redemption_transactions", "sum"),
            )
            .reset_index()
            .rename(columns={dimension: "segment_name"})
        )
        summary["segment_dimension"] = dimension
        summary["redemption_penetration"] = (
            summary["redeemed_household_campaigns"]
            / summary["household_campaign_exposures"]
        )
        summary["redemptions_per_100_exposures"] = (
            100
            * summary["redemption_transactions"]
            / summary["household_campaign_exposures"]
        )
        summary["evidence_type"] = "observed_behavior"
        rows.append(summary)
    return pd.concat(rows, ignore_index=True)[
        [
            "segment_dimension",
            "segment_name",
            "targeted_households",
            "household_campaign_exposures",
            "redeemed_household_campaigns",
            "redemption_transactions",
            "redemption_penetration",
            "redemptions_per_100_exposures",
            "evidence_type",
        ]
    ]


def build_category_scorecard() -> pd.DataFrame:
    tx = pd.read_parquet(PROCESSED_DIR / "beverage_transactions.parquet")
    causal_category = pd.read_csv(
        OUTPUT_DIR / "tables" / "promotion_category_heterogeneity.csv"
    )
    tx = tx.copy()
    tx["coupon_line_flag"] = (
        tx["coupon_disc"].fillna(0).lt(0)
        | tx["coupon_match_disc"].fillna(0).lt(0)
    )
    tx["promo_sales_value"] = tx["gross_revenue"].where(tx["is_promo"], 0.0)
    tx["merchandising_sales_value"] = tx["gross_revenue"].where(
        tx["causal_promo"], 0.0
    )
    tx["coupon_sales_value"] = tx["gross_revenue"].where(
        tx["coupon_line_flag"], 0.0
    )
    category = (
        tx.groupby("beverage_category", observed=True)
        .agg(
            observed_sales_value=("gross_revenue", "sum"),
            observed_units=("quantity", "sum"),
            households=("household_key", "nunique"),
            products=("product_id", "nunique"),
            stores=("store_id", "nunique"),
            promo_sales_value=("promo_sales_value", "sum"),
            merchandising_sales_value=("merchandising_sales_value", "sum"),
            coupon_sales_value=("coupon_sales_value", "sum"),
        )
        .reset_index()
    )
    total = category["observed_sales_value"].sum()
    category["sales_contribution"] = category["observed_sales_value"] / total
    category["promo_sales_share"] = (
        category["promo_sales_value"] / category["observed_sales_value"]
    )
    category["merchandising_sales_share"] = (
        category["merchandising_sales_value"]
        / category["observed_sales_value"]
    )
    category["coupon_sales_share"] = (
        category["coupon_sales_value"] / category["observed_sales_value"]
    )
    category = category.merge(
        causal_category,
        on="beverage_category",
        how="left",
        validate="one_to_one",
    )
    category["causal_evidence_status"] = np.where(
        category["did_units"].notna(),
        "matched_did_reportable",
        "insufficient_matched_events",
    )
    category["decision_status"] = np.select(
        [
            category["did_units_ci_low"].gt(0),
            category["did_units"].notna(),
        ],
        [
            "prioritise_controlled_expansion_test",
            "continue_test_no_clear_effect",
        ],
        default="collect_more_causal_evidence",
    )
    category["observed_metric_label"] = "observed_behavior"
    category["effect_metric_label"] = np.where(
        category["did_units"].notna(), "quasi_experimental_estimate", "not_estimated"
    )
    return category.sort_values("observed_sales_value", ascending=False)


def build_sku_contribution() -> pd.DataFrame:
    promotion = pd.read_parquet(PROCESSED_DIR / "promotion_performance.parquet")
    result = promotion.copy()
    result["total_beverage_revenue_share"] = (
        result["total_revenue"] / result["total_revenue"].sum()
    )
    result["category_revenue_share"] = result.groupby(
        "beverage_category", observed=True
    )["total_revenue"].transform(lambda values: values / values.sum())
    result["lift_evidence_qualified"] = (
        (result["units_sold"] >= 50)
        & (result["promo_weeks"] >= 3)
        & (result["non_promo_weeks"] >= 3)
        & np.isfinite(result["promotion_lift"])
    )
    result["evidence_type"] = "descriptive_not_causal"
    result["decision_note"] = np.where(
        result["lift_evidence_qualified"],
        "screen_for_follow-up causal test",
        "insufficient descriptive support",
    )
    keep = [
        "product_id",
        "beverage_category",
        "total_revenue",
        "units_sold",
        "promo_revenue",
        "non_promo_revenue",
        "promo_weeks",
        "non_promo_weeks",
        "promotion_lift",
        "lift_index_vs_category",
        "total_beverage_revenue_share",
        "category_revenue_share",
        "lift_evidence_qualified",
        "evidence_type",
        "decision_note",
    ]
    return result[keep].sort_values("total_revenue", ascending=False)


def build_roi_scenarios() -> pd.DataFrame:
    causal = pd.read_csv(POWERBI_DIR / "promotion_causal_summary.csv").set_index(
        "metric"
    )
    effect_row = causal.loc["did_incremental_revenue_per_event"]
    effect_cases = {
        "conservative_95ci_low": float(effect_row["ci_low"]),
        "base_point_estimate": float(effect_row["value"]),
        "upside_95ci_high": float(effect_row["ci_high"]),
    }
    records = []
    scenario_id = 0
    for effect_case, panel_effect in effect_cases.items():
        for multiplier in [1, 10, 25]:
            for margin in [0.20, 0.30, 0.40]:
                for event_cost in [1.0, 5.0, 10.0]:
                    for budget in [1_000.0, 2_500.0, 5_000.0]:
                        scenario_id += 1
                        events = np.floor(budget / event_cost)
                        incremental_revenue = events * panel_effect * multiplier
                        incremental_gross_profit = incremental_revenue * margin
                        net_contribution = incremental_gross_profit - budget
                        roi = net_contribution / budget
                        break_even_multiplier = event_cost / (panel_effect * margin)
                        records.append(
                            {
                                "scenario_id": scenario_id,
                                "effect_case": effect_case,
                                "panel_incremental_revenue_per_event": panel_effect,
                                "assumed_panel_to_total_multiplier": multiplier,
                                "assumed_gross_margin_rate": margin,
                                "assumed_execution_cost_per_event": event_cost,
                                "assumed_budget": budget,
                                "events_funded": int(events),
                                "projected_incremental_revenue": incremental_revenue,
                                "projected_incremental_gross_profit": incremental_gross_profit,
                                "projected_net_contribution": net_contribution,
                                "scenario_roi": roi,
                                "break_even_panel_to_total_multiplier": break_even_multiplier,
                                "evidence_type": "assumption_only_scenario",
                                "decision_warning": (
                                    "Not observed ROI: cost, margin and panel-to-total multiplier are assumptions"
                                ),
                            }
                        )
    return pd.DataFrame(records)


def build_decision_kpis(
    campaign: pd.DataFrame,
    target_outcomes: pd.DataFrame,
    category: pd.DataFrame,
) -> pd.DataFrame:
    causal = pd.read_csv(POWERBI_DIR / "promotion_causal_summary.csv").set_index(
        "metric"
    )
    transactions = pd.read_parquet(
        PROCESSED_DIR / "transactions.parquet", columns=["sales_value"]
    )
    profiles = pd.read_csv(POWERBI_DIR / "kmeans_cluster_profile.csv")
    high_value = profiles.loc[
        profiles["kmeans_segment"].eq("High-Value Frequent")
    ].iloc[0]
    redemption_penetration = target_outcomes["redeemed_flag"].mean()
    rows = [
        ("total_store_observed_sales", transactions["sales_value"].sum(), "dollars", "observed_behavior", "sum of observed transaction sales value"),
        ("beverage_observed_sales", category["observed_sales_value"].sum(), "dollars", "observed_behavior", "sum of observed beverage sales value"),
        ("beverage_share_of_store_sales", category["observed_sales_value"].sum() / transactions["sales_value"].sum(), "share", "observed_behavior", "beverage observed sales / total store observed sales"),
        ("target_household_coupon_redemption_penetration", redemption_penetration, "share", "observed_behavior", "redeemed targeted household-campaign pairs / all targeted pairs"),
        ("coupon_campaigns", campaign["campaign"].nunique(), "count", "observed_behavior", "campaigns with targeting and coupon definitions"),
        ("matched_promotion_events", causal.loc["matched_events", "value"], "count", "quasi_experimental_estimate", "events retained after matching and common-support rules"),
        ("incremental_units_per_merchandising_event", causal.loc["did_incremental_units_per_event", "value"], "units", "quasi_experimental_estimate", "matched DiD same-week estimate"),
        ("incremental_revenue_per_merchandising_event", causal.loc["did_incremental_revenue_per_event", "value"], "dollars", "quasi_experimental_estimate", "matched DiD same-week estimate in household panel"),
        ("high_value_frequent_household_share", high_value["household_share"], "share", "observed_behavior", "K-Means segment household share"),
        ("high_value_frequent_revenue_share", high_value["revenue_share"], "share", "observed_behavior", "K-Means segment observed revenue share"),
    ]
    return pd.DataFrame(
        rows, columns=["metric", "value", "unit", "evidence_type", "definition"]
    )


def build_quality_checks(
    campaign: pd.DataFrame,
    target_outcomes: pd.DataFrame,
    segment: pd.DataFrame,
    category: pd.DataFrame,
    sku: pd.DataFrame,
    scenarios: pd.DataFrame,
) -> pd.DataFrame:
    full_redemption = pd.read_parquet(PROCESSED_DIR / "coupon_redempt.parquet")
    target_pairs = target_outcomes[["campaign", "household_key"]]
    redeemed_pairs = full_redemption[["campaign", "household_key"]].drop_duplicates()
    unmatched_redemptions = len(
        redeemed_pairs.merge(
            target_pairs,
            on=["campaign", "household_key"],
            how="left",
            indicator=True,
        ).query("_merge == 'left_only'")
    )
    kmeans_exposures = segment.loc[
        segment["segment_dimension"].eq("kmeans_segment"),
        "household_campaign_exposures",
    ].sum()
    checks = [
        ("campaign_count", campaign["campaign"].nunique(), "30", campaign["campaign"].nunique() == 30),
        ("target_exposure_count", len(target_outcomes), "7208", len(target_outcomes) == 7208),
        ("unmatched_redemption_pairs", unmatched_redemptions, "0", unmatched_redemptions == 0),
        ("campaign_penetration_bounds", int(campaign["target_household_redemption_penetration"].between(0, 1).all()), "1", campaign["target_household_redemption_penetration"].between(0, 1).all()),
        ("segment_exposure_reconciliation", kmeans_exposures, str(len(target_outcomes)), kmeans_exposures == len(target_outcomes)),
        ("category_sales_share_sum", category["sales_contribution"].sum(), "1.0", np.isclose(category["sales_contribution"].sum(), 1.0)),
        ("sku_revenue_reconciliation", sku["total_revenue"].sum(), str(round(category["observed_sales_value"].sum(), 2)), np.isclose(sku["total_revenue"].sum(), category["observed_sales_value"].sum())),
        ("causal_category_rows", category["did_units"].notna().sum(), ">=2", category["did_units"].notna().sum() >= 2),
        ("scenario_row_count", len(scenarios), "243", len(scenarios) == 243),
        ("scenario_evidence_labels", scenarios["evidence_type"].eq("assumption_only_scenario").all(), "True", scenarios["evidence_type"].eq("assumption_only_scenario").all()),
    ]
    return pd.DataFrame(
        checks, columns=["check_name", "observed_value", "expected_value", "passed"]
    )


def plot_coupon_campaigns(campaign: pd.DataFrame) -> None:
    plot = campaign.sort_values("target_household_redemption_penetration")
    fig, ax = plt.subplots(figsize=(10, 8))
    colors = plot["campaign_type"].map(
        {"TypeA": "#2878B5", "TypeB": "#F28E2B", "TypeC": "#59A14F"}
    ).fillna("#999999")
    ax.barh(
        plot["campaign"].astype(str),
        plot["target_household_redemption_penetration"],
        color=colors,
    )
    average_line = ax.axvline(
        campaign["redeeming_households"].sum()
        / campaign["targeted_households"].sum(),
        color="black",
        linestyle="--",
        label="Target-weighted average",
    )
    ax.set_xlabel("Target-household redemption penetration")
    ax.set_ylabel("Campaign")
    ax.set_title("Coupon Redemption Penetration by Campaign")
    ax.xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    legend_items = [
        Patch(color="#2878B5", label="Type A"),
        Patch(color="#F28E2B", label="Type B"),
        Patch(color="#59A14F", label="Type C"),
        average_line,
    ]
    ax.legend(handles=legend_items, loc="lower right")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "coupon_campaign_penetration.png", dpi=180)
    plt.close(fig)


def plot_category_decision(category: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 6))
    observed = category.loc[category["did_units"].notna()].copy()
    missing = category.loc[category["did_units"].isna()].copy()
    ax.scatter(
        missing["sales_contribution"],
        np.zeros(len(missing)),
        s=80,
        alpha=0.55,
        color="grey",
        label="Insufficient causal events",
    )
    ax.scatter(
        observed["sales_contribution"],
        observed["did_units"],
        s=observed["event_count"].clip(lower=30) * 2,
        alpha=0.75,
        color="#2878B5",
        label="Reportable matched DiD",
    )
    for row in observed.itertuples(index=False):
        ax.annotate(
            row.beverage_category,
            (row.sales_contribution, row.did_units),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=9,
        )
    missing_offsets = [-34, -20, -6, 8, 22]
    for offset, row in zip(
        missing_offsets,
        missing.sort_values("sales_contribution").itertuples(index=False),
    ):
        ax.annotate(
            row.beverage_category,
            (row.sales_contribution, 0),
            xytext=(3, offset),
            textcoords="offset points",
            fontsize=8.5,
            color="#555555",
        )
    ax.axhline(0, color="black", linewidth=1)
    ax.set_xlabel("Observed beverage sales contribution")
    ax.set_ylabel("Matched incremental units per event")
    ax.set_title("Category Decision Map: Commercial Scale vs Causal Evidence")
    ax.xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    ax.legend()
    ax.grid(alpha=0.2)
    ax.set_ylim(bottom=-0.045)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "category_decision_map.png", dpi=180)
    plt.close(fig)


def plot_roi_break_even(scenarios: pd.DataFrame) -> None:
    base = scenarios.loc[
        scenarios["effect_case"].eq("base_point_estimate")
        & scenarios["assumed_budget"].eq(1_000.0)
    ].drop_duplicates(
        ["assumed_gross_margin_rate", "assumed_execution_cost_per_event"]
    )
    pivot = base.pivot(
        index="assumed_execution_cost_per_event",
        columns="assumed_gross_margin_rate",
        values="break_even_panel_to_total_multiplier",
    )
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    sns.heatmap(pivot, annot=True, fmt=".1f", cmap="YlOrRd", ax=ax)
    ax.set_xlabel("Assumed gross margin rate")
    ax.set_ylabel("Assumed execution cost per event")
    ax.set_title("Break-even Panel-to-Total Sales Multiplier\n(Base Causal Revenue Estimate)")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "roi_break_even_sensitivity.png", dpi=180)
    plt.close(fig)


def main() -> None:
    for directory in [POWERBI_DIR, CHART_DIR, VALIDATION_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

    print("=== Coupon campaign and customer-segment performance ===")
    campaign, target_outcomes = build_coupon_campaign_performance()
    segment = build_coupon_segment_performance(target_outcomes)

    print("=== Category and SKU contribution ===")
    category = build_category_scorecard()
    sku = build_sku_contribution()

    print("=== Assumption-only ROI scenarios ===")
    scenarios = build_roi_scenarios()
    kpis = build_decision_kpis(campaign, target_outcomes, category)
    quality = build_quality_checks(
        campaign, target_outcomes, segment, category, sku, scenarios
    )

    campaign.to_csv(POWERBI_DIR / "coupon_campaign_performance.csv", index=False)
    segment.to_csv(POWERBI_DIR / "coupon_segment_performance.csv", index=False)
    category.to_csv(POWERBI_DIR / "category_decision_scorecard.csv", index=False)
    sku.to_csv(POWERBI_DIR / "sku_sales_contribution.csv", index=False)
    scenarios.to_csv(POWERBI_DIR / "roi_assumption_scenarios.csv", index=False)
    kpis.to_csv(POWERBI_DIR / "decision_kpis.csv", index=False)
    quality.to_csv(VALIDATION_DIR / "commercial_decision_quality.csv", index=False)

    sns.set_theme(style="whitegrid")
    plot_coupon_campaigns(campaign)
    plot_category_decision(category)
    plot_roi_break_even(scenarios)

    print("\n=== Decision KPIs ===")
    print(kpis.to_string(index=False))
    print("\n=== Coupon segment performance ===")
    print(segment.to_string(index=False))
    print("\n=== Quality checks ===")
    print(quality.to_string(index=False))
    print("\nWrote Power BI-ready decision tables and charts.")


if __name__ == "__main__":
    main()

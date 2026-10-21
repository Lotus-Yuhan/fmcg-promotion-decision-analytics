"""Validated K-Means segmentation built from the local Customer 360 table.

The final three-cluster solution balances statistical evidence, stability and
business interpretability. K=2 has the strongest silhouette score but only
separates broadly engaged from low-engagement households. K=3 is retained as a
more actionable solution because it is highly stable across random seeds while
adding a meaningful middle-engagement group.
"""

from __future__ import annotations

import itertools
import os
import pathlib

os.environ.setdefault("OMP_NUM_THREADS", "10")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.preprocessing import StandardScaler

from src.customer_360 import build_customer_360


ROOT_DIR = pathlib.Path(__file__).parent.parent
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
LOCAL_EXPORT_DIR = ROOT_DIR / "data" / "local_exports"
POWERBI_DIR = ROOT_DIR / "data" / "powerbi_exports"
TABLE_DIR = ROOT_DIR / "outputs" / "tables"
CHART_DIR = ROOT_DIR / "outputs" / "charts"
VALIDATION_DIR = ROOT_DIR / "outputs" / "validation"

FEATURES = [
    "recency_days",
    "frequency_baskets",
    "monetary_value",
    "avg_basket_value",
    "active_weeks",
    "avg_days_between_purchases",
    "category_breadth",
    "discount_basket_rate",
    "coupon_basket_rate",
    "beverage_basket_penetration",
    "beverage_promo_share",
]
LOG_FEATURES = {
    "recency_days",
    "frequency_baskets",
    "monetary_value",
    "avg_basket_value",
    "active_weeks",
    "avg_days_between_purchases",
    "category_breadth",
}
FEATURE_LABELS = {
    "recency_days": "Recency",
    "frequency_baskets": "Basket frequency",
    "monetary_value": "Monetary value",
    "avg_basket_value": "Avg basket value",
    "active_weeks": "Active weeks",
    "avg_days_between_purchases": "Purchase gap",
    "category_breadth": "Category breadth",
    "discount_basket_rate": "Discount basket rate",
    "coupon_basket_rate": "Coupon basket rate",
    "beverage_basket_penetration": "Beverage penetration",
    "beverage_promo_share": "Beverage promo share",
}

CANDIDATE_K = range(2, 9)
SEEDS = [11, 29, 47, 71, 97]
SELECTED_K = 3
FINAL_SEED = 47
TIME_WINDOW_SHARE = 0.80


def prepare_features(customer: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    """Winsorise, log-transform, median-impute and standardise features."""
    transformed = customer[FEATURES].astype(float).copy()
    for column in FEATURES:
        lower, upper = transformed[column].quantile([0.01, 0.99])
        transformed[column] = transformed[column].clip(float(lower), float(upper))
        if column in LOG_FEATURES:
            transformed[column] = np.log1p(transformed[column])

    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    matrix = scaler.fit_transform(imputer.fit_transform(transformed))
    standardised = pd.DataFrame(matrix, columns=FEATURES, index=customer.index)
    return matrix, standardised


def evaluate_candidate_k(matrix: np.ndarray) -> pd.DataFrame:
    """Evaluate K=2..8 across internal metrics and random-seed stability."""
    rows = []
    for k in CANDIDATE_K:
        labels_by_seed = []
        models = []
        for seed in SEEDS:
            model = KMeans(
                n_clusters=k,
                random_state=seed,
                n_init=20,
                max_iter=500,
            ).fit(matrix)
            models.append(model)
            labels_by_seed.append(model.labels_)

        pairwise_ari = [
            adjusted_rand_score(labels_by_seed[left], labels_by_seed[right])
            for left, right in itertools.combinations(range(len(SEEDS)), 2)
        ]
        rows.append(
            {
                "k": k,
                "silhouette_mean": np.mean(
                    [silhouette_score(matrix, labels) for labels in labels_by_seed]
                ),
                "calinski_harabasz_mean": np.mean(
                    [
                        calinski_harabasz_score(matrix, labels)
                        for labels in labels_by_seed
                    ]
                ),
                "davies_bouldin_mean": np.mean(
                    [davies_bouldin_score(matrix, labels) for labels in labels_by_seed]
                ),
                "seed_stability_ari_mean": np.mean(pairwise_ari),
                "seed_stability_ari_min": np.min(pairwise_ari),
                "inertia_mean": np.mean([model.inertia_ for model in models]),
                "selected": k == SELECTED_K,
            }
        )
    return pd.DataFrame(rows).round(4)


def derive_cluster_names(customer: pd.DataFrame) -> dict[int, str]:
    """Name clusters from their observed profile rather than numeric IDs."""
    profile = customer.groupby("kmeans_cluster_id").agg(
        avg_recency=("recency_days", "mean"),
        avg_frequency=("frequency_baskets", "mean"),
        avg_monetary=("monetary_value", "mean"),
    )
    high_value_id = int(profile["avg_monetary"].idxmax())
    remaining = profile.drop(index=high_value_id)
    dormant_id = int(remaining["avg_recency"].idxmax())
    developing_id = int(
        next(cluster_id for cluster_id in profile.index if cluster_id not in {high_value_id, dormant_id})
    )
    return {
        high_value_id: "High-Value Frequent",
        dormant_id: "Dormant Low-Value",
        developing_id: "Developing Occasional",
    }


def fit_final_model(
    customer: pd.DataFrame, matrix: np.ndarray
) -> tuple[pd.DataFrame, KMeans]:
    """Fit the selected K=3 model and attach stable business names."""
    model = KMeans(
        n_clusters=SELECTED_K,
        random_state=FINAL_SEED,
        n_init=50,
        max_iter=500,
    ).fit(matrix)
    result = customer.copy()
    result["kmeans_cluster_id"] = model.labels_.astype(int)
    names = derive_cluster_names(result)
    result["kmeans_segment"] = result["kmeans_cluster_id"].map(names)
    return result, model


def build_cluster_profile(customer: pd.DataFrame) -> pd.DataFrame:
    """Create a public aggregate profile for the final clusters."""
    profile = (
        customer.groupby(["kmeans_cluster_id", "kmeans_segment"], as_index=False)
        .agg(
            household_count=("household_key", "size"),
            total_revenue=("monetary_value", "sum"),
            avg_recency_days=("recency_days", "mean"),
            avg_frequency_baskets=("frequency_baskets", "mean"),
            avg_monetary_value=("monetary_value", "mean"),
            avg_basket_value=("avg_basket_value", "mean"),
            avg_active_weeks=("active_weeks", "mean"),
            avg_purchase_gap_days=("avg_days_between_purchases", "mean"),
            avg_category_breadth=("category_breadth", "mean"),
            avg_discount_basket_rate=("discount_basket_rate", "mean"),
            avg_coupon_basket_rate=("coupon_basket_rate", "mean"),
            avg_beverage_penetration=("beverage_basket_penetration", "mean"),
            avg_beverage_promo_share=("beverage_promo_share", "mean"),
        )
    )
    profile["household_share"] = profile["household_count"] / len(customer)
    profile["revenue_share"] = profile["total_revenue"] / customer[
        "monetary_value"
    ].sum()
    return profile.round(
        {
            "total_revenue": 2,
            "avg_recency_days": 2,
            "avg_frequency_baskets": 2,
            "avg_monetary_value": 2,
            "avg_basket_value": 2,
            "avg_active_weeks": 2,
            "avg_purchase_gap_days": 2,
            "avg_category_breadth": 2,
            "avg_discount_basket_rate": 4,
            "avg_coupon_basket_rate": 4,
            "avg_beverage_penetration": 4,
            "avg_beverage_promo_share": 4,
            "household_share": 4,
            "revenue_share": 4,
        }
    ).sort_values("total_revenue", ascending=False)


def compute_time_window_stability(
    full_customer: pd.DataFrame, full_end_day: int
) -> tuple[float, int, int]:
    """Compare independently refit clusters on 80% and 100% time windows."""
    cutoff_day = int(full_end_day * TIME_WINDOW_SHARE)
    early_customer = build_customer_360(cutoff_day=cutoff_day)
    common_keys = full_customer[["household_key"]].merge(
        early_customer[["household_key"]], on="household_key", how="inner"
    )["household_key"]
    full_common = (
        full_customer.set_index("household_key").loc[common_keys].reset_index()
    )
    early_common = (
        early_customer.set_index("household_key").loc[common_keys].reset_index()
    )
    full_matrix, _ = prepare_features(full_common)
    early_matrix, _ = prepare_features(early_common)
    full_labels = KMeans(
        n_clusters=SELECTED_K,
        random_state=FINAL_SEED,
        n_init=50,
        max_iter=500,
    ).fit_predict(full_matrix)
    early_labels = KMeans(
        n_clusters=SELECTED_K,
        random_state=FINAL_SEED,
        n_init=50,
        max_iter=500,
    ).fit_predict(early_matrix)
    return (
        float(adjusted_rand_score(full_labels, early_labels)),
        cutoff_day,
        len(common_keys),
    )


def build_stability_evidence(
    model_selection: pd.DataFrame,
    time_window_ari: float,
    cutoff_day: int,
    common_households: int,
) -> pd.DataFrame:
    """Combine seed and time-window stability in one reviewable artifact."""
    selected = model_selection.loc[model_selection["k"] == SELECTED_K].iloc[0]
    return pd.DataFrame(
        [
            {
                "stability_test": "random_seed_pairwise_ari_mean",
                "value": selected["seed_stability_ari_mean"],
                "threshold": 0.90,
                "passed": selected["seed_stability_ari_mean"] >= 0.90,
                "notes": f"K={SELECTED_K}; seeds={SEEDS}",
            },
            {
                "stability_test": "random_seed_pairwise_ari_min",
                "value": selected["seed_stability_ari_min"],
                "threshold": 0.85,
                "passed": selected["seed_stability_ari_min"] >= 0.85,
                "notes": f"K={SELECTED_K}; seeds={SEEDS}",
            },
            {
                "stability_test": "80pct_vs_full_window_ari",
                "value": round(time_window_ari, 4),
                "threshold": 0.60,
                "passed": time_window_ari >= 0.60,
                "notes": (
                    f"cutoff_day={cutoff_day}; common_households={common_households}; "
                    "moderate stability threshold"
                ),
            },
        ]
    )


def validate_final_segmentation(
    customer: pd.DataFrame,
    profile: pd.DataFrame,
    model_selection: pd.DataFrame,
    stability: pd.DataFrame,
) -> pd.DataFrame:
    """Validate grain, cluster coverage, size and revenue reconciliation."""
    selected = model_selection.loc[model_selection["k"] == SELECTED_K].iloc[0]
    checks = [
        ("household_row_count", len(customer), 2500, len(customer) == 2500),
        (
            "unique_household_count",
            int(customer["household_key"].nunique()),
            len(customer),
            customer["household_key"].is_unique,
        ),
        (
            "missing_cluster_labels",
            int(customer["kmeans_segment"].isna().sum()),
            0,
            customer["kmeans_segment"].notna().all(),
        ),
        (
            "cluster_count",
            int(customer["kmeans_cluster_id"].nunique()),
            SELECTED_K,
            customer["kmeans_cluster_id"].nunique() == SELECTED_K,
        ),
        (
            "smallest_cluster_share",
            round(float(customer["kmeans_segment"].value_counts(normalize=True).min()), 4),
            ">=0.10",
            customer["kmeans_segment"].value_counts(normalize=True).min() >= 0.10,
        ),
        (
            "profile_households_reconcile",
            int(profile["household_count"].sum()),
            len(customer),
            profile["household_count"].sum() == len(customer),
        ),
        (
            "profile_revenue_difference",
            round(float(profile["total_revenue"].sum() - customer["monetary_value"].sum()), 6),
            0,
            np.isclose(
                profile["total_revenue"].sum(), customer["monetary_value"].sum(), atol=0.01
            ),
        ),
        (
            "selected_silhouette",
            float(selected["silhouette_mean"]),
            ">=0.15",
            selected["silhouette_mean"] >= 0.15,
        ),
        (
            "stability_tests_passed",
            int(stability["passed"].sum()),
            len(stability),
            stability["passed"].all(),
        ),
    ]
    return pd.DataFrame(
        checks, columns=["check_name", "observed_value", "expected_value", "passed"]
    )


def write_model_selection_chart(
    model_selection: pd.DataFrame, output_path: pathlib.Path
) -> None:
    """Plot separation and seed stability across candidate K values."""
    fig, ax1 = plt.subplots(figsize=(9, 5.5))
    ax2 = ax1.twinx()
    ax1.plot(
        model_selection["k"],
        model_selection["silhouette_mean"],
        marker="o",
        linewidth=2,
        color="#1f77b4",
        label="Silhouette",
    )
    ax2.plot(
        model_selection["k"],
        model_selection["seed_stability_ari_mean"],
        marker="s",
        linewidth=2,
        color="#d95f02",
        label="Seed stability ARI",
    )
    ax1.axvline(SELECTED_K, linestyle="--", color="#333333", alpha=0.7)
    ax1.text(SELECTED_K + 0.08, ax1.get_ylim()[1] * 0.96, "Selected K=3")
    ax1.set_xlabel("Number of clusters (K)")
    ax1.set_ylabel("Silhouette score", color="#1f77b4")
    ax2.set_ylabel("Mean pairwise ARI", color="#d95f02")
    ax1.set_title("K-Means Model Selection: Separation vs Stability", weight="bold")
    lines = ax1.get_lines()[:1] + ax2.get_lines()[:1]
    ax1.legend(lines, [line.get_label() for line in lines], loc="center right")
    ax1.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_profile_heatmap(
    standardised: pd.DataFrame,
    customer: pd.DataFrame,
    output_path: pathlib.Path,
) -> None:
    """Visualise cluster means in standard-deviation units."""
    chart_data = standardised.copy()
    chart_data["kmeans_segment"] = customer["kmeans_segment"].to_numpy()
    profile = chart_data.groupby("kmeans_segment")[FEATURES].mean()
    profile = profile.rename(columns=FEATURE_LABELS)
    fig, ax = plt.subplots(figsize=(12, 4.8))
    sns.heatmap(
        profile,
        cmap="RdBu_r",
        center=0,
        annot=True,
        fmt=".2f",
        linewidths=0.5,
        cbar_kws={"label": "Standard deviations from overall mean"},
        ax=ax,
    )
    ax.set_title("K-Means Cluster Profile", weight="bold", pad=12)
    ax.set_xlabel("")
    ax.set_ylabel("")
    plt.xticks(rotation=35, ha="right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_pca_chart(
    matrix: np.ndarray,
    customer: pd.DataFrame,
    output_path: pathlib.Path,
) -> None:
    """Create a two-dimensional diagnostic projection of the final clusters."""
    pca = PCA(n_components=2, random_state=FINAL_SEED)
    coordinates = pca.fit_transform(matrix)
    plot_data = pd.DataFrame(
        {
            "PC1": coordinates[:, 0],
            "PC2": coordinates[:, 1],
            "segment": customer["kmeans_segment"].to_numpy(),
        }
    )
    fig, ax = plt.subplots(figsize=(8.5, 6))
    sns.scatterplot(
        data=plot_data,
        x="PC1",
        y="PC2",
        hue="segment",
        alpha=0.55,
        s=28,
        linewidth=0,
        ax=ax,
    )
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%} variance)")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%} variance)")
    ax.set_title("K-Means Segments in Two-Dimensional PCA Space", weight="bold")
    ax.legend(title="Segment", frameon=True)
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    """Fit, validate and export the K-Means segmentation."""
    print("=== Loading Customer 360 ===")
    customer = pd.read_parquet(PROCESSED_DIR / "customer_360.parquet")
    matrix, standardised = prepare_features(customer)

    print("=== Evaluating K=2..8 ===")
    model_selection = evaluate_candidate_k(matrix)
    print(model_selection.to_string(index=False))

    segmented, _ = fit_final_model(customer, matrix)
    profile = build_cluster_profile(segmented)
    print("\n=== Final K=3 cluster profile ===")
    print(profile.to_string(index=False))

    full_end_day = int(segmented["observation_end_day"].max())
    time_ari, cutoff_day, common_households = compute_time_window_stability(
        customer, full_end_day
    )
    stability = build_stability_evidence(
        model_selection, time_ari, cutoff_day, common_households
    )
    print("\n=== Stability evidence ===")
    print(stability.to_string(index=False))

    quality = validate_final_segmentation(
        segmented, profile, model_selection, stability
    )
    print("\n=== Quality checks ===")
    print(quality.to_string(index=False))
    if not quality["passed"].all():
        failed = quality.loc[~quality["passed"], "check_name"].tolist()
        raise ValueError(f"K-Means validation failed: {failed}")

    rfm_crosstab = pd.crosstab(
        segmented["kmeans_segment"], segmented["rfm_segment"], margins=True
    )

    LOCAL_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    local_path = LOCAL_EXPORT_DIR / "customer_360_kmeans.csv"
    profile_path = POWERBI_DIR / "kmeans_cluster_profile.csv"
    selection_path = VALIDATION_DIR / "kmeans_model_selection.csv"
    stability_path = VALIDATION_DIR / "kmeans_stability.csv"
    quality_path = VALIDATION_DIR / "kmeans_quality.csv"
    crosstab_path = TABLE_DIR / "kmeans_rfm_crosstab.csv"
    selection_chart_path = CHART_DIR / "kmeans_model_selection.png"
    profile_chart_path = CHART_DIR / "kmeans_cluster_profile.png"
    pca_chart_path = CHART_DIR / "kmeans_pca_map.png"

    segmented.to_csv(local_path, index=False)
    profile.to_csv(profile_path, index=False)
    model_selection.to_csv(selection_path, index=False)
    stability.to_csv(stability_path, index=False)
    quality.to_csv(quality_path, index=False)
    rfm_crosstab.to_csv(crosstab_path)
    write_model_selection_chart(model_selection, selection_chart_path)
    write_profile_heatmap(standardised, segmented, profile_chart_path)
    write_pca_chart(matrix, segmented, pca_chart_path)

    print("\nWrote local household-level output:")
    print(f"  {local_path}")
    print("Wrote publishable aggregate and validation outputs:")
    for path in [
        profile_path,
        selection_path,
        stability_path,
        quality_path,
        crosstab_path,
        selection_chart_path,
        profile_chart_path,
        pca_chart_path,
    ]:
        print(f"  {path}")


if __name__ == "__main__":
    main()

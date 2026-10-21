"""Matched Difference-in-Differences evaluation of merchandising promotions.

The treatment is an isolated one-week display or mailer exposure for a
product-store pair. Each treated event is matched to another store selling the
same product in the same week, with no merchandising exposure in the full
event window. The estimand is the average incremental outcome in event week 0.
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

os.environ.setdefault("OMP_NUM_THREADS", "10")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import norm, ttest_1samp

from src.data_cleaning import load_causal


ROOT = pathlib.Path(__file__).parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
POWERBI_DIR = ROOT / "data" / "powerbi_exports"
LOCAL_EXPORT_DIR = ROOT / "data" / "local_exports"
OUTPUT_DIR = ROOT / "outputs"
CHART_DIR = OUTPUT_DIR / "charts"
TABLE_DIR = OUTPUT_DIR / "tables"
VALIDATION_DIR = OUTPUT_DIR / "validation"

PRE_WEEKS = np.array([-4, -3, -2, -1])
RELATIVE_WEEKS = np.arange(-4, 5)
CONTROL_CLEAN_WEEKS = RELATIVE_WEEKS.copy()
MIN_PRODUCT_UNITS = 200
MIN_PRODUCT_STORES = 10
MIN_PRODUCT_WEEKS = 30
MIN_POSITIVE_PRE_WEEKS = 2
MAX_MATCH_DISTANCE = 2.0
BOOTSTRAP_DRAWS = 1_000
RANDOM_SEED = 47

MATCH_FEATURES = [
    "pre_mean_units",
    "pre_mean_revenue",
    "pre_unit_trend",
    "pre_positive_weeks",
    "pre_avg_price",
    "pre_units_m4",
    "pre_units_m3",
    "pre_units_m2",
    "pre_units_m1",
]


@dataclass
class MatchResult:
    event: dict
    outcomes: list[dict]


def _qualified_products(sales: pd.DataFrame) -> pd.DataFrame:
    support = (
        sales.groupby("product_id", observed=True)
        .agg(
            product_revenue=("revenue", "sum"),
            product_units=("units", "sum"),
            selling_stores=("store_id", "nunique"),
            selling_weeks=("week_no", "nunique"),
        )
        .reset_index()
    )
    support["eligible_product"] = (
        (support["product_units"] >= MIN_PRODUCT_UNITS)
        & (support["selling_stores"] >= MIN_PRODUCT_STORES)
        & (support["selling_weeks"] >= MIN_PRODUCT_WEEKS)
    )
    return support


def load_weekly_sales() -> tuple[pd.DataFrame, pd.DataFrame]:
    tx = pd.read_parquet(
        PROCESSED_DIR / "beverage_transactions.parquet",
        columns=[
            "product_id",
            "store_id",
            "week_no",
            "quantity",
            "gross_revenue",
            "beverage_category",
        ],
    )
    weekly = (
        tx.groupby(
            ["product_id", "store_id", "week_no", "beverage_category"],
            observed=True,
            as_index=False,
        )
        .agg(units=("quantity", "sum"), revenue=("gross_revenue", "sum"))
    )
    weekly["product_id"] = weekly["product_id"].astype(int)
    weekly["store_id"] = weekly["store_id"].astype(int)
    weekly["week_no"] = weekly["week_no"].astype(int)
    support = _qualified_products(weekly)
    eligible_ids = set(
        support.loc[support["eligible_product"], "product_id"].astype(int)
    )
    return weekly.loc[weekly["product_id"].isin(eligible_ids)].copy(), support


def load_exposures(product_ids: set[int]) -> pd.DataFrame:
    """Read raw causal records and treat each unique key as an exposure."""
    raw = load_causal(product_ids=product_ids)
    exposure = (
        raw[["product_id", "store_id", "week_no"]]
        .dropna()
        .drop_duplicates()
        .astype(int)
        .sort_values(["product_id", "store_id", "week_no"])
        .reset_index(drop=True)
    )
    return exposure


def identify_isolated_events(exposure: pd.DataFrame) -> pd.DataFrame:
    """Find exposure weeks with no other exposure within +/- four weeks."""
    grouped = exposure.groupby(["product_id", "store_id"], observed=True)
    events = exposure.copy()
    events["previous_exposure_week"] = grouped["week_no"].shift()
    events["next_exposure_week"] = grouped["week_no"].shift(-1)
    previous_clean = events["previous_exposure_week"].isna() | (
        events["previous_exposure_week"] <= events["week_no"] - 5
    )
    next_clean = events["next_exposure_week"].isna() | (
        events["next_exposure_week"] >= events["week_no"] + 5
    )
    edge_clean = events["week_no"].between(13, 97)
    events = events.loc[previous_clean & next_clean & edge_clean].copy()

    # Avoid repeated observations of the same product-store unit.
    events = (
        events.sort_values(["product_id", "store_id", "week_no"])
        .drop_duplicates(["product_id", "store_id"], keep="first")
        .rename(columns={"week_no": "event_week"})
    )
    return events[["product_id", "store_id", "event_week"]].reset_index(drop=True)


def _pre_features(
    units: pd.DataFrame,
    revenue: pd.DataFrame,
    event_week: int,
) -> pd.DataFrame:
    weeks = event_week + PRE_WEEKS
    u = units.reindex(columns=weeks, fill_value=0.0).astype(float)
    r = revenue.reindex(columns=weeks, fill_value=0.0).astype(float)
    x = np.arange(len(PRE_WEEKS), dtype=float)
    x_centered = x - x.mean()
    denominator = float(np.square(x_centered).sum())
    slopes = (u.to_numpy() @ x_centered) / denominator
    total_units = u.sum(axis=1)

    result = pd.DataFrame(
        {
            "pre_mean_units": u.mean(axis=1),
            "pre_mean_revenue": r.mean(axis=1),
            "pre_unit_trend": slopes,
            "pre_positive_weeks": (u > 0).sum(axis=1),
            "pre_avg_price": r.sum(axis=1).div(total_units.replace(0, np.nan)),
        },
        index=units.index,
    ).fillna(0.0)
    for position, relative_week in enumerate(PRE_WEEKS):
        result[f"pre_units_m{abs(int(relative_week))}"] = u.iloc[:, position]
    return result


def _match_category_events(
    category: str,
    category_sales: pd.DataFrame,
    category_exposure: pd.DataFrame,
    category_events: pd.DataFrame,
    rng: np.random.Generator,
) -> list[MatchResult]:
    pairs = pd.MultiIndex.from_frame(
        category_sales[["product_id", "store_id"]]
        .drop_duplicates()
        .astype(int)
        .sort_values(["product_id", "store_id"]),
        names=["product_id", "store_id"],
    )
    weeks = np.arange(1, 103)
    units = (
        category_sales.pivot_table(
            index=["product_id", "store_id"],
            columns="week_no",
            values="units",
            aggfunc="sum",
        )
        .reindex(index=pairs, columns=weeks, fill_value=0.0)
        .fillna(0.0)
    )
    revenue = (
        category_sales.pivot_table(
            index=["product_id", "store_id"],
            columns="week_no",
            values="revenue",
            aggfunc="sum",
        )
        .reindex(index=pairs, columns=weeks, fill_value=0.0)
        .fillna(0.0)
    )
    exposure = pd.DataFrame(False, index=pairs, columns=weeks)
    valid_exposure = category_exposure.loc[
        category_exposure["week_no"].between(1, 102)
    ]
    for row in valid_exposure.itertuples(index=False):
        pair = (int(row.product_id), int(row.store_id))
        if pair in exposure.index:
            exposure.at[pair, int(row.week_no)] = True

    matches: list[MatchResult] = []
    for event_week, week_events in category_events.groupby("event_week", observed=True):
        event_week = int(event_week)
        window = event_week + RELATIVE_WEEKS
        features = _pre_features(units, revenue, event_week)
        clean_window = event_week + CONTROL_CLEAN_WEEKS
        base_eligible = features.index[
            (features["pre_positive_weeks"] >= MIN_POSITIVE_PRE_WEEKS)
            & (~exposure.loc[:, clean_window].any(axis=1))
        ]
        for event in week_events.itertuples(index=False):
            product_id = int(event.product_id)
            treated_store = int(event.store_id)
            treated_pair = (product_id, treated_store)
            if treated_pair not in units.index:
                continue

            eligible_controls = base_eligible[base_eligible != treated_pair]
            if (
                features.at[treated_pair, "pre_positive_weeks"]
                < MIN_POSITIVE_PRE_WEEKS
                or len(eligible_controls) == 0
            ):
                continue

            pool = features.loc[
                eligible_controls.append(pd.MultiIndex.from_tuples([treated_pair])),
                MATCH_FEATURES,
            ]
            scale = pool.std(ddof=0).replace(0, 1.0)
            distance = (
                (features.loc[eligible_controls, MATCH_FEATURES]
                 - features.loc[treated_pair, MATCH_FEATURES])
                .div(scale)
                .pow(2)
                .sum(axis=1)
                .pow(0.5)
            )
            control_pair = tuple(distance.idxmin())
            match_distance = float(distance.loc[control_pair])
            if match_distance > MAX_MATCH_DISTANCE:
                continue

            naive_pair = tuple(
                eligible_controls[int(rng.integers(0, len(eligible_controls)))]
            )
            control_product, control_store = map(int, control_pair)
            naive_product, naive_store = map(int, naive_pair)
            event_id = f"{product_id}_{treated_store}_{event_week}"
            if control_product == product_id:
                match_scope = "same_product_other_store"
            elif control_store == treated_store:
                match_scope = "same_store_same_category"
            else:
                match_scope = "same_category"

            event_record = {
                "event_id": event_id,
                "product_id": product_id,
                "control_product_id": control_product,
                "beverage_category": category,
                "treated_store_id": treated_store,
                "control_store_id": control_store,
                "naive_control_product_id": naive_product,
                "naive_control_store_id": naive_store,
                "event_week": event_week,
                "match_scope": match_scope,
                "match_distance": match_distance,
                "candidate_control_count": int(len(eligible_controls)),
            }
            for feature in MATCH_FEATURES:
                event_record[f"treated_{feature}"] = float(
                    features.at[treated_pair, feature]
                )
                event_record[f"control_{feature}"] = float(
                    features.at[control_pair, feature]
                )
                event_record[f"naive_control_{feature}"] = float(
                    features.at[naive_pair, feature]
                )

            outcomes = []
            for relative_week, week in zip(RELATIVE_WEEKS, window):
                outcomes.append(
                    {
                        "event_id": event_id,
                        "product_id": product_id,
                        "control_product_id": control_product,
                        "beverage_category": category,
                        "relative_week": int(relative_week),
                        "treated_units": float(units.at[treated_pair, week]),
                        "control_units": float(units.at[control_pair, week]),
                        "treated_revenue": float(revenue.at[treated_pair, week]),
                        "control_revenue": float(revenue.at[control_pair, week]),
                    }
                )
            matches.append(MatchResult(event=event_record, outcomes=outcomes))
    return matches


def match_events(
    sales: pd.DataFrame,
    exposure: pd.DataFrame,
    events: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(RANDOM_SEED)
    categories = (
        sales.groupby("product_id", observed=True)["beverage_category"]
        .first()
        .to_dict()
    )
    exposure = exposure.copy()
    exposure["beverage_category"] = exposure["product_id"].map(categories)
    events = events.copy()
    events["beverage_category"] = events["product_id"].map(categories)
    all_matches: list[MatchResult] = []
    for category, category_events in events.dropna(
        subset=["beverage_category"]
    ).groupby("beverage_category", observed=True):
        all_matches.extend(
            _match_category_events(
                str(category),
                sales.loc[sales["beverage_category"].eq(category)],
                exposure.loc[exposure["beverage_category"].eq(category)],
                category_events,
                rng,
            )
        )

    match_table = pd.DataFrame([result.event for result in all_matches])
    outcome_table = pd.DataFrame(
        [row for result in all_matches for row in result.outcomes]
    )
    return match_table, outcome_table


def _standardised_mean_difference(
    treated: pd.Series, control: pd.Series
) -> float:
    pooled = np.sqrt((treated.var(ddof=1) + control.var(ddof=1)) / 2)
    if pooled == 0 or np.isnan(pooled):
        return 0.0
    return float((treated.mean() - control.mean()) / pooled)


def build_balance_table(matches: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for feature in MATCH_FEATURES:
        treated = matches[f"treated_{feature}"]
        naive = matches[f"naive_control_{feature}"]
        control = matches[f"control_{feature}"]
        rows.append(
            {
                "feature": feature,
                "treated_mean": treated.mean(),
                "naive_control_mean": naive.mean(),
                "matched_control_mean": control.mean(),
                "smd_before_matching": _standardised_mean_difference(treated, naive),
                "smd_after_matching": _standardised_mean_difference(treated, control),
            }
        )
    return pd.DataFrame(rows)


def build_event_effects(
    matches: pd.DataFrame, outcomes: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = outcomes.copy()
    data["unit_difference"] = data["treated_units"] - data["control_units"]
    data["revenue_difference"] = (
        data["treated_revenue"] - data["control_revenue"]
    )
    pre = (
        data.loc[data["relative_week"].isin(PRE_WEEKS)]
        .groupby("event_id", observed=True)
        .agg(
            pre_unit_difference=("unit_difference", "mean"),
            pre_revenue_difference=("revenue_difference", "mean"),
            treated_pre_units=("treated_units", "mean"),
            treated_pre_revenue=("treated_revenue", "mean"),
        )
        .reset_index()
    )
    data = data.merge(pre, on="event_id", how="left")
    data["event_study_units"] = (
        data["unit_difference"] - data["pre_unit_difference"]
    )
    data["event_study_revenue"] = (
        data["revenue_difference"] - data["pre_revenue_difference"]
    )

    event_zero = data.loc[data["relative_week"].eq(0)].copy()
    event_zero = event_zero.merge(
        matches[
            [
                "event_id",
                "event_week",
                "treated_store_id",
                "control_store_id",
                "match_distance",
            ]
        ],
        on="event_id",
        how="left",
    )
    event_zero = event_zero.rename(
        columns={
            "event_study_units": "did_units",
            "event_study_revenue": "did_revenue",
        }
    )

    pre_only = data.loc[data["relative_week"].isin(PRE_WEEKS)].copy()
    slopes = []
    for event_id, group in pre_only.groupby("event_id", observed=True):
        group = group.sort_values("relative_week")
        slopes.append(
            {
                "event_id": event_id,
                "pretrend_unit_slope_difference": float(
                    np.polyfit(group["relative_week"], group["unit_difference"], 1)[0]
                ),
            }
        )
    event_zero = event_zero.merge(pd.DataFrame(slopes), on="event_id", how="left")

    placebo = pre_only.pivot(index="event_id", columns="relative_week", values="unit_difference")
    event_zero["placebo_units"] = event_zero["event_id"].map(
        placebo[-1] - placebo[[-4, -3, -2]].mean(axis=1)
    )
    return event_zero, data


def _cluster_bootstrap_ci(
    frame: pd.DataFrame,
    value_col: str,
    cluster_col: str = "product_id",
    draws: int = BOOTSTRAP_DRAWS,
) -> tuple[float, float]:
    low, high, _, _ = _cluster_bootstrap_stats(
        frame, value_col, cluster_col=cluster_col, draws=draws
    )
    return low, high


def _cluster_bootstrap_stats(
    frame: pd.DataFrame,
    value_col: str,
    cluster_col: str = "product_id",
    draws: int = BOOTSTRAP_DRAWS,
) -> tuple[float, float, float, float]:
    """Return percentile CI, bootstrap SE and a two-sided normal p-value.

    Resampling occurs at product level so repeated promotion events for the
    same product remain together. The p-value uses the bootstrap standard
    error and a normal approximation; the percentile interval is retained as
    the primary uncertainty interval shown in the report.
    """
    grouped = {
        key: values[value_col].dropna().to_numpy(dtype=float)
        for key, values in frame.groupby(cluster_col, observed=True)
    }
    keys = np.array(list(grouped), dtype=object)
    if len(keys) < 2:
        return np.nan, np.nan, np.nan, np.nan
    rng = np.random.default_rng(RANDOM_SEED)
    estimates = np.empty(draws)
    for draw in range(draws):
        sampled = rng.choice(keys, size=len(keys), replace=True)
        values = np.concatenate([grouped[key] for key in sampled])
        estimates[draw] = values.mean()
    low, high = np.quantile(estimates, [0.025, 0.975])
    std_error = float(np.std(estimates, ddof=1))
    point_estimate = float(frame[value_col].mean())
    p_value = (
        float(2 * norm.sf(abs(point_estimate / std_error)))
        if std_error > 0
        else np.nan
    )
    return float(low), float(high), std_error, p_value


def build_event_study(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for relative_week, group in data.groupby("relative_week", observed=True):
        unit_low, unit_high = _cluster_bootstrap_ci(group, "event_study_units")
        rev_low, rev_high = _cluster_bootstrap_ci(group, "event_study_revenue")
        rows.append(
            {
                "relative_week": int(relative_week),
                "event_count": group["event_id"].nunique(),
                "did_units": group["event_study_units"].mean(),
                "did_units_ci_low": unit_low,
                "did_units_ci_high": unit_high,
                "did_revenue": group["event_study_revenue"].mean(),
                "did_revenue_ci_low": rev_low,
                "did_revenue_ci_high": rev_high,
            }
        )
    return pd.DataFrame(rows).sort_values("relative_week")


def build_category_effects(event_effects: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for category, group in event_effects.groupby("beverage_category", observed=True):
        if len(group) < 30 or group["product_id"].nunique() < 3:
            continue
        low, high = _cluster_bootstrap_ci(group, "did_units")
        rows.append(
            {
                "beverage_category": category,
                "event_count": len(group),
                "product_count": group["product_id"].nunique(),
                "did_units": group["did_units"].mean(),
                "did_units_ci_low": low,
                "did_units_ci_high": high,
                "did_revenue": group["did_revenue"].mean(),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "beverage_category",
                "event_count",
                "product_count",
                "did_units",
                "did_units_ci_low",
                "did_units_ci_high",
                "did_revenue",
            ]
        )
    return pd.DataFrame(rows).sort_values("did_units", ascending=False)


def _product_level_test(frame: pd.DataFrame, value_col: str) -> float:
    product_means = frame.groupby("product_id", observed=True)[value_col].mean()
    if len(product_means) < 2:
        return np.nan
    return float(ttest_1samp(product_means, 0.0, nan_policy="omit").pvalue)


def build_summary(
    support: pd.DataFrame,
    candidate_events: pd.DataFrame,
    matches: pd.DataFrame,
    event_effects: pd.DataFrame,
    balance: pd.DataFrame,
) -> pd.DataFrame:
    units_low, units_high, units_se, units_p = _cluster_bootstrap_stats(
        event_effects, "did_units"
    )
    revenue_low, revenue_high, revenue_se, revenue_p = _cluster_bootstrap_stats(
        event_effects, "did_revenue"
    )
    placebo_low, placebo_high = _cluster_bootstrap_ci(event_effects, "placebo_units")
    baseline_units = event_effects["treated_pre_units"].mean()
    baseline_revenue = event_effects["treated_pre_revenue"].mean()
    unit_effect = event_effects["did_units"].mean()
    revenue_effect = event_effects["did_revenue"].mean()
    unit_bounds = event_effects["did_units"].quantile([0.025, 0.975])
    revenue_bounds = event_effects["did_revenue"].quantile([0.025, 0.975])
    winsor_units = event_effects["did_units"].clip(*unit_bounds).mean()
    winsor_revenue = event_effects["did_revenue"].clip(*revenue_bounds).mean()
    strict_matches = event_effects.loc[event_effects["match_distance"] <= 1.0]
    strict_low, strict_high = _cluster_bootstrap_ci(strict_matches, "did_units")

    def row(metric, value, low=np.nan, high=np.nan, unit="", se=np.nan, p=np.nan):
        return (metric, value, low, high, se, p, unit)

    rows = [
        row("eligible_products", int(support["eligible_product"].sum()), unit="count"),
        row("candidate_isolated_events", len(candidate_events), unit="count"),
        row("matched_events", len(matches), unit="count"),
        row("matched_products", matches["product_id"].nunique(), unit="count"),
        row("matched_categories", matches["beverage_category"].nunique(), unit="count"),
        row("mean_match_distance", matches["match_distance"].mean(), unit="standardised distance"),
        row("max_abs_smd_after_matching", balance["smd_after_matching"].abs().max(), unit="absolute SMD"),
        row("did_incremental_units_per_event", unit_effect, units_low, units_high, "units", units_se, units_p),
        row("did_incremental_units_pct", unit_effect / baseline_units, units_low / baseline_units, units_high / baseline_units, "share of treated pre mean", units_se / baseline_units, units_p),
        row("did_incremental_revenue_per_event", revenue_effect, revenue_low, revenue_high, "dollars", revenue_se, revenue_p),
        row("did_incremental_revenue_pct", revenue_effect / baseline_revenue, revenue_low / baseline_revenue, revenue_high / baseline_revenue, "share of treated pre mean", revenue_se / baseline_revenue, revenue_p),
        row("winsorized_did_units_per_event", winsor_units, unit="units; 2.5/97.5 pct winsorisation"),
        row("winsorized_did_revenue_per_event", winsor_revenue, unit="dollars; 2.5/97.5 pct winsorisation"),
        row("strict_distance_event_count", len(strict_matches), unit="count; match distance <=1"),
        row("strict_distance_did_units", strict_matches["did_units"].mean(), strict_low, strict_high, "units; match distance <=1"),
        row("same_product_control_events", matches["match_scope"].eq("same_product_other_store").sum(), unit="count"),
        row("same_store_control_events", matches["match_scope"].eq("same_store_same_category").sum(), unit="count"),
        row("same_category_control_events", matches["match_scope"].eq("same_category").sum(), unit="count"),
        row("pretrend_slope_p_value", _product_level_test(event_effects, "pretrend_unit_slope_difference"), unit="p-value"),
        row("preperiod_placebo_units", event_effects["placebo_units"].mean(), placebo_low, placebo_high, "units"),
        row("preperiod_placebo_p_value", _product_level_test(event_effects, "placebo_units"), unit="p-value"),
    ]
    return pd.DataFrame(
        rows,
        columns=["metric", "value", "ci_low", "ci_high", "std_error", "p_value", "unit"],
    )


def build_quality_checks(
    matches: pd.DataFrame,
    outcomes: pd.DataFrame,
    balance: pd.DataFrame,
    summary: pd.DataFrame,
) -> pd.DataFrame:
    values = summary.set_index("metric")["value"]
    identical_pair = (
        matches["product_id"].eq(matches["control_product_id"])
        & matches["treated_store_id"].eq(matches["control_store_id"])
    )
    checks = [
        ("matched_event_count", len(matches), ">=300", len(matches) >= 300),
        ("unique_matched_products", matches["product_id"].nunique(), ">=30", matches["product_id"].nunique() >= 30),
        ("complete_nine_week_windows", len(outcomes), f"{len(matches) * 9}", len(outcomes) == len(matches) * 9),
        ("duplicate_event_ids", matches["event_id"].duplicated().sum(), "0", not matches["event_id"].duplicated().any()),
        ("control_equals_treated_pair", identical_pair.sum(), "0", not identical_pair.any()),
        ("max_match_distance", matches["match_distance"].max(), f"<={MAX_MATCH_DISTANCE}", matches["match_distance"].max() <= MAX_MATCH_DISTANCE),
        ("max_abs_smd_after_matching", balance["smd_after_matching"].abs().max(), "<=0.10", balance["smd_after_matching"].abs().max() <= 0.10),
        ("parallel_pretrend_p_value", values["pretrend_slope_p_value"], ">=0.05", values["pretrend_slope_p_value"] >= 0.05),
        ("preperiod_placebo_p_value", values["preperiod_placebo_p_value"], ">=0.05", values["preperiod_placebo_p_value"] >= 0.05),
    ]
    return pd.DataFrame(checks, columns=["check_name", "observed_value", "expected_value", "passed"])


def plot_balance(balance: pd.DataFrame) -> None:
    plot = balance.copy()
    plot["feature"] = plot["feature"].str.replace("pre_", "", regex=False).str.replace("_", " ")
    fig, ax = plt.subplots(figsize=(9, 5.5))
    y = np.arange(len(plot))
    ax.scatter(plot["smd_before_matching"].abs(), y, label="Before matching", s=80)
    ax.scatter(plot["smd_after_matching"].abs(), y, label="After matching", s=80)
    ax.axvline(0.10, color="grey", linestyle="--", label="0.10 balance threshold")
    ax.set_yticks(y, plot["feature"])
    ax.set_xlabel("Absolute standardised mean difference")
    ax.set_title("Promotion Event Covariate Balance")
    ax.legend()
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "promotion_matching_balance.png", dpi=180)
    plt.close(fig)


def plot_event_study(event_study: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    x = event_study["relative_week"].to_numpy()
    y = event_study["did_units"].to_numpy()
    low = event_study["did_units_ci_low"].to_numpy()
    high = event_study["did_units_ci_high"].to_numpy()
    ax.fill_between(x, low, high, alpha=0.22, color="#2878B5", label="95% cluster bootstrap CI")
    ax.plot(x, y, marker="o", linewidth=2.2, color="#2878B5", label="Matched DiD estimate")
    ax.axhline(0, color="black", linewidth=1)
    ax.axvline(0, color="#D95319", linestyle="--", linewidth=1.5, label="Promotion week")
    ax.set_xticks(RELATIVE_WEEKS)
    ax.set_xlabel("Weeks relative to promotion")
    ax.set_ylabel("Incremental units per product-store event")
    ax.set_title("Matched Event Study: Units Sold")
    ax.legend()
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "promotion_event_study_units.png", dpi=180)
    plt.close(fig)


def plot_category_effects(category: pd.DataFrame) -> None:
    if category.empty:
        return
    plot = category.sort_values("did_units")
    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    y = np.arange(len(plot))
    ax.errorbar(
        plot["did_units"],
        y,
        xerr=[
            plot["did_units"] - plot["did_units_ci_low"],
            plot["did_units_ci_high"] - plot["did_units"],
        ],
        fmt="o",
        capsize=4,
        color="#2878B5",
    )
    ax.axvline(0, color="black", linewidth=1)
    ax.set_yticks(y, plot["beverage_category"])
    ax.set_xlabel("Incremental units per event (95% cluster bootstrap CI)")
    ax.set_title("Promotion Effect Heterogeneity by Beverage Category")
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "promotion_category_effects.png", dpi=180)
    plt.close(fig)


def main() -> None:
    for directory in [POWERBI_DIR, LOCAL_EXPORT_DIR, CHART_DIR, TABLE_DIR, VALIDATION_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

    print("=== Loading weekly beverage sales ===")
    sales, support = load_weekly_sales()
    eligible_ids = set(sales["product_id"].unique().astype(int))
    print(f"Eligible products: {len(eligible_ids):,}")

    print("=== Reading merchandising exposures from raw causal data ===")
    exposure = load_exposures(eligible_ids)
    print(f"Unique exposure keys: {len(exposure):,}")

    print("=== Identifying isolated one-week events ===")
    candidate_events = identify_isolated_events(exposure)
    print(f"Candidate events after one-per-unit rule: {len(candidate_events):,}")

    print("=== Matching treated events to same-product control stores ===")
    matches, outcomes = match_events(sales, exposure, candidate_events)
    if matches.empty:
        raise RuntimeError("No promotion events met the matching requirements.")
    print(f"Matched events: {len(matches):,}")

    balance = build_balance_table(matches)
    event_effects, event_panel = build_event_effects(matches, outcomes)
    event_study = build_event_study(event_panel)
    category = build_category_effects(event_effects)
    summary = build_summary(support, candidate_events, matches, event_effects, balance)
    quality = build_quality_checks(matches, outcomes, balance, summary)

    print("\n=== Causal summary ===")
    print(summary.to_string(index=False))
    print("\n=== Balance ===")
    print(balance.to_string(index=False))
    print("\n=== Quality and identification diagnostics ===")
    print(quality.to_string(index=False))

    matches.to_csv(LOCAL_EXPORT_DIR / "matched_promotion_events.csv", index=False)
    event_panel.to_parquet(
        PROCESSED_DIR / "matched_promotion_event_panel.parquet", index=False
    )
    summary.to_csv(POWERBI_DIR / "promotion_causal_summary.csv", index=False)
    event_study.to_csv(POWERBI_DIR / "promotion_event_study.csv", index=False)
    category.to_csv(TABLE_DIR / "promotion_category_heterogeneity.csv", index=False)
    balance.to_csv(VALIDATION_DIR / "promotion_matching_balance.csv", index=False)
    quality.to_csv(VALIDATION_DIR / "promotion_causal_quality.csv", index=False)

    sns.set_theme(style="whitegrid")
    plot_balance(balance)
    plot_event_study(event_study)
    plot_category_effects(category)

    print("\nWrote local event-level evidence and publishable aggregate outputs.")


if __name__ == "__main__":
    main()

"""Build the source-controlled Power BI PBIP portfolio report.

The script generates:
- TMDL tables and DAX measures backed by the committed Power BI CSV exports;
- four PBIR report pages with native Power BI visuals;
- a short build note for reviewers and future maintainers.

Run from the repository root with:
    python scripts/build_powerbi_project.py

WARNING: the committed powerbi/ files were later refined in Power BI Desktop
and by direct PBIR/TMDL edits (dropdown slicers, value-sorted parameters,
rewritten insight text, removed household-level Customers table). Re-running
this script overwrites those refinements; treat powerbi/ as the source of truth.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
POWERBI_DIR = ROOT / "powerbi"
REPORT_DIR = POWERBI_DIR / "FMCG_Promotion_Customer_Growth.Report"
MODEL_DIR = POWERBI_DIR / "FMCG_Promotion_Customer_Growth.SemanticModel"
DEFINITION_DIR = MODEL_DIR / "definition"
TABLES_DIR = DEFINITION_DIR / "tables"
PAGES_DIR = REPORT_DIR / "definition" / "pages"
DATA_DIR = ROOT / "data" / "powerbi_exports"
REGISTERED_RESOURCES_DIR = REPORT_DIR / "StaticResources" / "RegisteredResources"
REPORT_JSON = REPORT_DIR / "definition" / "report.json"

REPORT_IMAGES = {
    "cohort_customer_retention_20261016.png": ROOT / "outputs" / "charts" / "cohort_customer_retention.png",
    "promotion_event_study_units_20261016.png": ROOT / "outputs" / "charts" / "promotion_event_study_units.png",
}

VISUAL_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
    "visualContainer/2.9.0/schema.json"
)
PAGE_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
    "page/2.1.0/schema.json"
)
PAGES_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
    "pagesMetadata/1.1.0/schema.json"
)

TABLE_FILES = {
    "DecisionKPIs": "decision_kpis.csv",
    "CohortRetention": "cohort_retention_long.csv",
    "CohortOverview": "cohort_overview.csv",
    "ClusterProfile": "kmeans_cluster_profile.csv",
    "CategoryScorecard": "category_decision_scorecard.csv",
    "CouponCampaigns": "coupon_campaign_performance.csv",
    "CouponSegments": "coupon_segment_performance.csv",
    "PromotionSummary": "promotion_causal_summary.csv",
    "PromotionEventStudy": "promotion_event_study.csv",
    "ROIScenarios": "roi_assumption_scenarios.csv",
}

PARAMETER_TABLE_NAMES = [
    "ScenarioEffect",
    "MultiplierParameter",
    "MarginParameter",
    "CostParameter",
    "BudgetParameter",
    "MultiplierAxis",
]

PALETTE = {
    "navy": "#16324F",
    "navy_dark": "#0B1F33",
    "blue": "#2563EB",
    "blue_soft": "#EAF1FF",
    "teal": "#0F766E",
    "teal_soft": "#E6F4F1",
    "orange": "#D97706",
    "orange_soft": "#FFF3E0",
    "red": "#B91C1C",
    "green": "#15803D",
    "ink": "#172033",
    "muted": "#64748B",
    "line": "#DCE3EC",
    "surface": "#FFFFFF",
    "canvas": "#F4F7FB",
}


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\r\n")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def stable_id(label: str) -> str:
    return hashlib.sha1(label.encode("utf-8")).hexdigest()[:20]


def qname(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def dtype_to_tmdl(dtype) -> str:
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_integer_dtype(dtype):
        return "int64"
    if pd.api.types.is_float_dtype(dtype):
        return "double"
    return "string"


def dtype_to_m(dtype) -> str:
    if pd.api.types.is_bool_dtype(dtype):
        return "type logical"
    if pd.api.types.is_integer_dtype(dtype):
        return "Int64.Type"
    if pd.api.types.is_float_dtype(dtype):
        return "type number"
    return "type text"


def dtype_to_m_table(dtype) -> str:
    """M type names used inside a `type table [...]` declaration."""
    if pd.api.types.is_bool_dtype(dtype):
        return "logical"
    if pd.api.types.is_integer_dtype(dtype):
        return "Int64.Type"
    if pd.api.types.is_float_dtype(dtype):
        return "number"
    return "text"


def column_format(column: str, dtype) -> str | None:
    lowered = column.lower()
    if pd.api.types.is_float_dtype(dtype):
        if any(token in lowered for token in ("share", "rate", "penetration", "roi", "pct")):
            return "0.0%"
        if any(token in lowered for token in ("revenue", "sales", "spend", "budget", "contribution", "monetary")):
            return "$#,##0.00"
        return "0.000"
    if pd.api.types.is_integer_dtype(dtype):
        return "#,0"
    return None


def build_table_tmdl(table: str, filename: str) -> str:
    frame = pd.read_csv(DATA_DIR / filename, nrows=200)
    lines = [f"table {table}", ""]
    for column, dtype in frame.dtypes.items():
        lines.extend(
            [
                f"\tcolumn {qname(column)}",
                f"\t\tdataType: {dtype_to_tmdl(dtype)}",
                "\t\tsummarizeBy: none" if not pd.api.types.is_numeric_dtype(dtype) else "\t\tsummarizeBy: sum",
                f"\t\tsourceColumn: {qname(column)}",
            ]
        )
        fmt = column_format(column, dtype)
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        lines.append("")

    type_pairs = ", ".join(
        f'{{"{column}", {dtype_to_m(dtype)}}}'
        for column, dtype in frame.dtypes.items()
    )
    lines.extend(
        [
            f"\tpartition {table} = m",
            "\t\tmode: import",
            "\t\tsource =",
            "\t\t\tlet",
            f'\t\t\t\tSource = Csv.Document(File.Contents(DataFolderPath & "\\{filename}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
            '\t\t\t\t#"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),',
            f'\t\t\t\t#"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers", {{{type_pairs}}}, "en-US")',
            "\t\t\tin",
            '\t\t\t\t#"Changed Type"',
            "",
            "\tannotation PBI_NavigationStepName = Navigation",
            "",
            "\tannotation PBI_ResultType = Table",
            "",
        ]
    )
    return "\n".join(lines)


def m_literal(value) -> str:
    if pd.isna(value):
        return "null"
    if isinstance(value, (bool,)):
        return "true" if value else "false"
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, (float,)):
        return format(value, ".17g")
    return '"' + str(value).replace('"', '""') + '"'


def build_static_table_tmdl(
    table: str,
    frame: pd.DataFrame,
    *,
    sort_columns: dict[str, str] | None = None,
    hidden_columns: set[str] | None = None,
) -> str:
    sort_columns = sort_columns or {}
    hidden_columns = hidden_columns or set()
    lines = [f"table {table}", ""]
    for column, dtype in frame.dtypes.items():
        lines.extend(
            [
                f"\tcolumn {qname(column)}",
                f"\t\tdataType: {dtype_to_tmdl(dtype)}",
                "\t\tsummarizeBy: none",
                f"\t\tsourceColumn: {qname(column)}",
            ]
        )
        if column in sort_columns:
            lines.append(f"\t\tsortByColumn: {sort_columns[column]}")
        if column in hidden_columns:
            lines.append("\t\tisHidden")
        fmt = column_format(column, dtype)
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        lines.append("")

    type_pairs = ", ".join(
        f"{column} = {dtype_to_m_table(dtype)}"
        for column, dtype in frame.dtypes.items()
    )
    row_values = ", ".join(
        "{" + ", ".join(m_literal(value) for value in row) + "}"
        for row in frame.itertuples(index=False, name=None)
    )
    lines.extend(
        [
            f"\tpartition {table} = m",
            "\t\tmode: import",
            "\t\tsource =",
            "\t\t\tlet",
            f"\t\t\t\tSource = #table(type table [{type_pairs}], {{{row_values}}})",
            "\t\t\tin",
            "\t\t\t\tSource",
            "",
        ]
    )
    return "\n".join(lines)


def parameter_tables() -> dict[str, pd.DataFrame]:
    causal = pd.read_csv(DATA_DIR / "promotion_causal_summary.csv").set_index("metric")
    effect = causal.loc["did_incremental_revenue_per_event"]
    return {
        "ScenarioEffect": pd.DataFrame(
            [
                ("Base point estimate (Default)", float(effect["value"]), 0),
                ("Conservative (95% CI low)", float(effect["ci_low"]), 1),
                ("Upside (95% CI high)", float(effect["ci_high"]), 2),
            ],
            columns=["label", "effect_value", "effect_sort"],
        ),
        "MultiplierParameter": pd.DataFrame(
            [("10x (Default)", 10.0, 0), ("1x", 1.0, 1), ("5x", 5.0, 2), ("15x", 15.0, 3), ("20x", 20.0, 4), ("25x", 25.0, 5), ("30x", 30.0, 6), ("40x", 40.0, 7), ("50x", 50.0, 8), ("60x", 60.0, 9)],
            columns=["label", "multiplier_value", "multiplier_sort"],
        ),
        "MarginParameter": pd.DataFrame(
            [("30% (Default)", 0.30, 0), ("20%", 0.20, 1), ("40%", 0.40, 2)],
            columns=["label", "margin_value", "margin_sort"],
        ),
        "CostParameter": pd.DataFrame(
            [("$5 (Default)", 5.0, 0), ("$1", 1.0, 1), ("$10", 10.0, 2)],
            columns=["label", "cost_value", "cost_sort"],
        ),
        "BudgetParameter": pd.DataFrame(
            [("$1,000 (Default)", 1000.0, 0), ("$2,500", 2500.0, 1), ("$5,000", 5000.0, 2)],
            columns=["label", "budget_value", "budget_sort"],
        ),
        "MultiplierAxis": pd.DataFrame(
            [(value, order) for order, value in enumerate([1.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 60.0])],
            columns=["axis_multiplier", "axis_sort"],
        ),
    }


MEASURES = [
    ("Total Store Sales", 'CALCULATE(MAX(DecisionKPIs[value]), DecisionKPIs[metric] = "total_store_observed_sales")', "$#,##0"),
    ("Total Store Sales KPI", 'FORMAT(CALCULATE(MAX(DecisionKPIs[value]), DecisionKPIs[metric] = "total_store_observed_sales") / 1000000, "$0.0", "en-US") & "M"', ""),
    ("Beverage Sales", 'CALCULATE(MAX(DecisionKPIs[value]), DecisionKPIs[metric] = "beverage_observed_sales")', "$#,##0"),
    ("Beverage Sales KPI", 'FORMAT(CALCULATE(MAX(DecisionKPIs[value]), DecisionKPIs[metric] = "beverage_observed_sales") / 1000, "$0", "en-US") & "K"', ""),
    ("Beverage Share", 'CALCULATE(MAX(DecisionKPIs[value]), DecisionKPIs[metric] = "beverage_share_of_store_sales")', "0.0%"),
    ("Coupon Redemption", 'CALCULATE(MAX(DecisionKPIs[value]), DecisionKPIs[metric] = "target_household_coupon_redemption_penetration")', "0.0%"),
    ("Incremental Revenue per Event", 'CALCULATE(MAX(DecisionKPIs[value]), DecisionKPIs[metric] = "incremental_revenue_per_merchandising_event")', "$0.00"),
    ("Incremental Units per Event", 'CALCULATE(MAX(DecisionKPIs[value]), DecisionKPIs[metric] = "incremental_units_per_merchandising_event")', "0.000"),
    ("Matched Events", 'CALCULATE(MAX(DecisionKPIs[value]), DecisionKPIs[metric] = "matched_promotion_events")', "#,0"),
    ("High Value Household Share", 'CALCULATE(MAX(DecisionKPIs[value]), DecisionKPIs[metric] = "high_value_frequent_household_share")', "0.0%"),
    ("High Value Revenue Share", 'CALCULATE(MAX(DecisionKPIs[value]), DecisionKPIs[metric] = "high_value_frequent_revenue_share")', "0.0%"),
    ("Household Count", "SUM(ClusterProfile[household_count])", "#,0"),
    ("Household Count KPI", 'FORMAT(SUM(ClusterProfile[household_count]) / 1000, "0.0", "en-US") & "K"', ""),
    ("Category Sales", "SUM(CategoryScorecard[observed_sales_value])", "$#,##0"),
    ("Category Sales Share", "SUM(CategoryScorecard[sales_contribution])", "0.0%"),
    ("Segment Household Share", "SUM(ClusterProfile[household_share])", "0.0%"),
    ("Segment Revenue Share", "SUM(ClusterProfile[revenue_share])", "0.0%"),
    ("Weighted Customer Retention", "DIVIDE(CALCULATE(SUM(CohortRetention[active_households]), CohortRetention[comparison_eligible] = TRUE(), CohortRetention[left_censored_cohort] = FALSE()), CALCULATE(SUM(CohortRetention[cohort_size]), CohortRetention[comparison_eligible] = TRUE(), CohortRetention[left_censored_cohort] = FALSE()))", "0.0%"),
    ("Event Study Units", "AVERAGE(PromotionEventStudy[did_units])", "0.000"),
    ("Category DID Units", 'IF(SELECTEDVALUE(CategoryScorecard[causal_evidence_status]) = "matched_did_reportable", AVERAGE(CategoryScorecard[did_units]))', "0.000"),
    ("Pre-trend p-value", 'CALCULATE(MAX(PromotionSummary[value]), PromotionSummary[metric] = "pretrend_slope_p_value")', "0.000"),
    ("Incremental Units Standard Error", 'CALCULATE(MAX(PromotionSummary[std_error]), PromotionSummary[metric] = "did_incremental_units_per_event")', "0.000"),
    ("Incremental Units p-value", 'CALCULATE(MAX(PromotionSummary[p_value]), PromotionSummary[metric] = "did_incremental_units_per_event")', "0.000"),
    ("Incremental Units 95% CI", 'VAR Lower = CALCULATE(MAX(PromotionSummary[ci_low]), PromotionSummary[metric] = "did_incremental_units_per_event") VAR Upper = CALCULATE(MAX(PromotionSummary[ci_high]), PromotionSummary[metric] = "did_incremental_units_per_event") RETURN "[" & FORMAT(Lower, "0.000", "en-US") & ", " & FORMAT(Upper, "0.000", "en-US") & "]"', ""),
    ("Placebo P Value", 'CALCULATE(MAX(PromotionSummary[value]), PromotionSummary[metric] = "preperiod_placebo_p_value")', "0.000"),
    ("KMeans Coupon Penetration", 'IF(SELECTEDVALUE(CouponSegments[segment_dimension]) = "kmeans_segment", AVERAGE(CouponSegments[redemption_penetration]))', "0.0%"),
    ("Campaign Penetration", "AVERAGE(CouponCampaigns[target_household_redemption_penetration])", "0.0%"),
    ("Selected Effect", "SELECTEDVALUE(ScenarioEffect[effect_value], 0.5466784869976361)", "$0.000"),
    ("Selected Multiplier", "SELECTEDVALUE(MultiplierParameter[multiplier_value], 10)", "0.0x"),
    ("Selected Gross Margin", "SELECTEDVALUE(MarginParameter[margin_value], 0.30)", "0.0%"),
    ("Selected Cost per Event", "SELECTEDVALUE(CostParameter[cost_value], 5)", "$0.00"),
    ("Selected Budget", "SELECTEDVALUE(BudgetParameter[budget_value], 1000)", "$#,##0"),
    ("Events Funded", "INT(DIVIDE([Selected Budget], [Selected Cost per Event]))", "#,0"),
    ("Projected Incremental Revenue", "[Events Funded] * [Selected Effect] * [Selected Multiplier]", "$#,##0.00"),
    ("Selected Net Contribution", "[Projected Incremental Revenue] * [Selected Gross Margin] - [Selected Budget]", "$#,##0.00;-$#,##0.00"),
    ("Selected Scenario ROI", "DIVIDE([Selected Net Contribution], [Selected Budget])", "0.0%;-0.0%"),
    ("Selected Break-even Multiplier", "DIVIDE([Selected Cost per Event], [Selected Effect] * [Selected Gross Margin])", "0.0x"),
    ("Sensitivity ROI", "VAR AxisMultiplier = SELECTEDVALUE(MultiplierAxis[axis_multiplier]) VAR Revenue = [Events Funded] * [Selected Effect] * AxisMultiplier VAR Net = Revenue * [Selected Gross Margin] - [Selected Budget] RETURN DIVIDE(Net, [Selected Budget])", "0.0%;-0.0%"),
    ("Zero ROI", "0", "0.0%"),
    ("Scenario Value Color", "IF([Selected Scenario ROI] < 0, \"#B91C1C\", \"#15803D\")", ""),
    ("Net Contribution Color", "IF([Selected Net Contribution] < 0, \"#B91C1C\", \"#15803D\")", ""),
]


def build_measures_tmdl() -> str:
    lines = ["table ReportMeasures", ""]
    for name, expression, fmt in MEASURES:
        lines.append(f"\tmeasure {qname(name)} = {expression}")
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        lines.append("")
    lines.extend(
        [
            "\tcolumn MeasureKey",
            "\t\tdataType: int64",
            "\t\tisHidden",
            "\t\tsummarizeBy: none",
            "\t\tsourceColumn: MeasureKey",
            "",
            "\tpartition ReportMeasures = m",
            "\t\tmode: import",
            "\t\tsource =",
            "\t\t\tlet",
            "\t\t\t\tSource = #table(type table [MeasureKey = Int64.Type], {{1}})",
            "\t\t\tin",
            "\t\t\t\tSource",
            "",
        ]
    )
    return "\n".join(lines)


def build_semantic_model() -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    for old in TABLES_DIR.glob("*.tmdl"):
        old.unlink()
    relationships_path = DEFINITION_DIR / "relationships.tmdl"
    if relationships_path.exists():
        relationships_path.unlink()

    for table, filename in TABLE_FILES.items():
        write_text(TABLES_DIR / f"{table}.tmdl", build_table_tmdl(table, filename))
    for table, frame in parameter_tables().items():
        sort_column = next((column for column in frame.columns if column.endswith("_sort")), None)
        write_text(
            TABLES_DIR / f"{table}.tmdl",
            build_static_table_tmdl(
                table,
                frame,
                sort_columns={"label": sort_column} if "label" in frame and sort_column else {},
                hidden_columns={sort_column} if sort_column else set(),
            ),
        )
    write_text(TABLES_DIR / "ReportMeasures.tmdl", build_measures_tmdl())

    # Never write a contributor's absolute local path into a tracked TMDL file.
    # Set FMCG_POWERBI_DATA_PATH only for a private/local build, or update the
    # DataFolderPath parameter in Power BI Desktop before refreshing.
    data_path = os.environ.get(
        "FMCG_POWERBI_DATA_PATH",
        r"C:\path\to\fmcg-promotion-decision-analytics\data\powerbi_exports",
    ).replace('"', '""')
    expressions = (
        f'expression DataFolderPath = "{data_path}" '
        'meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
    )
    write_text(DEFINITION_DIR / "expressions.tmdl", expressions)

    refs = "\n".join(
        f"ref table {table}"
        for table in [*TABLE_FILES, *PARAMETER_TABLE_NAMES, "ReportMeasures"]
    )
    model = f"""model Model
\tculture: zh-CN
\tdefaultPowerBIDataSourceVersion: powerBI_V3
\tsourceQueryCulture: en-US
\tvalueFilterBehavior: independent
\tdataAccessOptions
\t\tlegacyRedirects
\t\treturnErrorValuesAsNull

annotation __PBI_TimeIntelligenceEnabled = 0

annotation PBI_ProTooling = [\"DevMode\"]

ref cultureInfo zh-CN

ref expression DataFolderPath

{refs}
"""
    write_text(DEFINITION_DIR / "model.tmdl", model)

    cultures_dir = DEFINITION_DIR / "cultures"
    cultures_dir.mkdir(parents=True, exist_ok=True)
    for old in cultures_dir.glob("*.tmdl"):
        old.unlink()
    write_text(
        cultures_dir / "zh-CN.tmdl",
        'cultureInfo zh-CN\n\n\tlinguisticMetadata =\n\t\t\t{\n\t\t\t  "Version": "1.0.0",\n\t\t\t  "Language": "en-US"\n\t\t\t}\n\t\tcontentType: json\n',
    )

    diagram_path = MODEL_DIR / "diagramLayout.json"
    if diagram_path.exists():
        diagram = json.loads(diagram_path.read_text(encoding="utf-8"))
        for item in diagram.get("diagrams", []):
            if item.get("name") == "所有表":
                item["name"] = "All tables"
        if diagram.get("selectedDiagram") == "所有表":
            diagram["selectedDiagram"] = "All tables"
        if diagram.get("defaultDiagram") == "所有表":
            diagram["defaultDiagram"] = "All tables"
        write_json(diagram_path, diagram)


def literal(value, kind: str = "string") -> dict:
    if kind == "bool":
        encoded = "true" if value else "false"
    elif kind == "integer":
        encoded = f"{int(value)}L"
    elif kind == "number":
        encoded = f"{value}D"
    else:
        encoded = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": encoded}}}


def fill(color: str) -> dict:
    return {"solid": {"color": literal(color)}}


def measure_fill(measure: str) -> dict:
    return {"solid": {"color": {"expr": measure_field(measure)}}}


def column_field(table: str, column: str) -> dict:
    return {
        "Column": {
            "Expression": {"SourceRef": {"Entity": table}},
            "Property": column,
        }
    }


def measure_field(measure: str) -> dict:
    return {
        "Measure": {
            "Expression": {"SourceRef": {"Entity": "ReportMeasures"}},
            "Property": measure,
        }
    }


def projection(field: dict, table: str, name: str, display_name: str | None = None) -> dict:
    item = {
        "field": field,
        "queryRef": f"{table}.{name}",
        "nativeQueryRef": display_name or name,
    }
    if display_name:
        item["displayName"] = display_name
    return item


def position(x: int, y: int, width: int, height: int, order: int) -> dict:
    return {
        "x": x,
        "y": y,
        "z": 1000 + order,
        "height": height,
        "width": width,
        "tabOrder": order,
    }


def container_objects(title: str | None = None, *, card: bool = False) -> dict:
    result = {
        "background": [
            {
                "properties": {
                    "show": literal(True, "bool"),
                    "color": fill(PALETTE["surface"]),
                    "transparency": literal(0, "number"),
                }
            }
        ],
        "border": [
            {
                "properties": {
                    "show": literal(True, "bool"),
                    "color": fill(PALETTE["line"]),
                    "radius": literal(10, "number"),
                    "width": literal(1, "number"),
                }
            }
        ],
        "dropShadow": [
            {
                "properties": {
                    "show": literal(True, "bool"),
                    "color": fill("#CBD5E1"),
                    "transparency": literal(70, "number"),
                    "position": literal("Outer"),
                    "preset": literal("BottomRight"),
                }
            }
        ],
        "subTitle": [{"properties": {"show": literal(False, "bool")}}],
    }
    result["title"] = [
        {
            "properties": {
                "show": literal(bool(title) and not card, "bool"),
                **(
                    {
                        "text": literal(title),
                        "fontSize": literal(13, "number"),
                        "bold": literal(True, "bool"),
                        "fontColor": fill(PALETTE["ink"]),
                    }
                    if title and not card
                    else {}
                ),
            }
        }
    ]
    return result


def textbox(
    label: str,
    text: str,
    x: int,
    y: int,
    w: int,
    h: int,
    order: int,
    *,
    size: int,
    color: str,
    bold: bool = False,
    background: str | None = None,
    border: str | None = None,
    align: str = "left",
    padding: int = 0,
) -> dict:
    return {
        "$schema": VISUAL_SCHEMA,
        "name": stable_id(label),
        "position": position(x, y, w, h, order),
        "visual": {
            "visualType": "textbox",
            "objects": {
                "general": [
                    {
                        "properties": {
                            "paragraphs": [
                                {
                                    "textRuns": [
                                        {
                                            "value": text,
                                            "textStyle": {
                                                "fontFamily": "Segoe UI",
                                                "fontSize": f"{size}pt",
                                                "color": color,
                                                **({"fontWeight": "bold"} if bold else {}),
                                            },
                                        }
                                    ],
                                    "horizontalTextAlignment": align,
                                }
                            ]
                        }
                    }
                ]
            },
            "visualContainerObjects": {
                "background": [
                    {
                        "properties": {
                            "show": literal(background is not None, "bool"),
                            **({"color": fill(background), "transparency": literal(0, "number")} if background else {}),
                        }
                    }
                ],
                "border": [
                    {
                        "properties": {
                            "show": literal(border is not None, "bool"),
                            **({"color": fill(border), "radius": literal(10, "number"), "width": literal(1, "number")} if border else {}),
                        }
                    }
                ],
                "padding": [
                    {
                        "properties": {
                            "top": literal(padding, "number"),
                            "bottom": literal(padding, "number"),
                            "left": literal(padding, "number"),
                            "right": literal(padding, "number"),
                        }
                    }
                ],
            },
            "drillFilterOtherVisuals": True,
        },
    }


def card(
    label: str,
    measure: str,
    x: int,
    y: int,
    w: int,
    h: int,
    order: int,
    accent: str,
    display_name: str | None = None,
    color_measure: str | None = None,
) -> dict:
    query_ref = f"ReportMeasures.{measure}"
    return {
        "$schema": VISUAL_SCHEMA,
        "name": stable_id(label),
        "position": position(x, y, w, h, order),
        "visual": {
            "visualType": "cardVisual",
            "query": {
                "queryState": {
                    "Data": {
                        "projections": [
                            projection(measure_field(measure), "ReportMeasures", measure, display_name)
                        ]
                    }
                }
            },
            "objects": {
                "value": [
                    {
                        "properties": {
                            "show": literal(True, "bool"),
                            "fontSize": literal(24, "number"),
                            "bold": literal(True, "bool"),
                            "fontColor": (
                                measure_fill(color_measure)
                                if color_measure
                                else fill(accent)
                            ),
                        },
                        "selector": {"id": "default"},
                    }
                ],
                "label": [
                    {
                        "properties": {
                            "show": literal(True, "bool"),
                            "fontSize": literal(10, "number"),
                            "fontColor": fill(PALETTE["muted"]),
                        },
                        "selector": {"id": "default"},
                    }
                ],
            },
            "visualContainerObjects": container_objects(card=True),
            "drillFilterOtherVisuals": True,
        },
    }


def chart(
    label: str,
    visual_type: str,
    title: str,
    category_table: str,
    category_column: str,
    measure: str | list[str],
    x: int,
    y: int,
    w: int,
    h: int,
    order: int,
    *,
    sort_desc: bool = False,
    accent: str = PALETTE["blue"],
) -> dict:
    category = column_field(category_table, category_column)
    measures = [measure] if isinstance(measure, str) else measure
    values = [measure_field(item) for item in measures]
    query = {
        "queryState": {
            "Category": {
                "projections": [
                    projection(category, category_table, category_column)
                ]
            },
            "Y": {
                "projections": [
                    projection(value, "ReportMeasures", name)
                    for value, name in zip(values, measures)
                ]
            },
        }
    }
    if sort_desc:
        query["sortDefinition"] = {
            "sort": [{"field": values[0], "direction": "Descending"}],
            "isDefaultSort": True,
        }
    objects = {}
    if visual_type in {"barChart", "columnChart"}:
        objects = {
            "dataPoint": [
                {"properties": {"defaultColor": fill(accent)}}
            ],
            "labels": [
                {
                    "properties": {
                        "show": literal(True, "bool"),
                        "labelPosition": literal("OutsideEnd"),
                        "labelDisplayUnits": literal(1, "number"),
                        "fontSize": literal(9, "number"),
                        "color": fill(PALETTE["ink"]),
                    }
                }
            ],
            "valueAxis": [
                {
                    "properties": {
                        "show": literal(False, "bool"),
                        "gridlineShow": literal(False, "bool"),
                    }
                }
            ],
        }
    elif visual_type == "lineChart":
        objects = {
            "dataPoint": [
                {"properties": {"defaultColor": fill(accent)}}
            ],
            "lineStyles": [
                {
                    "properties": {
                        "strokeWidth": literal(2.5, "number"),
                        "showMarker": literal(True, "bool"),
                        "markerSize": literal(4, "number"),
                    }
                }
            ]
        }
    return {
        "$schema": VISUAL_SCHEMA,
        "name": stable_id(label),
        "position": position(x, y, w, h, order),
        "visual": {
            "visualType": visual_type,
            "query": query,
            "objects": objects,
            "visualContainerObjects": container_objects(title),
            "drillFilterOtherVisuals": True,
        },
    }


def slicer(label: str, table: str, column: str, x: int, y: int, w: int, h: int, order: int, title: str) -> dict:
    field = column_field(table, column)
    return {
        "$schema": VISUAL_SCHEMA,
        "name": stable_id(label),
        "position": position(x, y, w, h, order),
        "visual": {
            "visualType": "slicer",
            "query": {
                "queryState": {
                    "Values": {
                        "projections": [projection(field, table, column, title)]
                    }
                }
            },
            "objects": {
                "selection": [
                    {
                        "properties": {
                            "strictSingleSelect": literal(True, "bool"),
                            "selectAllCheckboxEnabled": literal(False, "bool"),
                        }
                    }
                ]
            },
            "visualContainerObjects": container_objects(title),
            "drillFilterOtherVisuals": True,
        },
    }


def image_visual(label: str, resource_name: str, x: int, y: int, w: int, h: int, order: int) -> dict:
    return {
        "$schema": VISUAL_SCHEMA,
        "name": stable_id(label),
        "position": position(x, y, w, h, order),
        "visual": {
            "visualType": "image",
            "objects": {
                "general": [
                    {
                        "properties": {
                            "imageUrl": {
                                "expr": {
                                    "ResourcePackageItem": {
                                        "PackageName": "RegisteredResources",
                                        "PackageType": 1,
                                        "ItemName": resource_name,
                                    }
                                }
                            }
                        }
                    }
                ]
            },
            "visualContainerObjects": container_objects(),
            "drillFilterOtherVisuals": True,
        },
    }


def table_visual(label: str, title: str, fields: list[tuple[str, str, str]], x: int, y: int, w: int, h: int, order: int) -> dict:
    projections = []
    for table, name, display_name in fields:
        if table == "ReportMeasures":
            field = measure_field(name)
        else:
            field = column_field(table, name)
        projections.append(projection(field, table, name, display_name))
    return {
        "$schema": VISUAL_SCHEMA,
        "name": stable_id(label),
        "position": position(x, y, w, h, order),
        "visual": {
            "visualType": "tableEx",
            "query": {"queryState": {"Values": {"projections": projections}}},
            "visualContainerObjects": container_objects(title),
            "drillFilterOtherVisuals": True,
        },
    }


def page_header(page_key: str, title: str, subtitle: str, evidence_label: str, evidence_color: str) -> list[dict]:
    return [
        textbox(f"{page_key}-banner", "", 0, 0, 1280, 84, 0, size=1, color="#FFFFFF", background=PALETTE["navy_dark"]),
        textbox(f"{page_key}-title", title, 24, 8, 930, 42, 1, size=21, color="#FFFFFF", bold=True),
        textbox(f"{page_key}-subtitle", subtitle, 24, 50, 930, 22, 2, size=9, color="#CBD5E1"),
        textbox(f"{page_key}-evidence", evidence_label, 992, 23, 264, 34, 3, size=9, color="#FFFFFF", bold=True, background=evidence_color, align="center", padding=6),
    ]


def insight_box(label: str, heading: str, body: str, x: int, y: int, w: int, h: int, order: int, *, accent: str, background: str) -> list[dict]:
    return [
        textbox(f"{label}-bg", "", x, y, w, h, order, size=1, color=accent, background=background, border=accent),
        textbox(f"{label}-heading", heading, x + 16, y + 12, w - 32, 24, order + 1, size=11, color=accent, bold=True),
        textbox(f"{label}-body", body, x + 16, y + 38, w - 32, h - 48, order + 2, size=10, color=PALETTE["ink"]),
    ]


def build_pages() -> list[tuple[str, str, list[dict]]]:
    pages = []

    p1 = page_header(
        "executive",
        "Executive Summary",
        "Observed category sales, campaign redemption, and evidence boundaries in one view.",
        "OBSERVED PERFORMANCE",
        PALETTE["teal"],
    )
    p1 += [
        card("p1-store-sales", "Total Store Sales KPI", 24, 96, 292, 96, 10, PALETTE["navy"], "Total Store Sales"),
        card("p1-beverage-sales", "Beverage Sales KPI", 332, 96, 292, 96, 11, PALETTE["blue"], "Beverage Sales"),
        card("p1-beverage-share", "Beverage Share", 640, 96, 292, 96, 12, PALETTE["teal"]),
        card("p1-coupon", "Coupon Redemption", 948, 96, 308, 96, 13, PALETTE["orange"]),
        chart("p1-category", "barChart", "Revenue by Beverage Category", "CategoryScorecard", "beverage_category", "Category Sales", 24, 208, 600, 276, 20, sort_desc=True, accent=PALETTE["blue"]),
        chart("p1-campaign", "barChart", "Redemption Penetration by Campaign Type", "CouponCampaigns", "campaign_type", "Campaign Penetration", 640, 208, 616, 276, 21, sort_desc=True, accent=PALETTE["orange"]),
    ]
    p1 += insight_box(
        "p1-takeaway",
        "MANAGEMENT TAKEAWAY",
        "Beverages are 8.2% of observed store sales. The matched merchandising effect is +0.36 units per product-store event (95% CI +0.14 to +0.65; p=0.007). Under default cost and margin assumptions, break-even requires a ~30.5x panel-to-total-sales multiplier. Test CSD and juice before scaling spend.",
        24, 500, 752, 126, 30, accent=PALETTE["teal"], background=PALETTE["teal_soft"],
    )
    p1 += insight_box(
        "p1-boundary",
        "HOW TO READ THIS REPORT",
        "Sales and redemption are observed. Promotion lift is quasi-experimental. ROI is an assumption-based planning scenario because actual margin and execution cost are unavailable.",
        792, 500, 464, 126, 33, accent=PALETTE["orange"], background=PALETTE["orange_soft"],
    )
    p1.append(textbox("p1-footnote", "Source: dunnhumby The Complete Journey | Days 1-711 (102 weeks) | 2,500 households; 2,595,732 transaction lines", 24, 682, 1232, 20, 40, size=8, color=PALETTE["muted"]))
    pages.append(("Executive Summary", "Executive Summary", p1))

    p2 = page_header(
        "customer",
        "Customer Growth & Segmentation",
        "Who creates value, how concentrated that value is, and whether customers remain active.",
        "OBSERVED + MODEL-BASED",
        PALETTE["blue"],
    )
    p2 += [
        card("p2-households", "Household Count KPI", 24, 96, 394, 96, 10, PALETTE["navy"], "Household Count"),
        card("p2-hv-share", "High Value Household Share", 443, 96, 394, 96, 11, PALETTE["blue"]),
        card("p2-hv-revenue", "High Value Revenue Share", 862, 96, 394, 96, 12, PALETTE["teal"], "High Value Revenue Share (Whole Store)"),
        chart("p2-household-share", "barChart", "Household Share by Segment", "ClusterProfile", "kmeans_segment", "Segment Household Share", 24, 208, 390, 260, 20, sort_desc=True, accent=PALETTE["blue"]),
        chart("p2-revenue-share", "barChart", "Whole-Store Revenue Share by Segment", "ClusterProfile", "kmeans_segment", "Segment Revenue Share", 434, 208, 390, 260, 21, sort_desc=True, accent=PALETTE["teal"]),
        image_visual("p2-retention-heatmap", "cohort_customer_retention_20261016.png", 844, 208, 412, 260, 22),
    ]
    p2 += insight_box(
        "p2-insight",
        "VALUE CONCENTRATION",
        "High-Value Frequent households represent 45.2% of customers and generate 79.0% of observed whole-store revenue. This is concentration, not a causal segment effect.",
        24, 486, 602, 140, 30, accent=PALETTE["teal"], background=PALETTE["teal_soft"],
    )
    p2 += insight_box(
        "p2-action",
        "RECOMMENDED ACTION",
        "Retention uses 30-day periods and cohort-size weighting. P00 is shown but flagged as left-censored; comparisons use P01-P03 (n=1,962). Tiny later cohorts are excluded.",
        642, 486, 614, 140, 33, accent=PALETTE["blue"], background=PALETTE["blue_soft"],
    )
    p2.append(textbox("p2-footnote", "Source: dunnhumby The Complete Journey | Days 1-711 | 2,500 households | Comparable cohorts: P01-P03, n=1,962", 24, 682, 1232, 20, 40, size=8, color=PALETTE["muted"]))
    pages.append(("Customer Growth", "Customer Growth & Segmentation", p2))

    p3 = page_header(
        "promotion",
        "Promotion Incrementality",
        "Matched controls and Difference-in-Differences separate lift from simple promoted-sales correlation.",
        "QUASI-EXPERIMENTAL",
        PALETTE["blue"],
    )
    p3 += [
        card("p3-events", "Matched Events", 24, 96, 228, 96, 10, PALETTE["navy"]),
        card("p3-units", "Incremental Units per Event", 266, 96, 228, 96, 11, PALETTE["blue"]),
        card("p3-se", "Incremental Units Standard Error", 508, 96, 228, 96, 12, PALETTE["muted"], "Standard Error"),
        card("p3-ci", "Incremental Units 95% CI", 750, 96, 228, 96, 13, PALETTE["teal"], "95% Confidence Interval"),
        card("p3-p", "Incremental Units p-value", 992, 96, 264, 96, 14, PALETTE["muted"], "p-value"),
        image_visual("p3-event-study-image", "promotion_event_study_units_20261016.png", 24, 208, 760, 326, 20),
        chart("p3-category-lift", "barChart", "Incremental Units by Reportable Category", "CategoryScorecard", "beverage_category", "Category DID Units", 800, 208, 456, 326, 21, sort_desc=True, accent=PALETTE["teal"]),
    ]
    p3 += insight_box(
        "p3-result",
        "DECISION SIGNAL",
        "The main effect is event week 0 versus the mean treated-control gap in weeks -4 to -1. The event-study line includes product-cluster bootstrap 95% confidence bands.",
        24, 550, 752, 116, 30, accent=PALETTE["teal"], background=PALETTE["teal_soft"],
    )
    p3 += insight_box(
        "p3-caveat",
        "INTERPRETATION BOUNDARY",
        "Pre-trend p-value = 0.442. This does not reject parallel trends, but it does not prove them. Results remain quasi-experimental rather than randomised.",
        792, 550, 464, 116, 33, accent=PALETTE["orange"], background=PALETTE["orange_soft"],
    )
    p3.append(textbox("p3-footnote", "Source: dunnhumby The Complete Journey | 423 matched isolated merchandising events | Event window: weeks -4 to +4", 24, 690, 1232, 20, 40, size=8, color=PALETTE["muted"]))
    pages.append(("Promotion Incrementality", "Promotion Incrementality", p3))

    p4 = page_header(
        "decision",
        "Budget Scenario Planner",
        "Stress-test the commercial assumptions required for a promotion to create positive contribution.",
        "ASSUMPTION-BASED",
        PALETTE["orange"],
    )
    p4 += [
        card("p4-coupon", "Coupon Redemption", 24, 96, 292, 88, 10, PALETTE["orange"]),
        card("p4-roi", "Selected Scenario ROI", 332, 96, 292, 88, 11, PALETTE["red"], color_measure="Scenario Value Color"),
        card("p4-net", "Selected Net Contribution", 640, 96, 292, 88, 12, PALETTE["red"], color_measure="Net Contribution Color"),
        card("p4-breakeven", "Selected Break-even Multiplier", 948, 96, 308, 88, 13, PALETTE["navy"], "Break-even Multiplier"),
        # Give the five scenario slicers enough vertical room for their field label,
        # selected value and scrollbar. The previous 76 px height clipped the
        # selected values against the charts below in Power BI Desktop.
        slicer("p4-effect", "ScenarioEffect", "label", 24, 198, 260, 100, 20, "Effect Case"),
        slicer("p4-multiplier", "MultiplierParameter", "label", 300, 198, 196, 100, 21, "Panel-to-Total-Sales Multiplier"),
        slicer("p4-margin", "MarginParameter", "label", 512, 198, 220, 100, 22, "Gross Margin"),
        slicer("p4-cost", "CostParameter", "label", 748, 198, 220, 100, 23, "Cost per Event"),
        slicer("p4-budget", "BudgetParameter", "label", 984, 198, 272, 100, 24, "Budget"),
        chart("p4-segment-coupon", "barChart", "Coupon Redemption by Customer Segment", "CouponSegments", "segment_name", "KMeans Coupon Penetration", 24, 312, 500, 254, 30, sort_desc=True, accent=PALETTE["orange"]),
        chart("p4-roi-multiplier", "lineChart", "ROI vs Panel-to-Total-Sales Multiplier (break-even where lines cross)", "MultiplierAxis", "axis_multiplier", ["Sensitivity ROI", "Zero ROI"], 540, 312, 716, 254, 31, accent=PALETTE["blue"]),
    ]
    p4 += insight_box(
        "p4-warning",
        "BASE-CASE READOUT",
        "Default: Base effect $0.5467/event | 10x | 30% margin | $5/event | $1,000 budget. 200 events -> $1,093.36 revenue -> $328.01 gross profit -> -$671.99 net contribution -> -67.20% ROI. Break-even = 30.49x.",
        24, 584, 1232, 82, 40, accent=PALETTE["red"], background="#FFF1F2",
    )
    p4.append(textbox("p4-footnote", "Source: dunnhumby The Complete Journey | 7,208 targeted household-campaign exposures; 30 campaigns | ROI inputs are assumptions", 24, 690, 1232, 20, 44, size=8, color=PALETTE["muted"]))
    pages.append(("Budget Planner", "Budget Scenario Planner", p4))
    return pages


def build_report() -> None:
    REGISTERED_RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    for old in REGISTERED_RESOURCES_DIR.glob("*_20261016.png"):
        old.unlink()
    for resource_name, source in REPORT_IMAGES.items():
        if not source.exists():
            raise FileNotFoundError(f"Missing report image: {source}")
        shutil.copyfile(source, REGISTERED_RESOURCES_DIR / resource_name)

    report_definition = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    report_definition["resourcePackages"] = [
        package
        for package in report_definition.get("resourcePackages", [])
        if package.get("name") != "RegisteredResources"
    ]
    report_definition["resourcePackages"].append(
        {
            "name": "RegisteredResources",
            "type": "RegisteredResources",
            "items": [
                {"name": name, "path": name, "type": "Image"}
                for name in REPORT_IMAGES
            ],
        }
    )
    write_json(REPORT_JSON, report_definition)

    if PAGES_DIR.exists():
        resolved = PAGES_DIR.resolve()
        if REPORT_DIR.resolve() not in resolved.parents:
            raise RuntimeError(f"Refusing to replace unexpected directory: {resolved}")
        shutil.rmtree(PAGES_DIR)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    page_order = []
    for index, (page_key, display_name, visuals) in enumerate(build_pages()):
        page_id = stable_id(f"page-{page_key}")
        page_order.append(page_id)
        page_dir = PAGES_DIR / page_id
        write_json(
            page_dir / "page.json",
            {
                "$schema": PAGE_SCHEMA,
                "name": page_id,
                "displayName": display_name,
                "displayOption": "FitToPage",
                "height": 720,
                "width": 1280,
            },
        )
        for visual in visuals:
            visual_id = visual["name"]
            write_json(page_dir / "visuals" / visual_id / "visual.json", visual)

    write_json(
        PAGES_DIR / "pages.json",
        {
            "$schema": PAGES_SCHEMA,
            "pageOrder": page_order,
            "activePageName": page_order[0],
        },
    )


def build_readme() -> None:
    content = """# Power BI Portfolio Report

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
  gross margin and panel-to-total-sales multipliers.

Raw Dunnhumby files and household-level local analytical exports remain excluded
from redistribution under the repository data-use policy.

## Budget scenario definitions

The parameter slicers are disconnected, strict single-select tables. Their first
sorted values are the defaults: Base point estimate, 10x multiplier, 30% gross
margin, $5 per event and $1,000 budget.

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
"""
    write_text(POWERBI_DIR / "README.md", content)


def write_dashboard_validation() -> None:
    scenarios = pd.read_csv(DATA_DIR / "roi_assumption_scenarios.csv")
    causal = pd.read_csv(DATA_DIR / "promotion_causal_summary.csv").set_index("metric")
    cohort = pd.read_csv(DATA_DIR / "cohort_retention_long.csv")
    effect = float(causal.loc["did_incremental_revenue_per_event", "value"])
    margin = 0.30
    cost = 5.0
    budget = 1000.0
    multiplier = 10.0
    events = int(budget // cost)
    revenue = events * effect * multiplier
    net = revenue * margin - budget
    roi = net / budget
    break_even = cost / (effect * margin)

    age_12 = cohort.loc[cohort["cohort_age"].eq(12)].copy()
    eligible_12 = age_12.loc[
        age_12["comparison_eligible"] & ~age_12["left_censored_cohort"]
    ]
    old_retention = age_12["customer_retention_rate"].mean()
    new_retention = (
        eligible_12["active_households"].sum()
        / eligible_12["cohort_size"].sum()
    )

    rows = [
        ("Scenario ROI", scenarios["scenario_roi"].mean(), roi, "Old card averaged 243 incompatible scenarios; new value is one coherent default scenario."),
        ("Net Contribution", scenarios["projected_net_contribution"].mean(), net, "Old card averaged scenario dollars; new value reconciles to ROI and budget."),
        ("Break-even Multiplier", scenarios["break_even_panel_to_total_multiplier"].mean(), break_even, "Old card averaged break-even points; new value uses the selected effect, cost and margin."),
        ("Retention at Cohort Age 12", old_retention, new_retention, "Old value was an unweighted cohort mean including P00; new value weights P01-P03 by cohort size."),
        ("Incremental Units Standard Error", None, float(causal.loc["did_incremental_units_per_event", "std_error"]), "Product-cluster bootstrap standard error added."),
        ("Incremental Units p-value", None, float(causal.loc["did_incremental_units_per_event", "p_value"]), "Two-sided normal approximation using the product-cluster bootstrap SE."),
    ]
    for axis_multiplier in [1.0, 10.0, 20.0, 25.0]:
        sensitivity_net = events * effect * axis_multiplier * margin - budget
        rows.append(
            (
                f"Sensitivity ROI at {axis_multiplier:g}x",
                (
                    scenarios.loc[
                        scenarios["assumed_panel_to_total_multiplier"].eq(axis_multiplier),
                        "scenario_roi",
                    ].mean()
                    if axis_multiplier in set(scenarios["assumed_panel_to_total_multiplier"])
                    else None
                ),
                sensitivity_net / budget,
                "New line holds effect, margin, cost and budget fixed; ROI is monotonic in multiplier.",
            )
        )
    output = pd.DataFrame(rows, columns=["metric", "before", "after", "reason"])
    path = ROOT / "outputs" / "validation" / "dashboard_before_after.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)


def main() -> None:
    missing = [filename for filename in TABLE_FILES.values() if not (DATA_DIR / filename).exists()]
    if missing:
        raise FileNotFoundError(f"Missing Power BI exports: {missing}")
    build_semantic_model()
    build_report()
    build_readme()
    write_dashboard_validation()
    print(f"Built semantic model with {len(TABLE_FILES) + len(PARAMETER_TABLE_NAMES) + 1} tables.")
    print("Built 4 PBIR report pages.")
    print(f"Open: {POWERBI_DIR / 'FMCG.pbip'}")


if __name__ == "__main__":
    main()

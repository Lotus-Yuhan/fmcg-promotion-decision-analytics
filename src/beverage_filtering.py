"""
beverage_filtering.py — identify non-alcoholic, non-dairy beverage SKUs.

SCOPE DECISION: This project targets Coca-Cola-relevant beverages.
We include: carbonated soft drinks, juices, water, tea, coffee, energy/sports drinks,
and other non-dairy non-alcoholic beverages.
We EXCLUDE:
  - Alcohol (BEERS/ALES, DOMESTIC WINE, IMPORTED WINE, LIQUOR) — not Coca-Cola categories.
  - Dairy milk (FLUID MILK PRODUCTS) — not Coca-Cola's core beverage focus.
  - Baking mixes, dry mix desserts, salad mixes, coffee filters, sports memorabilia
    that incidentally matched the keyword scan — excluded by using an explicit
    allowlist of commodity strings rather than raw keyword matching.
"""

import pathlib
import pandas as pd

PROCESSED_DIR = pathlib.Path(__file__).parent.parent / "data" / "processed"
SUMMARY_DIR = pathlib.Path(__file__).parent.parent / "outputs" / "summary_tables"

# Explicit allowlist built from inspecting commodity_desc value_counts.
# Using an allowlist (rather than a keyword regex) avoids false positives like
# "BAKING MIXES", "SALAD MIX", "DRY MIX DESSERTS", "SPORTS MEMORABILIA", etc.
BEVERAGE_COMMODITIES = {
    "SOFT DRINKS",
    "CANNED JUICES",
    "COFFEE",
    "WATER - CARBONATED/FLVRD DRINK",
    "REFRGRATD JUICES/DRNKS",
    "TEAS",
    "ISOTONIC DRINKS",
    "JUICE",
    "NON-DAIRY BEVERAGES",
    "WATER",
    "DRY TEA/COFFEE/COCO MIX",
    "COCOA MIXES",
    "BEVERAGE",
    "SERVICE BEVERAGE",
    "NDAIRY/TEAS/JUICE/SOD",
}

# Map commodity_desc → beverage_category for downstream analysis.
# "Carbonated Soft Drinks" is the anchor category for Coca-Cola strategy work.
_CATEGORY_MAP = {
    "SOFT DRINKS": "Carbonated Soft Drinks",
    "WATER - CARBONATED/FLVRD DRINK": "Carbonated Soft Drinks",
    "CANNED JUICES": "Juice",
    "REFRGRATD JUICES/DRNKS": "Juice",
    "JUICE": "Juice",
    "WATER": "Water",
    "TEAS": "Tea",
    "DRY TEA/COFFEE/COCO MIX": "Tea",
    "COFFEE": "Coffee",
    "ISOTONIC DRINKS": "Energy/Sports Drinks",
    "NON-DAIRY BEVERAGES": "Other Beverages",
    "COCOA MIXES": "Other Beverages",
    "BEVERAGE": "Other Beverages",
    "SERVICE BEVERAGE": "Other Beverages",
    "NDAIRY/TEAS/JUICE/SOD": "Other Beverages",
}


def get_beverage_products() -> pd.DataFrame:
    """
    Returns a DataFrame of beverage products with an added `beverage_category` column.
    Reads from data/processed/products.parquet — run data_cleaning.py first.
    """
    products = pd.read_parquet(PROCESSED_DIR / "products.parquet")

    bev = products[products["commodity_desc"].isin(BEVERAGE_COMMODITIES)].copy()
    bev["beverage_category"] = bev["commodity_desc"].map(_CATEGORY_MAP).fillna("Other Beverages")

    return bev.reset_index(drop=True)


def main():
    print("=== Beverage product filtering ===\n")

    bev = get_beverage_products()

    print(f"Total beverage SKUs: {len(bev):,}")
    print()

    print("SKUs by beverage_category:")
    cat_counts = bev["beverage_category"].value_counts()
    print(cat_counts.to_string())
    print()

    print("SKUs by commodity_desc (top 15):")
    comm_counts = bev["commodity_desc"].value_counts().head(15)
    print(comm_counts.to_string())
    print()

    # Write parquet
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_parquet = PROCESSED_DIR / "beverage_products.parquet"
    bev.to_parquet(out_parquet, index=False, engine="pyarrow")
    print(f"wrote {out_parquet} ({len(bev):,} rows)")

    # Save summary CSV
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    summary = (
        bev.groupby(["beverage_category", "commodity_desc"])
        .size()
        .reset_index(name="sku_count")
        .sort_values(["beverage_category", "sku_count"], ascending=[True, False])
    )
    csv_path = SUMMARY_DIR / "beverage_sku_counts.csv"
    summary.to_csv(csv_path, index=False)
    print(f"wrote {csv_path}")

    print("\n=== Data quality notes ===")
    null_brand = bev["brand"].isna().sum()
    null_commodity = bev["commodity_desc"].isna().sum()
    print(f"Null brand values:         {null_brand:,}")
    print(f"Null commodity_desc:       {null_commodity:,}")
    print(f"Unique manufacturers:      {bev['manufacturer'].nunique():,}")
    print(f"Unique brands:             {bev['brand'].nunique():,}")


if __name__ == "__main__":
    main()

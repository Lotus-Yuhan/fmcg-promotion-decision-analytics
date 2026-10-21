"""
data_cleaning.py — load and clean all raw Dunnhumby Complete Journey tables.

Column names are lowercased everywhere so downstream modules can rely on
consistent attribute access (e.g. df['household_key'] not df['household_Key']).
"""

import pathlib
import pandas as pd

RAW_DIR = pathlib.Path(__file__).parent.parent / "data" / "raw"
PROCESSED_DIR = pathlib.Path(__file__).parent.parent / "data" / "processed"


def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Strip leading/trailing whitespace from all object columns in-place."""
    # pandas 3 uses a dedicated string dtype by default.  Include both legacy
    # object columns and the new string dtype so the cleaning step works across
    # pandas 2.x and 3.x without raising a compatibility warning.
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].str.strip()
    return df


def load_products() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "product.csv")
    df.columns = [c.lower() for c in df.columns]
    _strip_strings(df)
    return df


def load_transactions(chunked: bool = False):
    """
    chunked=True returns a TextFileReader iterator (chunksize=500_000).
    chunked=False returns the full DataFrame — only safe if you have enough RAM.
    """
    dtype = {
        "household_key": "Int64",
        "BASKET_ID": "Int64",
        "DAY": "Int64",
        "PRODUCT_ID": "Int64",
        "QUANTITY": "Int64",
        "SALES_VALUE": "float64",
        "STORE_ID": "Int64",
        "RETAIL_DISC": "float64",
        "TRANS_TIME": "Int64",
        "WEEK_NO": "Int64",
        "COUPON_DISC": "float64",
        "COUPON_MATCH_DISC": "float64",
    }
    col_rename = {k: k.lower() for k in dtype}

    reader = pd.read_csv(
        RAW_DIR / "transaction_data.csv",
        dtype=dtype,
        chunksize=500_000 if chunked else None,
    )

    if chunked:
        def _rename_iter(r):
            for chunk in r:
                chunk.columns = [c.lower() for c in chunk.columns]
                yield chunk
        return _rename_iter(reader)

    reader.columns = [c.lower() for c in reader.columns]
    return reader


def load_demographics() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "hh_demographic.csv")
    df.columns = [c.lower() for c in df.columns]
    _strip_strings(df)
    df["household_key"] = df["household_key"].astype("Int64")
    return df


def load_campaign_desc() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "campaign_desc.csv")
    df.columns = [c.lower() for c in df.columns]
    _strip_strings(df)
    return df


def load_campaign_table() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "campaign_table.csv")
    df.columns = [c.lower() for c in df.columns]
    _strip_strings(df)
    df["household_key"] = df["household_key"].astype("Int64")
    return df


def load_coupon() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "coupon.csv")
    df.columns = [c.lower() for c in df.columns]
    _strip_strings(df)
    return df


def load_coupon_redempt() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "coupon_redempt.csv")
    df.columns = [c.lower() for c in df.columns]
    _strip_strings(df)
    df["household_key"] = df["household_key"].astype("Int64")
    return df


def load_causal(product_ids: set | None = None) -> pd.DataFrame:
    """
    Reads causal_data.csv in 1M-row chunks.
    Pass a set of int product_ids to filter while reading — this keeps peak
    memory manageable on the 660MB file.
    """
    chunks = []
    for chunk in pd.read_csv(
        RAW_DIR / "causal_data.csv",
        chunksize=1_000_000,
        dtype={
            "PRODUCT_ID": "Int64",
            "STORE_ID": "Int64",
            "WEEK_NO": "Int64",
            "display": "string",
            "mailer": "string",
        },
    ):
        chunk.columns = [c.lower() for c in chunk.columns]
        if product_ids is not None:
            chunk = chunk[chunk["product_id"].isin(product_ids)]
        chunks.append(chunk)
    return pd.concat(chunks, ignore_index=True)


def write_processed(df: pd.DataFrame, name: str) -> pathlib.Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / f"{name}.parquet"
    df.to_parquet(path, index=False, engine="pyarrow")
    print(f"wrote {path} ({len(df):,} rows)")
    return path


def clean_all():
    """
    Load all small tables, clean, and write parquet.
    Transactions are streamed in 500k-row chunks to avoid OOM on the 135MB CSV.
    """
    print("=== Loading small tables ===")

    products = load_products()
    print(f"products: {len(products):,} rows, {products['product_id'].nunique():,} unique SKUs")
    write_processed(products, "products")

    demographics = load_demographics()
    print(f"demographics: {len(demographics):,} rows — "
          f"{demographics['household_key'].nunique():,} unique households with demo data")
    write_processed(demographics, "demographics")

    campaign_desc = load_campaign_desc()
    print(f"campaign_desc: {len(campaign_desc):,} campaigns")
    write_processed(campaign_desc, "campaign_desc")

    campaign_table = load_campaign_table()
    print(f"campaign_table: {len(campaign_table):,} rows, "
          f"{campaign_table['household_key'].nunique():,} unique targeted households")
    write_processed(campaign_table, "campaign_table")

    coupon = load_coupon()
    print(f"coupon: {len(coupon):,} rows, {coupon['product_id'].nunique():,} unique products")
    write_processed(coupon, "coupon")

    coupon_redempt = load_coupon_redempt()
    print(f"coupon_redempt: {len(coupon_redempt):,} redemptions")
    # Data quality note: coupon_redempt has far fewer rows than coupon — most
    # distributed coupons are never redeemed, which is expected retail behaviour.
    redempt_in_coupon = coupon_redempt["coupon_upc"].isin(coupon["coupon_upc"]).sum()
    unmatched = len(coupon_redempt) - redempt_in_coupon
    if unmatched > 0:
        print(f"  WARNING: {unmatched:,} redemptions have coupon_upc not in coupon.csv")
    write_processed(coupon_redempt, "coupon_redempt")

    print("\n=== Streaming transactions (500k-row chunks) ===")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    tx_path = PROCESSED_DIR / "transactions.parquet"

    all_chunks = []
    total_rows = 0
    for i, chunk in enumerate(load_transactions(chunked=True)):
        all_chunks.append(chunk)
        total_rows += len(chunk)
        print(f"  chunk {i+1}: {len(chunk):,} rows  (running total {total_rows:,})")

    transactions = pd.concat(all_chunks, ignore_index=True)
    transactions.to_parquet(tx_path, index=False, engine="pyarrow")
    print(f"wrote {tx_path} ({len(transactions):,} rows)")
    print(f"  unique households: {transactions['household_key'].nunique():,}")
    print(f"  unique products:   {transactions['product_id'].nunique():,}")
    print(f"  date range (day):  {transactions['day'].min()} – {transactions['day'].max()}")
    print(f"  week range:        {transactions['week_no'].min()} – {transactions['week_no'].max()}")
    print(f"  total sales value: ${transactions['sales_value'].sum():,.2f}")

    print("\n=== clean_all() complete ===")


if __name__ == "__main__":
    clean_all()

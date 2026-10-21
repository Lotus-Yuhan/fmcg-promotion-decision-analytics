"""
Generate LinkedIn-ready visuals for the Promotion & Revenue Growth Analytics project.

Outputs a cohesive 5-slide carousel (1080x1080 px) to outputs/linkedin/.
No Power BI — pure matplotlib with a consistent premium editorial style.

Run:  python scripts/make_linkedin_visuals.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "data" / "powerbi_exports"
OUT = ROOT / "outputs" / "linkedin"
OUT.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# Brand / style system
# --------------------------------------------------------------------------- #
INK      = "#14213D"   # deep navy — primary text
MUTED    = "#6B7280"   # secondary text
HAIRLINE = "#E5E7EB"   # subtle separators
BG       = "#FFFFFF"
PANEL    = "#F6F7FB"

RED      = "#E63946"   # primary accent (energy / beverage)
TEAL     = "#2A9D8F"
GOLD     = "#E9A23B"
BLUE     = "#457B9D"
PURPLE   = "#6D6875"

SEQ = [RED, BLUE, TEAL, GOLD, PURPLE, "#A8B0BD", "#C7CDD6"]

FONT = "Segoe UI"
mpl.rcParams.update({
    "font.family": FONT,
    "font.size": 14,
    "axes.edgecolor": HAIRLINE,
    "axes.linewidth": 1.0,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.dpi": 135,
    "savefig.dpi": 135,
})

PX = 1080
FIGSIZE = (PX / 135, PX / 135)  # -> 1080 x 1080

FOOTER = "Medhansh Rajdeo   ·   Revenue Growth Analytics   ·   Source: Dunnhumby Complete Journey"


def new_canvas():
    fig = plt.figure(figsize=FIGSIZE, facecolor=BG)
    fig.patch.set_facecolor(BG)
    return fig


def add_eyebrow(fig, text, x=0.075, y=0.935):
    """Small uppercase accent label."""
    fig.text(x, y, text.upper(), color=RED, fontsize=13.5, fontweight="bold",
             ha="left", va="center", family=FONT)
    # little tick mark
    fig.add_artist(plt.Line2D([x, x + 0.045], [y - 0.027, y - 0.027],
                              color=RED, lw=3, solid_capstyle="round"))


def add_title(fig, title, sub=None, x=0.075, top=0.862, size=30, lh=0.064):
    """Title may contain \\n for multiple lines. Subtitle placed below."""
    lines = title.split("\n")
    y = top
    for ln in lines:
        fig.text(x, y, ln, color=INK, fontsize=size, fontweight="bold",
                 ha="left", va="center", family=FONT)
        y -= lh
    last_center = top - (len(lines) - 1) * lh
    if sub:
        fig.text(x, last_center - 0.058, sub, color=MUTED, fontsize=14.5,
                 ha="left", va="center", family=FONT)


def add_footer(fig, page):
    fig.add_artist(plt.Line2D([0.075, 0.925], [0.055, 0.055],
                              color=HAIRLINE, lw=1.2))
    fig.text(0.075, 0.033, FOOTER, color=MUTED, fontsize=10.5,
             ha="left", va="center", family=FONT)
    fig.text(0.925, 0.033, f"{page}/5", color=MUTED, fontsize=10.5,
             ha="right", va="center", family=FONT, fontweight="bold")


def money(v):
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:,.0f}"


def save(fig, name):
    path = OUT / name
    fig.savefig(path, facecolor=BG, bbox_inches=None, pad_inches=0)
    plt.close(fig)
    print(f"  wrote {path.relative_to(ROOT)}")


# --------------------------------------------------------------------------- #
# Load data
# --------------------------------------------------------------------------- #
kpis = pd.read_csv(EXPORTS / "commercial_kpis.csv")
segments = pd.read_csv(EXPORTS / "household_segments.csv")
promo = pd.read_csv(EXPORTS / "promotion_performance.csv")
whatif = pd.read_csv(EXPORTS / "what_if_scenarios.csv")
products = pd.read_csv(EXPORTS / "dim_products_beverage.csv")


def kpi(name):
    return float(kpis.loc[kpis.kpi_name == name, "kpi_value"].iloc[0])


TOTAL_REV   = kpi("Total Revenue (All Categories)")
BEV_REV     = kpi("Beverage Revenue")
PROMO_PCT   = kpi("Beverage Promo Revenue %")
MEAN_LIFT   = kpi('Mean Promotion Lift (Beverages, Unit-Weighted)')
MEDIAN_LIFT = kpi("Median Promotion Lift (Beverages)")
N_SKU       = products["product_id"].nunique()


# =========================================================================== #
# SLIDE 1 — Cover + headline KPIs
# =========================================================================== #
def slide_cover():
    fig = new_canvas()

    # top accent band
    fig.add_artist(plt.Rectangle((0, 0.965), 1, 0.035, color=RED,
                                 transform=fig.transFigure, zorder=5))

    fig.text(0.075, 0.885, "REVENUE GROWTH MANAGEMENT", color=RED, fontsize=14,
             fontweight="bold", ha="left", va="center", family=FONT)
    fig.add_artist(plt.Line2D([0.075, 0.12], [0.86, 0.86], color=RED, lw=3,
                              solid_capstyle="round"))

    fig.text(0.075, 0.70, "Promotion &\nRevenue Growth\nAnalytics", color=INK,
             fontsize=44, fontweight="bold", ha="left", va="center",
             linespacing=1.08, family=FONT)

    fig.text(0.075, 0.535,
             "Where do beverage promotions actually create value —\n"
             "and which customers drive the revenue?",
             color=MUTED, fontsize=16.5, ha="left", va="center",
             linespacing=1.35, family=FONT)

    # KPI tiles 2x2
    tiles = [
        (money(TOTAL_REV), "Total revenue analyzed", RED),
        (money(BEV_REV),   "Beverage revenue",        BLUE),
        (f"{N_SKU:,}",     "Beverage SKUs",           TEAL),
        (f"{PROMO_PCT:.0f}%", "of beverage revenue on promo", GOLD),
    ]
    x0, y0 = 0.075, 0.115
    w, h, gx, gy = 0.40, 0.155, 0.045, 0.045
    coords = [(x0, y0 + h + gy), (x0 + w + gx, y0 + h + gy),
              (x0, y0),          (x0 + w + gx, y0)]
    for (val, label, c), (x, y) in zip(tiles, coords):
        box = FancyBboxPatch((x, y), w, h, transform=fig.transFigure,
                             boxstyle="round,pad=0.004,rounding_size=0.02",
                             linewidth=0, facecolor=PANEL, zorder=1)
        fig.add_artist(box)
        fig.add_artist(plt.Rectangle((x, y), 0.008, h, transform=fig.transFigure,
                                     color=c, zorder=2))
        fig.text(x + 0.035, y + h * 0.62, val, color=INK, fontsize=33,
                 fontweight="bold", ha="left", va="center", family=FONT)
        fig.text(x + 0.035, y + h * 0.24, label, color=MUTED, fontsize=13.5,
                 ha="left", va="center", family=FONT)

    save(fig, "01_cover.png")


# =========================================================================== #
# SLIDE 2 — Beverage revenue by category
# =========================================================================== #
def slide_categories():
    cat = (promo.groupby("beverage_category")["total_revenue"].sum()
           .sort_values(ascending=True))
    share = cat / cat.sum() * 100
    short_cat = {
        "Carbonated Soft Drinks": "Soft Drinks",
        "Sports & Energy Drinks": "Sports / Energy",
        "Other Beverages": "Other",
        "Water": "Water", "Juice": "Juice", "Coffee": "Coffee", "Tea": "Tea",
    }
    labels = [short_cat.get(c, c) for c in cat.index]

    fig = new_canvas()
    add_eyebrow(fig, "Portfolio mix")
    add_title(fig, "Carbonated soft drinks\ncarry the category",
              "Beverage revenue by sub-category · share of the $661K")

    ax = fig.add_axes([0.27, 0.135, 0.55, 0.55])
    colors = [RED if c == cat.index[-1] else "#C7CDD6" for c in cat.index]
    bars = ax.barh(labels, cat.values, color=colors, height=0.66, zorder=3)
    ax.set_xlim(0, cat.max() * 1.30)
    for b, v, s in zip(bars, cat.values, share.values):
        ax.text(b.get_width() + cat.max() * 0.02, b.get_y() + b.get_height() / 2,
                f"{money(v)}  ·  {s:.0f}%", va="center", ha="left",
                color=INK, fontsize=13, fontweight="bold", family=FONT)

    ax.set_facecolor(BG)
    for s in ["top", "right", "bottom"]:
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(HAIRLINE)
    ax.set_xticks([])
    ax.tick_params(axis="y", length=0, labelsize=15)
    for lbl in ax.get_yticklabels():
        lbl.set_color(INK)

    add_footer(fig, 2)
    save(fig, "02_category_revenue.png")


# =========================================================================== #
# SLIDE 3 — The promotion-lift reality (the honest insight)
# =========================================================================== #
def slide_lift():
    # Noise filter — lift is only trustworthy with enough observations.
    # Matches src/promotion_metrics.py qualification gate (and the README's 36).
    qual = promo[(promo["units_sold"] >= 50) &
                 (promo["promo_weeks"] >= 3) &
                 (promo["non_promo_weeks"] >= 3)].copy()
    qual = qual[np.isfinite(qual["lift_index_vs_category"])]

    n_total = N_SKU
    n_qual = len(qual)
    n_stars = int((qual["lift_index_vs_category"] >= 2.4).sum())

    s = qual["lift_index_vs_category"]
    s = s[(s > 0) & (s < 3)]  # trim extreme tail for a readable axis

    fig = new_canvas()
    add_eyebrow(fig, "The honest finding")
    add_title(fig, "Promotional ROI hides\nin a thin tail",
              "Lift vs. category average · 873 reliably-measured SKUs · 1.0× = on par")

    ax = fig.add_axes([0.075, 0.40, 0.85, 0.305])
    bins = np.linspace(0, 3, 31)
    ax.hist(s, bins=bins, color="#C7CDD6", edgecolor=BG, linewidth=0.8, zorder=3)
    # shade the high-lift zone (>= 2.4x) rather than recolour bars,
    # so no specific count is implied by the bars themselves
    ax.axvspan(2.4, 3.0, color=RED, alpha=0.10, zorder=1)
    ax.hist(s[s >= 2.4], bins=bins, color=RED, edgecolor=BG, linewidth=0.8, zorder=4)
    ax.axvline(1.0, color=INK, lw=1.6, ls=(0, (4, 3)), zorder=5)
    ax.text(1.04, ax.get_ylim()[1] * 0.96, "parity (1.0×)", color=INK,
            fontsize=12, va="top", ha="left", family=FONT)
    ax.text(2.42, ax.get_ylim()[1] * 0.55, "high-lift\nzone ≥ 2.4×", color=RED,
            fontsize=11.5, va="center", ha="left", family=FONT, linespacing=1.2)

    ax.set_facecolor(BG)
    for sp in ["top", "right", "left"]:
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(HAIRLINE)
    ax.set_yticks([])
    ax.tick_params(axis="x", length=0, labelsize=12.5)

    # Funnel — three populations, no conflation: 4,910 -> 873 -> 36
    funnel = [
        (f"{n_total:,}", "beverage\nSKUs", MUTED),
        (f"{n_qual:,}",  "measured\nreliably", BLUE),
        (f"{n_stars}",   "stars at\n≥ 2.4× lift", RED),
    ]
    fig.text(0.5, 0.305, "The typical promo barely beats its category — "
             "a handful of SKUs carry the return.",
             color=INK, fontsize=13, ha="center", va="center", family=FONT)

    xs = [0.15, 0.50, 0.85]
    yv = 0.175
    for (val, label, c), x in zip(funnel, xs):
        fig.text(x, yv, val, color=c, fontsize=40, fontweight="bold",
                 ha="center", va="center", family=FONT)
        fig.text(x, yv - 0.068, label, color=MUTED, fontsize=12.5,
                 ha="center", va="center", family=FONT, linespacing=1.25)
    for xa, xb in [(xs[0], xs[1]), (xs[1], xs[2])]:
        fig.text((xa + xb) / 2, yv, "→", color="#B8BFCC", fontsize=26,
                 ha="center", va="center", family=FONT)

    add_footer(fig, 3)
    save(fig, "03_promotion_lift.png")


# =========================================================================== #
# SLIDE 4 — Customer segments: 25% of households → 64% of revenue
# =========================================================================== #
def slide_segments():
    df = segments.copy()
    df["revenue"] = df["household_count"] * df["avg_beverage_spend"]
    df["hh_share"] = df["household_count"] / df["household_count"].sum() * 100
    df["rev_share"] = df["revenue"] / df["revenue"].sum() * 100
    # order by revenue share desc
    df = df.sort_values("rev_share", ascending=False).reset_index(drop=True)

    short = {
        "High-Value Beverage Buyers": "High-Value",
        "Promo-Sensitive Shoppers": "Promo-Sensitive",
        "Low-Engagement Shoppers": "Low-Engagement",
        "Coupon-Driven Shoppers": "Coupon-Driven",
    }
    labels = [short.get(s, s) for s in df["segment"]]

    fig = new_canvas()
    add_eyebrow(fig, "Customer value")
    add_title(fig, "A quarter of households\ndrive two-thirds of revenue",
              "Share of households vs. share of revenue, by segment")

    ax = fig.add_axes([0.30, 0.165, 0.60, 0.50])
    y = np.arange(len(df))[::-1]
    bh = 0.36
    b1 = ax.barh(y + bh / 2 + 0.02, df["hh_share"], height=bh, color="#C7CDD6",
                 zorder=3, label="% of households")
    b2 = ax.barh(y - bh / 2 - 0.02, df["rev_share"], height=bh, color=RED,
                 zorder=3, label="% of revenue")

    ax.set_xlim(0, max(df["hh_share"].max(), df["rev_share"].max()) * 1.2)
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_width() + 1.0, b.get_y() + b.get_height() / 2,
                    f"{b.get_width():.0f}%", va="center", ha="left",
                    color=INK, fontsize=12.5, fontweight="bold", family=FONT)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=14.5)
    for lbl in ax.get_yticklabels():
        lbl.set_color(INK)
    ax.set_facecolor(BG)
    for sp in ["top", "right", "bottom"]:
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color(HAIRLINE)
    ax.set_xticks([])
    ax.tick_params(axis="y", length=0)

    # legend
    fig.text(0.30, 0.115, "■", color="#C7CDD6", fontsize=15, va="center", family=FONT)
    fig.text(0.325, 0.115, "Share of households", color=MUTED, fontsize=13,
             va="center", family=FONT)
    fig.text(0.55, 0.115, "■", color=RED, fontsize=15, va="center", family=FONT)
    fig.text(0.575, 0.115, "Share of revenue", color=MUTED, fontsize=13,
             va="center", family=FONT)

    add_footer(fig, 4)
    save(fig, "04_segments.png")


# =========================================================================== #
# SLIDE 5 — What-if: discount depth vs revenue (directional)
# =========================================================================== #
def slide_whatif():
    csd = whatif[(whatif["beverage_category"] == "Carbonated Soft Drinks") &
                 (~whatif["coupon_applied"])].copy()
    csd = csd.sort_values("discount_pct")

    fig = new_canvas()
    add_eyebrow(fig, "Scenario planning")
    add_title(fig, "Modeling the\nrevenue lever",
              "Projected revenue change vs. discount depth (CSD)")

    ax = fig.add_axes([0.115, 0.205, 0.80, 0.48])
    x = csd["discount_pct"] * 100
    yv = csd["revenue_delta_pct"]
    ax.plot(x, yv, color=BLUE, lw=3, zorder=3, solid_capstyle="round")
    ax.scatter(x, yv, color=BLUE, s=70, zorder=4, edgecolor=BG, linewidth=1.5)
    # peak marker
    peak = csd.loc[csd["revenue_delta_pct"].idxmax()]
    ax.scatter([peak["discount_pct"] * 100], [peak["revenue_delta_pct"]],
               color=RED, s=170, zorder=5, edgecolor=BG, linewidth=2)

    for xi, yi in zip(x, yv):
        ax.text(xi, yi - 2.4, f"+{yi:.0f}%", ha="center", va="top",
                color=MUTED, fontsize=11, family=FONT)

    # peak callout inside the plot (top-left) — never clips
    ax.text(0.025, 0.94,
            f"Peak  +{peak['revenue_delta_pct']:.0f}%  @  {peak['discount_pct']*100:.0f}% off",
            transform=ax.transAxes, color=RED, fontsize=15, fontweight="bold",
            ha="left", va="top", family=FONT)

    ax.set_xlim(-1, x.max() + 1.5)
    ax.set_facecolor(BG)
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color(HAIRLINE)
    ax.spines["bottom"].set_color(HAIRLINE)
    ax.set_xlabel("Discount depth", color=MUTED, fontsize=13)
    ax.set_ylabel("Projected revenue change", color=MUTED, fontsize=13)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(decimals=0))
    ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(decimals=0))
    ax.tick_params(length=0, labelsize=12)
    ax.grid(axis="y", color=HAIRLINE, lw=1, zorder=0)
    ax.set_axisbelow(True)

    fig.text(0.115, 0.115, "Directional model for prioritization — not a causal estimate.",
             color=MUTED, fontsize=12.5, style="italic", family=FONT)

    add_footer(fig, 5)
    save(fig, "05_what_if.png")


if __name__ == "__main__":
    print("Generating LinkedIn carousel ->", OUT.relative_to(ROOT))
    slide_cover()
    slide_categories()
    slide_lift()
    slide_segments()
    slide_whatif()
    print("Done. 5 slides at 1080x1080.")

#!/usr/bin/env python3
"""Build age-standardized cancer mortality charts for a fixed developed-country panel.

Source: WHO Mortality Database via Our World in Data
https://ourworldindata.org/grapher/cancer-death-rate-who-mdb
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

ROOT = Path(__file__).resolve().parent
CSV_URL = (
    "https://ourworldindata.org/grapher/cancer-death-rate-who-mdb.csv"
    "?v=1&csvType=full&useColumnShortNames=false"
)
RAW_CSV = ROOT / "cancer-death-rate-who-mdb.csv"

# High-income countries with long vital-registration series from ~1950
# into the 2020s. Germany excluded (national series starts in 1990).
PANEL = [
    "United States",
    "United Kingdom",
    "Japan",
    "France",
    "Sweden",
    "Netherlands",
    "Australia",
    "Canada",
    "Denmark",
    "Finland",
    "Switzerland",
    "Italy",
    "Spain",
    "Belgium",
    "Austria",
]

BG = "#eef2f5"
INK = "#1c2430"
MUTED = "#5c6b7a"
LINE_GRAY = "#a8b4c0"


def download_raw() -> None:
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": "cancer-mortality-research/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        RAW_CSV.write_bytes(response.read())


def load_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(RAW_CSV)
    df.columns = ["entity", "code", "year", "rate"]
    panel_df = df[df.entity.isin(PANEL)].copy()
    counts = panel_df.groupby("year").size()
    min_n = max(8, len(PANEL) // 2)
    valid_years = counts[counts >= min_n].index
    panel_df = panel_df[panel_df.year.isin(valid_years)]
    avg = (
        panel_df.groupby("year", as_index=False)["rate"]
        .mean()
        .rename(columns={"rate": "panel_mean"})
    )
    avg["n_countries"] = panel_df.groupby("year").size().values
    return panel_df, avg


def decade_snapshots(avg: pd.DataFrame) -> list[dict]:
    latest = avg.iloc[-1]
    snapshots: list[dict] = []
    for year in range(1950, 2030, 10):
        if year < avg.year.min() or year > avg.year.max() + 2:
            continue
        nearest = avg.iloc[(avg.year - year).abs().argsort()[:1]].iloc[0]
        snapshots.append(
            {
                "target_year": year,
                "actual_year": int(nearest.year),
                "rate": round(float(nearest.panel_mean), 1),
            }
        )
    snapshots.append(
        {
            "target_year": "latest",
            "actual_year": int(latest.year),
            "rate": round(float(latest.panel_mean), 1),
        }
    )
    return snapshots


def build_summary(avg: pd.DataFrame, snapshots: list[dict]) -> dict:
    peak_row = avg.loc[avg.panel_mean.idxmax()]
    latest = avg.iloc[-1]
    first = avg.iloc[0]
    plat = avg[(avg.year >= 1960) & (avg.year <= 1995)]
    near_peak = plat[plat.panel_mean >= peak_row.panel_mean * 0.98]
    rate_1990 = float(avg.loc[avg.year == 1990, "panel_mean"].iloc[0])
    return {
        "source": "WHO Mortality Database via Our World in Data (cancer-death-rate-who-mdb)",
        "metric": "Age-standardized deaths from malignant neoplasms per 100,000, both sexes",
        "panel_countries": PANEL,
        "series_start": int(first.year),
        "series_end": int(latest.year),
        "start_rate": round(float(first.panel_mean), 1),
        "peak_year": int(peak_row.year),
        "peak_rate": round(float(peak_row.panel_mean), 1),
        "plateau_within_2pct_of_peak": [int(near_peak.year.min()), int(near_peak.year.max())],
        "latest_rate": round(float(latest.panel_mean), 1),
        "change_peak_to_latest_pct": round((latest.panel_mean / peak_row.panel_mean - 1) * 100, 1),
        "change_start_to_latest_pct": round((latest.panel_mean / first.panel_mean - 1) * 100, 1),
        "change_1990_to_latest_pct": round((float(latest.panel_mean) / rate_1990 - 1) * 100, 1),
        "decade_snapshots": snapshots,
        "verdict_ru": (
            "В панели развитых стран age-standardized смертность от рака "
            "росла/держалась на высоком плато примерно до конца 1980-х, "
            "затем устойчиво снизилась: к 2022 около −37% от пика среднего "
            "и около −36% относительно 1990."
        ),
    }


def style_axes() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": BG,
            "axes.facecolor": BG,
            "axes.edgecolor": INK,
            "axes.labelcolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "text.color": INK,
        }
    )


def chart_timeseries(panel_df: pd.DataFrame, avg: pd.DataFrame, summary: dict) -> Path:
    style_axes()
    fig, ax = plt.subplots(figsize=(11.2, 6.4), dpi=170)

    for _, group in panel_df.groupby("entity"):
        ax.plot(group.year, group.rate, color=LINE_GRAY, linewidth=0.7, alpha=0.4, zorder=1)

    highlights = {
        "United States": ("#0f6b4c", "США"),
        "United Kingdom": ("#1d4f91", "Великобритания"),
        "Japan": ("#c45c26", "Япония"),
    }
    for entity, (color, label) in highlights.items():
        group = panel_df[panel_df.entity == entity].sort_values("year")
        ax.plot(group.year, group.rate, color=color, linewidth=1.7, alpha=0.95, label=label, zorder=3)

    ax.plot(
        avg.year,
        avg.panel_mean,
        color=INK,
        linewidth=2.9,
        label=f"Среднее панели ({len(PANEL)} стран)",
        zorder=4,
    )

    plateau_start, plateau_end = summary["plateau_within_2pct_of_peak"]
    ax.axvspan(plateau_start, plateau_end, color="#d7e0ea", alpha=0.55, zorder=0)
    ax.scatter([summary["peak_year"]], [summary["peak_rate"]], color=INK, s=40, zorder=5)

    ax.annotate(
        f"Плато/пик {plateau_start}–{plateau_end}\n"
        f"макс. {summary['peak_rate']:.0f} ({summary['peak_year']})",
        xy=(summary["peak_year"], summary["peak_rate"]),
        xytext=(1962, summary["peak_rate"] + 22),
        fontsize=9,
        arrowprops=dict(arrowstyle="->", color=INK, lw=0.8),
    )
    ax.annotate(
        f"{summary['series_end']}: {summary['latest_rate']:.0f}\n"
        f"{summary['change_peak_to_latest_pct']:.0f}% к пику",
        xy=(summary["series_end"], summary["latest_rate"]),
        xytext=(2004, summary["latest_rate"] - 32),
        fontsize=9,
        arrowprops=dict(arrowstyle="->", color=INK, lw=0.8),
    )

    ax.set_title(
        "Возрастно-стандартизованная смертность от рака\n"
        "панель развитых стран (WHO Mortality Database), 1951–2022",
        fontsize=13,
        pad=12,
        fontweight="bold",
    )
    ax.set_xlabel("Год")
    ax.set_ylabel(
        "Смертей от злокачественных новообразований\nна 100 000 (оба пола, age-standardized)"
    )
    ax.set_xlim(1949, 2024)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(20))
    ax.xaxis.set_major_locator(mticker.MultipleLocator(10))
    ax.grid(axis="y", color="#c5d0db", linewidth=0.8)
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    ax.text(
        0.0,
        -0.17,
        "Источник: WHO Mortality Database через Our World in Data (reported, age-standardized).\n"
        f"Панель фиксирована: {', '.join(PANEL)}. "
        "Серые линии — страны панели; чёрная — невзвешенное среднее по странам с данными в данном году. "
        "Затенение — годы в пределах 2% от максимума среднего.",
        transform=ax.transAxes,
        fontsize=7.2,
        color=MUTED,
        ha="left",
        va="top",
    )
    fig.tight_layout()
    out = ROOT / "cancer_mortality_developed_panel.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def chart_decades(snapshots: list[dict]) -> Path:
    style_axes()
    fig, ax = plt.subplots(figsize=(10.2, 5.6), dpi=170)
    dec = [item for item in snapshots if item["target_year"] != "latest"]
    years = [item["actual_year"] for item in dec]
    rates = [item["rate"] for item in dec]
    colors = ["#8a5a3b" if year < 1990 else "#0f6b4c" for year in years]

    ax.bar(range(len(years)), rates, color=colors, width=0.72, edgecolor="none")
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels([str(year) for year in years])
    for i, rate in enumerate(rates):
        ax.text(i, rate + 2.2, f"{rate:.0f}", ha="center", va="bottom", fontsize=9)
    for i in range(1, len(rates)):
        pct = (rates[i] / rates[i - 1] - 1) * 100
        ax.text(
            i - 0.5,
            max(rates) * 1.02,
            f"{pct:+.0f}%",
            ha="center",
            va="bottom",
            fontsize=8,
            color=MUTED,
        )

    ax.set_title(
        "Смертность от рака с шагом 10 лет\nсреднее панели развитых стран (age-standardized)",
        fontsize=13,
        pad=14,
        fontweight="bold",
    )
    ax.set_ylabel("Смертей на 100 000")
    ax.set_ylim(0, max(rates) * 1.18)
    ax.grid(axis="y", color="#c5d0db", linewidth=0.8)
    ax.text(
        0.0,
        -0.14,
        "Коричневые столбцы — период до устойчивого снижения; зелёные — снижение после ~1990.\n"
        "Источник: WHO Mortality Database (OWID). Значения — среднее панели за указанный год.",
        transform=ax.transAxes,
        fontsize=7.2,
        color=MUTED,
        ha="left",
        va="top",
    )
    fig.tight_layout()
    out = ROOT / "cancer_mortality_decade_steps.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    if not RAW_CSV.exists():
        download_raw()

    panel_df, avg = load_panel()
    snapshots = decade_snapshots(avg)
    summary = build_summary(avg, snapshots)

    avg.to_csv(ROOT / "developed_panel_mean.csv", index=False)
    panel_df.to_csv(ROOT / "developed_panel_countries.csv", index=False)
    pd.DataFrame(snapshots).to_csv(ROOT / "decade_snapshots.csv", index=False)
    (ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    chart_timeseries(panel_df, avg, summary)
    chart_decades(snapshots)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

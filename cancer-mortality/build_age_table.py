#!/usr/bin/env python3
"""Build age-specific cancer mortality table (5-year ages from 40) for developed panel."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
CSV_URL = (
    "https://ourworldindata.org/grapher/cancer-death-rate-by-age-group.csv"
    "?v=1&csvType=full&useColumnShortNames=false"
)
RAW_CSV = ROOT / "cancer-death-rate-by-age-group.csv"

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

AGE_COLS = [
    "40-44 years",
    "45-49 years",
    "50-54 years",
    "55-59 years",
    "60-64 years",
    "65-69 years",
    "70-74 years",
    "75-79 years",
    "80-84 years",
    "Over 85s",
]
AGE_LABELS = [
    "40–44",
    "45–49",
    "50–54",
    "55–59",
    "60–64",
    "65–69",
    "70–74",
    "75–79",
    "80–84",
    "85+",
]
TARGET_YEARS = [1960, 1970, 1980, 1990, 2000, 2010, 2020]


def download_raw() -> None:
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": "cancer-mortality-research/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        RAW_CSV.write_bytes(response.read())


def build_year_rows(panel: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for year in TARGET_YEARS:
        usable = panel[panel.Year == year].dropna(subset=AGE_COLS)
        means = usable[AGE_COLS].mean()
        row = {"year": year, "n_countries": int(usable.Entity.nunique())}
        for col, label in zip(AGE_COLS, AGE_LABELS):
            row[label] = round(float(means[col]), 1)
        rows.append(row)

    coverage = panel.groupby("Year").size()
    for year in sorted(coverage.index, reverse=True):
        usable = panel[panel.Year == year].dropna(subset=AGE_COLS)
        if usable.Entity.nunique() < 10:
            continue
        year = int(year)
        if year in TARGET_YEARS:
            break
        means = usable[AGE_COLS].mean()
        row = {"year": year, "n_countries": int(usable.Entity.nunique())}
        for col, label in zip(AGE_COLS, AGE_LABELS):
            row[label] = round(float(means[col]), 1)
        rows.append(row)
        break
    return rows


def wide_table(rows: list[dict]) -> pd.DataFrame:
    long_rates = []
    for row in rows:
        for label in AGE_LABELS:
            long_rates.append(
                {
                    "age": label,
                    "year": row["year"],
                    "rate": row[label],
                    "n_countries": row["n_countries"],
                }
            )
    long_df = pd.DataFrame(long_rates)
    wide = long_df.pivot(index="age", columns="year", values="rate").reindex(AGE_LABELS)
    first_year = wide.columns[0]
    last_year = wide.columns[-1]
    base_year = 1990 if 1990 in wide.columns else first_year
    out = wide.copy()
    out[f"Δ {first_year}→{last_year}, %"] = ((wide[last_year] / wide[first_year] - 1) * 100).round(1)
    out[f"Δ {base_year}→{last_year}, %"] = ((wide[last_year] / wide[base_year] - 1) * 100).round(1)
    return out, long_df


def write_markdown(wide_out: pd.DataFrame, summary: dict) -> None:
    years = list(wide_out.columns)
    lines = [
        "# Смертность от рака по возрасту (шаг 5 лет, с 40 лет)",
        "",
        "Среднее панели из 15 развитых стран. Ставки на 100 000 человек **в данной возрастной группе** (оба пола).",
        "",
        "Источник: WHO Mortality Database через Our World in Data (`cancer-death-rate-by-age-group`).",
        "",
        "## Таблица",
        "",
        "| Возраст | " + " | ".join(str(c) for c in years) + " |",
        "|---|" + "|".join(["---:"] * len(years)) + "|",
    ]
    for age in AGE_LABELS:
        vals = []
        for col in years:
            value = wide_out.loc[age, col]
            if pd.isna(value):
                vals.append("—")
            elif isinstance(col, str) and str(col).startswith("Δ"):
                vals.append(f"{value:+.1f}")
            else:
                vals.append(f"{value:.1f}")
        lines.append(f"| {age} | " + " | ".join(vals) + " |")

    n_parts = [
        f"{year} — {summary['n_countries_by_year'][str(year)]}"
        for year in summary["years"]
        if str(year) in summary["n_countries_by_year"]
    ]
    lines += [
        "",
        "Число стран в среднем по годам: " + ", ".join(n_parts) + ".",
        "",
        "## Как читать",
        "",
        "- Строки — возраст с шагом 5 лет, начиная с 40.",
        "- Столбцы — годы с шагом 10 лет.",
        "- Это **не** age-standardized итог: виден риск смерти от рака в каждом возрасте.",
        "- Правые столбцы — изменение ставки в том же возрасте относительно 1960 и 1990.",
        "",
        f"Панель: {', '.join(PANEL)}.",
        "",
    ]
    (ROOT / "AGE_SPECIFIC_TABLE.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if not RAW_CSV.exists():
        download_raw()

    panel = pd.read_csv(RAW_CSV)
    panel = panel[panel.Entity.isin(PANEL)].copy()
    rows = build_year_rows(panel)
    wide_out, long_df = wide_table(rows)

    wide_out.to_csv(ROOT / "age_specific_mortality_table.csv")
    long_df.to_csv(ROOT / "age_specific_mortality_long.csv", index=False)
    pd.DataFrame(rows).to_csv(ROOT / "age_specific_mortality_by_year.csv", index=False)

    summary = {
        "source": "WHO Mortality Database via Our World in Data (cancer-death-rate-by-age-group)",
        "metric": "Deaths from malignant neoplasms per 100,000 people in each age group, both sexes",
        "panel_countries": PANEL,
        "age_groups": AGE_LABELS,
        "years": [int(y) for y in wide_out.columns if not isinstance(y, str)],
        "n_countries_by_year": {str(r["year"]): r["n_countries"] for r in rows},
        "note_ru": (
            "Ставки возрастно-специфичные (не age-standardized): число смертей от рака "
            "в возрастной группе / численность этой группы × 100 000. "
            "Среднее — невзвешенное по странам панели с полными данными за год."
        ),
    }
    (ROOT / "age_specific_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(wide_out, summary)
    print(wide_out.to_string())


if __name__ == "__main__":
    main()

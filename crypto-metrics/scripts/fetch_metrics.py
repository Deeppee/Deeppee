#!/usr/bin/env python3
"""Fetch and rebuild crypto-metrics/data/metrics.json from public APIs."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 crypto-metrics-dashboard/1.0", "Accept": "application/json"}


def get_json(url: str, retries: int = 4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2**i)
    raise RuntimeError(f"Failed {url}: {last}")


def get_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def fetch_btc_prices() -> dict[str, float]:
    start = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    end = int(dt.datetime.now(tz=dt.timezone.utc).timestamp())
    price: dict[str, float] = {}
    cur = start
    while cur < end:
        s = dt.datetime.fromtimestamp(cur, dt.UTC).strftime("%Y-%m-%dT00:00:00Z")
        e_ts = min(cur + 300 * 86400, end)
        e = dt.datetime.fromtimestamp(e_ts, dt.UTC).strftime("%Y-%m-%dT00:00:00Z")
        url = (
            "https://api.exchange.coinbase.com/products/BTC-USD/candles"
            f"?granularity=86400&start={s}&end={e}"
        )
        batch = get_json(url)
        for row in batch:
            day = dt.datetime.fromtimestamp(row[0], dt.UTC).date().isoformat()
            price[day] = float(row[4])
        cur = e_ts
        time.sleep(0.12)
    # Yahoo fill
    yurl = (
        "https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD"
        f"?period1={start}&period2={end}&interval=1d"
    )
    y = get_json(yurl)
    res = y["chart"]["result"][0]
    for ts, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
        if c is None:
            continue
        day = dt.datetime.fromtimestamp(ts, dt.UTC).date().isoformat()
        price.setdefault(day, float(c))
    return price


def fetch_fng() -> dict[str, dict]:
    raw = get_json("https://api.alternative.me/fng/?limit=0&format=json")["data"]
    out = {}
    for x in raw:
        day = dt.datetime.fromtimestamp(int(x["timestamp"]), dt.UTC).date().isoformat()
        if day >= "2023-01-01":
            out[day] = {"value": int(x["value"]), "class": x["value_classification"]}
    return out


def fetch_dominance() -> dict[str, dict]:
    start = 1672531200
    end = int(time.time())
    url = (
        "https://api.coinmarketcap.com/data-api/v3/global-metrics/quotes/historical"
        f"?format=chart&interval=1d&timeStart={start}&timeEnd={end}"
    )
    quotes = get_json(url)["data"]["quotes"]
    out = {}
    for q in quotes:
        usd = q["quote"][0]
        out[q["timestamp"][:10]] = {
            "btcDominance": q["btcDominance"],
            "totalMarketCap": usd.get("totalMarketCap"),
        }
    return out


def fetch_coinmetrics() -> tuple[dict[str, float], dict[str, float]]:
    raw = get_bytes("https://cdn.jsdelivr.net/gh/coinmetrics-io/data@master/csv/btc.csv")
    mvrv, netflow = {}, {}
    for row in csv.DictReader(io.StringIO(raw.decode())):
        if row["time"] < "2023-01-01":
            continue
        if row.get("CapMVRVCur"):
            mvrv[row["time"]] = float(row["CapMVRVCur"])
        if row.get("FlowInExUSD") and row.get("FlowOutExUSD"):
            netflow[row["time"]] = float(row["FlowInExUSD"]) - float(row["FlowOutExUSD"])
    return mvrv, netflow


def fetch_funding() -> dict[str, float]:
    rows = []
    page = 1
    while True:
        url = (
            "https://api.hbdm.com/linear-swap-api/v1/swap_historical_funding_rate"
            f"?contract_code=BTC-USDT&page_index={page}&page_size=50"
        )
        d = get_json(url)
        batch = d["data"]["data"]
        total_page = d["data"]["total_page"]
        rows.extend(batch)
        if page >= total_page:
            break
        page += 1
        time.sleep(0.05)
    cutoff = dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
    by_day: dict[str, list[float]] = defaultdict(list)
    for x in rows:
        t = int(x["funding_time"])
        if t < cutoff:
            continue
        day = dt.datetime.fromtimestamp(t / 1000, dt.UTC).date().isoformat()
        by_day[day].append(float(x["funding_rate"]) * 100)
    return {d: sum(v) / len(v) for d, v in by_day.items()}


def fetch_oi():
    begin = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000)
    all_rows = []
    cur = begin
    while cur < end:
        e = min(cur + 90 * 7 * 86400000, end)
        url = (
            "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history"
            f"?instType=SWAP&instId=BTC-USDT-SWAP&period=1W&begin={cur}&end={e}"
        )
        data = get_json(url).get("data") or []
        all_rows.extend(data)
        cur = e
        time.sleep(0.12)
    by = {r[0]: r for r in all_rows}
    out = []
    for r in sorted(by.values(), key=lambda x: int(x[0])):
        day = dt.datetime.fromtimestamp(int(r[0]) / 1000, dt.UTC).date().isoformat()
        out.append({"date": day, "oiUsd": float(r[3]), "oiContracts": float(r[1])})
    return out


def fetch_etf():
    url = "https://data.tbstat.com/dashboard/markets_structuredproducts_btcspotetfflows_daily_other.json"
    series = get_json(url)["Series"]
    by_ts: dict[int, float] = defaultdict(float)
    for meta in series.values():
        for pt in meta["Data"]:
            by_ts[pt["Timestamp"]] += float(pt["Result"] or 0)
    return [
        {
            "date": dt.datetime.fromtimestamp(ts, dt.UTC).date().isoformat(),
            "netFlowUsd": by_ts[ts],
        }
        for ts in sorted(by_ts)
    ]


def build():
    print("fetching prices…")
    price_by_date = fetch_btc_prices()
    print("fetching fear & greed…")
    fng = fetch_fng()
    print("fetching dominance…")
    dom = fetch_dominance()
    print("fetching coinmetrics…")
    mvrv, netflow = fetch_coinmetrics()
    print("fetching funding…")
    funding = fetch_funding()
    print("fetching OI…")
    oi = fetch_oi()
    print("fetching ETF flows…")
    etf = fetch_etf()

    dates = sorted(price_by_date)
    prices = [price_by_date[d] for d in dates]
    dma200 = []
    for i in range(len(prices)):
        window = prices[max(0, i - 199) : i + 1]
        dma200.append(sum(window) / len(window) if len(window) == 200 else None)
    above200 = [None if m is None else (1 if p >= m else 0) for p, m in zip(prices, dma200)]

    daily = []
    for i, d in enumerate(dates):
        if d < "2023-01-01":
            continue
        daily.append(
            {
                "date": d,
                "btcPrice": round(price_by_date[d], 2),
                "sma200": None if dma200[i] is None else round(dma200[i], 2),
                "aboveSma200": above200[i],
                "fearGreed": fng.get(d, {}).get("value"),
                "fearGreedClass": fng.get(d, {}).get("class"),
                "btcDominance": None if d not in dom else round(dom[d]["btcDominance"], 4),
                "totalMarketCapUsd": None if d not in dom else dom[d]["totalMarketCap"],
                "mvrv": None if d not in mvrv else round(mvrv[d], 4),
                "exchangeNetflowUsd": None if d not in netflow else round(netflow[d], 2),
                "fundingRatePct": None if d not in funding else round(funding[d], 6),
            }
        )

    for i, item in enumerate(daily):
        window = [
            daily[j]["exchangeNetflowUsd"]
            for j in range(max(0, i - 6), i + 1)
            if daily[j]["exchangeNetflowUsd"] is not None
        ]
        item["exchangeNetflowUsd7d"] = None if not window else round(sum(window) / len(window), 2)

    by_year: dict[str, list] = defaultdict(list)
    for item in daily:
        by_year[item["date"][:4]].append(item)

    def avg(vals):
        vals = [v for v in vals if v is not None]
        return None if not vals else round(sum(vals) / len(vals), 4)

    def last(vals):
        vals = [v for v in vals if v is not None]
        return None if not vals else vals[-1]

    etf_by_year: dict[str, float] = defaultdict(float)
    for e in etf:
        etf_by_year[e["date"][:4]] += e["netFlowUsd"]
    oi_by_year: dict[str, list] = defaultdict(list)
    for o in oi:
        oi_by_year[o["date"][:4]].append(o["oiUsd"])

    yearly = []
    for year in sorted(by_year):
        rows = by_year[year]
        prices_y = [r["btcPrice"] for r in rows]
        sma_cov = [r["aboveSma200"] for r in rows if r["aboveSma200"] is not None]
        yearly.append(
            {
                "year": year,
                "btcPriceStart": prices_y[0],
                "btcPriceEnd": prices_y[-1],
                "btcPriceAvg": round(sum(prices_y) / len(prices_y), 2),
                "btcPriceMin": min(prices_y),
                "btcPriceMax": max(prices_y),
                "btcReturnPct": round((prices_y[-1] / prices_y[0] - 1) * 100, 2),
                "pctDaysAboveSma200": None if not sma_cov else round(100 * sum(sma_cov) / len(sma_cov), 1),
                "fearGreedAvg": avg([r["fearGreed"] for r in rows]),
                "btcDominanceAvg": avg([r["btcDominance"] for r in rows]),
                "btcDominanceEnd": last([r["btcDominance"] for r in rows]),
                "totalMarketCapEnd": last([r["totalMarketCapUsd"] for r in rows]),
                "mvrvAvg": avg([r["mvrv"] for r in rows]),
                "mvrvEnd": last([r["mvrv"] for r in rows]),
                "fundingRateAvgPct": avg([r["fundingRatePct"] for r in rows]),
                "exchangeNetflowAvgUsd": avg([r["exchangeNetflowUsd"] for r in rows]),
                "etfNetFlowUsd": None if year < "2024" else etf_by_year.get(year, 0.0),
                "oiUsdAvg": None
                if year not in oi_by_year
                else round(sum(oi_by_year[year]) / len(oi_by_year[year]), 2),
                "days": len(rows),
            }
        )

    meta = {
        "generatedAt": dt.datetime.now(dt.UTC).isoformat(),
        "range": {"start": daily[0]["date"], "end": daily[-1]["date"]},
        "sources": {
            "btcPrice": "Coinbase Exchange candles (BTC-USD), gaps filled from Yahoo Finance",
            "sma200": "Computed 200-day simple moving average of BTC close",
            "fearGreed": "alternative.me Crypto Fear & Greed Index",
            "btcDominance": "CoinMarketCap global-metrics historical API",
            "totalMarketCap": "CoinMarketCap global-metrics historical API",
            "mvrv": "CoinMetrics community CSV (CapMVRVCur)",
            "exchangeNetflow": "CoinMetrics community CSV (FlowInExUSD - FlowOutExUSD)",
            "fundingRate": "HTX BTC-USDT perpetual historical funding rate; daily average of 8h rates (%)",
            "openInterest": "OKX BTC-USDT-SWAP weekly open interest (USD)",
            "etfFlows": "The Block Spot Bitcoin ETF Flows (sum of US spot BTC ETFs)",
        },
        "notes": [
            "Year-to-date values for the current year use the latest available date.",
            "Spot BTC ETFs start in January 2024; 2023 ETF flow is null.",
            "Positive exchange netflow = net BTC onto exchanges (often sell pressure).",
            "Funding > 0 = longs pay shorts; < 0 = shorts pay longs.",
            "MVRV > ~3.5 historically overheated; < ~1 historically undervalued.",
        ],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": meta,
        "yearly": yearly,
        "daily": daily,
        "openInterestWeekly": oi,
        "etfDaily": etf,
    }
    (OUT / "metrics.json").write_text(json.dumps(payload))
    (OUT / "yearly.json").write_text(json.dumps({"meta": meta, "yearly": yearly}, indent=2))
    print("wrote", OUT / "metrics.json", "daily", len(daily))


if __name__ == "__main__":
    build()

# Crypto bull/bear metrics (2023–today)

Interactive dashboard and yearly aggregates for common crypto market-regime indicators.

## Open the charts

Open [`crypto-metrics/index.html`](./crypto-metrics/index.html) in a browser (serve the folder so `data/metrics.json` loads), e.g.:

```bash
cd crypto-metrics && python3 -m http.server 8080
```

Then visit `http://localhost:8080`.

Static overview images are in [`crypto-metrics/charts/`](./crypto-metrics/charts/).

## Metrics

| Metric | What it signals | Source |
| --- | --- | --- |
| BTC price vs 200 DMA | Above = bull regime, below = bear | Coinbase / Yahoo |
| Bitcoin Dominance | Risk-off into BTC vs altseason | CoinMarketCap |
| Fear & Greed | Sentiment extremes | alternative.me |
| Funding rate | Crowded longs (+) / shorts (−) | HTX perpetuals |
| MVRV | Over/undervaluation vs realized cap | CoinMetrics |
| Exchange netflow | Onto exchanges = sell pressure | CoinMetrics |
| Open interest | Leverage / trend fuel | OKX |
| US spot BTC ETF flows | Institutional spot demand (from 2024) | The Block |

## Yearly snapshot (as of 2026-08-10)

See `crypto-metrics/data/yearly.json` for the full table. Headline read:

- **2023–2024**: strong bull (BTC +155% / +111%, F&G elevated, most days above 200 DMA)
- **2025**: cooling / late-cycle (+/− flat yearly return, higher BTC.D, softer F&G)
- **2026 YTD**: clearly defensive (BTC −27%, F&G ~22, **0%** of days above 200 DMA, ETF net outflows)

## Regenerate data

```bash
python3 crypto-metrics/scripts/fetch_metrics.py
```

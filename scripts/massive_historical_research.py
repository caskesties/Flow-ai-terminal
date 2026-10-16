#!/usr/bin/env python3
"""Massive Futures Basic: delayed 1-minute OHLCV exploratory report (not order flow)."""
import csv
import json
import os
import pathlib
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.massive.com/futures/v1/aggs/"
OUT = pathlib.Path("reports/massive")
OUT.mkdir(parents=True, exist_ok=True)

def download(ticker, day, key):
    query = urllib.parse.urlencode({
        "resolution": "1min",
        "window_start.gte": day,
        "window_start.lte": day,
        "limit": 1500,
        "sort": "window_start.asc",
    })
    req = urllib.request.Request(API + urllib.parse.quote(ticker, safe="") + "?" + query,
        headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            obj = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{ticker}: HTTP {exc.code} (check plan / contract)") from None
    if obj.get("status") not in ("OK", None):
        raise RuntimeError(f"{ticker}: unexpected status")
    if obj.get("next_url"):
        raise RuntimeError(f"{ticker}: paginated response; refusing incomplete analysis")
    bars = obj.get("results") or []
    cleaned = []
    for b in bars:
        try:
            ts = int(b["window_start"])
            row = {"timestamp_utc":datetime.fromtimestamp(ts / 1e9, tz=timezone.utc).isoformat(),
                "open":float(b["open"]), "high":float(b["high"]),
                "low":float(b["low"]), "close":float(b["close"]),
                "volume":float(b["volume"])}
            if row["low"] <= min(row["open"],row["close"]) <= max(row["open"],row["close"]) <= row["high"] and row["volume"] >= 0:
                cleaned.append(row)
        except (KeyError,ValueError,TypeError,OverflowError):
            continue
    cleaned.sort(key=lambda x:x["timestamp_utc"])
    return cleaned

def evaluate(rows):
    signals = []
    for i in range(20, len(rows)-5):
        prior = rows[i-20:i]
        current = rows[i]
        mean_vol = statistics.mean(x["volume"] for x in prior)
        if not mean_vol or current["volume"] < 1.5*mean_vol:
            continue
        direction = 1 if current["close"] > max(x["high"] for x in prior) else (-1 if current["close"] < min(x["low"] for x in prior) else 0)
        if not direction:
            continue
        # Close-to-close, not tradable fill: future high/low excursion is unknown order within each candle.
        after = rows[i+5]["close"]
        progress = direction * (after-current["close"])
        signals.append({"time_utc":current["timestamp_utc"],"direction":"up" if direction==1 else "down",
                        "price":current["close"],"volume_ratio":round(current["volume"]/mean_vol,3),
                        "five_bar_close_move":round(progress,5),"continued":progress>0})
    return signals

def main():
    key=os.environ.get("MASSIVE_API_KEY")
    if not key:
        print("Missing MASSIVE_API_KEY",file=sys.stderr);return 1
    day=os.environ.get("RESEARCH_DAY","2026-10-13")
    try:
        datetime.strptime(day,"%Y-%m-%d")
    except ValueError:
        print("RESEARCH_DAY must be YYYY-MM-DD",file=sys.stderr); return 1
    tickers=[v.strip().upper() for v in os.environ.get("RESEARCH_TICKERS","GCZ6,MGCZ6").split(",") if v.strip()]
    if not (1<=len(tickers)<=2) or any(not x.isalnum() or len(x)>12 for x in tickers):
        print("Provide 1-2 contract tickers e.g. GCZ6,MGCZ6",file=sys.stderr);return 1
    report=["# Massive historical futures — initial research","",
            f"Requested UTC window start: {day}; resolution: 1min; source: Massive Futures REST.","",
            "Research only. Delayed bars, not trades/order flow; no delta, institutional identity, or real-time signals.",
            "No trading fees/slippage, bid/ask, or execution model. Breakout rule is exploratory, not validated.",""]
    failures=0
    for ticker in tickers:
        try:
            rows=download(ticker,day,key)
        except Exception as exc:
            failures+=1
            report.extend([f"## {ticker}",f"API/query failed: {exc}",""])
            continue
        filename=OUT / f"{ticker}_{day}_1min.csv"
        with filename.open("w",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=["timestamp_utc","open","high","low","close","volume"])
            writer.writeheader();writer.writerows(rows)
        signals=evaluate(rows)
        with (OUT/f"{ticker}_{day}_signals.json").open("w") as f:
            json.dump(signals,f,indent=2)
        gaps=sum((datetime.fromisoformat(b["timestamp_utc"])-datetime.fromisoformat(a["timestamp_utc"])).total_seconds()>60 for a,b in zip(rows,rows[1:]))
        wins=sum(x["continued"] for x in signals)
        report += [f"## {ticker}",f"- Candles returned: {len(rows)}",f"- Missing/closed minute gaps in received sequence: {gaps}",
                   f"- Exploratory 20-bar breakout + 1.5x volume signals: {len(signals)}",
                   f"- Positive directional close after 5 bars: {wins}/{len(signals)}" if signals else "- No qualifying signals (rate not computed).",
                   "- Sample is neither a backtest nor proof of predictive accuracy.",""]
    (OUT/"REPORT.md").write_text("\n".join(report)+"\n")
    print("\n".join(report))
    return 1 if failures else 0

if __name__=="__main__":
    sys.exit(main())

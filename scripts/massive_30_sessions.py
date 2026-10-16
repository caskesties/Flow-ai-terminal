#!/usr/bin/env python3
"""30-session Massive OHLCV study; chronological day-level holdout, NOT order flow."""
import csv
import os
import pathlib
import statistics
from datetime import date, timedelta
from massive_historical_research import download
from validate_massive import candidates, nonoverlapping, PARAMETERS, HORIZON

OUT = pathlib.Path("reports/massive_30")
OUT.mkdir(parents=True, exist_ok=True)
TARGET = 30
MAX_WEEKDAYS = 55

def metrics(moves):
    if not moves:
        return "0 independent signals; no estimate"
    return (f"{len(moves)} signals; favorable {sum(v > 0 for v in moves)}/{len(moves)} "
            f"({sum(v > 0 for v in moves)/len(moves):.1%}); "
            f"mean signed 5-minute close move {statistics.mean(moves):.4f}; "
            f"median {statistics.median(moves):.4f}")

def main():
    api_key = os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        raise SystemExit("MASSIVE_API_KEY secret missing")
    final_day = date.fromisoformat(os.environ.get("RESEARCH_END_DAY", "2026-10-13"))
    if final_day >= date.today():
        raise SystemExit("End date must be in the past; ensure sufficient historical delay")
    symbols = [s.strip().upper() for s in os.environ.get("RESEARCH_TICKERS","GCZ6,MGCZ6").split(",")]
    if not symbols or len(symbols) > 2 or any(not s.isalnum() for s in symbols):
        raise SystemExit("Provide one or two dated futures symbols")
    dates = []
    d = final_day
    while len(dates) < MAX_WEEKDAYS:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d -= timedelta(days=1)
    lines = ["# Massive 30-session OHLCV research", "",
        "Delayed minute candles only, NOT trade-level delta, absorption, or institutional flow.",
        "Train/holdout split by COMPLETE historical sessions. Signal outcomes use later candle CLOSES, not fills.",
        "No fees, slippage, stop, order book, trade direction, or profit claims.", ""]
    failed = False
    for symbol in symbols:
        sessions = {}
        errors = []
        for day in dates:
            if len(sessions) >= TARGET:
                break
            try:
                bars = download(symbol, day, api_key)
                sessions[day] = [
                    {"t":__import__("datetime").datetime.fromisoformat(b["timestamp_utc"]),
                     **{k:float(b[k]) for k in ("open","high","low","close","volume")}}
                    for b in bars]
            except Exception as exc:
                errors.append(f"{day}: {str(exc)[:130]}")
        ordered = sorted(sessions)
        lines += [f"## {symbol}", "", f"Usable sessions: {len(ordered)}/{TARGET}; skipped/failed: {len(errors)}."]
        if errors:
            lines += ["Skipped dates (may be market holidays, plan restriction, or API errors):"] + [f"- {e}" for e in errors]
        if len(ordered) < TARGET:
            failed = True
            lines += ["Insufficient data: refused to estimate a 30-session holdout.", ""]
            continue
        split = int(len(ordered) * .7)
        train, test = ordered[:split], ordered[split:]
        def score(days, multiple, window):
            moves = []
            for day in days:
                bars = sessions[day]
                sampled = candidates(bars, multiple, window, 0, len(bars))
                moves.extend(nonoverlapping(sampled))
            return moves
        choices = []
        for mult, window in PARAMETERS:
            moves = score(train, mult, window)
            if len(moves) >= 10:
                choices.append((statistics.mean(moves), mult, window, moves))
        lines += [f"Training sessions: {len(train)} ({train[0]} to {train[-1]}); "
                  f"untouched holdout sessions: {len(test)} ({test[0]} to {test[-1]})."]
        if not choices:
            failed = True
            lines += ["No parameter has at least 10 independent training signals; no holdout scored.", ""]
            continue
        _, mult, window, training = max(choices, key=lambda x:x[0])
        holdout = score(test, mult, window)
        lines += [f"Chosen on training ONLY: volume {mult}x; breakout {window} candles.",
                  f"Training: {metrics(training)}",
                  f"Untouched holdout: {metrics(holdout)}",
                  "GC and MGC are correlated; do not treat their signals as independent.",
                  "No claim of statistical significance or executable profitability.", ""]
    path=OUT/"REPORT.md"
    path.write_text("\n".join(lines)+"\n")
    print(path.read_text())
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())

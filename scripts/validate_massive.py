#!/usr/bin/env python3
"""OHLCV-only out-of-sample validation. Not order flow or an executable backtest."""
import csv
import pathlib
import statistics
from datetime import datetime

ROOT = pathlib.Path("reports/massive")
HORIZON = 5
PARAMETERS = [(1.5, 20), (2.0, 20), (1.5, 30)]

def load(path):
    with path.open(newline="") as stream:
        raw = list(csv.DictReader(stream))
    bars = []
    seen = set()
    for row in raw:
        t = datetime.fromisoformat(row["timestamp_utc"].replace("Z", "+00:00"))
        if t in seen:
            raise ValueError("Duplicate timestamp in " + str(path))
        seen.add(t)
        b = {"t": t, **{k: float(row[k]) for k in ("open", "high", "low", "close", "volume")}}
        if not (b["low"] <= min(b["open"], b["close"]) <= max(b["open"], b["close"]) <= b["high"] and b["volume"] >= 0):
            raise ValueError("Invalid OHLCV in " + str(path))
        bars.append(b)
    bars.sort(key=lambda b: b["t"])
    return bars

def contiguous(window):
    return all((b["t"]-a["t"]).total_seconds() == 60 for a, b in zip(window, window[1:]))

def candidates(bars, multiple, lookback, start, end):
    matches = []
    for i in range(max(start, lookback), min(end, len(bars)-HORIZON)):
        if not contiguous(bars[i-lookback:i+HORIZON+1]):
            continue
        prev = bars[i-lookback:i]
        volume_mean = statistics.mean(b["volume"] for b in prev)
        if volume_mean <= 0 or bars[i]["volume"] < multiple*volume_mean:
            continue
        direction = (1 if bars[i]["close"] > max(b["high"] for b in prev)
                     else -1 if bars[i]["close"] < min(b["low"] for b in prev) else 0)
        if direction:
            move = direction*(bars[i+HORIZON]["close"]-bars[i]["close"])
            matches.append((i, move))
    return matches

def nonoverlapping(signals):
    selected = []
    next_allowed = 0
    for i, move in signals:
        if i >= next_allowed:
            selected.append(move)
            next_allowed = i+HORIZON+1
    return selected

def metrics(moves):
    if not moves:
        return "No independent qualifying signals; no estimate available."
    n = len(moves)
    favorable = sum(x > 0 for x in moves)
    return (f"Independent signals: {n}; favorable 5-minute close: {favorable}/{n} "
            f"({favorable/n:.1%}); mean signed price change: {statistics.mean(moves):.4f}; "
            f"median: {statistics.median(moves):.4f}.")

def validate(bars):
    split = int(len(bars)*0.7)
    training = []
    for multiple, window in PARAMETERS:
        # Entire 5-bar outcome stays on training side of split.
        moves = nonoverlapping(candidates(bars, multiple, window, 0, split-HORIZON))
        score = statistics.mean(moves) if moves else float("-inf")
        training.append((score, multiple, window, moves))
    _, multiple, window, in_sample = max(training, key=lambda x: x[0])
    out_sample = nonoverlapping(candidates(bars, multiple, window, split, len(bars)))
    return [
        f"Bars: {len(bars)}. Chronological split: {split} training / {len(bars)-split} holdout.",
        "Parameter choices evaluated on training only: volume 1.5x/20 bars; 2.0x/20; 1.5x/30.",
        "Selection criterion: highest mean signed future close change (subject to selection bias).",
        f"Chosen parameters: {multiple}x volume and {window}-bar breakout.",
        "Requires uninterrupted 1-minute windows through signal horizon; skips gaps and overlapping signals.",
        "Training: " + metrics(in_sample),
        "Untouched holdout: " + metrics(out_sample),
        "Signals evaluated at completed candle close; 5 later candle closes are NOT executable fills.",
        "No bid/ask, trade-level delta, order-book, bank identity, commissions, stop, slippage, or intrabar fill sequence.",
        "Research only: one day and one holdout are insufficient for predictive or profitability claims."
    ]

def main():
    paths = sorted(ROOT.glob("*_1min.csv"))
    if not paths:
        raise SystemExit("No historical CSV found: download Massive bars first.")
    lines = ["# Massive chronological validation — OHLCV only", ""]
    for path in paths:
        lines += ["## " + path.stem, ""] + ["- " + line for line in validate(load(path))] + [""]
    destination = ROOT/"VALIDATION.md"
    destination.write_text("\n".join(lines)+"\n")
    print(destination.read_text())

if __name__ == "__main__":
    main()

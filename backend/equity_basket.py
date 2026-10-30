"""Six-stock Nasdaq context. Quotes only, fixed dated weights, no trade gating."""
from collections import deque
import math

# Nasdaq-100 weights published by State Street, 2026-10-29.
DEFAULT_WEIGHTS = {"NVDA": 8.10, "AAPL": 8.01, "MSFT": 6.19,
                   "MU": 4.58, "AMZN": 4.14, "AMD": 4.02}

class EquityBasket:
    def __init__(self, weights=None, weights_asof="2026-10-29"):
        self.weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
        if set(self.weights) != set(DEFAULT_WEIGHTS) or any(
            not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
            for v in self.weights.values()):
            raise ValueError("Provide positive index weights for all six stocks")
        self.weights_asof = weights_asof
        self.rows = {symbol: deque(maxlen=400) for symbol in self.weights}
        self.connected = False
        self.status = "CONNECTING"

    def on_quote(self, msg, now):
        if msg.get("ev") != "Q" or msg.get("sym") not in self.rows:
            return False
        try:
            ts, bid, ask = int(msg["t"]), float(msg["bp"]), float(msg["ap"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return False
        if not all(math.isfinite(x) for x in (bid, ask)) or bid <= 0 or ask < bid or not -1000 <= now-ts <= 10000:
            return False
        rows = self.rows[msg["sym"]]
        if rows and ts <= rows[-1][0]:
            return False
        # One endpoint per second bounds memory and snapshot cost.
        point = (ts, (bid+ask)/2)
        if rows and ts//1000 == rows[-1][0]//1000:
            rows[-1] = point
        else:
            rows.append(point)
        while rows and ts-rows[0][0] > 330000:
            rows.popleft()
        return True

    def snapshot(self, now):
        windows = {}
        for label, span in (("2m",120000),("5m",300000)):
            changes = {}
            for symbol, rows in self.rows.items():
                if not rows or not -1000 <= now-rows[-1][0] <= 10000:
                    continue
                baseline = min(rows, key=lambda x: abs(x[0]-(now-span)))
                if abs(baseline[0]-(now-span)) > 5000:
                    continue
                segment = [x for x in rows if x[0]>=baseline[0]]
                if any(b[0]-a[0]>10000 for a,b in zip(segment,segment[1:])):
                    continue
                changes[symbol] = (rows[-1][1]/baseline[1]-1)*100
            complete = self.connected and len(changes)==6
            total = sum(self.weights.values())
            weighted = sum(self.weights[s]*v for s,v in changes.items())/total if complete else None
            direction = (1 if weighted>0 else -1 if weighted<0 else 0) if complete else None
            windows[label] = dict(ready=complete, coverage=len(changes), weighted_pct=weighted,
                direction=direction, up=sum(v>0 for v in changes.values()),
                down=sum(v<0 for v in changes.values()), changes=changes)
        a,b = windows["2m"], windows["5m"]
        ready = a["ready"] and b["ready"]
        direction = a["direction"] if ready and a["direction"]==b["direction"] else 0
        return dict(type="equity_basket", timestamp=now, connected=self.connected,
            status=self.status, ready=ready, direction=direction, windows=windows,
            weights=self.weights, weights_asof=self.weights_asof,
            mode="context_only", source="Massive stocks NBBO midpoint")

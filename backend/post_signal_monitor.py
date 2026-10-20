"""Experimental post-signal flow monitor. Signals are NOT evidence of a filled position.
No orders, exit sizes, institutional identities, or guaranteed reversal predictions.
"""
from collections import defaultdict, deque

TICKS = {"MGC": 0.1, "GC": 0.1, "MNQ": 0.25, "NQ": 0.25}

class PostSignalMonitor:
    def __init__(self):
        self.active = {}
        self.prints = defaultdict(lambda: deque(maxlen=5000))
        self.cooldown = {}

    def register(self, signal):
        symbol = signal.get("symbol", "")
        if symbol not in TICKS or signal.get("side") not in ("buy", "sell"):
            return
        self.active[symbol] = dict(signal_id=signal["timestamp"], time=signal["timestamp"],
            direction=signal["side"], entry=float(signal["price"]),
            best=float(signal["price"]), absorption=False, reversal=False)
        self.prints[symbol].clear()

    def on_trade(self, trade):
        symbol = trade.get("symbol")
        if symbol not in TICKS or trade.get("side") not in ("buy", "sell"):
            return []
        state = self.active.get(symbol)
        if not state:
            return []
        ts = int(trade["timestamp"])
        if ts <= state["time"] or ts-state["time"] > 180000:
            if ts-state["time"] > 180000:
                self.active.pop(symbol, None)
            return []
        px = float(trade["price"])
        size = float(trade["size"])
        if size <= 0:
            return []
        q = self.prints[symbol]
        if q and ts < q[-1]["timestamp"]:
            return []
        q.append(dict(timestamp=ts, price=px, size=size, side=trade["side"]))
        while q and ts-q[0]["timestamp"] > 15000:
            q.popleft()
        tick=TICKS[symbol]
        direction = 1 if state["direction"] == "buy" else -1
        state["best"] = max(state["best"], px) if direction == 1 else min(state["best"], px)
        favorable = direction*(state["best"]-state["entry"])/tick
        recent=[x for x in q if 0 <= ts-x["timestamp"] <= 5000]
        prior=[x for x in q if 5000 < ts-x["timestamp"] <= 15000]
        if len(recent) < 8 or len(prior) < 8 or recent[-1]["timestamp"]-recent[0]["timestamp"] < 2500:
            return []
        total=sum(x["size"] for x in recent)
        if total<=0:
            return []
        with_flow=sum(x["size"] for x in recent if x["side"] == state["direction"])
        against=total-with_flow
        baseline=sum(x["size"] for x in prior)/max((prior[-1]["timestamp"]-prior[0]["timestamp"])/1000,1)
        intensity=(total/5)/max(baseline,0.001)
        spread=(max(x["price"] for x in recent)-min(x["price"] for x in recent))/tick
        latest_move=direction*(px-recent[0]["price"])/tick
        from_peak=direction*(state["best"]-px)/tick
        result=[]
        def event(stage,detail):
            return dict(type="post_signal_alert",model="POST_SIGNAL",stage=stage,
                symbol=symbol,timestamp=ts,side=state["direction"],price=px,
                signal_timestamp=state["signal_id"],flow_share=round(with_flow/total,3),
                opposing_share=round(against/total,3),volume_ratio=round(intensity,2),
                favorable_ticks=round(favorable,1),from_peak_ticks=round(from_peak,1),
                source="inferred_aggression",reason=detail,
                trade_execution_confirmed=False,exit_size_recommended=False)
        # High same-direction aggression without meaningful price advance.
        if (not state["absorption"] and not state["reversal"] and favorable>=3
            and with_flow/total>=.60 and intensity>=1.2 and spread<=3 and latest_move<=1):
            state["absorption"]=True
            result.append(event("POSSIBLE_ABSORPTION",
                "Agressao direcional continua com pouco deslocamento; avaliar risco, nao presume reversao."))
        # Opposing aggression, actual adverse movement and retreat from best observed price.
        if (not state["reversal"] and favorable>=3 and against/total>=.65
            and intensity>=1.3 and latest_move<=-2 and from_peak>=3):
            state["reversal"]=True
            result.append(event("POSSIBLE_REVERSAL",
                "Agressao contraria e recuo confirmados; nao significa zeragem institucional ou ordem automatica."))
        return result

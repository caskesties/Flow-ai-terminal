"""Independent, research-only absorption proxy after a directional price excursion.

Uses classified prints, not order-book or institutional identities.
Emits diagnostic observations only, never entry or exit alerts.
"""
from collections import defaultdict,deque

class AbsorptionResearch:
    def __init__(self):
        self.rows=defaultdict(lambda:deque(maxlen=5000))
        self.last=defaultdict(int)

    def on_trade(self, trade):
        symbol=str(trade.get("symbol",""))
        if not symbol.startswith(("MNQ","NQ","MGC","GC")):return None
        if trade.get("side") not in ("buy","sell"):return None
        ts=int(trade["timestamp"]);px=float(trade["price"]);size=float(trade["size"])
        if size<=0:return None
        rows=self.rows[symbol]
        if rows and ts<rows[-1]["timestamp"]:return None
        rows.append(dict(timestamp=ts,price=px,size=size,side=trade["side"]))
        while rows and ts-rows[0]["timestamp"]>45000:rows.popleft()
        if ts-self.last[symbol]<20000:return None
        past=[x for x in rows if 12000<ts-x["timestamp"]<=40000]
        recent=[x for x in rows if 0<=ts-x["timestamp"]<=8000]
        if len(past)<12 or len(recent)<10:return None
        tick=.25 if symbol.startswith(("MNQ","NQ")) else .1
        excursion=px-past[0]["price"]
        prior_peak=max(x["price"] for x in rows)
        prior_low=min(x["price"] for x in rows)
        # The market must have previously travelled at least 8 ticks.
        if max(prior_peak-past[0]["price"],past[0]["price"]-prior_low)<8*tick:return None
        buys=sum(x["size"] for x in recent if x["side"]=="buy")
        sells=sum(x["size"] for x in recent if x["side"]=="sell")
        total=buys+sells
        if total<40:return None
        share=max(buys,sells)/total
        if share<.60:return None
        start=recent[0]["price"]
        local_range=max(x["price"] for x in recent)-min(x["price"] for x in recent)
        local_move=px-start
        # Buyer absorption = aggressive buying without lift near recent highs.
        # Seller absorption = aggressive selling without decline near recent lows.
        side="buy" if buys>sells else "sell"
        near_extreme=px>=prior_peak-3*tick if side=="buy" else px<=prior_low+3*tick
        stalled=(local_move<=tick if side=="buy" else local_move>=-tick) and local_range<=5*tick
        if not near_extreme or not stalled:return None
        self.last[symbol]=ts
        return dict(type="absorption_research",symbol=symbol,timestamp=ts,side=side,price=px,
                    traded_volume=round(total,2),aggressor_share=round(share,3),
                    local_range_ticks=round(local_range/tick,1),local_move_ticks=round(local_move/tick,1),
                    status="POSSIBLE_ABSORPTION_UNCONFIRMED",source="classified_trades_only",
                    research_only=True)

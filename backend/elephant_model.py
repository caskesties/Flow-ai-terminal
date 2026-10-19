"""Experimental 2-minute wickless Elephant Bar with flow and level confirmation.
Uses classified trade prints, not exchange OHLC. Research signals only.
"""
from collections import defaultdict, deque
import time

class ElephantFlowModel:
    def __init__(self):
        self.bars=defaultdict(lambda:deque(maxlen=64))
        self.recent=defaultdict(lambda:deque(maxlen=20000))
        self.candidates={}
        self.last={}
    def on_trade(self, trade):
        ts=int(trade["timestamp"]); sym=trade["symbol"]
        px=float(trade["price"]); size=float(trade["size"])
        if abs(time.time()*1000-ts)>3000 or size<=0:return None
        start=(ts//120000)*120000
        bars=self.bars[sym]
        if bars and start<bars[-1]["start"]:return None
        if not bars or bars[-1]["start"]!=start:
            if bars:self._close(sym,bars[-1],list(bars)[:-1])
            bars.append({"start":start,"o":px,"h":px,"l":px,"c":px,
                         "buy":0.0,"sell":0.0,"count":0,"last":ts})
        b=bars[-1];b["h"]=max(b["h"],px);b["l"]=min(b["l"],px)
        b["c"]=px;b[trade["side"]]+=size;b["count"]+=1;b["last"]=ts
        recent=self.recent[sym]
        recent.append(trade)
        while recent and ts-recent[0]["timestamp"]>190000:recent.popleft()
        c=self.candidates.get(sym)
        if not c:return None
        if ts-c["closed_at"]>20000:
            self.candidates.pop(sym,None);return None
        # Any transaction back inside the former broken level cancels this candidate.
        if (c["side"]=="buy" and px<=c["level"]) or (c["side"]=="sell" and px>=c["level"]):
            self.candidates.pop(sym,None);return None
        if ts-c["closed_at"]<5000:return None
        follow=[x for x in recent if c["closed_at"]<=x["timestamp"]<=ts]
        if len(follow)<5:return None
        same=sum(x["size"] for x in follow if x["side"]==c["side"])
        volume=sum(x["size"] for x in follow)
        if not volume or same/volume<.65:return None
        if (c["side"]=="buy" and px<=c["price"]) or (c["side"]=="sell" and px>=c["price"]):
            return None
        key=(sym,c["side"])
        if ts-self.last.get(key,0)<120000:return None
        self.last[key]=ts;self.candidates.pop(sym,None)
        return {"type":"server_signal","model":"C","stage":"ELEPHANT_2M_CONFIRMED",
                "symbol":sym,"timestamp":ts,"side":c["side"],"price":px,
                "ratio":c["ratio"],"directional_share":round(same/volume,3),
                "treasury":"not_required","source":"server_live",
                "elephant":{"open":c["open"],"high":c["high"],"low":c["low"],"close":c["price"],
                            "timeframe_seconds":120,"wickless":True,
                            "relative_range":c["relative_range"],
                            "confirmation":"5s above/below breakout; continuation"},
                "level_type":c["level_type"],"level":c["level"],
                "reason":"Barra 2m sem pavios nos prints classificados; agressao alinhada, nivel rompido e sustentado por 5s. Diagnostico experimental."}
    def _close(self,sym,bar,previous):
        # Require a completed interval with prices throughout, and enough historical bars.
        if bar["last"]<bar["start"]+115000 or bar["count"]<15 or len(previous)<20:return
        prior=previous[-20:]
        if any(prior[i]["start"]-prior[i-1]["start"]!=120000 for i in range(1,len(prior))):return
        ranges=[x["h"]-x["l"] for x in prior]
        avg=sum(ranges)/len(ranges)
        if avg<=0:return
        span=bar["h"]-bar["l"]
        if span<avg*1.8 or span<=0:return
        buy=bar["buy"];sell=bar["sell"];total=buy+sell
        if total<=0:return
        side="buy" if bar["c"]>bar["o"] else "sell" if bar["c"]<bar["o"] else None
        if not side:return
        # Exact zero wicks in classified prints; one tick of shadow disqualifies.
        if side=="buy" and (bar["o"]!=bar["l"] or bar["c"]!=bar["h"]):return
        if side=="sell" and (bar["o"]!=bar["h"] or bar["c"]!=bar["l"]):return
        strength=(buy if side=="buy" else sell)/total
        if strength<.65:return
        prev_volume=sum(x[side] for x in prior)/len(prior)
        ratio=(buy if side=="buy" else sell)/max(prev_volume,1)
        if ratio<1.8:return
        # Previous 20 complete 2m bars: confirmed support/resistance and Fibonacci.
        lo=min(x["l"] for x in prior);hi=max(x["h"] for x in prior)
        fibs=[lo+(hi-lo)*r for r in (.382,.5,.618)]
        resistance=max(x["h"] for x in prior[-10:])
        support=min(x["l"] for x in prior[-10:])
        level=resistance if side=="buy" else support
        crossed=bar["o"]<=level<bar["c"] if side=="buy" else bar["o"]>=level>bar["c"]
        # Fibonacci confluence must coincide with the crossed support/resistance;
        # don't treat merely being near a fib while away from breakout as enough.
        fib_near=min(fibs,key=lambda f:abs(f-level))
        tolerance=min(avg*.25,(hi-lo)*.025)
        if not crossed or abs(fib_near-level)>tolerance:return
        self.candidates[sym]={"closed_at":bar["start"]+120000,"side":side,
           "price":bar["c"],"open":bar["o"],"high":bar["h"],"low":bar["l"],
           "relative_range":round(span/avg,2),"ratio":round(ratio,2),
           "level":level,"level_type":"support_resistance_with_fibonacci"}

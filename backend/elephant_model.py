"""Experimental 2-minute strong-close Elephant Bar with flow and level confirmation.
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
        self.tick_size={"GC":0.1,"MGC":0.1,"NQ":0.25,"MNQ":0.25}
        self.diagnostics=defaultdict(lambda:{"closed":0,"body_size":0,"wickless":0,"delta":0,"waves":0,"technical":0,"candidates":0})
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
                         "buy":0.0,"sell":0.0,"count":0,"last":ts,"waves":{}})
        b=bars[-1];b["h"]=max(b["h"],px);b["l"]=min(b["l"],px)
        b["c"]=px;b["count"]+=1;b["last"]=ts
        if trade.get("side") in ("buy","sell"):
            b[trade["side"]]+=size
            bucket=(ts-start)//5000
            wave=b["waves"].setdefault(bucket,{"buy":0.0,"sell":0.0})
            wave[trade["side"]]+=size
        recent=self.recent[sym]
        if trade.get("side") in ("buy","sell"):recent.append(trade)
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
                            "timeframe_seconds":120,"closing_wick_ticks":c["closing_wick_ticks"],"body_fraction":c["body_fraction"],
                            "relative_range":c["relative_range"],"body_larger_than_previous":3,
                            "confirmation":"5s above/below breakout; continuation"},
                "level_type":c["level_type"],"level":c["level"],"large_flow_waves":c["large_flow_waves"],"institution_identity_verified":False,
                "reason":"Barra 2m maior que os 3 corpos anteriores, com fechamento ate 1 tick da extremidade e corpo solido; agressao alinhada, nivel rompido e sustentado por 5s. Diagnostico experimental."}
    def _close(self,sym,bar,previous):
        # Require a completed interval with prices throughout, and enough historical bars.
        self.diagnostics[sym]["closed"]+=1
        if bar["last"]<bar["start"]+115000 or bar["count"]<15 or len(previous)<20:return
        prior=previous[-20:]
        if any(prior[i]["start"]-prior[i-1]["start"]!=120000 for i in range(1,len(prior))):return
        ranges=[x["h"]-x["l"] for x in prior]
        avg=sum(ranges)/len(ranges)
        if avg<=0:return
        span=bar["h"]-bar["l"]
        # Strictly larger body than each of the last three completed 2-minute bars.
        previous_bodies=[abs(x["c"]-x["o"]) for x in prior[-3:]]
        body=abs(bar["c"]-bar["o"])
        if span<=0 or body<=max(previous_bodies):return
        self.diagnostics[sym]["body_size"]+=1
        buy=bar["buy"];sell=bar["sell"];total=buy+sell
        if total<=0:return
        side="buy" if bar["c"]>bar["o"] else "sell" if bar["c"]<bar["o"] else None
        if not side:return
        # Only the closing-side wick is decisive: ideal zero, at most one tick.
        # Price OHLC is built from every print, including those not classified.
        tick=next((v for prefix,v in self.tick_size.items() if sym.startswith(prefix)),None)
        if tick is None:return
        closing_wick=bar["h"]-bar["c"] if side=="buy" else bar["c"]-bar["l"]
        if closing_wick < -1e-7 or closing_wick>tick+1e-7:return
        # At least 80% of the whole candle must be real body; large opposing
        # rejection wicks should not qualify as a solid Elephant Bar.
        if body/span<.80:return
        self.diagnostics[sym]["wickless"]+=1
        strength=(buy if side=="buy" else sell)/total
        if strength<.65:return
        prev_volume=sum(x[side] for x in prior)/len(prior)
        ratio=(buy if side=="buy" else sell)/max(prev_volume,1)
        if ratio<1.8:return
        self.diagnostics[sym]["delta"]+=1
        # Separate waves are NOT proof of distinct market participants.
        baseline=sum(x[side] for x in prior)/len(prior)/24
        qualifying=[bucket for bucket,w in bar["waves"].items()
                    if w[side]>=max(1,baseline*1.8)
                    and w[side]/max(w["buy"]+w["sell"],1)>=.65]
        qualifying.sort()
        if not any(b-a>=2 for i,a in enumerate(qualifying) for b in qualifying[i+1:]):return
        self.diagnostics[sym]["waves"]+=1
        # Previous 20 complete 2m bars: confirmed support/resistance and Fibonacci.
        lo=min(x["l"] for x in prior);hi=max(x["h"] for x in prior)
        fibs=[lo+(hi-lo)*r for r in (.382,.5,.618)]
        resistance=max(x["h"] for x in prior[-10:])
        support=min(x["l"] for x in prior[-10:])
        level=resistance if side=="buy" else support
        crossed=bar["o"]<=level<bar["c"] if side=="buy" else bar["o"]>=level>bar["c"]
        # Accept either a validated support/resistance breakout OR a Fibonacci
        # crossing, but never just proximity to a level without crossing it.
        fib_cross=[f for f in fibs if
                   (bar["o"]<=f<bar["c"] if side=="buy" else bar["o"]>=f>bar["c"])]
        if not crossed and not fib_cross:return
        if crossed:
            level_type="support_resistance_breakout"
        else:
            level=min(fib_cross,key=lambda x:abs(bar["c"]-x))
            level_type="fibonacci_cross"
        self.diagnostics[sym]["technical"]+=1
        # Reject an opposing structural obstacle immediately beyond the close.
        obstacle=max((x["h"] for x in prior if x["h"]>bar["c"]),default=None) if side=="buy" else min((x["l"] for x in prior if x["l"]<bar["c"]),default=None)
        if obstacle is not None and abs(obstacle-bar["c"])<=avg*.25:return
        self.diagnostics[sym]["candidates"]+=1
        self.candidates[sym]={"closed_at":bar["start"]+120000,"side":side,
           "large_flow_waves":len(qualifying),
           "price":bar["c"],"open":bar["o"],"high":bar["h"],"low":bar["l"],
           "relative_range":round(span/avg,2),"ratio":round(ratio,2),
           "closing_wick_ticks":round(closing_wick/tick,3),"body_fraction":round(body/span,3),
           "level":level,"level_type":level_type}

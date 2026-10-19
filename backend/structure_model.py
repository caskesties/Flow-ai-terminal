"""Experimental structure/flow diagnostics; NOT trade execution or validated advice."""
from collections import defaultdict, deque
import time

class StructureFlowModel:
    def __init__(self):
        self.minutes=defaultdict(lambda:deque(maxlen=90))
        self.recent=defaultdict(lambda:deque(maxlen=3000))
        self.last={}
    def on_trade(self,t):
        sym=t["symbol"]; ts=int(t["timestamp"]); px=float(t["price"]); size=float(t["size"])
        if abs(time.time()*1000-ts)>3000 or size<=0:return None
        minute=ts//60000
        bars=self.minutes[sym]
        if bars and minute<bars[-1]["minute"]:return None
        if not bars or bars[-1]["minute"]!=minute:
            bars.append(dict(minute=minute,o=px,h=px,l=px,c=px,v=0,buy=0,sell=0))
        bar=bars[-1];bar["h"]=max(bar["h"],px);bar["l"]=min(bar["l"],px);bar["c"]=px;bar["v"]+=size
        bar[t["side"]]+=size
        recent=self.recent[sym];recent.append(t)
        while recent and ts-recent[0]["timestamp"]>15000:recent.popleft()
        if len(bars)<31:return None # at least 30 fully completed minute bars for Fibonacci
        completed=list(bars)[:-1]
        if any(completed[i]["minute"]!=completed[i-1]["minute"]+1 for i in range(len(completed)-29,len(completed))):return None
        # Completed 5m bars only, not partial/future data.
        def aggregate(start,end):
            xs=[b for b in completed if start<=b["minute"]<end]
            if len(xs)!=end-start:return None
            return dict(h=max(b["h"] for b in xs),l=min(b["l"] for b in xs),v=sum(b["v"] for b in xs),o=xs[0]["o"],c=xs[-1]["c"])
        boundary=(minute//5)*5
        prev5=aggregate(boundary-5,boundary)
        prevprev5=aggregate(boundary-10,boundary-5)
        if not prev5 or not prevprev5:return None
        boundary15=(minute//15)*15
        prev15=aggregate(boundary15-15,boundary15)
        if not prev15:return None
        # Absorption proxy: high traded volume with a relatively narrow price range.
        prev_range=max(prev5["h"]-prev5["l"],0)
        older_range=max(prevprev5["h"]-prevprev5["l"],0)
        absorption=prev5["v"]>=prevprev5["v"]*1.3 and prev_range<=older_range*.8 and older_range>0
        if not absorption:return None
        last5=[x for x in recent if ts-x["timestamp"]<=5000]
        before5=[x for x in recent if 5000<ts-x["timestamp"]<=10000]
        if len(last5)<5 or len(before5)<5:return None
        buy=sum(x["size"] for x in last5 if x["side"]=="buy")
        sell=sum(x["size"] for x in last5 if x["side"]=="sell")
        side="buy" if buy>sell else "sell" if sell>buy else None
        if not side:return None
        total=buy+sell
        old=sum(x["size"] for x in before5 if x["side"]==side)
        strength=max(buy,sell)/total if total else 0
        ratio=max(buy,sell)/max(old,1)
        if strength<.65 or ratio<1.8:return None
        move=px-last5[0]["price"]
        if not ((side=="buy" and move>0 and px>prev5["h"] and px>prev15["o"])
                or (side=="sell" and move<0 and px<prev5["l"] and px<prev15["o"])):return None
        # Fibonacci context only: 30 completed bars, measured extrema, no claimed predictive edge.
        last30=completed[-30:]
        lo=min(b["l"] for b in last30);hi=max(b["h"] for b in last30)
        levels=[lo+(hi-lo)*r for r in (.382,.5,.618)]
        near=min(levels,key=lambda x:abs(px-x)) if levels else px
        key=(sym,side)
        if ts-self.last.get(key,0)<60000:return None
        self.last[key]=ts
        return dict(type="server_signal",model="B",stage="ESTRUTURA_EXPERIMENTAL",symbol=sym,
                    timestamp=ts,side=side,price=px,ratio=round(ratio,2),
                    directional_share=round(strength,3),treasury="not_required",
                    source="server_live",absorption="proxy_volume_range_5m",
                    structure="completed_5m_breakout_with_15m_context",
                    fib_nearest=round(near,4),fib_distance=round(abs(px-near),4),
                    reason="Proxy de absorcao 5m, agressao e rompimento 5m; 15m e Fibonacci como contexto; sem book real, sem ordem.")

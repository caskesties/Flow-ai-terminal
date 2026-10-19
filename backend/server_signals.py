"""Conservative informational server-side flow diagnostics. No orders or performance claims."""
from collections import defaultdict,deque
import time
class ServerFlowSignals:
    def __init__(self):
        self.trades=defaultdict(lambda:deque(maxlen=20000))
        self.treasury=deque(maxlen=5000)
        self.last_alert={}
        self.alerts=defaultdict(lambda:deque(maxlen=100))
    def on_treasury(self,timestamp,price,source):
        if not isinstance(timestamp,(int,float)) or not isinstance(price,(int,float)):return
        if timestamp<=0 or price<=0 or abs(time.time()*1000-timestamp)>10000:return
        if self.treasury and timestamp<self.treasury[-1][0]:return
        self.treasury.append((timestamp,price,source))
    def on_trade(self,item):
        sym=item.get("symbol","")
        if not sym.startswith(("MNQ","NQ","MGC","GC")):return None
        ts=item["timestamp"]
        if abs(time.time()*1000-ts)>3000:return None
        rows=self.trades[sym]
        if rows and ts<rows[-1]["timestamp"]:return None
        rows.append(item)
        while rows and ts-rows[0]["timestamp"]>190000:rows.popleft()
        if len(rows)<25:return None
        recent=[x for x in rows if ts-x["timestamp"]<=5000]
        prior=[x for x in rows if 5000<ts-x["timestamp"]<=185000]
        if len(recent)<5 or len(prior)<20:return None
        span=prior[-1]["timestamp"]-prior[0]["timestamp"]
        if span<120000:return None
        buys=sum(x["size"] for x in recent if x["side"]=="buy")
        sells=sum(x["size"] for x in recent if x["side"]=="sell")
        direction="buy" if buys>sells else "sell" if sells>buys else None
        if direction is None:return None
        directional=max(buys,sells);total=buys+sells
        reference=sum(x["size"] for x in prior if x["side"]==direction)
        if reference<=0 or total<=0:return None
        ratio=(directional/5)/(reference/(span/1000))
        if directional/total<.65 or ratio<1.8:return None
        move=item["price"]-recent[0]["price"]
        if not ((direction=="buy" and move>0) or (direction=="sell" and move<0)):return None
        treasury_status="not_applicable"
        if sym.startswith(("NQ","MNQ")):
            if len(self.treasury)<2 or abs(ts-self.treasury[-1][0])>10000:return None
            newest=self.treasury[-1]
            older=next((x for x in self.treasury if newest[0]-5000<=x[0]<=newest[0]-1500 and x[2]==newest[2]),None)
            if older is None or newest[2]!="ZN":return None
            change=newest[1]-older[1]
            if abs(change)<.015:return None
            if (direction=="buy" and change<=0) or (direction=="sell" and change>=0):return None
            treasury_status="ZN_price_proxy"
        key=(sym,direction)
        if ts-self.last_alert.get(key,0)<30000:return None
        self.last_alert[key]=ts
        event=dict(type="server_signal",stage="PRESSAO_EXPERIMENTAL",symbol=sym,timestamp=ts,side=direction,price=item["price"],ratio=round(ratio,2),directional_share=round(directional/total,3),treasury=treasury_status,source="server_live",reason="Agressao e deslocamento alinhados; sinal experimental, sem ordem automatica")
        self.alerts[sym].append(event)
        return event
    def recent_alerts(self,symbol,seconds=300):
        cutoff=time.time()*1000-seconds*1000
        return [dict(x,historical=True) for x in self.alerts[symbol] if x["timestamp"]>=cutoff]

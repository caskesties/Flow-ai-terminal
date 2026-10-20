"""Conservative informational server-side flow diagnostics. No orders or performance claims."""
from collections import defaultdict,deque
import time
class ServerFlowSignals:
    def __init__(self):
        self.trades=defaultdict(lambda:deque(maxlen=20000))
        self.treasury=deque(maxlen=5000)
        self.last_alert={}
        self.alerts=defaultdict(lambda:deque(maxlen=100))
        self.pending=defaultdict(list)
        self.updates=[]
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
        self._evaluate(sym,item)
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
        if directional/total<.60 or ratio<1.8:return None
        move=item["price"]-recent[0]["price"]
        if not ((direction=="buy" and move>0) or (direction=="sell" and move<0)):return None
        treasury_status="not_applicable"
        if sym.startswith(("NQ","MNQ")):
            if len(self.treasury)<2 or abs(ts-self.treasury[-1][0])>10000:return None
            newest=self.treasury[-1]
            if newest[2]!="ZN":return None
            # Require coherent movement in 5s/10s; 2s is diagnostic only.
            decisions=[]
            for window_ms in (5000,10000):
                candidates=[x for x in self.treasury if x[2]=="ZN" and x[0]<newest[0] and window_ms*.75<=newest[0]-x[0]<=window_ms*1.25]
                older=min(candidates,key=lambda x:abs(newest[0]-x[0]-window_ms)) if candidates else None
                if older is None:continue
                change=newest[1]-older[1]
                if abs(change)>=.015625:decisions.append(1 if change>0 else -1)
            if not decisions or len(set(decisions))>1:return None
            if (direction=="buy" and decisions[0]<=0) or (direction=="sell" and decisions[0]>=0):return None
            treasury_status="ZN_price_proxy"
        key=(sym,direction)
        if ts-self.last_alert.get(key,0)<30000:return None
        self.last_alert[key]=ts
        event=dict(type="server_signal",stage="PRESSAO_EXPERIMENTAL",symbol=sym,timestamp=ts,side=direction,price=item["price"],ratio=round(ratio,2),directional_share=round(directional/total,3),treasury=treasury_status,source="server_live",reason="Agressao e deslocamento alinhados; sinal experimental, sem ordem automatica")
        self.alerts[sym].append(event)
        self.pending[sym].append({"event":event,"high":item["price"],"low":item["price"],"last_ts":ts,"completed":set()})
        return event
    def recent_alerts(self,symbol,seconds=300):
        cutoff=time.time()*1000-seconds*1000
        return [dict(x,historical=True) for x in self.alerts[symbol] if x["timestamp"]>=cutoff]

    def _evaluate(self,symbol,trade):
        """Observe first classified print at/after each horizon, and extrema along the way."""
        ts=trade["timestamp"]
        for record in list(self.pending[symbol]):
            event=record["event"]
            if ts<=event["timestamp"]:continue
            # Do not silently treat long feed gaps as continuous observations.
            gap=ts-record["last_ts"]
            record["last_ts"]=ts
            if gap>3000:record["gap_detected"]=True
            record["high"]=max(record["high"],trade["price"])
            record["low"]=min(record["low"],trade["price"])
            for seconds in (5,15,30,60):
                if seconds in record["completed"] or ts-event["timestamp"]<seconds*1000:continue
                delay=ts-event["timestamp"]-seconds*1000
                delayed=delay>2000
                sign=1 if event["side"]=="buy" else -1
                entry=event["price"]
                favorable=(record["high"]-entry) if sign==1 else (entry-record["low"])
                adverse=(entry-record["low"]) if sign==1 else (record["high"]-entry)
                signed=(trade["price"]-entry)*sign
                update={"type":"server_outcome","symbol":symbol,"signal_timestamp":event["timestamp"],
                    "horizon_seconds":seconds,"observed_timestamp":ts,"observed_price":trade["price"],
                    "signed_move":round(signed,6),"favorable_excursion":round(max(0,favorable),6),
                    "adverse_excursion":round(max(0,adverse),6),
                    "reversal_observed":favorable>0 and signed<0,
                    "data_gap":bool(record.get("gap_detected",False)),
                    "observation_delay_ms":delay,
                    "status":"GAP_IN_DATA" if record.get("gap_detected",False) else "DELAYED_OBSERVATION" if delayed else "OBSERVED",
                    "units":"price_points","method":"classified_trades_only"}
                event.setdefault("outcomes",{})[str(seconds)]=update
                record["completed"].add(seconds)
                self.updates.append(update)
            if len(record["completed"])==4:self.pending[symbol].remove(record)
    def drain_updates(self):
        updates=self.updates
        self.updates=[]
        return updates

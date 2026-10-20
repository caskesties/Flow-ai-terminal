"""Research-only two-wave aggressor diagnostic; never emits trade signals."""
from collections import defaultdict, deque

class WaveResearch:
    def __init__(self):
        self.trades=defaultdict(lambda:deque(maxlen=14000))
        self.last_emit={}
        self.pending=defaultdict(list)
        self.updates=[]
    def on_trade(self,item,treasury_fresh=False):
        sym=item.get("symbol","")
        if not sym.startswith(("NQ","MNQ","GC","MGC")):return []
        ts=item["timestamp"]
        rows=self.trades[sym]
        rows.append(item)
        while rows and ts-rows[0]["timestamp"]>90000:rows.popleft()
        events=self._follow(sym,item)
        if len(rows)<12:return events
        # Nonoverlapping consecutive 3s windows: two independent pressure waves,
        # NOT two identified institutions.
        windows=[[x for x in rows if ts-end<=x["timestamp"]<ts-start] for start,end in ((3000,6000),(0,3000))]
        result=[]
        for window in windows:
            buy=sum(x["size"] for x in window if x["side"]=="buy")
            sell=sum(x["size"] for x in window if x["side"]=="sell")
            total=buy+sell
            result.append((buy,sell,total,len(window)))
        direction=1 if all(b>0 and b/(b+s)>=.58 for b,s,_,_ in result if b+s) and all(v[2]>=8 and v[3]>=3 for v in result) else -1 if all(s>0 and s/(b+s)>=.58 for b,s,_,_ in result if b+s) and all(v[2]>=8 and v[3]>=3 for v in result) else 0
        if not direction:return events
        previous=[x for x in rows if 6000<ts-x["timestamp"]<=20000]
        high=max((x["price"] for x in previous),default=None)
        low=min((x["price"] for x in previous),default=None)
        breakout=bool(previous and (item["price"]>high if direction>0 else item["price"]<low))
        key=(sym,direction)
        if ts-self.last_emit.get(key,0)<15000:return events
        self.last_emit[key]=ts
        reasons=[]
        if not breakout:reasons.append("NO_SHORT_BREAKOUT")
        if sym.startswith(("NQ","MNQ")) and not treasury_fresh:reasons.append("TREASURY_NOT_FRESH")
        event={"type":"wave_research","symbol":sym,"timestamp":ts,"side":"buy" if direction>0 else "sell",
          "price":item["price"],"waves":[{"buy":b,"sell":s,"trades":n,"share":round((b if direction>0 else s)/v,3)} for b,s,v,n in result],
          "short_breakout":breakout,"treasury_fresh":bool(treasury_fresh),"status":"CANDIDATE_NOT_VALIDATED" if not reasons else "REJECTED",
          "blockers":reasons,"research_only":True}
        self.pending[sym].append({"event":event,"last_ts":ts,"high":item["price"],"low":item["price"],"done":set(),"gap":False})
        events.append(event)
        return events
    def _follow(self,sym,item):
        ts=item["timestamp"];events=[]
        for record in list(self.pending[sym]):
            e=record["event"]
            if ts<=e["timestamp"]:continue
            if ts-record["last_ts"]>3000:record["gap"]=True
            record["last_ts"]=ts
            record["high"]=max(record["high"],item["price"])
            record["low"]=min(record["low"],item["price"])
            for sec in (5,15,30,60):
                if sec in record["done"] or ts-e["timestamp"]<sec*1000:continue
                sign=1 if e["side"]=="buy" else -1
                outcome={"type":"wave_research_outcome","symbol":sym,"candidate_timestamp":e["timestamp"],"horizon_seconds":sec,
                    "signed_move":round((item["price"]-e["price"])*sign,5),
                    "favorable":round(max(0,(record["high"]-e["price"]) if sign>0 else (e["price"]-record["low"])),5),
                    "adverse":round(max(0,(e["price"]-record["low"]) if sign>0 else (record["high"]-e["price"])),5),
                    "data_gap":record["gap"],"research_only":True}
                events.append(outcome);record["done"].add(sec)
            if len(record["done"])==4:self.pending[sym].remove(record)
        return events

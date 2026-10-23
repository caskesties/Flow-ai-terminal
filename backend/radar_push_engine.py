"""Server-side staged radar/absorption events for iPhone Web Push.
Observational only; never places orders. Market data classifications are estimates.
"""
from collections import defaultdict, deque
from bisect import bisect_left

class _RadarWindow:
    """A time slice with O(1) cumulative volume/delta, preserving every print."""
    def __init__(self,rows,start,end):
        self.rows,self.start,self.end=rows,start,end
    def __len__(self):return self.end-self.start
    def __iter__(self):return iter(self.rows[self.start:self.end])
    def __getitem__(self,index):
        if index<0:index+=len(self)
        if index<0 or index>=len(self):raise IndexError(index)
        return self.rows[self.start+index]
    def metrics(self):
        if not len(self):return 0,0
        first,last=self[0],self[-1]
        volume=last["_volume"]-first["_volume"]+int(first["size"])
        delta=last["_delta"]-first["_delta"]+int(first["size"])*(1 if first["side"]=="buy" else -1)
        return volume,delta


class RadarPushEngine:
    def __init__(self, legacy_absorption=False):
        self.legacy_absorption=legacy_absorption
        self.trades=defaultdict(lambda:deque(maxlen=50000))
        self.cumulative=defaultdict(lambda:[0,0])
        self.phase=defaultdict(lambda:("NONE",None))
        self.last_emit={}
        self.abs_watch={}
        self.last_abs={}
    @staticmethod
    def metrics(rows):
        if isinstance(rows,_RadarWindow):return rows.metrics()
        vol=sum(int(x["size"]) for x in rows)
        delta=sum(int(x["size"])*(1 if x["side"]=="buy" else -1) for x in rows)
        return vol,delta
    @classmethod
    def wave(cls,rows):
        volume,delta=cls.metrics(rows)
        if len(rows)<3 or volume<8 or delta==0:return None
        return ("buy" if delta>0 else "sell", (volume+abs(delta))/(2*volume))
    @classmethod
    def direction(cls,rows,threshold=.53):
        vol,delta=cls.metrics(rows)
        if vol<=0:return None
        share=(vol+abs(delta))/(2*vol)
        return ("buy" if delta>0 else "sell") if delta and share>=threshold else None
    def on_trade(self,item):
        symbol=item["symbol"]
        if not symbol.startswith(("MNQ","NQ","GC","MGC")):return []
        ts=int(item["timestamp"])
        rows=self.trades[symbol]
        if rows and ts<rows[-1]["timestamp"]:return []
        totals=self.cumulative[symbol]
        size=int(item["size"])
        totals[0]+=size
        totals[1]+=size*(1 if item["side"]=="buy" else -1)
        rows.append(dict(item,_volume=totals[0],_delta=totals[1]))
        while rows and ts-rows[0]["timestamp"]>340000:rows.popleft()
        # One ordered snapshot per print; slice only the requested time range.
        # Repeated Python scans over the full 5-minute deque caused CPU backlog.
        ordered=list(rows)
        timestamps=[x["timestamp"] for x in ordered]
        def window(a,b):
            start=bisect_left(timestamps,ts-b)
            end=bisect_left(timestamps,ts-a)
            return _RadarWindow(ordered,start,end)
        recent60=window(0,60000)
        recent120=window(0,120000)
        recent300=window(0,300000)
        w1=self.wave(window(3000,6000))
        w2=self.wave(window(0,3000))
        overall=self.direction(recent60)
        two=self.direction(recent120)
        _,delta2=self.metrics(recent120)
        sufficient2=(len(recent120)>=12 and self.metrics(recent120)[0]>=40)
        pre=(two if sufficient2 and overall==two and two and w1 and w2 and
             w1[0]==w2[0]==two and ((two=="buy" and delta2>=100) or
             (two=="sell" and delta2<=-100)) else None)
        first5=window(150000,300000)
        second5=window(0,150000)
        w5a=self.wave(first5)
        w5b=self.wave(second5)
        five=self.direction(recent300)
        _,delta5=self.metrics(recent300)
        has5=(len(recent300)>=12 and recent300[-1]["timestamp"]-recent300[0]["timestamp"]>=240000)
        confirmed=bool(pre and has5 and five==pre and w5a and w5b and
                       w5a[0]==w5b[0]==pre and
                       ((pre=="buy" and delta5>0) or (pre=="sell" and delta5<0)))
        phase="CONFIRMADO" if confirmed else "POSSIVEL" if pre else "NONE"
        previous=self.phase[symbol]
        events=[]
        if phase!="NONE" and previous!=(phase,pre) and ts-self.last_emit.get((symbol,phase,pre),0)>=30000:
            stage="CONFIRMADO_5M" if confirmed else "POSSIVEL_2M"
            events.append(dict(type="radar_push",symbol=symbol,side=pre,stage=stage,
                               timestamp=ts,price=item["price"]))
            self.last_emit[(symbol,phase,pre)]=ts
        self.phase[symbol]=(phase,pre)
        # Absorption alerts now come exclusively from CandleFlowEngine.
        # Radar agreement describes flow context, not a candle entry trigger.
        if not self.legacy_absorption:return events
        # Absorption research: fresh signed aggression rises while price stays in a tight range
        # near an independently observed prior price extreme (support / resistance).
        sample=window(0,15000)
        before=window(7500,15000)
        after=window(0,7500)
        vol,delta=self.metrics(sample)
        _,ed=self.metrics(before);_,ld=self.metrics(after)
        side="buy" if delta>0 else "sell" if delta<0 else None
        prior=window(15000,105000)
        tick=.25 if symbol.startswith(("NQ","MNQ")) else .1
        boundary=(max(x["price"] for x in prior) if side=="buy"
                  else min(x["price"] for x in prior)) if len(prior)>=20 and (
                  prior[-1]["timestamp"]-prior[0]["timestamp"]>=30000) and side else None
        enough=(len(before)>=5 and len(after)>=5 and len(sample)>=10 and
                sample[-1]["timestamp"]-sample[0]["timestamp"]>=10000)
        growth=(side is not None and ed*delta>0 and ld*delta>0 and
                abs(ld)>=max(35,abs(ed)*1.15))
        stalled=(enough and vol>=100 and abs(delta)>=100 and
                 abs(delta)/vol>=.06 and growth and boundary is not None and
                 abs(item["price"]-boundary)<=max(4*tick,abs(boundary)*.00005) and
                 abs(item["price"]-sample[0]["price"])<=3*tick)
        watch=self.abs_watch.get(symbol)
        if stalled:
            if not watch or watch["side"]!=side or ts-watch["timestamp"]>30000:
                watch=dict(side=side,timestamp=ts,high=max(x["price"] for x in sample),
                           low=min(x["price"] for x in sample),weak=False)
                self.abs_watch[symbol]=watch
                if ts-self.last_abs.get((symbol,"ABS",side),0)>=30000:
                    events.append(dict(type="radar_push",symbol=symbol,stage="ABSORCAO",
                                       side="sell" if side=="buy" else "buy",timestamp=ts,
                                       price=item["price"]))
                    self.last_abs[(symbol,"ABS",side)]=ts
        elif watch and ts-watch["timestamp"]<=30000:
            reverse="sell" if watch["side"]=="buy" else "buy"
            recent=window(0,5000)
            previous5=window(5000,10000)
            _,dr=self.metrics(recent);_,dp=self.metrics(previous5)
            sign=1 if watch["side"]=="buy" else -1
            weakening=(len(recent)>=5 and len(previous5)>=5 and sign*dp>=35 and
                       sign*dr<=sign*dp*.6 and
                       watch["low"]-3*tick<=item["price"]<=watch["high"]+3*tick)
            breakout=(item["price"]>watch["high"]+tick if reverse=="buy"
                      else item["price"]<watch["low"]-tick)
            reversed_flow=(len(recent)>=5 and (dr>=20 if reverse=="buy" else dr<=-20))
            if reversed_flow and breakout:
                events.append(dict(type="radar_push",symbol=symbol,stage="REVERSAO_OBSERVADA",
                                   side=reverse,timestamp=ts,price=item["price"]))
                self.abs_watch.pop(symbol,None)
            elif weakening and not watch["weak"]:
                events.append(dict(type="radar_push",symbol=symbol,stage="DELTA_ENFRAQUECENDO",
                                   side=reverse,timestamp=ts,price=item["price"]))
                watch["weak"]=True
        elif watch:
            self.abs_watch.pop(symbol,None)
        return events

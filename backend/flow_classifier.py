"""Classify Massive futures trades against recent top-of-book quotes.
Aggressor is inferred, never reported as an exchange-verified flag.
"""
from collections import defaultdict,deque

class FlowClassifier:
    def __init__(self,max_quote_age_ms=1000):
        self.quotes={}
        self.previous_price={}
        self.max_quote_age_ms=max_quote_age_ms
        self.recent=defaultdict(lambda:deque(maxlen=50000))
        self.sequences={}
    def process(self,event):
        typ=event.get("ev"); sym=event.get("sym")
        if not sym or typ not in ("Q","T"):return None
        if typ=="Q":
            try: ts=int(max(event.get("bt",0),event.get("at",0)) or event["t"]); bid=float(event["bp"]); ask=float(event["ap"])
            except (ValueError,TypeError,KeyError):return None
            if bid<=0 or ask<=bid:return None
            old=self.quotes.get(sym)
            if old is None or ts>=old["timestamp"]:
                self.quotes[sym]={"timestamp":ts,"bid":bid,"ask":ask}
            return None
        try: ts=int(event["t"]); price=float(event["p"]); size=int(event["s"])
        except (ValueError,TypeError,KeyError):return None
        if price<=0 or size<=0:return None
        seq=event.get("q")
        if seq is not None:
            try: seq=int(seq)
            except (ValueError,TypeError):return None
            if seq<=self.sequences.get(sym,-1):return None
            self.sequences[sym]=seq
        quote=self.quotes.get(sym)
        side=None; method=None
        if quote and 0<=ts-quote["timestamp"]<=self.max_quote_age_ms:
            if price>=quote["ask"]:side="buy"
            elif price<=quote["bid"]:side="sell"
            if side:method="bbo"
        previous=self.previous_price.get(sym)
        self.previous_price[sym]=price
        if side is None and previous is not None:
            if price>previous:side="buy"
            elif price<previous:side="sell"
            if side:method="tick_rule"
        if side is None:return None
        item={"timestamp":ts,"price":price,"size":size,"side":side,"symbol":sym,"method":method}
        if seq is not None:item["trade_id"]=str(seq)
        self.recent[sym].append(item)
        return item
    def stats(self,sym,now,window_ms=60000):
        items=[t for t in self.recent[sym] if 0<=now-t["timestamp"]<=window_ms]
        buy=sum(t["size"] for t in items if t["side"]=="buy")
        sell=sum(t["size"] for t in items if t["side"]=="sell")
        return {"buy":buy,"sell":sell,"delta":buy-sell,"total":buy+sell,"trades":len(items)}

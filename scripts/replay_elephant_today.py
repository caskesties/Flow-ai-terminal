#!/usr/bin/env python3
"""Replay historical Massive trades+quotes through the live inferred-aggression
classifier and Elephant model. Only complete data yields a numeric signal count.
No institutional identification and no exchange-verified aggressor flag.
"""
import os,sys,json,urllib.request,urllib.parse,urllib.error,time,heapq,pathlib
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"backend"))
from flow_classifier import FlowClassifier
from elephant_model import ElephantFlowModel
DATE=os.getenv("FLOW_RESEARCH_DAY","2026-10-19")
SYMBOLS=[s.strip() for s in os.getenv("FLOW_RESEARCH_SYMBOLS","GCZ6,MGCZ6,NQZ6,MNQZ6").split(",") if s.strip()]
API="https://api.massive.com/futures/v1/"
MAX_PAGES=int(os.getenv("FLOW_MAX_PAGES","500"))
REPORT=pathlib.Path("reports/elephant_today")
REPORT.mkdir(parents=True,exist_ok=True)
def to_ns(hour,minute):
    dt=datetime.fromisoformat(DATE).replace(tzinfo=ZoneInfo("America/Los_Angeles"))
    return int(dt.replace(hour=hour,minute=minute).astimezone(timezone.utc).timestamp()*1e9)
START=to_ns(5,45) # warm-up for 20 complete 2m bars
ANALYZE=to_ns(6,30)
END=to_ns(12,0)
KEY=os.environ["MASSIVE_API_KEY"]
def events(sym,kind):
    params=urllib.parse.urlencode({"timestamp.gte":START,"timestamp.lt":END,"limit":50000,"sort":"timestamp.asc"})
    url=API+kind+"/"+urllib.parse.quote(sym,safe="")+"?"+params
    page=0;seen=0
    while url:
        page+=1
        if page>MAX_PAGES:raise RuntimeError(kind+": PAGE_CAP_REACHED")
        req=urllib.request.Request(url,headers={"Authorization":"Bearer "+KEY,"Accept":"application/json"})
        for retry in range(4):
            try:
                with urllib.request.urlopen(req,timeout=60) as res: data=json.load(res)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (429,500,502,503,504) and retry<3:
                    time.sleep(4*(retry+1));continue
                raise RuntimeError(kind+": HTTP "+str(exc.code)) from None
        if data.get("status") not in ("OK",None):raise RuntimeError(kind+": BAD_STATUS")
        rows=data.get("results") or []
        for x in rows:
            ts=x.get("timestamp")
            if isinstance(ts,int) and START<=ts<END:
                seen+=1
                yield ts,x
        url=data.get("next_url")
        if url and not url.startswith("https://api.massive.com/"):
            raise RuntimeError(kind+": UNSAFE_PAGINATION_URL")
        if page%20==0:print("PROGRESS "+sym+" "+kind+" pages="+str(page)+" rows="+str(seen),flush=True)
    print("COMPLETE "+sym+" "+kind+" pages="+str(page)+" rows="+str(seen),flush=True)

def run(sym):
    classifier=FlowClassifier();model=ElephantFlowModel()
    trades=events(sym,"trades");quotes=events(sym,"quotes")
    merged=heapq.merge(((t,0,row) for t,row in quotes),((t,1,row) for t,row in trades))
    signals=[];trade_count=quote_count=classified=0
    import elephant_model
    original=elephant_model.time.time
    try:
        for ts,kind,row in merged:
            millis=ts//1000000
            if kind==0:
                quote_count+=1
                bid=row.get("bid_price");ask=row.get("ask_price")
                if bid is None or ask is None:continue
                classifier.process({"ev":"Q","sym":sym,"bp":bid,"ap":ask,
                                    "bt":int(row.get("bid_timestamp") or ts)//1000000,
                                    "at":int(row.get("ask_timestamp") or ts)//1000000,
                                    "t":millis})
            else:
                trade_count+=1
                if row.get("price") is None or row.get("size") is None:continue
                record=classifier.process({"ev":"T","sym":sym,"t":millis,
                       "p":row["price"],"s":row["size"],"q":row.get("sequence_number")})
                if record is not None:classified+=1
                # Build OHLC from ALL trades; use estimated side only for flow.
                raw_record={"timestamp":millis,"price":float(row["price"]),
                            "size":float(row["size"]),"symbol":sym,
                            "side":record["side"] if record else None}
                elephant_model.time.time=lambda:millis/1000
                signal=model.on_trade(raw_record)
                if signal and ANALYZE<=ts<END:
                    signals.append({k:signal[k] for k in ("timestamp","symbol","side","price","ratio","large_flow_waves","level_type","level")})
    finally:elephant_model.time.time=original
    return {"symbol":sym,"trades":trade_count,"quotes":quote_count,
            "classified":classified,"signals":signals,"count":len(signals),
            "diagnostics":dict(model.diagnostics[sym]),
            "status":"COMPLETE"}
def main():
    summary={"date":DATE,"timezone":"America/Los_Angeles",
             "window":"06:30-12:00","preload":"05:45-06:30","results":[]}
    for sym in SYMBOLS:
        try: row=run(sym)
        except Exception as exc:
            row={"symbol":sym,"status":"INCOMPLETE","error":str(exc),"count":None,"signals":[]}
        summary["results"].append(row)
        print("RESEARCH_RESULT "+json.dumps(row,ensure_ascii=False),flush=True)
        (REPORT/"REPORT.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    return 1 if any(x["status"]!="COMPLETE" for x in summary["results"]) else 0
if __name__=="__main__":sys.exit(main())

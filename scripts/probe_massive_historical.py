#!/usr/bin/env python3
"""Read-only Massive historical entitlement probe. Does not print credentials or trade data."""
import json,os,urllib.request,urllib.parse,urllib.error
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
DATE=os.getenv("FLOW_RESEARCH_DAY","2026-10-19")
TICKERS=[x.strip() for x in os.getenv("FLOW_RESEARCH_SYMBOLS","GCZ6,MGCZ6,NQZ6,MNQZ6").split(",") if x.strip()]
API="https://api.massive.com"
def check(symbol,kind):
    start=datetime.fromisoformat(DATE+"T06:30:00").replace(tzinfo=ZoneInfo("America/Los_Angeles")).astimezone(timezone.utc).isoformat().replace("+00:00","Z")
    params=urllib.parse.urlencode({"timestamp.gte":start,"limit":10,"sort":"timestamp.asc"})
    url=f"{API}/futures/v1/{kind}/{urllib.parse.quote(symbol,safe='')}?{params}"
    req=urllib.request.Request(url,headers={"Authorization":"Bearer "+os.environ["MASSIVE_API_KEY"],"Accept":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=25) as res: data=json.load(res)
        items=data.get("results") or []
        return {"http":200,"rows":len(items),"has_next_page":bool(data.get("next_url")),"first_timestamp_ns":items[0].get("timestamp") if items else None}
    except urllib.error.HTTPError as e:return {"http":e.code,"rows":0}
    except Exception as e:return {"error":type(e).__name__}
def main():
    for sym in TICKERS:
        for kind in ("trades","quotes"):
            print("HISTORICAL_PROBE "+json.dumps({"symbol":sym,"kind":kind,**check(sym,kind)}),flush=True)
if __name__=="__main__":main()

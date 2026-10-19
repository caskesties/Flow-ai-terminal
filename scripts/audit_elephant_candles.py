#!/usr/bin/env python3
"""Audit all MNQ/NQ OHLC bars directly from historical trades, independently of delta.
Print exact candle metrics and distinct filters; no assumptions of institutional identity.
"""
import os,json,urllib.request,urllib.parse,datetime,collections,statistics
from zoneinfo import ZoneInfo
DAY="2026-10-19"
TZ=ZoneInfo("America/Los_Angeles")
def ns(h,m):
 d=datetime.datetime(2026,10,19,h,m,tzinfo=TZ)
 return int(d.timestamp()*1_000_000_000)
def audit(sym):
 start,end=ns(6,0),ns(8,30)
 p=urllib.parse.urlencode({"timestamp.gte":start,"timestamp.lt":end,"limit":50000,"sort":"timestamp.asc"})
 url="https://api.massive.com/futures/v1/trades/"+sym+"?"+p
 bars={};last_ts=0;count=0;pages=0
 while url:
  pages+=1
  if pages>30:raise RuntimeError("PAGE CAP")
  req=urllib.request.Request(url,headers={"Authorization":"Bearer "+os.environ["MASSIVE_API_KEY"]})
  with urllib.request.urlopen(req,timeout=60) as f: data=json.load(f)
  for r in data.get("results",[]):
   t=r.get("timestamp");price=r.get("price");volume=r.get("size",0)
   if not isinstance(t,int) or not isinstance(price,(int,float)):continue
   if not start<=t<end:continue
   count+=1;idx=t//120_000_000_000
   if idx not in bars:bars[idx]={"t":idx,"o":price,"h":price,"l":price,"c":price,"v":0,"n":0,"first":t,"last":t}
   b=bars[idx]
   b["h"]=max(b["h"],price);b["l"]=min(b["l"],price)
   if t>=b["last"]:b["c"]=price;b["last"]=t
   if t<b["first"]:b["o"]=price;b["first"]=t
   b["v"]+=volume;b["n"]+=1
  url=data.get("next_url")
  if url and not url.startswith("https://api.massive.com/"):raise RuntimeError("bad next_url")
 sequence=sorted(bars)
 print("AUDIT_HEADER "+json.dumps({"symbol":sym,"trades":count,"pages":pages,"bars":len(bars)}),flush=True)
 for idx in sequence:
  if not ns(6,30)<=idx*120_000_000_000<ns(8,30):continue
  b=bars[idx]; prior=[bars.get(idx-k) for k in range(1,21)]
  if any(x is None for x in prior):continue
  avg=statistics.mean(x["h"]-x["l"] for x in prior)
  body=abs(b["c"]-b["o"]);span=b["h"]-b["l"]
  if span<=0:continue
  side="buy" if b["c"]>b["o"] else "sell"
  wick=b["h"]-b["c"] if side=="buy" else b["c"]-b["l"]
  maxbody=max(abs(x["c"]-x["o"]) for x in prior[:3])
  local=datetime.datetime.fromtimestamp(idx*120, TZ).strftime("%H:%M")
  info={"symbol":sym,"time":local,"o":b["o"],"h":b["h"],"l":b["l"],"c":b["c"],
       "volume":b["v"],"side":side,"body":round(body,2),"max_previous3_body":round(maxbody,2),
       "body_frac":round(body/span,4),"closing_wick_ticks":round(wick/.25,2),
       "range_ratio":round(span/avg,3) if avg else None,
       "larger3":body>maxbody,"strong_close":wick<=.2500001 and body/span>=.8,
       "passes_extra_1_8x":span>=1.8*avg if avg else False}
  if info["larger3"] or local in ("07:12","07:14","07:16","07:18","07:20","08:10","08:12","08:14","08:16"):
   print("AUDIT_BAR "+json.dumps(info),flush=True)
for sym in ("MNQZ6","NQZ6"):audit(sym)

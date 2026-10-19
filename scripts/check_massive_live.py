#!/usr/bin/env python3
"""Short Massive Futures Advanced entitlement test. Never prints credentials or market payloads."""
import json, os, time, sys
from collections import Counter
import websocket

def main():
    key=os.environ.get("MASSIVE_API_KEY")
    ticker=os.environ.get("LIVE_TEST_TICKER","GCZ6").strip().upper()
    if not key:
        raise SystemExit("MASSIVE_API_KEY GitHub secret missing")
    if not ticker.isalnum() or len(ticker)>24:
        raise SystemExit("Invalid ticker")
    counts=Counter()
    authed=False
    subscribed=False
    print("Testing Massive Futures real-time entitlements for",ticker,flush=True)
    ws=websocket.create_connection("wss://socket.massive.com/futures",timeout=8)
    try:
        ws.send(json.dumps({"action":"auth","params":key}))
        until=time.monotonic()+35
        while time.monotonic()<until:
            ws.settimeout(min(5,max(1,until-time.monotonic())))
            try: raw=ws.recv()
            except websocket.WebSocketTimeoutException: continue
            try: items=json.loads(raw)
            except (ValueError,TypeError): continue
            if not isinstance(items,list): items=[items]
            for msg in items:
                ev=msg.get("ev")
                if ev=="status":
                    status=str(msg.get("status",""))
                    print("Provider status:",status,flush=True)
                    if status in ("auth_failed","max_connections"): return 2
                    if status=="auth_success": authed=True
                elif ev in ("T","Q") and msg.get("sym")==ticker:
                    counts[ev]+=1
            if authed and not subscribed:
                ws.send(json.dumps({"action":"subscribe","params":f"T.{ticker},Q.{ticker}"}))
                subscribed=True
            if counts["T"]>=5 and counts["Q"]>=5: break
    finally:
        ws.close()
    print("Messages received: trades =",counts["T"],", quotes =",counts["Q"])
    print("Authentication:", "OK" if authed else "NOT CONFIRMED")
    if not authed:return 2
    if counts["T"] and counts["Q"]:
        print("SUCCESS: both trade and BBO quote channels received. No aggressor classification validated.")
        return 0
    print("INCONCLUSIVE: connected but missing trades/quotes. Check contract activity, trading hours, symbols and entitlements.")
    return 1
if __name__=="__main__":sys.exit(main())

"""Private Massive-to-Flow WebSocket bridge.
Requires a private TLS reverse proxy and server-side Massive key.
Never serve this directly to the public internet.
"""
import asyncio,json,os,time
from collections import Counter
import websockets
from flow_classifier import FlowClassifier

MAX_CLIENT_QUEUE=1000
async def main():
    api_key=os.environ["MASSIVE_API_KEY"]
    access=os.environ["FLOW_BRIDGE_TOKEN"]
    if len(access)<24:raise SystemExit("FLOW_BRIDGE_TOKEN must be at least 24 characters")
    symbols=[s.strip().upper() for s in os.getenv("MASSIVE_SYMBOLS","GCZ6").split(",") if s.strip()]
    if not symbols or any(not s.isalnum() for s in symbols):raise SystemExit("Invalid dated futures symbols")
    classifier=FlowClassifier()
    counts=Counter()
    last_report=time.monotonic()
    clients=set()
    async def browser(ws):
        # Token is sent in initial auth message, not in URL/query logs.
        try:
            raw=await asyncio.wait_for(ws.recv(),timeout=5)
            hello=json.loads(raw)
            import hmac
            if not hmac.compare_digest(str(hello.get("token","")),access):
                print("Flow browser rejected: token mismatch",flush=True)
                await ws.close(code=1008,reason="Unauthorized");return
            requested=hello.get("symbol")
            if requested not in symbols:
                print("Flow browser rejected: unsupported contract",flush=True)
                await ws.close(code=1008,reason="Unknown contract");return
            queue=asyncio.Queue(maxsize=MAX_CLIENT_QUEUE)
            clients.add((ws,requested,queue))
            print("Flow browser authenticated for %s" % requested,flush=True)
            await ws.send(json.dumps({"type":"ready","contract":requested,"classification":"estimated"}))
            try:
                while True:
                    event=await queue.get()
                    await ws.send(json.dumps(event))
            finally:clients.discard((ws,requested,queue))
        except (asyncio.TimeoutError,ValueError,KeyError):await ws.close(code=1008,reason="Invalid authorization")
    async def provider():
        nonlocal last_report
        retry=2
        while True:
            try:
                async with websockets.connect("wss://socket.massive.com/futures",ping_interval=20,max_size=4_000_000) as ws:
                    await ws.send(json.dumps({"action":"auth","params":api_key}))
                    authorized=False
                    async for raw in ws:
                        data=json.loads(raw)
                        for msg in data if isinstance(data,list) else [data]:
                            if msg.get("ev")=="status":
                                if msg.get("status")=="auth_success":
                                    print("Massive authentication OK",flush=True)
                                    authorized=True
                                    channels=",".join(kind+"."+sym for sym in symbols for kind in ("T","Q"))
                                    await ws.send(json.dumps({"action":"subscribe","params":channels}))
                                if msg.get("status")=="auth_failed":raise RuntimeError("Massive authorization failed")
                                if msg.get("status") in ("error","success"):
                                    print("Massive subscription status: %s %s" % (msg.get("status"),str(msg.get("message",""))[:160]),flush=True)
                                continue
                            if not authorized:continue
                            if msg.get("ev") in ("T","Q"):
                                counts[msg["ev"]]+=1
                            item=classifier.process(msg)
                            if item:counts["classified"]+=1
                            if time.monotonic()-last_report>=30:
                                print("Provider 30s diagnostics: trades=%d quotes=%d classified=%d clients=%d" %(counts["T"],counts["Q"],counts["classified"],len(clients)),flush=True)
                                counts.clear()
                                last_report=time.monotonic()
                            if item:
                                for client,sym,queue in tuple(clients):
                                    if sym==item["symbol"]:
                                        outgoing=dict(item)
                                        outgoing["contract"]=sym
                                        outgoing["symbol"]=next((p for p in ("MNQ","MGC","NQ","GC","ZN") if sym.startswith(p)),sym)
                                        if queue.full():
                                            await client.close(code=1013,reason="Slow client, reconnect")
                                            clients.discard((client,sym,queue))
                                        else:queue.put_nowait(outgoing)
                    retry=2
            except (OSError,websockets.exceptions.WebSocketException,RuntimeError,ValueError) as exc:
                print("Massive stream disconnected: %s code=%s reason=%s" % (type(exc).__name__,getattr(exc,"code",getattr(getattr(exc,"rcvd",None),"code","n/a")),str(getattr(exc,"reason",getattr(getattr(exc,"rcvd",None),"reason","")))[:120]),flush=True)
                for client,_,_ in tuple(clients):
                    try:await client.close(code=1012,reason="Upstream restarting")
                    except Exception:pass
                clients.clear()
                await asyncio.sleep(retry)
                retry=min(retry*2,60)
    async with websockets.serve(browser,"0.0.0.0",int(os.getenv("FLOW_BRIDGE_PORT","8765")),max_size=10000,ping_interval=20):
        print("Private Flow bridge running on port %s; TLS reverse proxy required" % os.getenv("FLOW_BRIDGE_PORT","8765"),flush=True)
        await provider()
if __name__=="__main__":asyncio.run(main())

"""Private Massive-to-Flow WebSocket bridge.
Requires a private TLS reverse proxy and server-side Massive key.
Never serve this directly to the public internet.
"""
import asyncio,json,os,time
from datetime import datetime,time as clock_time
from zoneinfo import ZoneInfo

PACIFIC=ZoneInfo('America/Los_Angeles')
def event_in_session(timestamp_ms):
    return within_session(datetime.fromtimestamp(timestamp_ms/1000, PACIFIC))

def within_session(now=None):
    local=(now or datetime.now(PACIFIC)).astimezone(PACIFIC)
    if local.weekday()>=5:return False
    t=local.time()
    return clock_time(6,29)<=t<clock_time(8,30) or clock_time(16,30)<=t<clock_time(20,0)

from collections import Counter,defaultdict,deque
import websockets
from flow_classifier import FlowClassifier
from server_signals import ServerFlowSignals
from structure_model import StructureFlowModel
import push_alerts

MAX_CLIENT_QUEUE=1000
async def main():
    api_key=os.environ["MASSIVE_API_KEY"]
    access=os.environ["FLOW_BRIDGE_TOKEN"]
    if len(access)<24:raise SystemExit("FLOW_BRIDGE_TOKEN must be at least 24 characters")
    symbols=[s.strip().upper() for s in os.getenv("MASSIVE_SYMBOLS","GCZ6,MGCZ6,NQZ6,MNQZ6").split(",") if s.strip()]
    if not symbols or any(not s.isalnum() for s in symbols):raise SystemExit("Invalid dated futures symbols")
    classifier=FlowClassifier()
    signal_engine=ServerFlowSignals()
    structure_engine=StructureFlowModel()
    counts=Counter()
    last_report=time.monotonic()
    clients=set()
    replay=defaultdict(lambda:deque(maxlen=40000))
    relayed=0
    latest_treasury=None
    feed_health={"last_market_event_ms":0,"last_classified_ms":0,"provider_connected":False}
    async def health_loop():
        while True:
            await asyncio.sleep(1)
            now=int(time.time()*1000)
            age=now-feed_health["last_market_event_ms"] if feed_health["last_market_event_ms"] else None
            status="LIVE" if feed_health["provider_connected"] and age is not None and age<=3000 else "STALE"
            event={"type":"feed_health","status":status,"provider_connected":feed_health["provider_connected"],"last_market_event_ms":feed_health["last_market_event_ms"],"last_classified_ms":feed_health["last_classified_ms"],"age_ms":age,"server_timestamp":now}
            for _,_,q in tuple(clients):
                if not q.full():q.put_nowait(event)
    async def browser(ws):
        # Token is sent in initial auth message, not in URL/query logs.
        try:
            raw=await asyncio.wait_for(ws.recv(),timeout=5)
            hello=json.loads(raw)
            import hmac
            if not hmac.compare_digest(str(hello.get("token","")),access):
                print("Flow browser rejected: token mismatch",flush=True)
                await ws.close(code=1008,reason="Unauthorized");return
            if hello.get("type")=="push_test":
                success=bool(within_session() and push_alerts.enabled() and push_alerts.SUBSCRIPTIONS)
                if success:
                    await push_alerts.deliver({"title":"FLOW · TESTE DE NOTIFICAÇÃO","body":"Teste técnico de push. NÃO é um sinal de mercado nem recomendação de entrada.","tag":"flow-push-test","url":"./index.html"})
                await ws.send(json.dumps({"type":"push_test_result","success":success,"reason":"Envio solicitado; entrega no iPhone não confirmada" if success else "Teste indisponível fora dos horários de alerta ou push não configurado"}))
                await ws.close(code=1000)
                return
            if hello.get("type")=="push_subscribe":
                try:
                    push_alerts.add(hello.get("subscription"))
                    await ws.send(json.dumps({"type":"push_registered","success":True}))
                except ValueError as exc:
                    await ws.send(json.dumps({"type":"push_registered","success":False,"reason":str(exc)}))
                await ws.close(code=1000)
                return
            requested=str(hello.get("symbol","")).strip().upper()
            paired=bool(hello.get("paired")) and requested.startswith("MGC")
            if requested not in symbols:
                matches=[contract for contract in symbols if contract.startswith(requested) and len(contract)>len(requested)]
                if len(matches)==1:requested=matches[0]
            if requested not in symbols:
                print("Flow browser rejected: unsupported contract requested=%s allowed=%s" % (requested,",".join(symbols)),flush=True)
                await ws.close(code=1008,reason="Unknown contract");return
            queue=asyncio.Queue(maxsize=MAX_CLIENT_QUEUE)
            print("Flow browser authenticated for %s" % requested,flush=True)
            await ws.send(json.dumps({"type":"ready","contract":requested,"classification":"estimated","server_analysis":"experimental","push_public_key":push_alerts.PUBLIC_KEY}))
            now_ms=int(time.time()*1000)
            snapshot=[row for row in replay[requested] if now_ms-row["timestamp"]<=190000]
            print("Flow replay for %s: %d classified prints" % (requested,len(snapshot)),flush=True)
            for offset in range(0,len(snapshot),150):
                await ws.send(json.dumps({"type":"replay_batch","trades":snapshot[offset:offset+150]}))
            await ws.send(json.dumps({"type":"replay_complete","count":len(snapshot)}))
            if requested.startswith(("MNQ","NQ")) and latest_treasury and abs(now_ms-latest_treasury["timestamp"])<=10000:
                await ws.send(json.dumps(latest_treasury))
            for alert in signal_engine.recent_alerts(requested):
                if event_in_session(alert["timestamp"]):
                    await ws.send(json.dumps(alert))
            clients.add((ws,requested,queue))
            try:
                while True:
                    event=await queue.get()
                    await ws.send(json.dumps(event))
            finally:clients.discard((ws,requested,queue))
        except (asyncio.TimeoutError,ValueError,KeyError):await ws.close(code=1008,reason="Invalid authorization")
        except websockets.exceptions.ConnectionClosed:
            print("Flow browser disconnected",flush=True)
    async def provider():
        nonlocal last_report,latest_treasury
        retry=15
        while True:
            try:
                async with websockets.connect("wss://socket.massive.com/futures",ping_interval=20,max_size=4_000_000) as ws:
                    await ws.send(json.dumps({"action":"auth","params":api_key}))
                    authorized=False
                    feed_health["provider_connected"]=False
                    async for raw in ws:
                        data=json.loads(raw)
                        for msg in data if isinstance(data,list) else [data]:
                            if msg.get("ev")=="status":
                                if msg.get("status")=="auth_success":
                                    print("Massive authentication OK",flush=True)
                                    authorized=True
                                    feed_health["provider_connected"]=True
                                    channels=",".join(kind+"."+sym for sym in dict.fromkeys([*symbols,"ZNZ6"]) for kind in ("T","Q"))
                                    print("Massive subscribing: "+channels,flush=True)
                                    await ws.send(json.dumps({"action":"subscribe","params":channels}))
                                if msg.get("status")=="auth_failed":raise RuntimeError("Massive authorization failed")
                                if msg.get("status") in ("max_connections","auth_failed"):
                                    print("Massive provider status: %s details=%s" % (msg.get("status"),str(msg.get("message",""))[:220]),flush=True)
                                if msg.get("status") in ("error","success"):
                                    print("Massive subscription status: %s %s" % (msg.get("status"),str(msg.get("message",""))[:160]),flush=True)
                                continue
                            if not authorized:continue
                            if msg.get("ev") in ("T","Q"):
                                feed_health["last_market_event_ms"]=int(time.time()*1000)
                                counts[msg["ev"]]+=1
                                counts[msg["ev"]+"."+str(msg.get("sym","unknown"))]+=1
                            if msg.get("ev")=="T" and str(msg.get("sym","")).startswith("ZN"):
                                try:
                                    zn_price=float(msg["p"]);zn_time=int(msg["t"])
                                    if zn_price>0:
                                        zn_event={"symbol":"ZN","timestamp":zn_time,"price":zn_price,"contract":str(msg["sym"]),"source":"ZN futures last trade"}
                                        signal_engine.on_treasury(zn_time,zn_price,"ZN")
                                        latest_treasury=zn_event
                                        for _,contract,q in tuple(clients):
                                            if contract.startswith(("MNQ","NQ")) and not q.full():q.put_nowait(zn_event)
                                except (KeyError,TypeError,ValueError):pass
                            if msg.get("ev")=="Q" and str(msg.get("sym","")).startswith("ZN"):
                                try:
                                    bid=float(msg["bp"]);ask=float(msg["ap"])
                                    zn_ts=int(max(msg.get("bt",0),msg.get("at",0)) or msg["t"])
                                    if bid>0 and ask>bid and zn_ts>0:
                                        zn_quote={"symbol":"ZN","contract":str(msg["sym"]),"timestamp":zn_ts,"price":(bid+ask)/2,"source":"BBO midpoint (derived, not yield)"}
                                        signal_engine.on_treasury(zn_ts,(bid+ask)/2,"ZN")
                                        latest_treasury=zn_quote
                                        for _,contract,q in tuple(clients):
                                            if contract.startswith(("MNQ","NQ")) and not q.full():q.put_nowait(zn_quote)
                                except (KeyError,TypeError,ValueError):pass
                            item=classifier.process(msg)
                            if item:
                                replay[item["symbol"]].append(dict(item))
                                feed_health["last_classified_ms"]=int(time.time()*1000)
                                server_signal=signal_engine.on_trade(item)
                                structure_signal=structure_engine.on_trade(item)
                                for outcome in signal_engine.drain_updates():
                                    print("Server outcome: %s %ss signed=%s favorable=%s adverse=%s gap=%s" % (outcome["symbol"],outcome["horizon_seconds"],outcome["signed_move"],outcome["favorable_excursion"],outcome["adverse_excursion"],outcome["data_gap"]),flush=True)
                                    for _,contract,q in tuple(clients):
                                        if contract==outcome["symbol"] and not q.full():q.put_nowait(outcome)
                                if server_signal:
                                    print("Server flow diagnostic: %s %s ratio=%s clients=%d" % (server_signal["symbol"],server_signal["side"],server_signal["ratio"],len(clients)),flush=True)
                                    if event_in_session(server_signal["timestamp"]):
                                        asyncio.create_task(push_alerts.deliver(push_alerts.payload_for_signal(server_signal)))
                                        for _,contract,q in tuple(clients):
                                            if contract==server_signal["symbol"] and not q.full():q.put_nowait(server_signal)
                                if structure_signal:
                                    signal_engine.alerts[item["symbol"]].append(structure_signal)
                                    signal_engine.pending[item["symbol"]].append({"event":structure_signal,"high":item["price"],"low":item["price"],"last_ts":item["timestamp"],"completed":set()})
                                    print("Model B structure diagnostic: %s %s ratio=%s" % (item["symbol"],structure_signal["side"],structure_signal["ratio"]),flush=True)
                                    if event_in_session(structure_signal["timestamp"]):
                                        asyncio.create_task(push_alerts.deliver(push_alerts.payload_for_signal(structure_signal)))
                                        for _,contract,q in tuple(clients):
                                            if contract==structure_signal["symbol"] and not q.full():q.put_nowait(structure_signal)
                                counts["classified"]+=1
                                counts["classified."+item["symbol"]]+=1
                            if time.monotonic()-last_report>=30:
                                print("Provider 30s diagnostics: trades=%d quotes=%d classified=%d clients=%d samples=%s" %(counts["T"],counts["Q"],counts["classified"],len(clients),str(getattr(classifier,"recent",{}).get(symbols[0],[]) and list(classifier.recent[symbols[0]])[-1].get("timestamp","none"))),flush=True)
                                print("Per-contract 30s: "+", ".join("%s=%d"%(k,v) for k,v in sorted(counts.items()) if "." in k),flush=True)
                                counts.clear()
                                last_report=time.monotonic()
                            if item:
                                for client,sym,queue in tuple(clients):
                                    if sym==item["symbol"] or ((sym.startswith("MGC") or sym.startswith("MNQ")) and item["symbol"]==(sym.replace("MGC","GC",1) if sym.startswith("MGC") else sym.replace("MNQ","NQ",1))):
                                        outgoing=dict(item)
                                        outgoing["contract"]=sym
                                        outgoing["symbol"]=next((p for p in ("MNQ","MGC","NQ","GC","ZN") if item["symbol"].startswith(p)),item["symbol"])
                                        outgoing["reference"]=item["symbol"]!=sym
                                        if queue.full():
                                            await client.close(code=1013,reason="Slow client, reconnect")
                                            clients.discard((client,sym,queue))
                                        else:queue.put_nowait(outgoing)
                    retry=15
            except (OSError,websockets.exceptions.WebSocketException,RuntimeError,ValueError) as exc:
                feed_health["provider_connected"]=False
                print("Massive stream disconnected: %s code=%s reason=%s" % (type(exc).__name__,getattr(exc,"code",getattr(getattr(exc,"rcvd",None),"code","n/a")),str(getattr(exc,"reason",getattr(getattr(exc,"rcvd",None),"reason","")))[:120]),flush=True)
                for client,_,_ in tuple(clients):
                    try:await client.close(code=1012,reason="Upstream restarting")
                    except Exception:pass
                clients.clear()
                await asyncio.sleep(retry)
                retry=min(retry*2,60)
    async with websockets.serve(browser,"0.0.0.0",int(os.getenv("FLOW_BRIDGE_PORT","8765")),max_size=10000,ping_interval=60,ping_timeout=60):
        print("Private Flow bridge running on port %s; TLS reverse proxy required" % os.getenv("FLOW_BRIDGE_PORT","8765"),flush=True)
        watchdog=asyncio.create_task(health_loop())
        try:await provider()
        finally:watchdog.cancel()
if __name__=="__main__":asyncio.run(main())

"""Private Massive-to-Flow WebSocket bridge.
Requires a private TLS reverse proxy and server-side Massive key.
Never serve this directly to the public internet.
"""
import asyncio,json,os,time,hmac
from push_schedule import event_in_session, within_session

from collections import Counter,defaultdict,deque
import websockets
from flow_classifier import FlowClassifier
from server_signals import ServerFlowSignals
from structure_model import StructureFlowModel
from elephant_model import ElephantFlowModel
from post_signal_monitor import PostSignalMonitor
from wave_research import WaveResearch
from absorption_research import AbsorptionResearch
from radar_push_engine import RadarPushEngine
from candle_flow import CandleFlowEngine, push_payload as candle_push_payload
import push_alerts
from equity_basket import EquityBasket

MAX_CLIENT_QUEUE=1000
TRANSPORT_VERSION="spark-auth-20261026"

def token_matches(provided,expected):
    # compare_digest(str, str) rejects non-ASCII. Compare exact UTF-8 bytes;
    # never normalize, truncate, log or change the configured credential.
    if not isinstance(provided,str):return False
    try:return hmac.compare_digest(provided.encode("utf-8"),expected.encode("utf-8"))
    except UnicodeError:return False

async def main():
    api_key=os.environ["MASSIVE_API_KEY"]
    access=os.environ["FLOW_BRIDGE_TOKEN"]
    if len(access)<24:raise SystemExit("FLOW_BRIDGE_TOKEN must be at least 24 characters")
    symbols=[s.strip().upper() for s in os.getenv("MASSIVE_SYMBOLS","GCZ6,MGCZ6,NQZ6,MNQZ6").split(",") if s.strip()]
    if not symbols or any(not s.isalnum() for s in symbols):raise SystemExit("Invalid dated futures symbols")
    classifier=FlowClassifier()
    signal_engine=ServerFlowSignals()
    structure_engine=StructureFlowModel()
    elephant_engine=ElephantFlowModel()
    post_monitor=PostSignalMonitor()
    wave_research=WaveResearch()
    absorption_research=AbsorptionResearch()
    radar_push_engine=RadarPushEngine()
    candle_engine=CandleFlowEngine()
    candle_published={}
    counts=Counter()
    last_report=time.monotonic()
    clients=set()
    replay=defaultdict(lambda:deque(maxlen=40000))
    relayed=0
    basket=EquityBasket(json.loads(os.environ["FLOW_EQUITY_WEIGHTS"]) if os.getenv("FLOW_EQUITY_WEIGHTS") else None,
        os.getenv("FLOW_EQUITY_WEIGHTS_ASOF","2026-10-29"))
    feed_health={"last_market_event_ms":0,"last_classified_ms":0,"provider_connected":False}
    contract_health=defaultdict(lambda:{"quote_ms":0,"trade_ms":0,"classified_ms":0,"received_ms":0,"lag_ms":None})
    close_tasks=set()
    def disconnect_slow(client, sym, queue):
        # Never wait for a frozen phone's close handshake inside provider ingest.
        clients.discard((client,sym,queue))
        task=asyncio.create_task(client.close(code=1013,reason="Slow client, reconnect"))
        close_tasks.add(task)
        task.add_done_callback(close_tasks.discard)
    async def health_loop():
        while True:
            await asyncio.sleep(1)
            now=int(time.time()*1000)
            for client,contract,q in tuple(clients):
                metrics=contract_health[contract]
                event_ms=max(metrics["quote_ms"],metrics["trade_ms"])
                age=now-event_ms if event_ms else None
                status="LIVE" if feed_health["provider_connected"] and age is not None and -5000<=age<=3000 else "STALE"
                event={"type":"feed_health","status":status,"contract":contract,
                    "transport_version":TRANSPORT_VERSION,
                    "provider_connected":feed_health["provider_connected"],
                    "last_market_event_ms":event_ms,"last_trade_ms":metrics["trade_ms"],
                    "last_classified_ms":metrics["classified_ms"],"age_ms":age,
                    "provider_lag_ms":metrics["lag_ms"],"queue_depth":q.qsize(),
                    "server_timestamp":now}
                if q.full():disconnect_slow(client,contract,q)
                else:q.put_nowait(event)
                if contract.startswith(("NQ","MNQ")) and not q.full():
                    q.put_nowait(basket.snapshot(now))
    async def browser(ws):
        # Token is sent in initial auth message, not in URL/query logs.
        try:
            raw=await asyncio.wait_for(ws.recv(),timeout=5)
            hello=json.loads(raw)
            if not isinstance(hello,dict) or not token_matches(hello.get("token"),access):
                print("Flow browser rejected: token mismatch",flush=True)
                await ws.close(code=1008,reason="Unauthorized");return
            if hello.get("type")=="push_test":
                success=bool(within_session() and push_alerts.enabled() and push_alerts.SUBSCRIPTIONS)
                if success:
                    await push_alerts.deliver({"title":"SPARK AI · TESTE DE NOTIFICAÇÃO","body":"Teste técnico de push. NÃO é um sinal de mercado nem recomendação de entrada.","tag":"flow-push-test","url":"./index.html"})
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
            await ws.send(json.dumps({"type":"ready","transport_version":TRANSPORT_VERSION,"contract":requested,"classification":"estimated","server_analysis":"experimental","push_public_key":push_alerts.PUBLIC_KEY}))
            now_ms=int(time.time()*1000)
            snapshot=[row for row in replay[requested] if 0<=now_ms-row["timestamp"]<=330000]
            print("Flow replay for %s: %d classified prints" % (requested,len(snapshot)),flush=True)
            for offset in range(0,len(snapshot),150):
                await ws.send(json.dumps({"type":"replay_batch","trades":snapshot[offset:offset+150]}))
            await ws.send(json.dumps({"type":"replay_complete","count":len(snapshot)}))
            await ws.send(json.dumps(candle_engine.snapshot(requested)))
            if requested.startswith(("MNQ","NQ")):
                await ws.send(json.dumps(basket.snapshot(now_ms)))
            for alert in signal_engine.recent_alerts(requested):
                if event_in_session(alert["timestamp"]):
                    await ws.send(json.dumps(alert))
            clients.add((ws,requested,queue))
            async def send_events():
                while True:
                    event=await queue.get()
                    batch=[event]
                    while len(batch)<100 and not queue.empty():
                        batch.append(queue.get_nowait())
                    await ws.send(json.dumps(batch if len(batch)>1 else event))
            sender=asyncio.create_task(send_events())
            closed=asyncio.create_task(ws.wait_closed())
            try:
                done,_=await asyncio.wait((sender,closed),return_when=asyncio.FIRST_COMPLETED)
                for task in done:task.result()
            finally:
                clients.discard((ws,requested,queue))
                sender.cancel();closed.cancel()
                await asyncio.gather(sender,closed,return_exceptions=True)
        except (asyncio.TimeoutError,ValueError,KeyError):await ws.close(code=1008,reason="Invalid authorization")
        except websockets.exceptions.ConnectionClosed:
            print("Flow browser disconnected",flush=True)
    async def equities_provider():
        retry=15
        stock_key=os.getenv("MASSIVE_STOCKS_API_KEY",api_key)
        while True:
            try:
                basket.status="CONNECTING"
                async with websockets.connect("wss://socket.massive.com/stocks",ping_interval=20,max_size=4_000_000) as stock_ws:
                    await stock_ws.send(json.dumps({"action":"auth","params":stock_key}))
                    async for raw in stock_ws:
                        data=json.loads(raw)
                        for msg in data if isinstance(data,list) else [data]:
                            await asyncio.sleep(0)
                            if msg.get("ev")=="status":
                                status=msg.get("status")
                                detail=str(msg.get("message", ""))
                                for secret in (stock_key,api_key,access):
                                    if secret:detail=detail.replace(secret,"[REDACTED]")
                                print("Equity provider status: %s %s" % (status,detail[:240]),flush=True)
                                if status=="auth_success":
                                    basket.connected=True
                                    basket.status="WAITING_FOR_QUOTES"
                                    await stock_ws.send(json.dumps({"action":"subscribe","params":",".join("Q."+s for s in basket.weights)}))
                                elif status in ("auth_failed","not_authorized","error","max_connections"):
                                    basket.status="ACCESS_UNAVAILABLE"
                                    raise RuntimeError("Stock stream unavailable")
                            elif basket.connected and basket.on_quote(msg,int(time.time()*1000)):
                                basket.status="RECEIVING"
                                retry=15
            except (OSError,websockets.exceptions.WebSocketException,RuntimeError,ValueError) as exc:
                print("Equity connection error: %s" % type(exc).__name__,flush=True)
                basket.status="ACCESS_OR_CONNECTION_UNAVAILABLE"
                print("Equity context unavailable; futures feed continues independently",flush=True)
            finally:
                basket.connected=False
            await asyncio.sleep(retry)
            retry=min(retry*2,120)

    async def provider():
        nonlocal last_report
        retry=15
        connection_limited=False
        while True:
            try:
                connection_limited=False
                async with websockets.connect("wss://socket.massive.com/futures",ping_interval=20,max_size=4_000_000) as ws:
                    await ws.send(json.dumps({"action":"auth","params":api_key}))
                    authorized=False
                    feed_health["provider_connected"]=False
                    async for raw in ws:
                        data=json.loads(raw)
                        for msg in data if isinstance(data,list) else [data]:
                            # A buffered provider recv may complete without yielding. Keep
                            # browser handshakes, heartbeats and delivery responsive under load.
                            await asyncio.sleep(0)
                            if msg.get("ev")=="status":
                                if msg.get("status")=="auth_success":
                                    print("Massive authentication OK",flush=True)
                                    authorized=True
                                    feed_health["provider_connected"]=True
                                    channels=",".join(kind+"."+sym for sym in dict.fromkeys(symbols) for kind in ("T","Q"))
                                    print("Massive subscribing: "+channels,flush=True)
                                    await ws.send(json.dumps({"action":"subscribe","params":channels}))
                                if msg.get("status")=="auth_failed":raise RuntimeError("Massive authorization failed")
                                if msg.get("status") in ("max_connections","auth_failed"):
                                    if msg.get("status")=="max_connections":connection_limited=True
                                    print("Massive provider status: %s details=%s" % (msg.get("status"),str(msg.get("message",""))[:220]),flush=True)
                                if msg.get("status") in ("error","success"):
                                    print("Massive subscription status: %s %s" % (msg.get("status"),str(msg.get("message",""))[:160]),flush=True)
                                continue
                            if not authorized:continue
                            if msg.get("ev") in ("T","Q"):
                                try:
                                    event_ms=int((max(msg.get("bt",0),msg.get("at",0)) if msg.get("ev")=="Q" else 0) or msg["t"])
                                    feed_health["last_market_event_ms"]=event_ms
                                    metrics=contract_health[str(msg.get("sym",""))]
                                    field="quote_ms" if msg.get("ev")=="Q" else "trade_ms"
                                    if event_ms>=metrics[field]:
                                        metrics[field]=event_ms
                                        metrics["received_ms"]=int(time.time()*1000)
                                        metrics["lag_ms"]=metrics["received_ms"]-event_ms
                                except (KeyError,TypeError,ValueError):pass
                                counts[msg["ev"]]+=1
                                counts[msg["ev"]+"."+str(msg.get("sym","unknown"))]+=1
                            item=classifier.process(msg)
                            # Model C forms true tick-derived OHLC from all prints,
                            # even when aggression cannot be classified.
                            elephant_signal=None
                            if msg.get("ev")=="T" and str(msg.get("sym","")) in symbols:
                                try:
                                    raw_trade={"symbol":str(msg["sym"]),
                                        "timestamp":int(msg["t"]),"price":float(msg["p"]),
                                        "size":float(msg["s"]),
                                        "side":item["side"] if item else None,
                                        "method":item.get("method") if item else None,
                                        "trade_id":msg.get("q")}
                                    elephant_signal=elephant_engine.on_trade(raw_trade)
                                    candle_events=candle_engine.on_trade(raw_trade)
                                    for candle_event in candle_events:
                                        print('Candle state transition: '+json.dumps(candle_event,ensure_ascii=False),flush=True)
                                        for _,contract,q in tuple(clients):
                                            if contract==raw_trade['symbol'] and not q.full():q.put_nowait(candle_event)
                                        if candle_event['stage']=='GATILHO_CONFIRMADO':
                                            signal_engine.pending[raw_trade['symbol']].append({'event':candle_event,'high':raw_trade['price'],'low':raw_trade['price'],'last_ts':raw_trade['timestamp'],'completed':set()})
                                            print('Candle flow trigger: %s %s %ss delta5s=%s' % (raw_trade['symbol'],candle_event['model'],candle_event['timeframe_seconds'],candle_event['delta_5s']),flush=True)
                                            if event_in_session(candle_event['timestamp']):
                                                asyncio.create_task(push_alerts.deliver(candle_push_payload(candle_event)))
                                    if raw_trade['timestamp']-candle_published.get(raw_trade['symbol'],0)>=1000:
                                        candle_published[raw_trade['symbol']]=raw_trade['timestamp']
                                        state=candle_engine.snapshot(raw_trade['symbol'])
                                        for _,contract,q in tuple(clients):
                                            if contract==raw_trade['symbol'] and not q.full():q.put_nowait(state)
                                except (KeyError,ValueError,TypeError):pass
                            if item:
                                replay[item["symbol"]].append(dict(item))
                                feed_health["last_classified_ms"]=item["timestamp"]
                                contract_health[item["symbol"]]["classified_ms"]=item["timestamp"]
                                # Radar direction remains context; candles own entry pushes.
                                radar_push_engine.on_trade(item)
                                post_events=post_monitor.on_trade(item)
                                absorption_observation=absorption_research.on_trade(item)
                                if absorption_observation:
                                    print('Independent absorption research: %s %s share=%s range_ticks=%s' % (item['symbol'],absorption_observation['side'],absorption_observation['aggressor_share'],absorption_observation['local_range_ticks']),flush=True)
                                wave_events=wave_research.on_trade(item,treasury_fresh=False)
                                for research_event in wave_events:
                                    if research_event['type']=='wave_research':
                                        print('Wave research: %s %s short=%s prev2m=%s valid2m=%s share=%s status=%s blockers=%s' % (research_event['symbol'],research_event['side'],research_event['short_breakout'],research_event['previous_2m_breakout'],research_event['previous_2m_valid'],','.join(str(w['share']) for w in research_event['waves']),research_event['status'],','.join(research_event['blockers'])),flush=True)
                                    else:
                                        print('Wave research outcome: %s %ss signed=%s gap=%s' % (research_event['symbol'],research_event['horizon_seconds'],research_event['signed_move'],research_event['data_gap']),flush=True)
                                server_signal=signal_engine.on_trade(item)
                                structure_signal=structure_engine.on_trade(item)
                                for watch_event in post_events:
                                    print('Post-signal diagnostic: %s %s' % (watch_event['symbol'],watch_event['stage']),flush=True)
                                    if event_in_session(watch_event['timestamp']):
                                        asyncio.create_task(push_alerts.deliver({'title':'SPARK AI · ALERTA DE FLUXO · '+watch_event['symbol'],'body':'Possível reversão ou absorção detectada; confira o painel antes de decidir.','tag':'post-'+watch_event['symbol']+'-'+str(watch_event['signal_timestamp']),'timestamp':watch_event['timestamp'],'url':'./index.html'}))
                                        for _,contract,q in tuple(clients):
                                            if contract==watch_event['symbol'] and not q.full():q.put_nowait(watch_event)
                                for outcome in signal_engine.drain_updates():
                                    print("Server outcome: %s %ss signed=%s favorable=%s adverse=%s gap=%s" % (outcome["symbol"],outcome["horizon_seconds"],outcome["signed_move"],outcome["favorable_excursion"],outcome["adverse_excursion"],outcome["data_gap"]),flush=True)
                                    for _,contract,q in tuple(clients):
                                        if contract==outcome["symbol"] and not q.full():q.put_nowait(outcome)
                                if server_signal:
                                    post_monitor.register(server_signal)
                                    print("Server flow diagnostic: %s %s ratio=%s clients=%d" % (server_signal["symbol"],server_signal["side"],server_signal["ratio"],len(clients)),flush=True)
                                    if event_in_session(server_signal["timestamp"]):
                                        pass # Legacy model A: diagnostic history only.
                                        for _,contract,q in tuple(clients):
                                            if contract==server_signal["symbol"] and not q.full():q.put_nowait(server_signal)
                                if structure_signal:
                                    post_monitor.register(structure_signal)
                                    signal_engine.alerts[item["symbol"]].append(structure_signal)
                                    signal_engine.pending[item["symbol"]].append({"event":structure_signal,"high":item["price"],"low":item["price"],"last_ts":item["timestamp"],"completed":set()})
                                    print("Model B structure diagnostic: %s %s ratio=%s" % (item["symbol"],structure_signal["side"],structure_signal["ratio"]),flush=True)
                                    if event_in_session(structure_signal["timestamp"]):
                                        pass # Legacy model B: diagnostic history only.
                                        for _,contract,q in tuple(clients):
                                            if contract==structure_signal["symbol"] and not q.full():q.put_nowait(structure_signal)
                                if elephant_signal:
                                    post_monitor.register(elephant_signal)
                                    signal_engine.alerts[item["symbol"]].append(elephant_signal)
                                    signal_engine.pending[item["symbol"]].append({"event":elephant_signal,"high":item["price"],"low":item["price"],"last_ts":item["timestamp"],"completed":set()})
                                    print("Model C Elephant diagnostic: %s %s ratio=%s" % (item["symbol"],elephant_signal["side"],elephant_signal["ratio"]),flush=True)
                                    if event_in_session(elephant_signal["timestamp"]):
                                        pass # Elephant: optional context, not a separate entry banner.
                                        for _,contract,q in tuple(clients):
                                            if contract==elephant_signal["symbol"] and not q.full():q.put_nowait(elephant_signal)
                                counts["classified"]+=1
                                counts["classified."+item["symbol"]]+=1
                            if time.monotonic()-last_report>=30:
                                print("Provider 30s diagnostics: trades=%d quotes=%d classified=%d clients=%d samples=%s" %(counts["T"],counts["Q"],counts["classified"],len(clients),str(getattr(classifier,"recent",{}).get(symbols[0],[]) and list(classifier.recent[symbols[0]])[-1].get("timestamp","none"))),flush=True)
                                now_ms=int(time.time()*1000)
                                print("Transport 30s: "+json.dumps({sym:{"market_age_ms":now_ms-max(v["quote_ms"],v["trade_ms"]),"provider_lag_ms":v["lag_ms"],"trade_age_ms":now_ms-v["trade_ms"] if v["trade_ms"] else None} for sym,v in contract_health.items()}),flush=True)
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
                                            disconnect_slow(client,sym,queue)
                                        else:queue.put_nowait(outgoing)
                    retry=15
            except (OSError,websockets.exceptions.WebSocketException,RuntimeError,ValueError) as exc:
                feed_health["provider_connected"]=False
                print("Massive stream disconnected: %s code=%s reason=%s" % (type(exc).__name__,getattr(exc,"code",getattr(getattr(exc,"rcvd",None),"code","n/a")),str(getattr(exc,"reason",getattr(getattr(exc,"rcvd",None),"reason","")))[:120]),flush=True)
                # Keep browser WebSockets open: health_loop will report STALE until provider recovers.
                # Provider connection limits can be caused by overlapping deployments or other clients.
                # Avoid quickly competing for an already occupied account connection slot.
                if connection_limited:
                    retry=max(retry,120)
                await asyncio.sleep(retry)
                retry=min(retry*2,300 if connection_limited else 60)
    async with websockets.serve(browser,"0.0.0.0",int(os.getenv("FLOW_BRIDGE_PORT","8765")),max_size=10000,ping_interval=60,ping_timeout=60):
        print("Private Flow bridge running on port %s; TLS reverse proxy required" % os.getenv("FLOW_BRIDGE_PORT","8765"),flush=True)
        watchdog=asyncio.create_task(health_loop())
        equities=asyncio.create_task(equities_provider())
        try:await provider()
        finally:
            watchdog.cancel();equities.cancel()
            await asyncio.gather(watchdog,equities,return_exceptions=True)
if __name__=="__main__":asyncio.run(main())


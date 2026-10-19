"""Opt-in Web Push subscriptions and delivery (ephemeral until persistent storage is added)."""
import asyncio,base64,json,os,time
from pathlib import Path
from urllib.parse import urlparse
from pywebpush import webpush,WebPushException

PUBLIC_KEY=os.getenv("FLOW_VAPID_PUBLIC_KEY","")
PRIVATE_B64=os.getenv("FLOW_VAPID_PRIVATE_PEM_B64","")
SUBSCRIPTIONS={}
STORAGE=Path(os.getenv("FLOW_PUSH_STORAGE_PATH","/data/push_subscriptions.json"))
def load_subscriptions():
    try:
        data=json.loads(STORAGE.read_text())
        if isinstance(data,dict):
            for endpoint,entry in data.items():
                if isinstance(entry,dict) and isinstance(entry.get("keys"),dict) and endpoint.startswith("https://"):
                    SUBSCRIPTIONS[endpoint]=entry
    except (OSError,ValueError,TypeError):pass
def save_subscriptions():
    try:
        STORAGE.parent.mkdir(parents=True,exist_ok=True)
        temp=STORAGE.with_suffix(".tmp")
        temp.write_text(json.dumps(SUBSCRIPTIONS))
        os.chmod(temp,0o600)
        os.replace(temp,STORAGE)
    except OSError as exc:
        print("Push storage write failure: "+type(exc).__name__,flush=True)
        raise RuntimeError("Push registration cannot be persisted") from exc
load_subscriptions()
def enabled():return bool(PUBLIC_KEY and PRIVATE_B64)
def add(subscription):
    if not enabled():raise ValueError("Push not configured")
    if not isinstance(subscription,dict):raise ValueError("Invalid subscription")
    endpoint=subscription.get("endpoint","")
    url=urlparse(endpoint)
    if url.scheme!="https" or not url.netloc or len(endpoint)>2500 or not url.hostname:raise ValueError("Invalid endpoint")
    # Restrict outgoing requests to recognized Apple, Google, Mozilla and Microsoft Web Push servers.
    host=url.hostname.lower()
    allowed=("push.apple.com","push.services.mozilla.com","fcm.googleapis.com","updates.push.services.mozilla.com","notify.windows.com")
    if not any(host==x or host.endswith("."+x) for x in allowed):raise ValueError("Unsupported push provider")
    keys=subscription.get("keys") or {}
    if not all(isinstance(keys.get(k),str) and 15<=len(keys[k])<=200 for k in ("p256dh","auth")):raise ValueError("Invalid encryption keys")
    SUBSCRIPTIONS[endpoint]={"endpoint":endpoint,"keys":{"p256dh":keys["p256dh"],"auth":keys["auth"]},"added":time.time()}
    if len(SUBSCRIPTIONS)>20:
        oldest=min(SUBSCRIPTIONS,key=lambda e:SUBSCRIPTIONS[e]["added"])
        SUBSCRIPTIONS.pop(oldest,None)
    save_subscriptions()
def _send(subscription,payload):
    private=base64.b64decode(PRIVATE_B64).decode()
    webpush(subscription_info=subscription,data=json.dumps(payload),vapid_private_key=private,vapid_claims={"sub":"https://github.com/caskesties/Flow-ai-terminal"},ttl=20)
async def deliver(payload):
    if not enabled():return
    for endpoint,subscription in list(SUBSCRIPTIONS.items()):
        try:await asyncio.to_thread(_send,subscription,payload)
        except WebPushException as e:
            if getattr(getattr(e,"response",None),"status_code",None) in (404,410):
                SUBSCRIPTIONS.pop(endpoint,None)
                save_subscriptions()
            else:print("Push delivery failure: "+str(type(e).__name__),flush=True)
        except Exception as e:print("Push delivery failure: "+str(type(e).__name__),flush=True)
def payload_for_signal(event):
    direction="COMPRA" if event["side"]=="buy" else "VENDA"
    price=event["price"]
    strength=min(99,max(1,round(event["directional_share"]*100)))
    return {"title":f"FLOW · POSSÍVEL {direction} · {event['symbol']}",
        "body":f"Pressão experimental · preço {price:.2f} · força {strength}/100 · {event['ratio']:.1f}×",
        "tag":f"{event['symbol']}-{event['timestamp']}","timestamp":event["timestamp"],"url":"./index.html"}

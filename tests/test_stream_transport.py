"""Exercise the real bridge with a local, synthetic Massive stream (no credentials)."""
import asyncio
import importlib
import json
from pathlib import Path
import socket
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
# Push transport isn't exercised in these feed tests.
sys.modules.setdefault('pywebpush', types.SimpleNamespace(webpush=lambda *a, **k: None, WebPushException=Exception))
import massive_bridge as bridge
import websockets


class TransportTest(unittest.IsolatedAsyncioTestCase):
    async def test_health_is_contract_specific_and_delivery_continues(self):
        events = asyncio.Queue()
        real_connect = websockets.connect
        class Provider:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def send(self, value): pass
            def __aiter__(self): return self
            async def __anext__(self): return json.dumps(await events.get())
        def connect(uri, **kwargs):
            return Provider() if 'socket.massive.com' in uri else real_connect(uri, **kwargs)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = {'MASSIVE_API_KEY': 'synthetic', 'FLOW_BRIDGE_TOKEN': 't'*24,
               'FLOW_BRIDGE_PORT': str(port), 'MASSIVE_SYMBOLS': 'MNQZ6,GCZ6'}
        with patch.dict('os.environ', env), patch.object(websockets, 'connect', connect):
            task = asyncio.create_task(bridge.main())
            try:
                for _ in range(100):
                    try:
                        ws = await real_connect(f'ws://127.0.0.1:{port}'); break
                    except OSError: await asyncio.sleep(.01)
                else: self.fail('bridge did not start')
                async with ws:
                    await ws.send(json.dumps({'token': 't'*24, 'symbol': 'MNQZ6'}))
                    self.assertEqual(json.loads(await ws.recv())['transport_version'], bridge.TRANSPORT_VERSION)
                    await events.put({'ev':'status','status':'auth_success'})
                    async def health():
                        while True:
                            frame = json.loads(await asyncio.wait_for(ws.recv(), 3))
                            for event in frame if isinstance(frame, list) else [frame]:
                                if event.get('type') == 'feed_health': return event
                    now = int(bridge.time.time()*1000)
                    await events.put({'ev':'Q','sym':'GCZ6','t':now,'bp':100,'ap':101})
                    h = await health()
                    self.assertEqual(h['status'], 'STALE')  # GC cannot make MNQ look live.
                    now = int(bridge.time.time()*1000)
                    await events.put({'ev':'Q','sym':'MNQZ6','t':now,'bp':100,'ap':101})
                    h = await health()
                    self.assertEqual(h['status'], 'LIVE')
                    self.assertEqual(h['last_classified_ms'], 0)  # no fabricated delta
                    self.assertLess(abs(h['provider_lag_ms']), 1000)
                    await events.put({'ev':'Q','sym':'MNQZ6','t':int(bridge.time.time()*1000),'bp':100,'ap':101})
                    await events.put({'ev':'T','sym':'MNQZ6','t':int(bridge.time.time()*1000),'p':101,'s':2,'q':1})
                    while True:
                        frame=json.loads(await asyncio.wait_for(ws.recv(),3))
                        trades=[e for e in (frame if isinstance(frame,list) else [frame]) if e.get('side')=='buy']
                        if trades:
                            self.assertEqual(trades[0]['size'],2);break
            finally:
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass

    async def test_slow_close_does_not_block_ingest(self):
        import ast
        tree=ast.parse(Path(bridge.__file__).read_text())
        main=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='main')
        node=next(n for n in main.body if isinstance(n,ast.FunctionDef) and n.name=='disconnect_slow')
        closed=asyncio.Event()
        class Client:
            async def close(self, **kwargs): await closed.wait()
        client=Client(); q=asyncio.Queue(); clients={(client,'MNQZ6',q)}
        namespace={'asyncio':asyncio,'clients':clients,'close_tasks':set()}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'close-test','exec'),namespace)
        namespace['disconnect_slow'](client,'MNQZ6',q)
        self.assertFalse(clients)
        self.assertEqual(len(namespace['close_tasks']),1)
        closed.set()
        await asyncio.gather(*namespace['close_tasks'])

if __name__=='__main__': unittest.main()

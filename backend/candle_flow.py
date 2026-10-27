"""Event-time 2m/5m candles and experimental, staged flow setups.

All prints form OHLC/volume; only classified prints form delta. No orders.
Thresholds are provisional and exposed here for replay calibration.
"""
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from math import isfinite
from statistics import median
import time


@dataclass
class Candle:
    start: int
    period: int
    open: float
    high: float
    low: float
    close: float
    first: int
    last: int
    volume: float = 0
    buy: float = 0
    sell: float = 0
    bbo_volume: float = 0
    count: int = 0
    max_gap: int = 0

    def add(self, t):
        self.max_gap = max(self.max_gap, t['timestamp'] - self.last)
        self.last = t['timestamp']
        self.high = max(self.high, t['price'])
        self.low = min(self.low, t['price'])
        self.close = t['price']
        self.volume += t['size']
        self.count += 1
        if t.get('side') in ('buy', 'sell'):
            setattr(self, t['side'], getattr(self, t['side']) + t['size'])
            if t.get('method') == 'bbo':
                self.bbo_volume += t['size']

    @property
    def complete(self):
        return (self.first - self.start <= 2000 and
                self.last >= self.start + self.period - 2000 and
                self.max_gap <= 3000 and self.count >= 15)

    @property
    def quality(self):
        return (self.volume > 0 and (self.buy + self.sell) / self.volume >= .80
                and self.bbo_volume / self.volume >= .70)

    def snapshot(self):
        return dict(asdict(self), delta=self.buy-self.sell,
                    body=abs(self.close-self.open),
                    upper_wick=self.high-max(self.open,self.close),
                    lower_wick=min(self.open,self.close)-self.low,
                    classified_fraction=(self.buy+self.sell)/self.volume if self.volume else 0,
                    bbo_fraction=self.bbo_volume/self.volume if self.volume else 0,
                    complete=self.complete, quality=self.quality)


class CandleFlowEngine:
    VERSION = 'candles-20261026-v2'
    MIN_AGGRESSOR_SHARE = .57

    def __init__(self, clock=None):
        self.clock = clock or (lambda: int(time.time()*1000))
        self.current = {}
        self.closed = defaultdict(lambda: deque(maxlen=24))
        self.recent = defaultdict(deque)
        self.last_ts = {}
        self.last_seq = {}
        self.setups = {}
        self.latest = {}
        self.evaluated = {}
        self.stats = defaultdict(int)
        self.blockers = {}

    @staticmethod
    def tick(symbol):
        if symbol.startswith(('MNQ','NQ')): return .25
        if symbol.startswith(('MGC','GC')): return .1
        return None

    @staticmethod
    def flow(rows):
        volume = sum(t['size'] for t in rows)
        buy = sum(t['size'] for t in rows if t.get('side') == 'buy')
        sell = sum(t['size'] for t in rows if t.get('side') == 'sell')
        bbo = sum(t['size'] for t in rows if t.get('side') in ('buy','sell') and t.get('method') == 'bbo')
        return volume, buy-sell, (buy+sell)/volume if volume else 0, bbo/volume if volume else 0

    def _event(self, key, setup, stage, t, reason):
        event = dict(type='candle_signal', version=self.VERSION, symbol=key[0],
                     timeframe_seconds=key[1]//1000, model=setup['model'], stage=stage,
                     side=setup['side'], timestamp=t['timestamp'], price=t['price'],
                     level=setup['level'], trigger=setup['trigger'],
                     invalidation=setup['invalidation'], reason=reason,
                     setup_id=setup['id'], classification='estimated', experimental=True)
        recent = [x for x in self.recent[key[0]] if x['timestamp'] >= t['timestamp']-5000]
        volume, delta, coverage, bbo = self.flow(recent)
        event.update(delta_5s=delta, classified_fraction=coverage, bbo_fraction=bbo,
                     directional_share=(1+abs(delta)/(volume*coverage))/2 if volume and coverage else 0,
                     minimum_aggressor_share=self.MIN_AGGRESSOR_SHARE)
        self.latest[key] = event
        return event

    def _context(self, key):
        bars = list(self.closed[key])[-3:]
        if len(bars) != 3 or any(not b.complete or not b.quality for b in bars): return None
        if any(bars[i].start-bars[i-1].start != key[1] for i in (1,2)): return None
        return bars

    def on_trade(self, raw):
        try:
            t = dict(raw, timestamp=int(raw['timestamp']),price=float(raw['price']),size=float(raw['size']))
            sym = t['symbol']; tick = self.tick(sym)
            if tick is None or not all(isfinite(t[k]) and t[k]>0 for k in ('price','size')): return []
            age = self.clock()-t['timestamp']
            if age < -1000 or age > 3000:
                self.stats['stale_rejected'] += 1
                return []
        except (KeyError,TypeError,ValueError,OverflowError): return []
        ts = t['timestamp']
        if ts < self.last_ts.get(sym,ts):
            self.stats['out_of_order_rejected'] += 1
            return []
        seq = t.get('trade_id')
        if seq is not None:
            try: seq = int(seq)
            except (ValueError,TypeError): return []
            if seq <= self.last_seq.get(sym,-1): return []
            self.last_seq[sym] = seq
        gap = ts-self.last_ts.get(sym,ts)
        self.last_ts[sym] = ts
        rows = self.recent[sym]
        rows.append(t)
        while rows and ts-rows[0]['timestamp'] > 45000: rows.popleft()
        # Bounded memory: overflow blocks warmup instead of truncating silently.
        if len(rows)>100000:
            rows.clear(); self.reset(sym); self.stats['overflow'] += 1
            return []
        events = []
        for period in (120000,300000):
            key = (sym,period); start = ts//period*period
            b = self.current.get(key)
            setup = self.setups.get(key)
            if gap>3000 and setup:
                events.append(self._event(key,setup,'INVALIDADO',t,'Lacuna nos negócios; aguardar nova formação.'))
                self.setups.pop(key,None)
            if b is None or start!=b.start:
                if b:
                    events.extend(self._close(key,b,t,tick))
                    self.closed[key].append(b)
                b = Candle(start,period,t['price'],t['price'],t['price'],t['price'],ts,ts)
                self.current[key] = b
            b.add(t)
            # Trigger, expiry and invalidation evaluated for EVERY raw print.
            events.extend(self._advance(key,b,t,tick))
            # Formation scans are bounded to 4Hz; candle OHLC never drops prints.
            if ts-self.evaluated.get(key,-1000)>=250:
                self.evaluated[key] = ts
                events.extend(self._observe(key,b,t,tick))
        return events

    def reset(self, sym):
        for key in [k for k in self.current if k[0]==sym]:
            self.current.pop(key,None); self.closed.pop(key,None)
            self.setups.pop(key,None); self.latest.pop(key,None)
        self.recent.pop(sym,None)

    def _blocked(self,key,reason):
        self.blockers[key]=reason
        return []

    def _observe(self,key,b,t,tick):
        if key in self.setups: return []
        self.blockers[key] = 'NO_ABSORPTION_PATTERN'
        prior = self._context(key)
        if not prior:
            bars=list(self.closed[key])[-3:]
            reason='WARMUP' if len(bars)<3 else 'CONTEXT_GAPS' if any(not x.complete for x in bars) else 'CONTEXT_CLASSIFICATION'
            return self._blocked(key,reason)
        if b.first-b.start>2000 or b.max_gap>3000: return self._blocked(key,'CURRENT_GAPS')
        ts = t['timestamp']; rows = list(self.recent[key[0]])
        sample = [x for x in rows if x['timestamp'] >= ts-15000]
        baseline = [x for x in rows if ts-45000<=x['timestamp']<ts-15000]
        if len(sample)<10 or sample[-1]['timestamp']-sample[0]['timestamp']<10000: return self._blocked(key,'SAMPLE_TOO_SHORT')
        if len(baseline)<10 or baseline[-1]['timestamp']-baseline[0]['timestamp']<20000: return self._blocked(key,'BASELINE_TOO_SHORT')
        volume,delta,coverage,bbo = self.flow(sample)
        if volume<40: return self._blocked(key,'LOW_VOLUME')
        if coverage<.8 or bbo<.7: return self._blocked(key,'SAMPLE_CLASSIFICATION')
        if (1+abs(delta)/(volume*coverage))/2<=self.MIN_AGGRESSOR_SHARE: return self._blocked(key,'LOW_DOMINANCE')
        # Actual total activity, independent of delta share. Provisional 1.3x.
        if volume/15 < sum(x['size'] for x in baseline)/30*1.3: return self._blocked(key,'LOW_ACTIVITY')
        side = 'buy' if delta<0 else 'sell'
        sign = 1 if side=='buy' else -1
        level = min(x.low for x in prior) if side=='buy' else max(x.high for x in prior)
        span = max(x['price'] for x in sample)-min(x['price'] for x in sample)
        # Adaptive but capped amplitude; first-to-last stall alone is insufficient.
        cap = max(3*tick,min(12*tick,median(x.high-x.low for x in prior)*.10))
        if span>cap+1e-8 or abs(sample[-1]['price']-sample[0]['price'])>3*tick+1e-8: return self._blocked(key,'PRICE_NOT_STALLED')
        if abs(t['price']-level)>3*tick+1e-8: return self._blocked(key,'AWAY_FROM_LEVEL')
        setup = dict(id=f'{key[0]}:{key[1]}:{ts}:ABS',model='ABSORCAO',side=side,
                     level=level,trigger=b.high+tick if sign==1 else b.low-tick,
                     invalidation=min(b.low,level)-tick if sign==1 else max(b.high,level)+tick,
                     born=ts,bar_start=b.start,ready=False,expires=b.start+3*key[1])
        self.blockers[key] = None
        self.setups[key] = setup
        return [self._event(key,setup,'EM_FORMACAO',t,'Agressão contrária com amplitude limitada junto ao nível; aguardar fechamento e reação.')]

    def _close(self,key,b,t,tick):
        events = []; setup = self.setups.get(key)
        if setup and b.start>=setup['bar_start'] and not setup['ready']:
            span = b.high-b.low
            pos = (b.close-b.low)/span if span>0 else .5
            sign = 1 if setup['side']=='buy' else -1
            wick = min(b.open,b.close)-b.low if sign==1 else b.high-max(b.open,b.close)
            if not b.complete or not b.quality or t['timestamp']-b.last>3000:
                events.append(self._event(key,setup,'INVALIDADO',t,'Candle incompleto ou classificação insuficiente.'))
                self.setups.pop(key,None)
            elif setup['model']=='ABSORCAO' and b.start==setup['bar_start']:
                rejected = span>0 and wick/span>=.25 and (pos>=.60 if sign==1 else pos<=.40)
                if rejected:
                    setup.update(ready=True,trigger=b.high+tick if sign==1 else b.low-tick,
                                 invalidation=b.low-tick if sign==1 else b.high+tick)
                    events.append(self._event(key,setup,'REJEICAO_CONFIRMADA',t,'Candle fechado rejeitou o extremo; entrada ainda depende do gatilho e delta recente.'))
                else:
                    events.append(self._event(key,setup,'INVALIDADO',t,'Fechamento não confirmou rejeição da região.'))
                    self.setups.pop(key,None)
            elif setup['model']=='ROMPIMENTO_RETESTE' and setup.get('retest_start')==b.start:
                held = b.close>setup['level'] if sign==1 else b.close<setup['level']
                if held:
                    setup.update(ready=True,trigger=b.high+tick if sign==1 else b.low-tick,
                                 invalidation=b.low-tick if sign==1 else b.high+tick)
                    events.append(self._event(key,setup,'RETESTE_CONFIRMADO',t,'Reteste fechado sustentou o nível; aguardar retomada com delta alinhado.'))
                else:
                    events.append(self._event(key,setup,'INVALIDADO',t,'Reteste fechou do lado contrário do nível.'))
                    self.setups.pop(key,None)
        if key in self.setups: return events
        prior = self._context(key)
        if not prior or not b.complete or not b.quality or t['timestamp']-b.last>3000: return events
        if b.start-prior[-1].start!=key[1]: return events
        span = b.high-b.low; classified = b.buy+b.sell
        if span<=0 or classified<=0 or abs(b.close-b.open)/span<.5: return events
        side = 'buy' if b.close>b.open else 'sell'
        sign = 1 if side=='buy' else -1
        delta = b.buy-b.sell
        if sign*delta<=0 or (b.buy if sign==1 else b.sell)/classified<=self.MIN_AGGRESSOR_SHARE: return events
        if b.volume < median(x.volume for x in prior)*1.3: return events
        level = max(x.high for x in prior) if sign==1 else min(x.low for x in prior)
        if sign*(b.close-level)<tick-1e-8: return events
        setup = dict(id=f'{key[0]}:{key[1]}:{b.start}:RET',model='ROMPIMENTO_RETESTE',
                     side=side,level=level,trigger=b.high+tick if sign==1 else b.low-tick,
                     invalidation=level-sign*3*tick,born=t['timestamp'],bar_start=b.start,
                     ready=False,expires=b.start+4*key[1])
        self.setups[key] = setup
        events.append(self._event(key,setup,'AGUARDAR_RETESTE',t,'Rompimento fechado com volume e delta alinhados; aguardar retorno ao nível.'))
        return events

    def _advance(self,key,b,t,tick):
        s = self.setups.get(key)
        if not s: return []
        ts = t['timestamp']; px = t['price']; sign = 1 if s['side']=='buy' else -1
        reason = None
        if ts>=s['expires']: reason='Prazo do padrão encerrado.'
        elif sign*(px-s['invalidation'])<=0: reason='Preço perdeu a região de invalidação.'
        if reason:
            self.setups.pop(key,None)
            return [self._event(key,s,'EXPIRADO' if ts>=s['expires'] else 'INVALIDADO',t,reason)]
        if s.get('triggered'): return []
        if s['model']=='ROMPIMENTO_RETESTE' and not s['ready'] and 'retest_start' not in s:
            if ts>s['born'] and abs(px-s['level'])<=2*tick+1e-8:
                s['retest_start']=b.start
                return [self._event(key,s,'RETESTE_EM_FORMACAO',t,'Preço voltou ao nível; aguardar sustentação no fechamento.')]
        if not s['ready']: return []
        # No chasing: trigger must be crossed now, not reached with opposite
        # flow and reused later after price has moved far away.
        previous = s.get('last_price', b.open)
        s['last_price'] = px
        if sign*(px-s['trigger'])< -1e-8: return []
        if sign*(previous-s['trigger'])>=0 or sign*(px-s['trigger'])>2*tick: return []
        recent = [x for x in self.recent[key[0]] if x['timestamp']>=ts-5000]
        volume,delta,coverage,bbo = self.flow(recent)
        if len(recent)<5 or volume<20 or coverage<.8 or bbo<.7: return []
        if (1+sign*delta/(volume*coverage))/2<=self.MIN_AGGRESSOR_SHARE or sign*(px-recent[0]['price'])<=0: return []
        if max((recent[i]['timestamp']-recent[i-1]['timestamp'] for i in range(1,len(recent))),default=0)>3000: return []
        event=self._event(key,s,'GATILHO_CONFIRMADO',t,'Preço rompeu a reação com delta recente na mesma direção; sinal experimental, sem execução.')
        event['candle']=b.snapshot()
        s['triggered']=True
        return [event]

    def snapshot(self,symbol):
        return dict(type='candle_state',version=self.VERSION,symbol=symbol,
                    timestamp=self.last_ts.get(symbol,0),
                    candles=[dict(b.snapshot(),timeframe_seconds=k[1]//1000,
                                  warming_up=len(self.closed[k])<3,
                                  context_ready=self._context(k) is not None,
                                  context_bars=len(list(self.closed[k])[-3:]),
                                  context_complete=sum(x.complete for x in list(self.closed[k])[-3:]),
                                  context_quality=sum(x.quality for x in list(self.closed[k])[-3:]),
                                  formation_blocker=self.blockers.get(k,'WARMUP'))
                             for k,b in self.current.items() if k[0]==symbol],
                    setups=[e for k,e in self.latest.items() if k[0]==symbol])


def push_payload(event):
    side='COMPRA' if event['side']=='buy' else 'VENDA'
    return dict(title=f"SPARK AI · {event['model']} · {side}",
                body=f"Gatilho observado {event['price']:g}; invalida {event['invalidation']:g}. Delta alinhado. Experimental.",
                tag=event['setup_id'],timestamp=event['timestamp'],url='./index.html')


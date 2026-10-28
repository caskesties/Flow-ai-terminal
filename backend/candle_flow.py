"""Event-time 2m/5m candles and experimental, staged flow setups.

All prints form OHLC/volume; only classified prints form delta. No orders.
Thresholds are provisional and exposed here for replay calibration.
"""
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from math import isfinite
import time

MIN_BBO_COVERAGE = .57


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
                and self.bbo_volume / self.volume > MIN_BBO_COVERAGE)

    def snapshot(self):
        return dict(asdict(self), delta=self.buy-self.sell,
                    body=abs(self.close-self.open),
                    upper_wick=self.high-max(self.open,self.close),
                    lower_wick=min(self.open,self.close)-self.low,
                    classified_fraction=(self.buy+self.sell)/self.volume if self.volume else 0,
                    bbo_fraction=self.bbo_volume/self.volume if self.volume else 0,
                    complete=self.complete, quality=self.quality)


class CandleFlowEngine:
    VERSION = 'candles-20261028-v5'
    MIN_AGGRESSOR_SHARE = .54

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
                     minimum_aggressor_share=self.MIN_AGGRESSOR_SHARE,
                     minimum_bbo_coverage=MIN_BBO_COVERAGE)
        event.update(volume_weakening=setup.get('volume_weakening',False),
                     absorption_evidence=setup.get('absorption',False),
                     original_rate=setup.get('original_rate'),
                     reverse_rate=setup.get('reverse_rate'),
                     baseline_reverse_rate=setup.get('base_reverse'))
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
        if key[1] != 120000:
            return self._blocked(key,'CONTEXT_ONLY')
        return self._observe_live(key,b,t,tick)

    def _observe_live(self,key,b,t,tick):
        rows=[x for x in self.recent[key[0]] if x['timestamp']>=b.start]
        ts=t['timestamp']
        prior=[x for x in rows if ts-15000<=x['timestamp']<ts-5000]
        recent=[x for x in rows if x['timestamp']>=ts-5000]
        if b.max_gap>3000: return self._blocked(key,'CURRENT_GAPS')
        if len(prior)<5 or len(recent)<5 or prior[-1]['timestamp']-prior[0]['timestamp']<5000:
            return self._blocked(key,'SAMPLE_TOO_SHORT')
        baseline=[x for x in self.recent[key[0]] if ts-45000<=x['timestamp']<ts-15000]
        if len(baseline)<10 or baseline[-1]['timestamp']-baseline[0]['timestamp']<20000:
            return self._blocked(key,'BASELINE_TOO_SHORT')
        if any(baseline[i]['timestamp']-baseline[i-1]['timestamp']>3000 for i in range(1,len(baseline))):
            return self._blocked(key,'CONTEXT_GAPS')
        _,_,base_coverage,base_bbo=self.flow(baseline)
        if base_coverage<.8 or base_bbo<=MIN_BBO_COVERAGE:
            return self._blocked(key,'SAMPLE_CLASSIFICATION')
        volume,delta,coverage,bbo=self.flow(prior)
        if volume<20: return self._blocked(key,'LOW_VOLUME')
        if coverage<.8 or bbo<=MIN_BBO_COVERAGE: return self._blocked(key,'SAMPLE_CLASSIFICATION')
        if (1+abs(delta)/(volume*coverage))/2<self.MIN_AGGRESSOR_SHARE:
            return self._blocked(key,'LOW_DOMINANCE')
        sign=-1 if delta>0 else 1
        span=b.high-b.low
        wick=b.high-max(b.open,b.close) if sign<0 else min(b.open,b.close)-b.low
        displacement=(b.high-b.open) if sign<0 else (b.open-b.low)
        move=prior[-1]['price']-prior[0]['price']
        if span<=0 or displacement<3*tick or wick<max(2*tick,span*.25) or sign*move>=0:
            return self._blocked(key,'NO_REJECTION')
        original='buy' if sign<0 else 'sell'
        reverse='sell' if sign<0 else 'buy'
        original_rate=sum(x['size'] for x in prior if x.get('side')==original)/10
        base_original=sum(x['size'] for x in baseline if x.get('side')==original)/30
        base_reverse=sum(x['size'] for x in baseline if x.get('side')==reverse)/30
        first=[x for x in prior if x['timestamp']<ts-10000]
        last=[x for x in prior if x['timestamp']>=ts-10000]
        def efficiency(part):
            vol=sum(x['size'] for x in part if x.get('side')==original)
            return max(0,-sign*(part[-1]['price']-part[0]['price']))/vol if len(part)>1 and vol else 0
        absorption=(base_original>0 and original_rate>=base_original*1.3
                    and efficiency(first)>0 and efficiency(last)<=efficiency(first)*.5)
        recent_original=sum(x['size'] for x in recent if x.get('side')==original)/5
        if not absorption and recent_original>original_rate*.7:
            return self._blocked(key,'NO_VOLUME_REJECTION')
        side='buy' if sign>0 else 'sell' 
        setup=dict(id=f'{key[0]}:{key[1]}:{ts}:LIVE',model='ABSORCAO' if absorption else 'REJEICAO_FLUXO',side=side,
                   level=b.low if sign>0 else b.high,
                   trigger=max(x['price'] for x in recent)+tick if sign>0 else min(x['price'] for x in recent)-tick,
                   invalidation=b.low-tick if sign>0 else b.high+tick,
                   born=ts,bar_start=b.start,ready=False,live=True,
                   original_rate=original_rate,base_reverse=base_reverse,absorption=absorption,
                   expires=min(ts+30000,b.start+key[1]),last_price=t['price'])
        self.setups[key]=setup
        self.blockers[key]=None
        return [self._event(key,setup,'EM_FORMACAO',t,'Rejeição em formação; observar volume por segundo e virada da agressão ≥54%.')]

    def _close(self,key,b,t,tick):
        # Entry rules are exclusively live rejection/volume/flow; 5m is context.
        return []

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
        if s.get('live') and not s['ready']:
            recent=[x for x in self.recent[key[0]] if x['timestamp']>=ts-5000]
            volume,delta,coverage,bbo=self.flow(recent)
            reverse='buy' if sign>0 else 'sell'
            original='sell' if sign>0 else 'buy'
            reverse_rate=sum(x['size'] for x in recent if x.get('side')==reverse)/5
            original_rate=sum(x['size'] for x in recent if x.get('side')==original)/5
            weakening=original_rate<=s['original_rate']*.7
            participation=reverse_rate>s['base_reverse']
            s['volume_weakening']=weakening
            s['reverse_rate']=reverse_rate
            if (participation and (s['absorption'] or weakening) and len(recent)>=5 and volume>=20 and coverage>=.8 and bbo>MIN_BBO_COVERAGE
                and (1+sign*delta/(volume*coverage))/2>=self.MIN_AGGRESSOR_SHARE
                and sign*(px-recent[0]['price'])>0):
                s.update(ready=True,last_price=px,
                         trigger=max(x['price'] for x in recent)+tick if sign>0 else min(x['price'] for x in recent)-tick)
                return [self._event(key,s,'FLUXO_VIROU',t,'Rejeição com absorção ou queda ≥30% da agressão original; volume contrário acima da referência e participação ≥54%. Aguardar gatilho.')]
            return []
        if not s['ready']: return []
        # No chasing: trigger must be crossed now, not reached with opposite
        # flow and reused later after price has moved far away.
        previous = s.get('last_price', b.open)
        s['last_price'] = px
        if sign*(px-s['trigger'])< -1e-8: return []
        if sign*(previous-s['trigger'])>=0 or sign*(px-s['trigger'])>2*tick: return []
        recent = [x for x in self.recent[key[0]] if x['timestamp']>=ts-5000]
        volume,delta,coverage,bbo = self.flow(recent)
        if len(recent)<5 or volume<20 or coverage<.8 or bbo<=MIN_BBO_COVERAGE: return []
        if (1+sign*delta/(volume*coverage))/2<self.MIN_AGGRESSOR_SHARE or sign*(px-recent[0]['price'])<=0: return []
        if max((recent[i]['timestamp']-recent[i-1]['timestamp'] for i in range(1,len(recent))),default=0)>3000: return []
        if s.get('live'):
            reverse='buy' if sign>0 else 'sell'
            original='sell' if sign>0 else 'buy'
            if sum(x['size'] for x in recent if x.get('side')==reverse)/5<=s['base_reverse']: return []
            if not s['absorption'] and sum(x['size'] for x in recent if x.get('side')==original)/5>s['original_rate']*.7: return []
        event=self._event(key,s,'GATILHO_CONFIRMADO' ,t,'Preço rompeu a reação com delta recente na mesma direção; sinal experimental, sem execução.')
        event['candle']=b.snapshot()
        s['triggered']=True
        return [event]

    def snapshot(self,symbol):
        return dict(type='candle_state',version=self.VERSION,symbol=symbol,
                    timestamp=self.last_ts.get(symbol,0),
                    minimum_bbo_coverage=MIN_BBO_COVERAGE,
                    candles=[dict(b.snapshot(),timeframe_seconds=k[1]//1000,
                                  warming_up=(self.last_ts.get(symbol,0)-self.recent[symbol][0]['timestamp']<35000 if self.recent[symbol] else True),
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



import sys
from pathlib import Path
import unittest
from collections import deque
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from flow_classifier import FlowClassifier
from candle_flow import CandleFlowEngine,Candle

class ClassifierTimingTests(unittest.TestCase):
    def test_interleaved_quotes_use_causal_history(self):
        c=FlowClassifier()
        c.process(dict(ev='Q',sym='MNQZ6',t=1000,bp=100,ap=100.25))
        c.process(dict(ev='Q',sym='MNQZ6',t=1010,bp=100.25,ap=100.5))
        t=c.process(dict(ev='T',sym='MNQZ6',t=1005,p=100.25,s=2,q=1))
        self.assertEqual((t['side'],t['method']),('buy','bbo'))
        t=c.process(dict(ev='T',sym='MNQZ6',t=1006,p=100,s=2,q=2))
        self.assertEqual((t['side'],t['method']),('sell','bbo'))
    def test_never_uses_future_or_stale_quote(self):
        for quote_ts in (1010,1):
            c=FlowClassifier()
            c.process(dict(ev='Q',sym='MNQZ6',t=quote_ts,bp=100,ap=100.25))
            self.assertIsNone(c.process(dict(ev='T',sym='MNQZ6',t=1005 if quote_ts==1010 else 2000,p=100.25,s=2,q=1)))
    def test_quote_history_is_bounded_and_contracts_isolated(self):
        c=FlowClassifier()
        for ts in range(5000):c.process(dict(ev='Q',sym='MNQZ6',t=ts+1,bp=100,ap=101))
        self.assertLessEqual(len(c.quote_history['MNQZ6']),2001)
        self.assertIsNone(c.process(dict(ev='T',sym='GCZ6',t=5001,p=101,s=1,q=1)))

class RuleTests(unittest.TestCase):
    def setup_engine(self,buy=False):
        key=('MNQZ6',120000);e=CandleFlowEngine(clock=lambda:405000)
        # Mirror the sell setup to exercise symmetric buy rules.
        px=(lambda p:200-p) if buy else (lambda p:p)
        side=(lambda s:'sell' if s=='buy' else 'buy') if buy else (lambda s:s)
        for start in (0,120000,240000):
            e.closed[key].append(Candle(start,120000,px(99.75),max(px(99),px(100)),min(px(99),px(100)),px(99.75),start,start+119000,volume=100,buy=50,sell=50,bbo_volume=100,count=100,max_gap=1000))
        b=Candle(360000,120000,px(100),max(px(99.75),px(100.5)),min(px(99.75),px(100.5)),px(100),360000,405000,volume=100,buy=60,sell=40,bbo_volume=100,count=50,max_gap=1000)
        e.current[key]=b
        for i in range(46):
            e.recent[key[0]].append(dict(symbol=key[0],timestamp=360000+i*1000,price=px(100),size=1 if i<30 else 5,side=side('buy'),method='bbo'))
        t=dict(e.recent[key[0]][-1]);return e,key,b,t,px,side
    def test_absorption_then_reaction_and_entry_both_directions(self):
        for buy in (False,True):
            e,key,b,t,px,side=self.setup_engine(buy)
            events=e._observe(key,b,t,.25)
            self.assertEqual(events[0]['stage'],'EM_FORMACAO')
            self.assertEqual(events[0]['side'],'buy' if buy else 'sell')
            b.last=479000;b.close=px(99.75)
            t.update(timestamp=480000,price=px(99.75))
            self.assertEqual(e._close(key,b,t,.25)[0]['stage'],'REJEICAO_CONFIRMADA')
            b2=Candle(480000,120000,px(99.75),px(99.75),px(99.75),px(99.75),480000,480000)
            e.recent[key[0]]=deque(dict(t,timestamp=480000+i*500,price=px(99.75 if i<7 else 99.5),side=side('sell'),size=5,method='bbo') for i in range(8))
            t=dict(e.recent[key[0]][-1])
            events=e._advance(key,b2,t,.25)
            self.assertEqual(events[0]['stage'],'GATILHO_CONFIRMADO')
    def test_low_bbo_blocks_absorption_with_explicit_reason(self):
        e,key,b,t,_,_=self.setup_engine()
        for x in e.recent[key[0]]:x['method']='tick_rule'
        self.assertEqual(e._observe(key,b,t,.25),[])
        self.assertEqual(e.snapshot(key[0])['candles'][0]['formation_blocker'],'SAMPLE_CLASSIFICATION')
    def test_aggression_must_exceed_57_percent_of_classified_volume(self):
        # 80% coverage remains mandatory; unknown volume isn't assigned a side.
        for delta,expected in ((22.4,False),(24,True)):
            e,key,b,t,_,_=self.setup_engine()
            e.flow=lambda rows:(200,delta,.8,.7)
            events=e._observe(key,b,t,.25)
            self.assertEqual(bool(events),expected)
            if expected:self.assertAlmostEqual(events[0]['directional_share'],.575)

    def test_bbo_must_exceed_57_percent_in_candle_and_sample(self):
        for share,allowed in ((.56,False),(.57,False),(.58,True),(.60,True)):
            e,key,b,t,_,_=self.setup_engine()
            b.bbo_volume=b.volume*share
            self.assertEqual(b.quality,allowed)
            e.flow=lambda rows:(200,80,1,share)
            self.assertEqual(bool(e._observe(key,b,t,.25)),allowed)

    def test_bbo_must_exceed_57_percent_at_entry(self):
        for share,allowed in ((.57,False),(.58,True),(.60,True)):
            e,key,b,t,_,_=self.setup_engine()
            e._observe(key,b,t,.25)
            e.setups[key].update(ready=True,trigger=99.5)
            recent=[dict(t,timestamp=480000+i*500,price=99.75 if i<7 else 99.5,side='sell',size=5,method='bbo') for i in range(8)]
            e.recent[key[0]]=deque(recent)
            b2=Candle(480000,120000,99.75,99.75,99.5,99.5,480000,483500)
            e.flow=lambda rows:(200,-80,1,share)
            self.assertEqual(bool(e._advance(key,b2,recent[-1],.25)),allowed)

    def test_price_must_stall(self):
        e,key,b,t,_,_=self.setup_engine()
        e.recent[key[0]][-1]['price']=102;t['price']=102
        self.assertEqual(e._observe(key,b,t,.25),[])
        self.assertEqual(e.blockers[key],'PRICE_NOT_STALLED')
    def test_context_quality_block_is_not_reported_as_warmup(self):
        e,key,b,t,_,_=self.setup_engine()
        for old in e.closed[key]:old.bbo_volume=10
        self.assertEqual(e._observe(key,b,t,.25),[])
        state=e.snapshot(key[0])['candles'][0]
        self.assertFalse(state['warming_up']);self.assertFalse(state['context_ready'])
        self.assertEqual(state['formation_blocker'],'CONTEXT_CLASSIFICATION')

if __name__=='__main__':unittest.main()

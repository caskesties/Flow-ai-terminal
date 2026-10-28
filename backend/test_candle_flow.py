"""Synthetic flow scenarios; these do not measure profitability."""
import unittest
from candle_flow import CandleFlowEngine

class CandleFlowTests(unittest.TestCase):
    def setUp(self):
        self.now=1800000
        self.engine=CandleFlowEngine(clock=lambda:self.now)
        self.events=[]
    def trade(self,sec,px,size,side,method='bbo'):
        self.now=1800000+sec*1000
        result=self.engine.on_trade(dict(symbol='NQZ6',timestamp=self.now,price=px,size=size,side=side,method=method))
        self.events.extend(result)
        return result
    def scenario(self,mirror=False,weak=True,opposite=True,method='bbo',base=10):
        for sec in range(40):
            self.trade(sec,100,base,'buy',method)
            self.trade(sec,100,base,'sell',method)
        for sec in range(40,61):
            n=sec-40
            px=100+min(n,10)*.25-max(0,n-10)*.25
            if mirror:px=200-px
            original='sell' if mirror else 'buy'
            reverse='buy' if mirror else 'sell'
            self.trade(sec,px,2 if n>=15 and weak else 10,original,method)
            if n>=15 and opposite:self.trade(sec,px,20,reverse,method)
    def test_buy_and_sell_without_closed_context(self):
        for mirror in (False,True):
            self.setUp();self.scenario(mirror)
            hits=[e for e in self.events if e['stage']=='GATILHO_CONFIRMADO']
            self.assertTrue(hits)
            self.assertEqual(hits[0]['side'],'buy' if mirror else 'sell')
            self.assertTrue(all(e['timeframe_seconds']==120 for e in self.events))
            self.assertEqual(len(self.engine.closed[('NQZ6',120000)]),0)
    def test_absorption_does_not_require_volume_drop(self):
        self.scenario(weak=False,base=1)
        hits=[e for e in self.events if e['stage']=='GATILHO_CONFIRMADO']
        self.assertTrue(hits)
        self.assertTrue(hits[0]['absorption_evidence'])

    def test_without_absorption_or_weakening_no_entry(self):
        self.scenario(weak=False)
        self.assertFalse(any(e['stage']=='GATILHO_CONFIRMADO' for e in self.events))

    def test_no_opposite_volume_no_entry(self):
        self.scenario(opposite=False)
        self.assertFalse(any(e['stage']=='GATILHO_CONFIRMADO' for e in self.events))
    def test_percentage_without_increasing_opposite_volume_is_blocked(self):
        for sec in range(40):
            self.trade(sec,100,10,'buy');self.trade(sec,100,30,'sell')
        for sec in range(40,61):
            n=sec-40;px=100+min(n,10)*.25-max(0,n-10)*.25
            self.trade(sec,px,2 if n>=15 else 10,'buy')
            if n>=15:self.trade(sec,px,20,'sell')
        self.assertFalse(any(e['stage']=='GATILHO_CONFIRMADO' for e in self.events))
    def test_missing_classification_blocks(self):
        self.scenario(method='tick_rule')
        self.assertEqual(self.events,[])
    def test_no_baseline_no_signal(self):
        for sec in range(21):self.trade(sec,100+min(sec,10)*.25-max(0,sec-10)*.25,20,'buy' if sec<15 else 'sell')
        self.assertEqual(self.events,[])
    def test_stale_rejected(self):
        self.engine.on_trade(dict(symbol='NQZ6',timestamp=self.now-4000,price=100,size=1,side='buy'))
        self.assertEqual(self.engine.stats['stale_rejected'],1)
    def test_gap_invalidates(self):
        self.scenario(opposite=False)
        result=self.trade(65,100,20,'sell')
        self.assertTrue(any(e['stage']=='INVALIDADO' for e in result))
    def test_old_breakout_rules_are_removed(self):
        for sec in range(1000):self.trade(sec,100+sec*.25,10,'buy')
        self.assertFalse(any(e['model']=='ROMPIMENTO_RETESTE' for e in self.events))

if __name__=='__main__':unittest.main()

"""Synthetic scenario regressions, not a strategy profitability backtest."""
import unittest
from candle_flow import CandleFlowEngine


class CandleFlowTests(unittest.TestCase):
    def setUp(self):
        self.now=1800000
        self.engine=CandleFlowEngine(clock=lambda:self.now)
        self.events=[]

    def trade(self,second,price=100,size=1,side='buy',method='bbo',symbol='NQZ6',**extra):
        self.now=1800000+second*1000
        result=self.engine.on_trade(dict(symbol=symbol,timestamp=self.now,price=price,size=size,
                                         side=side,method=method,**extra))
        self.events.extend(result)
        return result

    def seed(self):
        for sec in range(360):
            px=101 if sec%120==30 else 99 if sec%120==60 else 100
            self.trade(sec,px,side='buy' if sec%2 else 'sell')

    def absorption(self,mirror=False):
        self.seed()
        for sec in range(360,480):
            px=101 if sec<380 else 99 if sec<460 else 100.5
            size=10 if 435<=sec<460 else 1
            side='sell' if sec<460 else 'buy'
            if mirror:px=200-px;side='buy' if side=='sell' else 'sell'
            self.trade(sec,px,size,side)
        self.trade(480,99.5 if mirror else 100.5,20,'sell' if mirror else 'buy')

    def test_event_time_2m_5m_and_unknown_volume(self):
        self.trade(0,100,3,'buy')
        self.trade(1,102,7,None,None)
        self.trade(2,99,2,'sell')
        for seconds in (120,300):
            b=self.engine.current[('NQZ6',seconds*1000)]
            self.assertEqual((b.open,b.high,b.low,b.close,b.volume,b.buy-b.sell),(100,102,99,99,12,1))
            self.assertFalse(b.quality)
        self.trade(120,101)
        self.assertEqual(len(self.engine.closed[('NQZ6',120000)]),1)
        self.assertEqual(len(self.engine.closed[('NQZ6',300000)]),0)
        self.assertFalse(self.engine.closed[('NQZ6',120000)][0].complete)

    def test_live_rejection_and_flow_flip_without_closed_context(self):
        for mirror in (False,True):
            self.setUp()
            for sec in range(21):
                px=100+min(sec,10)*.25-max(0,sec-10)*.25
                side='buy' if sec<15 else 'sell'
                if mirror: px=200-px;side='sell' if side=='buy' else 'buy'
                self.trade(sec,px,10,side)
            stages=[e['stage'] for e in self.events]
            self.assertIn('EM_FORMACAO',stages)
            self.assertIn('FLUXO_VIROU',stages)
            self.assertIn('GATILHO_CONFIRMADO',stages)
            hit=next(e for e in self.events if e['stage']=='GATILHO_CONFIRMADO')
            self.assertEqual(hit['side'],'buy' if mirror else 'sell')
            self.assertEqual(hit['timeframe_seconds'],120)
            self.assertEqual(len(self.engine.closed[('NQZ6',120000)]),0)

    def test_live_wick_without_flow_flip_has_no_entry(self):
        for sec in range(21):
            self.trade(sec,100+min(sec,10)*.25-max(0,sec-10)*.25,10,'buy')
        self.assertTrue(any(e['stage']=='EM_FORMACAO' for e in self.events))
        self.assertFalse(any(e['stage']=='GATILHO_CONFIRMADO' for e in self.events))

    def test_live_aggression_boundary_is_inclusive_54_percent(self):
        for share,expected in ((54,True),(53,False)):
            self.setUp()
            for sec in range(14):
                px=100+min(sec,10)*.25-max(0,sec-10)*.25
                self.trade(sec,px,share,'buy')
                self.trade(sec,px,100-share,'sell')
            self.assertEqual(any(e['stage']=='EM_FORMACAO' for e in self.events),expected)

    def test_absorption_to_buy_then_invalidation(self):
        self.absorption()
        self.assertIn('EM_FORMACAO',[e['stage'] for e in self.events])
        self.assertIn('REJEICAO_CONFIRMADA',[e['stage'] for e in self.events])
        for sec in range(481,487):self.trade(sec,100.5,20,'buy')
        self.trade(487,101.25,20,'buy')
        hits=[e for e in self.events if e['stage']=='GATILHO_CONFIRMADO']
        self.assertEqual(len(hits),1)
        self.assertEqual(hits[0]['side'],'buy')
        self.assertGreater(hits[0]['delta_5s'],0)
        self.trade(488,101.5,20,'buy')
        self.assertEqual(len([e for e in self.events if e['stage']=='GATILHO_CONFIRMADO']),1)
        events=self.trade(489,98.75,30,'sell')
        self.assertTrue(any(e['stage']=='INVALIDADO' for e in events))

    def test_absorption_mirrored_sell(self):
        self.absorption(mirror=True)
        for sec in range(481,487):self.trade(sec,99.5,20,'sell')
        self.trade(487,98.75,20,'sell')
        hits=[e for e in self.events if e['stage']=='GATILHO_CONFIRMADO']
        self.assertEqual(len(hits),1)
        self.assertEqual(hits[0]['side'],'sell')
        self.assertLess(hits[0]['delta_5s'],0)

    def test_opposite_delta_blocks_trigger_and_late_chase(self):
        self.absorption()
        for sec in range(481,487):self.trade(sec,100.5,20,'sell')
        self.trade(487,101.25,20,'sell')
        for sec in range(488,494):self.trade(sec,102,20,'buy')
        self.assertFalse(any(e['stage']=='GATILHO_CONFIRMADO' for e in self.events))

    def test_wide_round_trip_is_not_absorption(self):
        self.seed()
        for sec in range(360,400):self.trade(sec,100)
        for sec in range(400,430):self.trade(sec,99 if sec%2 else 105,10,'sell')
        self.assertFalse(any(e['stage']=='EM_FORMACAO' for e in self.events))

    def test_stale_out_of_order_duplicate_and_contract_isolation(self):
        self.trade(10,100,trade_id='1')
        self.trade(11,101,trade_id='1')
        self.now+=5000
        self.assertEqual(self.engine.on_trade(dict(symbol='NQZ6',timestamp=self.now-6000,price=99,size=1,side='sell')),[])
        self.trade(9,99,trade_id='2')
        self.trade(12,200,symbol='MNQZ6',trade_id='1')
        self.assertEqual(self.engine.current[('NQZ6',120000)].volume,1)
        self.assertEqual(self.engine.current[('MNQZ6',120000)].open,200)

    def test_gap_invalidates_pending_setup(self):
        self.absorption()
        events=self.trade(490,101.25,20,'buy')
        self.assertTrue(any(e['stage']=='INVALIDADO' for e in events))
        self.assertFalse(any(e['stage']=='GATILHO_CONFIRMADO' for e in events))

    def test_warmup_partial_candle_and_tick_rule_do_not_signal(self):
        for sec in range(10,500):self.trade(sec,99 if sec%2 else 100,10,'sell','tick_rule')
        self.assertEqual(self.events,[])

    def test_breakout_retest_continuation(self):
        self.seed()
        for sec in range(360,480):
            self.trade(sec,100 if sec<380 else 102 if sec<450 else 103,2,'buy')
        self.trade(480,102,1,'sell')
        self.assertIn('AGUARDAR_RETESTE',[e['stage'] for e in self.events])
        for sec in range(481,600):
            self.trade(sec,101 if sec<550 else 102,1,'buy' if sec%2 else 'sell')
        self.trade(600,102,20,'buy')
        self.assertIn('RETESTE_CONFIRMADO',[e['stage'] for e in self.events])
        for sec in range(601,607):self.trade(sec,102,20,'buy')
        self.trade(607,102.25,20,'buy')
        hits=[e for e in self.events if e['stage']=='GATILHO_CONFIRMADO']
        self.assertEqual(len(hits),1)
        self.assertEqual(hits[0]['model'],'ROMPIMENTO_RETESTE')

    def test_five_minute_calendar_boundary(self):
        for sec in range(1200):self.trade(sec,100+(1 if sec%4==0 else -1 if sec%4==2 else 0))
        self.trade(1200,100)
        state=self.engine.snapshot('NQZ6')
        five=next(b for b in state['candles'] if b['timeframe_seconds']==300)
        self.assertFalse(five['warming_up'])
        self.assertEqual(five['start'],3000000)

    def test_five_minute_absorption_requires_close_and_delta(self):
        for sec in range(900):
            self.trade(sec,101 if sec%300==30 else 99 if sec%300==60 else 100,
                       side='buy' if sec%2 else 'sell')
        for sec in range(900,1200):
            self.trade(sec,101 if sec<920 else 99 if sec<1180 else 100.5,
                       10 if 1155<=sec<1180 else 1,'sell' if sec<1180 else 'buy')
        self.assertFalse(any(e['stage']=='GATILHO_CONFIRMADO' and e['timeframe_seconds']==300 for e in self.events))
        for sec in range(1200,1207):self.trade(sec,100.5,20,'buy')
        self.trade(1207,101.25,20,'buy')
        self.assertTrue(any(e['stage']=='GATILHO_CONFIRMADO' and e['timeframe_seconds']==300 and e['side']=='buy' for e in self.events))

    def test_sell_breakout_retest_is_symmetric(self):
        self.seed()
        for sec in range(360,480):
            self.trade(sec,100 if sec<380 else 98 if sec<450 else 97,2,'sell')
        self.trade(480,98,1,'buy')
        for sec in range(481,600):self.trade(sec,99 if sec<550 else 98,1,'sell' if sec%2 else 'buy')
        for sec in range(600,607):self.trade(sec,98,20,'sell')
        self.trade(607,97.75,20,'sell')
        hits=[e for e in self.events if e['stage']=='GATILHO_CONFIRMADO' and e['model']=='ROMPIMENTO_RETESTE']
        self.assertEqual(len(hits),1)
        self.assertEqual(hits[0]['side'],'sell')


if __name__=='__main__':unittest.main()


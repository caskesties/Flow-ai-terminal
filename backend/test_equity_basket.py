import unittest
from equity_basket import EquityBasket, DEFAULT_WEIGHTS

class BasketTests(unittest.TestCase):
    def series(self, move=lambda s,i:i/1000, omit=None, gap=False):
        e=EquityBasket();e.connected=True
        for i in range(301):
            if gap and 100<i<125:continue
            for s in DEFAULT_WEIGHTS:
                if s==omit:continue
                p=100+move(s,i)
                e.on_quote(dict(ev='Q',sym=s,t=1000000+i*1000,bp=p-.01,ap=p+.01),1000000+i*1000)
        return e
    def test_weighted_direction_and_breadth(self):
        e=self.series(lambda s,i:i/100 if s=='NVDA' else -i/1000)
        x=e.snapshot(1300000)
        expected=(8.10*3-(sum(DEFAULT_WEIGHTS.values())-8.10)*.3)/sum(DEFAULT_WEIGHTS.values())
        self.assertAlmostEqual(x['windows']['5m']['weighted_pct'],expected)
        self.assertEqual(x['windows']['5m']['up'],1)
        self.assertEqual(x['direction'],1)
    def test_missing_stale_disconnected(self):
        self.assertFalse(self.series(omit='AMD').snapshot(1300000)['ready'])
        e=self.series();self.assertFalse(e.snapshot(1311000)['ready'])
        e.connected=False;self.assertFalse(e.snapshot(1300000)['ready'])
    def test_gap_and_warmup(self):
        self.assertFalse(self.series(gap=True).snapshot(1300000)['ready'])
        self.assertFalse(EquityBasket().snapshot(1300000)['ready'])
    def test_mixed_windows(self):
        x=self.series(lambda s,i:i/100 if i<180 else 1.8-(i-180)/200).snapshot(1300000)
        self.assertTrue(x['ready']);self.assertEqual(x['direction'],0)
        self.assertLess(x['windows']['2m']['weighted_pct'],0)
        self.assertGreater(x['windows']['5m']['weighted_pct'],0)
    def test_invalid_quotes_and_order(self):
        e=self.series();n=len(e.rows['NVDA'])
        for p,t in [(float('nan'),1300001),(100,1299000),(100,1),(100,1400000)]:
            self.assertFalse(e.on_quote(dict(ev='Q',sym='NVDA',t=t,bp=p,ap=p),1300000))
        self.assertEqual(len(e.rows['NVDA']),n)
    def test_weights(self):
        with self.assertRaises(ValueError):EquityBasket({'NVDA':1})

if __name__=='__main__':unittest.main()

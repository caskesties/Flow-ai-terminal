import unittest
from post_signal_monitor import PostSignalMonitor

class PostSignalMonitorTests(unittest.TestCase):
    def setUp(self):
        self.w=PostSignalMonitor()
        self.w.register({"symbol":"NQZ6","timestamp":100000,"side":"buy","price":100.0})
    def feed(self, start, count, step, price, side, size=10):
        outputs=[]
        for i in range(count):
            outputs.extend(self.w.on_trade({"symbol":"NQZ6","timestamp":start+i*step,
                "price":price if not callable(price) else price(i),"side":side,"size":size}))
        return outputs
    def test_no_filled_position_claim(self):
        self.feed(101000,15,700,102.0,"buy")
        found=self.feed(112000,12,400,102.0,"buy",20)
        for x in found:
            self.assertFalse(x["trade_execution_confirmed"])
            self.assertFalse(x["exit_size_recommended"])
    def test_reversal_needs_opposing_flow_and_adverse_move(self):
        self.feed(101000,15,650,102.0,"buy")
        found=self.feed(112000,15,350,lambda i: 102.0-i*.35,"sell",20)
        self.assertTrue(any(x["stage"]=="POSSIBLE_REVERSAL" for x in found))
        self.assertFalse(any(x["stage"]=="POSSIBLE_REVERSAL" for x in self.feed(120000,10,400,96,"sell")))
    def test_no_alert_on_stale_signal(self):
        self.assertEqual(self.feed(300001,12,300,103,"sell"),[])
    def test_invalid_or_unclassified_data(self):
        self.assertEqual(self.w.on_trade({"symbol":"NQZ6","timestamp":101000,"price":100,"size":10,"side":None}),[])

if __name__=="__main__":
    unittest.main()

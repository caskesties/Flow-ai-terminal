import unittest
from flow_classifier import FlowClassifier
class FlowTests(unittest.TestCase):
 def test_buy_sell_bbo(self):
  f=FlowClassifier()
  f.process({"ev":"Q","sym":"GCZ6","bp":3000,"ap":3000.1,"t":1000})
  self.assertEqual(f.process({"ev":"T","sym":"GCZ6","p":3000.1,"s":4,"t":1001,"q":1})["side"],"buy")
  self.assertEqual(f.process({"ev":"T","sym":"GCZ6","p":3000,"s":3,"t":1002,"q":2})["side"],"sell")
  self.assertEqual(f.stats("GCZ6",1002)["delta"],1)
 def test_duplicate_sequence(self):
  f=FlowClassifier()
  f.process({"ev":"Q","sym":"MNQZ6","bp":20000,"ap":20000.25,"t":1000})
  self.assertIsNotNone(f.process({"ev":"T","sym":"MNQZ6","p":20000.25,"s":1,"t":1000,"q":3}))
  self.assertIsNone(f.process({"ev":"T","sym":"MNQZ6","p":20000.25,"s":1,"t":1000,"q":3}))
 def test_no_quote_no_tick(self):
  f=FlowClassifier()
  self.assertIsNone(f.process({"ev":"T","sym":"GCZ6","p":3000,"s":1,"t":1000}))
 def test_stale_quote_tick_rule(self):
  f=FlowClassifier(max_quote_age_ms=50)
  f.process({"ev":"Q","sym":"GCZ6","bp":2999.9,"ap":3000.1,"t":1000})
  self.assertIsNone(f.process({"ev":"T","sym":"GCZ6","p":3000,"s":1,"t":1500}))
  a=f.process({"ev":"T","sym":"GCZ6","p":3000.2,"s":1,"t":1600})
  self.assertEqual(a["method"],"tick_rule")
if __name__=="__main__":unittest.main()

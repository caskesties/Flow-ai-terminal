"""Deterministic regression tests for server-side outcome measurements."""
import unittest
from unittest.mock import patch
from server_signals import ServerFlowSignals

class OutcomeTests(unittest.TestCase):
    def engine(self):
        e=ServerFlowSignals()
        initial={"type":"server_signal","timestamp":100000,"symbol":"MGCZ6","side":"buy","price":100.0}
        e.alerts["MGCZ6"].append(initial)
        e.pending["MGCZ6"].append({"event":initial,"high":100.0,"low":100.0,"last_ts":100000,"completed":set()})
        return e,initial
    def test_full_horizons(self):
        e,alert=self.engine()
        for i in range(1,62):
            e._evaluate("MGCZ6",{"timestamp":100000+i*1000,"price":100.0+i*.1})
        out=alert["outcomes"]
        self.assertEqual(set(out),{"5","15","30","60"})
        self.assertEqual(out["5"]["status"],"OBSERVED")
        self.assertAlmostEqual(out["60"]["signed_move"],6)
        self.assertEqual(len(e.pending["MGCZ6"]),0)
    def test_gap_not_counted_as_clean(self):
        e,alert=self.engine()
        e._evaluate("MGCZ6",{"timestamp":105000,"price":100.5})
        self.assertEqual(alert["outcomes"]["5"]["status"],"GAP_IN_DATA")
    def test_delayed_observation(self):
        e,alert=self.engine()
        for i in range(1,5):
            e._evaluate("MGCZ6",{"timestamp":100000+i*1000,"price":100+i*.1})
        e._evaluate("MGCZ6",{"timestamp":108000,"price":101})
        self.assertEqual(alert["outcomes"]["5"]["status"],"GAP_IN_DATA")
        self.assertEqual(alert["outcomes"]["5"]["observation_delay_ms"],3000)
    def test_sell_signed_move(self):
        e,alert=self.engine()
        alert["side"]="sell"
        for i in range(1,6):
            e._evaluate("MGCZ6",{"timestamp":100000+i*1000,"price":100-i*.1})
        self.assertAlmostEqual(alert["outcomes"]["5"]["signed_move"],.5)

if __name__=="__main__":
    unittest.main()

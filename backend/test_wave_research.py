"""Deterministic checks for research-only aggression wave detection."""
import unittest
from wave_research import WaveResearch

class WaveResearchTests(unittest.TestCase):
    def test_two_buy_waves_without_breakout_stays_research_only(self):
        engine=WaveResearch()
        events=[]
        sym="MGCZ6"
        for i in range(25):
            item={"symbol":sym,"timestamp":100000+i*500,"price":100.0,"side":"buy" if i%5 else "sell","size":4}
            events.extend(engine.on_trade(item))
        candidates=[e for e in events if e["type"]=="wave_research"]
        self.assertTrue(candidates)
        self.assertFalse(candidates[0]["short_breakout"])
        self.assertIn("NO_SHORT_BREAKOUT",candidates[0]["blockers"])
        self.assertTrue(candidates[0]["research_only"])

    def test_conflicting_waves_do_not_qualify(self):
        engine=WaveResearch()
        events=[]
        for i in range(25):
            # The earlier segment is mostly buyers, the later segment mostly sellers.
            events.extend(engine.on_trade({"symbol":"MNQZ6","timestamp":100000+i*500,"price":100.0,
                                           "side":"buy" if i<13 else "sell","size":3}))
        self.assertFalse([e for e in events if e["type"]=="wave_research"])

    def test_measurement_does_not_emit_trade_signal(self):
        engine=WaveResearch()
        ev={"symbol":"GCZ6","timestamp":100000,"price":100.0,"side":"buy","research_only":True}
        engine.pending["GCZ6"].append({"event":ev,"last_ts":100000,"high":100.0,"low":100.0,"done":set(),"gap":False})
        results=[]
        for i in range(1,62):
            results.extend(engine._follow("GCZ6",{"timestamp":100000+1000*i,"price":100+i*.1}))
        self.assertEqual([e["horizon_seconds"] for e in results],[5,15,30,60])
        self.assertAlmostEqual(results[-1]["signed_move"],6.0)
        self.assertTrue(all(e["research_only"] for e in results))

if __name__=="__main__":
    unittest.main()

import unittest
from absorption_research import AbsorptionResearch

class AbsorptionResearchTests(unittest.TestCase):
    def test_no_prior_signal_required_for_absorption_candidate(self):
        model=AbsorptionResearch()
        found=[]
        # Push eight ticks higher, then aggressive buying stalls near the high.
        for i in range(40):
            ts=100000+i*500
            px=100+min(i,16)*.25
            event=model.on_trade(dict(symbol="MNQZ6",timestamp=ts,price=px,side="buy",size=10))
            if event:found.append(event)
        self.assertTrue(found)
        self.assertEqual(found[0]["status"],"POSSIBLE_ABSORPTION_UNCONFIRMED")
        self.assertTrue(found[0]["research_only"])

    def test_insufficient_history_does_not_flag(self):
        model=AbsorptionResearch()
        self.assertIsNone(model.on_trade(dict(symbol="MNQZ6",timestamp=100000,price=100,side="buy",size=10)))

if __name__=="__main__":
    unittest.main()

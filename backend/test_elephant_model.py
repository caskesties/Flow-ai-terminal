import unittest
from unittest.mock import patch
from elephant_model import ElephantFlowModel

class ElephantTests(unittest.TestCase):
    def test_rejects_without_history(self):
        e=ElephantFlowModel()
        with patch("elephant_model.time.time",return_value=240):
            self.assertIsNone(e.on_trade({"symbol":"MGCZ6","timestamp":240000,"price":4000.0,"size":1,"side":"buy"}))
        self.assertEqual(len(e.candidates),0)
    def test_rejects_wickful_bar(self):
        e=ElephantFlowModel()
        prior=[{"start":i*120000,"h":101,"l":99,"o":99.5,"c":100.5,"buy":30,"sell":30} for i in range(20)]
        b={"start":20*120000,"last":21*120000+115000,"count":30,
           "o":100,"h":107,"l":99,"c":106.5,"buy":600,"sell":1,"waves":{}}
        e._close("GCZ6",b,prior)
        self.assertNotIn("GCZ6",e.candidates)
    def test_95_percent_body_with_small_opposite_wick_is_accepted(self):
        e=ElephantFlowModel()
        prior=[{"start":i*120000,"h":101,"l":99,"o":99.5,"c":100.5,
                "buy":30,"sell":30} for i in range(20)]
        waves={2:{"buy":120,"sell":10},6:{"buy":120,"sell":10}}
        b={"start":20*120000,"last":21*120000+119000,"count":80,
           "o":99.25,"h":109,"l":99,"c":108.75,"buy":650,"sell":30,"waves":waves}
        e._close("MNQZ6",b,prior)
        self.assertEqual(e.diagnostics["MNQZ6"]["wickless"],1)
        self.assertEqual(e.diagnostics["MNQZ6"]["delta"],1)
        self.assertEqual(e.diagnostics["MNQZ6"]["waves"],1)
    def test_old_84_percent_body_is_rejected(self):
        e=ElephantFlowModel()
        prior=[{"start":i*120000,"h":101,"l":99,"o":99.5,"c":100.5,
                "buy":30,"sell":30} for i in range(20)]
        b={"start":20*120000,"last":21*120000+119000,"count":80,
           "o":100,"h":107,"l":99,"c":106.75,"buy":650,"sell":30,
           "waves":{2:{"buy":120,"sell":10},6:{"buy":120,"sell":10}}}
        e._close("MNQZ6",b,prior)
        self.assertEqual(e.diagnostics["MNQZ6"]["wickless"],0)
    def test_closing_wick_above_one_tick_rejected(self):
        e=ElephantFlowModel()
        prior=[{"start":i*120000,"h":101,"l":99,"o":99.5,"c":100.5,
                "buy":30,"sell":30} for i in range(20)]
        b={"start":20*120000,"last":21*120000+119000,"count":80,
           "o":100,"h":107,"l":99,"c":106.5,"buy":650,"sell":30,
           "waves":{2:{"buy":120,"sell":10},6:{"buy":120,"sell":10}}}
        e._close("MNQZ6",b,prior)
        self.assertEqual(e.diagnostics["MNQZ6"]["wickless"],0)
    def test_no_early_notification_from_partial_bar(self):
        e=ElephantFlowModel()
        with patch("elephant_model.time.time",return_value=10):
            for i in range(30):
                e.on_trade({"symbol":"GCZ6","timestamp":1000+i*100,"price":100+i*.1,"size":10,"side":"buy"})
        self.assertEqual(e.candidates,{})
if __name__=="__main__":unittest.main()

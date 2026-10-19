import unittest
from massive_contract_guard import choose_contract
class TestGuard(unittest.TestCase):
 def test_no_activity_blocks(self):
  self.assertEqual(choose_contract([{"ticker":"GCZ6"}],"GC")["status"],"UNCONFIRMED")
 def test_ambiguous_month_blocks(self):
  cs=[{"ticker":"GCZ6"},{"ticker":"GCG7"}]
  self.assertEqual(choose_contract(cs,"GC",{"GCZ6":100,"GCG7":90})["status"],"UNCONFIRMED")
 def test_liquid_candidate_needs_confirm(self):
  self.assertEqual(choose_contract([{"ticker":"GCZ6"}],"GC",{"GCZ6":100})["status"],"CANDIDATE")
if __name__=="__main__": unittest.main()

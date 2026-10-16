#!/usr/bin/env python3
"""Deterministic smoke tests for historical signal validation, no API key needed."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_massive import candidates, nonoverlapping, contiguous, validate
from massive_historical_research import evaluate

def bars(count=90, gap=None):
    base = datetime(2026, 10, 13, tzinfo=timezone.utc)
    result = []
    for i in range(count):
        offset = i + (1 if gap is not None and i >= gap else 0)
        price = 100 + i * 0.01
        result.append({"t": base + timedelta(minutes=offset), "open": price,
                       "high": price+0.1, "low": price-0.1,
                       "close": price, "volume": 10.})
    return result

class ValidationTests(unittest.TestCase):
    def test_uninterrupted(self):
        self.assertTrue(contiguous(bars(4)))
        self.assertFalse(contiguous(bars(4, gap=2)))

    def test_no_overlapping_horizon(self):
        self.assertEqual(nonoverlapping([(10, 2.), (12, -1.), (16, 3.), (23, 1.)]), [2., 3., 1.])

    def test_no_false_breakouts(self):
        self.assertEqual(candidates(bars(), 1.5, 20, 0, 85), [])

    def test_detect_breakout(self):
        sample = bars()
        sample[40]["close"] = 106.
        sample[40]["high"] = 106.1
        sample[40]["volume"] = 100.
        indices = [i for i, _ in candidates(sample, 1.5, 20, 0, 85)]
        self.assertIn(40, indices)

    def test_future_gap_blocks_signal(self):
        sample = bars(gap=43)
        sample[40]["close"] = 106.
        sample[40]["high"] = 106.1
        sample[40]["volume"] = 100.
        indices = [i for i, _ in candidates(sample, 1.5, 20, 0, 85)]
        self.assertNotIn(40, indices)

    def test_baseline_skips_gaps(self):
        sample = bars(gap=43)
        sample[40]["close"] = 106.
        sample[40]["high"] = 106.1
        sample[40]["volume"] = 100.
        raw = [{"timestamp_utc": b["t"].isoformat(), "open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"], "volume": b["volume"]} for b in sample]
        self.assertFalse(any(s["time_utc"] == sample[40]["t"].isoformat() for s in evaluate(raw)))

    def test_small_sample_does_not_select_parameters(self):
        output = validate(bars())
        self.assertTrue(any("Insufficient evidence" in line for line in output))
        self.assertFalse(any("Chosen parameters" in line for line in output))

    def test_report_no_signal(self):
        output = validate(bars())
        self.assertTrue(any("Insufficient evidence" in line for line in output))

if __name__ == "__main__":
    unittest.main()

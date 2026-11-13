"""Regression tests for the evidence-limited Checkpoint Forensics Lab."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from phidiscovery.checkpoint_lab import (
    SCHEMA_REPORT, analyze_synthetic, make_synthetic, _digest, _read_record,
)

ROOT = Path(__file__).resolve().parents[1]


class SyntheticCheckpointTests(unittest.TestCase):
    def test_seed_and_layout_recovery_on_disjoint_holdout(self):
        record = make_synthetic(seed=953049583, lanes=148, count=2048, noise=0.25)
        report = analyze_synthetic(record)
        self.assertEqual(report["schema"], SCHEMA_REPORT)
        self.assertTrue(report["controlled_pattern_recovered"])
        self.assertEqual(report["selected_candidate"]["seed"], 953049583)
        self.assertEqual(report["selected_candidate"]["layout"], 148)
        self.assertGreater(report["selected_candidate"]["holdout_pearson"], 0.9)
        self.assertLessEqual(report["max_candidate_null_p_monte_carlo"], 0.05)
        self.assertFalse(report["training_hardware_verified"])
        self.assertFalse(report["export_control_violation_verified"])

    def test_off_by_one_seed_and_wrong_layout_rejected(self):
        record = make_synthetic(seed=42, lanes=152, count=1024, noise=0)
        report = analyze_synthetic(record)
        winner = report["selected_candidate"]
        self.assertEqual((winner["seed"], winner["layout"]), (42, 152))
        self.assertAlmostEqual(winner["holdout_pearson"], 1.0, places=12)
        for candidate in report["candidates_ranked_by_training_only"][1:]:
            self.assertLess(candidate["holdout_pearson"], 0.3)

    def test_heavy_drift_suppresses_confident_decision(self):
        record = make_synthetic(seed=73, lanes=132, count=1024, noise=100)
        report = analyze_synthetic(record)
        self.assertFalse(report["controlled_pattern_recovered"])

    def test_weight_tampering_detected(self):
        record = make_synthetic(count=512)
        record["values"][0] += 1
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            analyze_synthetic(record)

    def test_unsupported_schema_and_nonfinite_weights_rejected(self):
        record = make_synthetic(count=512)
        record["schema"] = "phi.fake"
        with self.assertRaises(ValueError):
            analyze_synthetic(record)
        record = make_synthetic(count=512)
        record["values"][0] = float("nan")
        with self.assertRaises(ValueError):
            analyze_synthetic(record)

    def test_deterministic_provenance_hash_and_analysis(self):
        r1 = make_synthetic(count=512)
        r2 = make_synthetic(count=512)
        self.assertEqual(r1, r2)
        self.assertEqual(analyze_synthetic(r1), analyze_synthetic(r2))
        self.assertEqual(r1["values_sha256"], _digest(r1["values"]))

    def test_cli_produces_exclusive_create_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "checkpoint.json"
            args = [sys.executable, "-m", "phidiscovery.checkpoint_lab",
                    "synthetic", "--count", "512", "--out", str(output)]
            first = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            saved = _read_record(output)
            self.assertTrue(saved["analysis"]["controlled_pattern_recovered"])
            self.assertEqual(saved["checkpoint"]["schema"], "phi.checkpoint.synthetic.v1")
            again = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertIn("exists", again.stderr)

    def test_input_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                _read_record(path)


class TorchLocalTests(unittest.TestCase):
    @unittest.skipUnless(__import__("importlib").util.find_spec("torch"),
                         "PyTorch optional; CI standard library tests still run")
    def test_cpu_same_device_replay_not_hardware_attribution(self):
        from phidiscovery.checkpoint_lab import capture_torch, compare_torch
        record = capture_torch(seed=42, rows=16, cols=32, device="cpu")
        report = compare_torch(record, seeds=[43, 42], device="cpu")
        self.assertTrue(report["controlled_pattern_recovered"])
        self.assertEqual(report["selected_candidate"]["seed"], 42)
        self.assertEqual(report["hardware_attribution"], "NOT_PERFORMED")
        self.assertFalse(report["published_model_provenance_verified"])
        record["values"][0] = 999
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            compare_torch(record, seeds=[42], device="cpu")


if __name__ == "__main__":
    unittest.main()

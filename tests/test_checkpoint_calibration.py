"""R0.2: calibration requires controls and never treats self-report as hardware proof."""
import copy
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from phidiscovery.checkpoint_calibration import (
    _validate_capture, compare_captures, demo, synthetic_demo_capture,
    CAPTURE_SCHEMA, REPORT_SCHEMA,
)

ROOT = Path(__file__).resolve().parents[1]


def fixture(label="alpha", seed=369, lanes=148):
    return synthetic_demo_capture(label, seed=seed, lanes=lanes,
                                  rows=16, cols=32, repeats=3)


class CalibrationPurePythonTests(unittest.TestCase):
    def test_simulated_equal_layout_is_reproducible_with_negative_controls(self):
        a = fixture("a")
        b = fixture("b")
        report = compare_captures(a, b)
        self.assertEqual(report["schema"], REPORT_SCHEMA)
        self.assertEqual(report["evidence_class"], "SYNTHETIC_DEMO_ONLY")
        self.assertTrue(report["descriptive_summary"]["all_cross_machine_values_bit_identical"])
        self.assertTrue(report["descriptive_summary"]["all_within_capture_repeats_bit_identical"])
        self.assertFalse(report["descriptive_summary"]["same_input_file_contents"])
        self.assertGreater(report["descriptive_summary"]["difference_same_minus_control"], 0.8)
        self.assertEqual(report["hardware_attribution"], "NOT_PERFORMED")
        self.assertFalse(report["actual_training_hardware_verified"])

    def test_simulated_different_layout_is_detectably_different(self):
        a = fixture("a", lanes=148)
        b = fixture("b", lanes=132)
        report = compare_captures(a, b)
        self.assertFalse(report["descriptive_summary"]["all_cross_machine_values_bit_identical"])
        self.assertLess(report["descriptive_summary"]["same_seed_mean_pearson"], 0.5)
        self.assertFalse(report["hardware_identity_verified"])
        self.assertFalse(report["cross_machine_independence_verified"])

    def test_repeats_detect_mutated_data_only_if_receipt_digest_is_updated(self):
        a, b = fixture("a"), fixture("b")
        b["trials"][2]["values"][0] += 0.25
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            compare_captures(a, b)
        # Tamper with the receipt by rewriting digest too; still reveals failed repeat.
        from phidiscovery.checkpoint_lab import _digest
        b["trials"][2]["values_sha256_float64_le"] = _digest(b["trials"][2]["values"])
        report = compare_captures(a, b)
        self.assertFalse(report["descriptive_summary"]["all_within_capture_repeats_bit_identical"])
        self.assertFalse(report["descriptive_summary"]["all_cross_machine_values_bit_identical"])

    def test_mismatched_seed_or_shape_rejected(self):
        with self.assertRaisesRegex(ValueError, "identical protocol"):
            compare_captures(fixture("a", seed=369), fixture("b", seed=370))
        with self.assertRaisesRegex(ValueError, "identical protocol"):
            compare_captures(fixture("a"), synthetic_demo_capture("b", 369, rows=16, cols=64))

    def test_self_comparison_report_marks_not_independent(self):
        a = fixture("same")
        report = compare_captures(a, copy.deepcopy(a))
        self.assertTrue(report["descriptive_summary"]["same_input_file_contents"])
        self.assertFalse(report["cross_machine_independence_verified"])

    def test_reject_synthetic_masquerading_as_hardware(self):
        a = fixture()
        a["data_class"] = "CONTROLLED_LOCAL_CAPTURE"
        with self.assertRaisesRegex(ValueError, "class/protocol"):
            _validate_capture(a)
        a = fixture()
        a["device_declaration_unverified"]["kind"] = "cuda"
        with self.assertRaisesRegex(ValueError, "synthetic record must not"):
            _validate_capture(a)
        a = fixture()
        a["hardware_identity_independently_verified"] = True
        with self.assertRaisesRegex(ValueError, "authenticated hardware"):
            _validate_capture(a)

    def test_duplicate_trial_is_rejected(self):
        a = fixture()
        a["trials"][1] = copy.deepcopy(a["trials"][0])
        with self.assertRaisesRegex(ValueError, "duplicate or unsupported"):
            _validate_capture(a)

    def test_corrupt_seed_and_dtype_rejected(self):
        a = fixture()
        a["trials"][0]["seed"] = 370
        with self.assertRaisesRegex(ValueError, "seed does not match"):
            _validate_capture(a)
        a = fixture()
        a["tensor"]["dtype"] = "float64"
        with self.assertRaisesRegex(ValueError, "invalid tensor protocol"):
            _validate_capture(a)

    def test_input_bounds_and_names(self):
        with self.assertRaisesRegex(ValueError, "label"):
            fixture("../not-a-label")
        with self.assertRaisesRegex(ValueError, "128..8192"):
            synthetic_demo_capture("a", 369, rows=1, cols=32)
        with self.assertRaisesRegex(ValueError, "repeats"):
            synthetic_demo_capture("a", 369, repeats=1)
        with self.assertRaisesRegex(ValueError, "toy lanes"):
            synthetic_demo_capture("a", 369, lanes=100)

    def test_demo_contains_only_synthetic_reports(self):
        result = demo()
        self.assertIn("SYNTHETIC", result["data_class"])
        self.assertEqual(result["same_simulated_layout"]["evidence_class"], "SYNTHETIC_DEMO_ONLY")
        self.assertFalse(result["different_simulated_layout"]["hardware_identity_verified"])

    def test_cli_demo_create_only_and_strict_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "demo.json"
            cmd = [sys.executable, "-m", "phidiscovery.checkpoint_calibration",
                   "demo", "--out", str(out)]
            first = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue(out.exists())
            self.assertIn("SYNTHETIC DEMO", first.stdout)
            second = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("exists", second.stderr)


class CalibrationTorchTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("torch"),
                         "optional PyTorch not installed; pure Python tests still pass")
    def test_two_cpu_captures_replay_and_negative_controls(self):
        from phidiscovery.checkpoint_calibration import capture_pytorch
        a = capture_pytorch("cpu-a", seed=42, rows=16, cols=16,
                            repeats=2, device="cpu")
        b = capture_pytorch("cpu-b", seed=42, rows=16, cols=16,
                            repeats=2, device="cpu")
        self.assertEqual(a["schema"], CAPTURE_SCHEMA)
        report = compare_captures(a, b)
        self.assertTrue(report["descriptive_summary"]["all_cross_machine_values_bit_identical"])
        self.assertTrue(report["descriptive_summary"]["all_within_capture_repeats_bit_identical"])
        self.assertLess(report["descriptive_summary"]["opposite_seed_control_mean_pearson"], 0.2)
        self.assertEqual(report["evidence_class"], "SELF_REPORTED_CONTROLLED_CAPTURE_COMPARISON")
        self.assertFalse(report["hardware_identity_verified"])


if __name__ == "__main__":
    unittest.main()

"""PhiDiscovery R0.5: offline, preregistered holdout prediction scoring tests."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

from phidiscovery.cli import main
from phidiscovery.engine import InputError, sha256
from phidiscovery.predictions import (
    register, score, validate_holdout, validate_plan, verify_registration,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN_FILE = ROOT / "examples" / "prediction-plan-r05.json"
HOLDOUT_FILE = ROOT / "examples" / "synthetic-holdout-r05.json"


def plan():
    return json.loads(PLAN_FILE.read_text(encoding="utf-8"))


def heldout():
    return json.loads(HOLDOUT_FILE.read_text(encoding="utf-8"))


class PredictionHoldoutTests(unittest.TestCase):
    def test_register_and_synthetic_score(self):
        p, h = plan(), heldout()
        lock = register(p)
        self.assertEqual(lock["plan_sha256"], sha256(p))
        self.assertFalse(lock["external_timestamp_verified"])
        self.assertTrue(verify_registration(p, lock))
        result = score(p, lock, h)
        self.assertEqual(result["schema"], "phidiscovery.prediction-score.v0.5")
        self.assertTrue(result["synthetic_holdout"])
        self.assertFalse(result["hypothesis_validated"])
        self.assertFalse(result["raw_measurements_authenticated"])
        self.assertFalse(result["evidence_stage_modified"])
        self.assertFalse(result["external_timestamp_verified"])
        self.assertEqual(result["counts"], {"targets": 3, "models": 2})
        self.assertEqual(result["lowest_mae_model_ids_descriptive_only"], ["nonlinear"])
        summaries = {s["model_id"]: s for s in result["model_summary"]}
        self.assertGreater(summaries["constant"]["mean_absolute_error"],
                           summaries["nonlinear"]["mean_absolute_error"])
        self.assertEqual(summaries["constant"]["tolerance_hits"], 1)
        self.assertEqual(summaries["nonlinear"]["tolerance_hits"], 3)
        self.assertAlmostEqual(summaries["constant"]["mae_improvement_vs_baseline"], 0)
        self.assertEqual(result, score(p, lock, h))

    def test_prediction_is_locked_even_if_tolerance_or_baseline_changes(self):
        p = plan()
        lock = register(p)
        for modifier in (
            lambda x: x["targets"][0]["predictions"].__setitem__("constant", 99.0),
            lambda x: x["targets"][0].__setitem__("tolerance", 99.0),
            lambda x: x["study"].__setitem__("baseline_model_id", "nonlinear"),
            lambda x: x["study"].__setitem__("holdout_id", "changed"),
        ):
            changed = copy.deepcopy(p)
            modifier(changed)
            with self.assertRaises(InputError):
                verify_registration(changed, lock)
            with self.assertRaises(InputError):
                score(changed, lock, heldout())

    def test_commitment_metadata_tampering_detected(self):
        p = plan()
        lock = register(p)
        lock["external_timestamp_verified"] = True
        with self.assertRaises(InputError):
            verify_registration(p, lock)

    def test_holdout_exact_coverage_and_binding(self):
        p, lock = plan(), register(plan())
        for operation in (
            lambda h: h["observations"].pop(),
            lambda h: h["observations"].append(copy.deepcopy(h["observations"][0])),
            lambda h: h["observations"][0].__setitem__("target_id", "not-registered"),
            lambda h: h["observations"][0].__setitem__("unit", "milliseconds"),
            lambda h: h["observations"][0].__setitem__("quantity", "frequency"),
            lambda h: h.__setitem__("holdout_id", "different"),
            lambda h: h.__setitem__("study_id", "different"),
        ):
            h = heldout()
            operation(h)
            with self.assertRaises(InputError):
                score(p, lock, h)

    def test_numeric_validation_blocks_nan_bool_infinity_zero_tolerance(self):
        p = plan()
        for value in (math.nan, math.inf, -math.inf, True, "2.0"):
            altered = copy.deepcopy(p)
            altered["targets"][0]["predictions"]["constant"] = value
            with self.subTest(value=str(value)), self.assertRaises(InputError):
                register(altered)
        p["targets"][0]["tolerance"] = 0
        with self.assertRaises(InputError):
            register(p)
        p = plan()
        p["targets"][0]["predictions"]["constant"] = 10 ** 400
        with self.assertRaises(InputError):
            register(p)

    def test_invalid_source_and_uncertainty_are_refused(self):
        p, lock = plan(), register(plan())
        for value in (-0.2, math.nan, True):
            h = heldout()
            h["observations"][0]["uncertainty"] = value
            with self.assertRaises(InputError):
                score(p, lock, h)
        h = heldout()
        h["source"]["type"] = "impossible-source"
        with self.assertRaises(InputError):
            score(p, lock, h)

    def test_missing_prediction_baseline_and_duplicate_models(self):
        p = plan()
        p["targets"][0]["predictions"].pop("nonlinear")
        with self.assertRaises(InputError):
            register(p)
        p = plan()
        p["study"]["baseline_model_id"] = "unknown"
        with self.assertRaises(InputError):
            register(p)
        p = plan()
        p["models"].append(copy.deepcopy(p["models"][0]))
        with self.assertRaises(InputError):
            register(p)

    def test_observed_values_cannot_leak_into_registered_plan(self):
        p = plan()
        p["targets"][0]["observed"] = 2.002
        with self.assertRaises(InputError):
            register(p)

    def test_mixed_units_and_unhashable_source_type_are_rejected(self):
        p = plan()
        p["targets"][1]["unit"] = "ms"
        with self.assertRaises(InputError):
            register(p)
        p = plan()
        h = heldout()
        h["source"]["type"] = {"pretend": "instrument"}
        with self.assertRaises(InputError):
            score(p, register(p), h)

    def test_declared_uncertainty_exceeding_tolerance_is_flagged(self):
        p = plan()
        h = heldout()
        h["observations"][1]["uncertainty"] = 0.2
        result = score(p, register(p), h)
        relevant = next(t for t in result["target_results"] if t["target_id"] == "theta-40")
        self.assertTrue(relevant["uncertainty_exceeds_tolerance"])
        self.assertFalse(result["hypothesis_validated"])

    def test_user_asserted_instrument_is_not_authenticated(self):
        p, h = plan(), heldout()
        h["source"]["type"] = "instrument"
        result = score(p, register(p), h)
        self.assertFalse(result["synthetic_holdout"])
        self.assertFalse(result["raw_measurements_authenticated"])
        self.assertFalse(result["hypothesis_validated"])
        self.assertFalse(result["external_timestamp_verified"])

    def test_holdout_order_does_not_change_scores(self):
        p, h = plan(), heldout()
        original = score(p, register(p), h)
        h["observations"].reverse()
        new = score(p, register(p), h)
        self.assertNotEqual(original["holdout_sha256"], new["holdout_sha256"])
        self.assertEqual(original["model_summary"], new["model_summary"])
        self.assertEqual(original["target_results"], new["target_results"])

    def test_preregister_and_score_cli_offline_without_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock = root / "registration.json"
            report = root / "score.json"
            self.assertEqual(main(["predict-register", str(PLAN_FILE),
                                   "--out", str(lock)]), 0)
            self.assertTrue(lock.is_file())
            self.assertEqual(main(["predict-check", str(PLAN_FILE), str(lock)]), 0)
            self.assertEqual(main(["predict-score", str(PLAN_FILE), str(lock),
                                   str(HOLDOUT_FILE), "--out", str(report)]), 0)
            self.assertEqual(json.loads(report.read_text())["counts"]["targets"], 3)
            self.assertEqual(main(["predict-score", str(PLAN_FILE), str(lock),
                                   str(HOLDOUT_FILE), "--out", str(report)]), 2)
            self.assertEqual(main(["predict-register", str(PLAN_FILE),
                                   "--out", str(lock)]), 2)

    def test_reject_oversized_trial_or_unbounded_model_count(self):
        p = plan()
        p["targets"] *= 75
        with self.assertRaises(InputError):
            register(p)
        p = plan()
        p["models"] *= 8
        with self.assertRaises(InputError):
            register(p)


if __name__ == "__main__":
    unittest.main()

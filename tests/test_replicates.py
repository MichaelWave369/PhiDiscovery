"""Offline R0.6 repeated holdout and declared contamination tests."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

from phidiscovery.cli import main
from phidiscovery.engine import InputError
from phidiscovery.predictions import register, score
from phidiscovery.replicates import score_replicates, validate_replicates

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "examples" / "prediction-plan-r05.json"
HOLDOUT = ROOT / "examples" / "synthetic-replicates-r06.json"


def plan():
    return json.loads(PLAN.read_text(encoding="utf-8"))


def heldout():
    return json.loads(HOLDOUT.read_text(encoding="utf-8"))


class ReplicateTests(unittest.TestCase):
    def test_synthetic_replicates_score_equal_weight_by_target(self):
        p, h = plan(), heldout()
        result = score_replicates(p, register(p), h)
        self.assertEqual(result["counts"], {"targets": 3, "trials": 9, "models": 2})
        self.assertEqual(result["leakage_audit"]["status"], "SYNTHETIC_DEMONSTRATION")
        self.assertFalse(result["leakage_audit"]["ranking_suppressed"])
        self.assertEqual(result["descriptive_leaders_if_not_quarantined"], ["nonlinear"])
        self.assertFalse(result["hypothesis_validated"])
        self.assertFalse(result["actual_instrument_execution_verified"])
        self.assertFalse(result["independent_replication_verified"])
        summary = {s["model_id"]: s for s in result["model_summary"]}
        self.assertEqual(summary["nonlinear"]["tolerance_hits"], 3)
        self.assertEqual(summary["constant"]["tolerance_hits"], 1)
        self.assertLess(summary["nonlinear"]["mean_absolute_error_of_target_means"],
                        summary["constant"]["mean_absolute_error_of_target_means"])
        self.assertEqual(result, score_replicates(p, register(p), h))

    def test_replicate_order_and_target_order_do_not_change_metrics(self):
        p, h = plan(), heldout()
        before = score_replicates(p, register(p), h)
        h["observations"].reverse()
        for group in h["observations"]:
            group["replicates"].reverse()
        after = score_replicates(p, register(p), h)
        self.assertEqual(before["model_summary"], after["model_summary"])
        self.assertEqual(before["target_results"], after["target_results"])
        self.assertNotEqual(before["holdout_sha256"], after["holdout_sha256"])

    def test_declared_leakage_quarantines_rankings_not_scores(self):
        p, h = plan(), heldout()
        h["model_exposure"][0]["prior_outcome_access"] = "known_access"
        result = score_replicates(p, register(p), h)
        self.assertEqual(result["leakage_audit"]["status"], "DECLARED_LEAKAGE_RISK")
        self.assertTrue(result["leakage_audit"]["ranking_suppressed"])
        self.assertIsNone(result["descriptive_leaders_if_not_quarantined"])
        self.assertEqual(len(result["model_summary"]), 2)
        h = heldout()
        h["model_exposure"][1]["training_overlap"] = "unknown"
        self.assertTrue(score_replicates(p, register(p), h)["leakage_audit"]["ranking_suppressed"])

    def test_chronology_not_proven_and_false_flags_quarantine(self):
        p, h = plan(), heldout()
        h["source"]["type"] = "instrument"
        result = score_replicates(p, register(p), h)
        self.assertEqual(result["leakage_audit"]["status"], "DECLARED_CLEAN_NOT_VERIFIED")
        self.assertFalse(result["leakage_audit"]["prediction_chronology_independently_verified"])
        self.assertFalse(result["leakage_audit"]["source_provenance_authenticated"])
        h["protocol"]["predictions_frozen_before_collection"] = False
        self.assertTrue(score_replicates(p, register(p), h)["leakage_audit"]["ranking_suppressed"])

    def test_duplicate_ids_missing_targets_and_nonfinite_values_fail(self):
        p = plan()
        for edit in (
            lambda h: h["observations"].pop(),
            lambda h: h["observations"][1].__setitem__("target_id", "theta-05"),
            lambda h: h["observations"][1]["replicates"][0].__setitem__("id", "toy05-a"),
            lambda h: h["observations"][0]["replicates"].pop(),
            lambda h: h["observations"][0]["replicates"][0].__setitem__("value", math.nan),
            lambda h: h["observations"][0]["replicates"][0].__setitem__("reported_uncertainty", -1),
            lambda h: h["observations"][0].__setitem__("unit", "ms"),
            lambda h: h.__setitem__("holdout_id", "changed"),
        ):
            h = heldout()
            edit(h)
            with self.assertRaises(InputError):
                score_replicates(p, register(p), h)

    def test_malformed_exposure_and_protocol_rejected(self):
        p = plan()
        for edit in (
            lambda h: h["model_exposure"].pop(),
            lambda h: h["model_exposure"][1].__setitem__("model_id", "constant"),
            lambda h: h["model_exposure"][0].__setitem__("training_overlap", "claim-proven"),
            lambda h: h["model_exposure"][0].__setitem__("prior_outcome_access", []),
            lambda h: h["protocol"].__setitem__("holdout_blinded_until_commitment", "true"),
            lambda h: h["protocol"].__setitem__("unknown_field", True),
            lambda h: h["source"].__setitem__("type", {"instrument": True}),
        ):
            h = heldout()
            edit(h)
            with self.assertRaises(InputError):
                score_replicates(p, register(p), h)

    def test_replicates_never_escape_registered_prediction_values(self):
        p, h = plan(), heldout()
        lock = register(p)
        p["targets"][0]["predictions"]["constant"] = 99.0
        with self.assertRaises(InputError):
            score_replicates(p, lock, h)

    def test_uncertainty_margin_has_no_confidence_claim(self):
        p, h = plan(), heldout()
        for group in h["observations"]:
            for trial in group["replicates"]:
                trial["reported_uncertainty"] = 0.5
        report = score_replicates(p, register(p), h)
        self.assertTrue(all(t["uncertainty_margin_exceeds_tolerance"]
                            for t in report["target_results"]))
        self.assertFalse(report["hypothesis_validated"])
        self.assertIn("not a confidence interval", report["interpretation"])

    def test_v05_scoring_still_works_unchanged(self):
        p = plan()
        old = json.loads((ROOT / "examples" / "synthetic-holdout-r05.json").read_text())
        self.assertEqual(score(p, register(p), old)["counts"]["targets"], 3)

    def test_cli_creates_private_new_result_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            lock = Path(folder) / "lock.json"
            report = Path(folder) / "replicated.json"
            self.assertEqual(main(["predict-register", str(PLAN), "--out", str(lock)]), 0)
            self.assertEqual(main(["replicate-score", str(PLAN), str(lock),
                                   str(HOLDOUT), "--out", str(report)]), 0)
            data = json.loads(report.read_text())
            self.assertEqual(data["counts"]["trials"], 9)
            self.assertEqual(main(["replicate-score", str(PLAN), str(lock),
                                   str(HOLDOUT), "--out", str(report)]), 2)


if __name__ == "__main__":
    unittest.main()

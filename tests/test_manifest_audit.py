"""R0.7: manifest identifier overlaps must never certify independent science."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from phidiscovery.cli import main
from phidiscovery.engine import InputError, sha256
from phidiscovery.manifest_audit import audit_manifest, fingerprint, validate_manifest
from phidiscovery.predictions import register
from phidiscovery.replicates import score_replicates

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "examples" / "prediction-plan-r05.json"
HOLDOUT = ROOT / "examples" / "synthetic-replicates-r06.json"
MANIFEST = ROOT / "examples" / "synthetic-manifest-r07.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def inputs():
    p = read(PLAN)
    return p, register(p), read(HOLDOUT), read(MANIFEST)


def remove_planted_overlap(manifest):
    for dataset in manifest["model_datasets"][1]["datasets"]:
        dataset["record_ids"] = [rid for rid in dataset["record_ids"] if rid != "toy70-a"]


class ManifestAuditTests(unittest.TestCase):
    def test_planted_training_overlap_quarantines_ranking(self):
        p, lock, h, m = inputs()
        report = audit_manifest(p, lock, h, m)
        self.assertEqual(report["schema"], "phidiscovery.manifest-leakage-audit.v0.7")
        self.assertEqual(report["manifest_status"], "EXACT_IDENTIFIER_OVERLAP_DECLARED")
        self.assertTrue(report["ranking_suppressed"])
        self.assertFalse(report["hypothesis_validated"])
        self.assertFalse(report["proof_of_actual_training_exposure"])
        self.assertFalse(report["manifest_completeness_independently_verified"])
        self.assertEqual(report["holdout_trial_id_count"], 9)
        by_model = {x["model_id"]: x for x in report["model_manifest_audit"]}
        self.assertEqual(by_model["constant"]["matched_holdout_record_count"], 0)
        self.assertEqual(by_model["nonlinear"]["matched_holdout_record_count"], 1)
        self.assertEqual(by_model["nonlinear"]["matched_splits"], ["evaluation", "training"])
        self.assertEqual(by_model["nonlinear"]["cross_split_identifier_count"], 1)
        self.assertEqual(len(by_model["nonlinear"]["matched_record_digests_sample"]), 1)
        self.assertEqual(
            by_model["nonlinear"]["matched_record_digests_sample"][0],
            fingerprint(m["identifier_namespace"], "toy70-a"))
        self.assertIsNone(report["descriptive_r06_diagnostics"]["descriptive_leaders_if_not_quarantined"])
        self.assertEqual(report, audit_manifest(p, lock, h, m))

    def test_clean_supplied_records_cannot_certify_training_history(self):
        p, lock, h, m = inputs()
        remove_planted_overlap(m)
        report = audit_manifest(p, lock, h, m)
        self.assertEqual(report["manifest_status"], "NO_EXACT_MATCH_IN_SUPPLIED_MANIFESTS_UNVERIFIED")
        self.assertFalse(report["ranking_suppressed"])
        self.assertFalse(report["proof_of_actual_training_exposure"])
        self.assertFalse(report["manifest_completeness_independently_verified"])
        self.assertEqual(report["descriptive_r06_diagnostics"]["descriptive_leaders_if_not_quarantined"], ["nonlinear"])
        self.assertIn("No match does NOT establish clean data", report["interpretation"])

    def test_incomplete_or_empty_manifest_quarantines_without_overlap(self):
        p, lock, h, m = inputs()
        remove_planted_overlap(m)
        m["model_datasets"][0]["inventory_complete_declared"] = False
        r = audit_manifest(p, lock, h, m)
        self.assertEqual(r["manifest_status"], "INCOMPLETE_OR_UNCERTAIN_EXPOSURE")
        self.assertTrue(r["ranking_suppressed"])
        self.assertIsNone(r["descriptive_r06_diagnostics"]["descriptive_leaders_if_not_quarantined"])
        m["model_datasets"][0]["inventory_complete_declared"] = True
        for dataset in m["model_datasets"][0]["datasets"]:
            dataset["record_ids"] = []
        r = audit_manifest(p, lock, h, m)
        self.assertTrue(r["ranking_suppressed"])
        self.assertIn("No record identifiers were supplied for this model",
                      r["model_manifest_audit"][0]["issues"])

    def test_cross_split_overlap_alone_is_flagged(self):
        p, lock, h, m = inputs()
        remove_planted_overlap(m)
        m["model_datasets"][1]["datasets"][0]["record_ids"].append("same-old-example")
        m["model_datasets"][1]["datasets"][1]["record_ids"].append("same-old-example")
        r = audit_manifest(p, lock, h, m)
        self.assertTrue(r["ranking_suppressed"])
        self.assertEqual(r["manifest_status"], "INCOMPLETE_OR_UNCERTAIN_EXPOSURE")
        item = r["model_manifest_audit"][1]
        self.assertEqual(item["matched_holdout_record_count"], 0)
        self.assertEqual(item["cross_split_identifier_count"], 1)

    def test_prior_exposure_already_declared_in_r06_still_quarantines(self):
        p, lock, h, m = inputs()
        remove_planted_overlap(m)
        h["model_exposure"][0]["prior_outcome_access"] = "known_access"
        r = audit_manifest(p, lock, h, m)
        self.assertTrue(r["ranking_suppressed"])
        self.assertTrue(any("known_access" in risk for risk in r["risk_reasons"]))
        self.assertIsNone(r["descriptive_r06_diagnostics"]["descriptive_leaders_if_not_quarantined"])

    def test_study_identity_or_registered_predictions_change_rejected(self):
        p, lock, h, m = inputs()
        m["holdout_id"] = "another-holdout"
        with self.assertRaises(InputError):
            audit_manifest(p, lock, h, m)
        p, lock, h, m = inputs()
        p["targets"][0]["predictions"]["constant"] = 999
        with self.assertRaises(InputError):
            audit_manifest(p, lock, h, m)

    def test_bad_manifest_shape_and_unregistered_model_fail(self):
        operations = [
            lambda m: m["model_datasets"].pop(),
            lambda m: m["model_datasets"][1].__setitem__("model_id", "constant"),
            lambda m: m["model_datasets"][0].__setitem__("inventory_complete_declared", "true"),
            lambda m: m["model_datasets"][0]["datasets"][0].__setitem__("split", "unknown"),
            lambda m: m["model_datasets"][0]["datasets"][0].__setitem__("record_ids", "one-two"),
            lambda m: m["model_datasets"][0]["datasets"][0]["record_ids"].append("historic-pendulum-a"),
            lambda m: m["model_datasets"][0]["datasets"].append(
                copy.deepcopy(m["model_datasets"][0]["datasets"][0])),
            lambda m: m["model_datasets"][1]["datasets"][0]["record_ids"].append(12),
            lambda m: m.__setitem__("identifier_namespace", ""),
            lambda m: m.__setitem__("schema_version", "0.8"),
            lambda m: m.__setitem__("unexpected", True),
        ]
        for operation in operations:
            p, lock, h, m = inputs()
            operation(m)
            with self.subTest(operation=str(operation)), self.assertRaises(InputError):
                validate_manifest(p, lock, h, m)

    def test_identifier_hash_is_deterministic_and_namespaced(self):
        self.assertEqual(fingerprint("a", "record1"), fingerprint("a", "record1"))
        self.assertNotEqual(fingerprint("a", "record1"), fingerprint("b", "record1"))
        self.assertNotEqual(fingerprint("a", "record1"), fingerprint("a", "record2"))
        with self.assertRaises(InputError):
            fingerprint(" ", "record1")
        with self.assertRaises(InputError):
            fingerprint("a", "")

    def test_existing_r06_scorer_unmodified(self):
        p, lock, h, m = inputs()
        before = score_replicates(p, lock, h)
        audit_manifest(p, lock, h, m)
        self.assertEqual(before, score_replicates(p, lock, h))
        self.assertEqual(before["descriptive_leaders_if_not_quarantined"], ["nonlinear"])

    def test_cli_private_receipt_and_exclusive_create(self):
        with tempfile.TemporaryDirectory() as folder:
            lock_path = Path(folder) / "preregister.json"
            report_path = Path(folder) / "manifest-audit.json"
            self.assertEqual(main(["predict-register", str(PLAN), "--out", str(lock_path)]), 0)
            args = ["manifest-audit", str(PLAN), str(lock_path),
                    str(HOLDOUT), str(MANIFEST), "--out", str(report_path)]
            self.assertEqual(main(args), 0)
            output = read(report_path)
            self.assertTrue(output["ranking_suppressed"])
            self.assertEqual(main(args), 2)
            self.assertEqual(output["manifest_sha256"], sha256(read(MANIFEST)))


if __name__ == "__main__":
    unittest.main()

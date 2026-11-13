"""R0.8: renamed training-content overlaps, weak similarity, and quarantine."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest
from phidiscovery.cli import main
from phidiscovery.content_audit import audit_content, fingerprints, validate_content_index
from phidiscovery.engine import InputError, sha256
from phidiscovery.predictions import register
from phidiscovery.manifest_audit import audit_manifest

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "examples" / "prediction-plan-r05.json"
HOLDOUT = ROOT / "examples" / "synthetic-replicates-r06.json"
MANIFEST = ROOT / "examples" / "synthetic-manifest-r08.json"
INDEX = ROOT / "examples" / "synthetic-content-index-r08.json"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def fixture():
    p = read(PLAN)
    return p, register(p), read(HOLDOUT), read(MANIFEST), read(INDEX)

def discard_overlaps(index):
    for row in index["model_records"]:
        if row["record_id"] in ("alias-renamed-40-b", "historic-evaluation-n"):
            row["content"] = ("FICTIONAL independent calibration notebook that shares no "
                              "holdout data or source transcript from the invented trial series."
                              + row["record_id"])

class ContentAuditTests(unittest.TestCase):
    def test_renamed_id_detected_by_exact_content_and_quarantined(self):
        p, lock, h, m, index = fixture()
        prior = audit_manifest(p, lock, h, m)
        self.assertEqual(prior["manifest_status"],
                         "NO_EXACT_MATCH_IN_SUPPLIED_MANIFESTS_UNVERIFIED")
        result = audit_content(p, lock, h, m, index)
        self.assertEqual(result["status"], "EXACT_CONTENT_OVERLAP_IN_SUPPLIED_RECORDS")
        self.assertTrue(result["ranking_suppressed"])
        self.assertFalse(result["hypothesis_validated"])
        self.assertFalse(result["actual_training_data_authenticated"])
        self.assertFalse(result["external_timestamp_verified"])
        self.assertEqual(result["holdout_content_record_count"], 9)
        self.assertIsNone(result["r07_diagnostics"]["descriptive_r06_diagnostics"][
            "descriptive_leaders_if_not_quarantined"])
        models = {x["model_id"]: x for x in result["models"]}
        self.assertEqual(models["nonlinear"]["exact_content_matched_holdout_trial_count"], 1)
        self.assertEqual(models["nonlinear"]["whitespace_candidate_trial_count"], 1)
        self.assertEqual(models["nonlinear"]["exact_matched_trial_ids_sample"], ["toy40-b"])
        self.assertEqual(models["nonlinear"]["whitespace_candidate_trial_ids_sample"], ["toy05-a"])
        self.assertEqual(models["nonlinear"]["missing_model_content_records"], 0)
        self.assertEqual(result, audit_content(p, lock, h, m, index))

    def test_no_match_does_not_claim_clean_training(self):
        p, lock, h, m, index = fixture()
        discard_overlaps(index)
        result = audit_content(p, lock, h, m, index)
        self.assertEqual(result["status"], "NO_CONTENT_MATCH_IN_SUPPLIED_RECORDS_UNVERIFIED")
        self.assertFalse(result["ranking_suppressed"])
        self.assertFalse(result["actual_training_data_authenticated"])
        self.assertFalse(result["hypothesis_validated"])
        self.assertFalse(result["provenance_receipt"]["third_party_anchor_verified"])

    def test_partial_content_inventory_suppresses_rankings(self):
        p, lock, h, m, index = fixture()
        discard_overlaps(index)
        index["model_records"].pop()
        result = audit_content(p, lock, h, m, index)
        self.assertEqual(result["status"], "INCOMPLETE_OR_DECLARED_RISK")
        self.assertTrue(result["ranking_suppressed"])
        self.assertTrue(any(x["missing_model_content_records"] for x in result["models"]))

    def test_whitespace_match_is_candidate_not_exact(self):
        p, lock, h, m, index = fixture()
        for row in index["model_records"]:
            if row["record_id"] == "alias-renamed-40-b":
                row["content"] = ("FICTIONAL independent training record, not holdout data, "
                                  "reserved solely for model calibration documentation.")
        result = audit_content(p, lock, h, m, index)
        self.assertEqual(result["status"], "WHITESPACE_SIMILARITY_CANDIDATE")
        self.assertTrue(result["ranking_suppressed"])
        model = next(x for x in result["models"] if x["model_id"] == "nonlinear")
        self.assertEqual(model["exact_content_matched_holdout_trial_count"], 0)
        self.assertEqual(model["whitespace_candidate_trial_count"], 1)

    def test_existing_r07_declared_id_leak_still_quarantines(self):
        p, lock, h, m, index = fixture()
        discard_overlaps(index)
        m["model_datasets"][1]["datasets"][0]["record_ids"][1] = "toy70-a"
        entry = next(x for x in index["model_records"] if x["record_id"] == "alias-renamed-40-b")
        entry["record_id"] = "toy70-a"
        result = audit_content(p, lock, h, m, index)
        self.assertEqual(result["status"], "INCOMPLETE_OR_DECLARED_RISK")
        self.assertTrue(result["ranking_suppressed"])
        self.assertEqual(result["r07_diagnostics"]["manifest_status"],
                         "EXACT_IDENTIFIER_OVERLAP_DECLARED")

    def test_rejects_missing_duplicate_and_invalid_content_records(self):
        operations = [
            lambda idx: idx["holdout_records"].pop(),
            lambda idx: idx["holdout_records"][1].__setitem__(
                "trial_id", idx["holdout_records"][0]["trial_id"]),
            lambda idx: idx["holdout_records"][0].__setitem__("trial_id", "unknown-trial"),
            lambda idx: idx["model_records"][0].__setitem__("record_id", "unknown-record"),
            lambda idx: idx["model_records"].append(copy.deepcopy(idx["model_records"][0])),
            lambda idx: idx.__setitem__("identifier_namespace", "wrong-namespace"),
            lambda idx: idx.__setitem__("study_id", "wrong-study"),
            lambda idx: idx.__setitem__("schema_version", "0.9"),
            lambda idx: idx["model_records"][0].__setitem__("media_type", "image/jpeg"),
            lambda idx: idx["model_records"][0].__setitem__("content", "short"),
            lambda idx: idx["holdout_records"][0].__setitem__("content", ""),
            lambda idx: idx.__setitem__("extra", True),
        ]
        for op in operations:
            p, lock, h, m, idx = fixture()
            op(idx)
            with self.subTest(op=str(op)), self.assertRaises(InputError):
                validate_content_index(p, lock, h, m, idx)

    def test_normalization_is_bounded_and_domain_separated(self):
        raw = "FICTIONAL measurement transcript:  2.077 seconds for angle 40 deg."
        folded = "FICTIONAL measurement transcript:\n2.077 seconds for angle 40 deg."
        a, b = fingerprints(raw), fingerprints(folded)
        self.assertNotEqual(a["exact_sha256"], b["exact_sha256"])
        self.assertEqual(a["whitespace_folded_sha256"], b["whitespace_folded_sha256"])
        self.assertNotEqual(a["exact_sha256"], a["whitespace_folded_sha256"])
        with self.assertRaises(InputError):
            fingerprints(" " * 5000)

    def test_input_content_modification_changes_receipt_and_plan_change_refused(self):
        p, lock, h, m, index = fixture()
        original = audit_content(p, lock, h, m, index)
        altered = copy.deepcopy(index)
        altered["model_records"][0]["content"] += " Further fictional annotation."
        changed = audit_content(p, lock, h, m, altered)
        self.assertNotEqual(original["content_index_sha256"], changed["content_index_sha256"])
        self.assertEqual(changed["manifest_sha256"], sha256(m))
        p["targets"][0]["predictions"]["constant"] = 99.0
        with self.assertRaises(InputError):
            audit_content(p, lock, h, m, index)

    def test_cli_private_output_exclusive(self):
        with tempfile.TemporaryDirectory() as folder:
            lock = Path(folder) / "lock.json"
            output = Path(folder) / "content-audit.json"
            self.assertEqual(main(["predict-register", str(PLAN), "--out", str(lock)]), 0)
            args = ["content-audit", str(PLAN), str(lock), str(HOLDOUT),
                    str(MANIFEST), str(INDEX), "--out", str(output)]
            self.assertEqual(main(args), 0)
            self.assertTrue(read(output)["ranking_suppressed"])
            self.assertEqual(main(args), 2)

if __name__ == "__main__":
    unittest.main()

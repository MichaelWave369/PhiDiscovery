"""Crop observations R0.5 tests: source relationships, uncertainty and no claim promotion."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from phidiscovery.cli import main
from phidiscovery.crop_observations import audit_observations
from phidiscovery.engine import InputError, analyze, validate_bundle

FIXTURE = Path(__file__).resolve().parent.parent / "examples" / "synthetic-crop-observations-r05.json"


class CropObservationAuditTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_detect_declared_duplicates_and_independence_unknown(self):
        bundle, audit = audit_observations(self.manifest)
        validate_bundle(bundle)
        self.assertEqual(audit["counts"]["observations"], 3)
        self.assertEqual(audit["counts"]["comparisons"], 2)
        self.assertEqual(audit["counts"]["linked_or_duplicate"], 1)
        self.assertEqual(audit["counts"]["unproven_independent"], 1)
        dup = audit["comparisons"][0]
        self.assertEqual(dup["independence"], "linked_or_duplicate")
        self.assertIn("same_declared_image_sha256", dup["link_reasons"])
        self.assertIn("shared_declared_ancestor_or_derivative", dup["link_reasons"])
        self.assertIn("same_declared_capture_id", dup["link_reasons"])
        self.assertEqual(audit["comparisons"][1]["independence"], "not_proven_independent")
        self.assertTrue(all(e["relation"] == "inconclusive" for e in bundle["evidence"]))
        self.assertTrue(all(e["source"]["type"] == "synthetic" for e in bundle["evidence"]))
        self.assertEqual(audit["counts"]["eligible_support"], 0)
        self.assertFalse(audit["claim_validated"])
        self.assertFalse(audit["communication_decoded"])
        report = analyze(bundle)
        self.assertTrue(all(c["stage"] == "insufficient_evidence" for c in report["results"]))
        self.assertTrue(all(c["eligible_support_count"] == 0 for c in report["results"]))

    def test_similarity_and_seeded_sensitivity_are_reproducible(self):
        _, a = audit_observations(self.manifest)
        _, b = audit_observations(self.manifest)
        self.assertEqual(a, b)
        same = a["comparisons"][0]["uncertainty"]
        diff = a["comparisons"][1]["uncertainty"]
        self.assertEqual(same["observed_score"], 100)
        self.assertLess(diff["observed_score"], same["observed_score"])
        self.assertEqual(same["sample_count"], 256)
        self.assertLessEqual(same["sensitivity_band"]["p05"], same["sensitivity_band"]["median"])
        self.assertLessEqual(same["sensitivity_band"]["median"], same["sensitivity_band"]["p95"])
        self.assertIn("not-confidence-interval", same["sensitivity_band"]["model"])

    def test_missing_uncertainty_is_not_treated_as_certainty(self):
        for o in self.manifest["observations"]:
            o["uncertainty_px"] = [0 for _ in o["radii"]]
        _, audit = audit_observations(self.manifest)
        for row in audit["comparisons"]:
            self.assertIsNone(row["uncertainty"]["sensitivity_band"])
            self.assertEqual(row["uncertainty"]["sample_count"], 0)
            self.assertIn("NOT been assessed", row["uncertainty"]["note"])

    def test_no_experimental_support_even_with_non_synthetic_labels(self):
        for o in self.manifest["observations"]:
            o["source"]["type"] = "original_photo"
        bundle, _ = audit_observations(self.manifest)
        self.assertEqual(analyze(bundle)["counts"]["synthetic_evidence"], 0)
        self.assertTrue(all(e["source"]["type"] == "other" for e in bundle["evidence"]))
        self.assertTrue(all(r["eligible_support_count"] == 0 for r in analyze(bundle)["results"]))

    def test_reject_bad_measurements_and_schema(self):
        variants = []
        bad = copy.deepcopy(self.manifest);bad["schema"] = "wrong";variants.append(bad)
        bad = copy.deepcopy(self.manifest);bad["observations"][0]["radii"] = [18, 17, 60, 100];variants.append(bad)
        bad = copy.deepcopy(self.manifest);bad["observations"][0]["uncertainty_px"] = [1];variants.append(bad)
        bad = copy.deepcopy(self.manifest);bad["observations"][0]["uncertainty_px"][0] = 18;variants.append(bad)
        bad = copy.deepcopy(self.manifest);bad["observations"][1]["id"] = "SYN-A";variants.append(bad)
        bad = copy.deepcopy(self.manifest);bad["observations"][0]["radii"][0] = True;variants.append(bad)
        bad = copy.deepcopy(self.manifest);bad["observations"][0]["radii"][0] = float("nan");variants.append(bad)
        bad = copy.deepcopy(self.manifest);bad["sensitivity_trials"] = 10000;variants.append(bad)
        bad = copy.deepcopy(self.manifest);bad["seed"] = -1;variants.append(bad)
        for item in variants:
            with self.subTest(case=variants.index(item)), self.assertRaises(InputError):
                audit_observations(item)

    def test_reject_parent_cycles_unknowns_and_duplicate_pairs(self):
        bad = copy.deepcopy(self.manifest)
        bad["observations"][0]["source"]["parent_ids"] = ["SYN-B"]
        with self.assertRaisesRegex(InputError, "Cycle"):
            audit_observations(bad)
        bad = copy.deepcopy(self.manifest)
        bad["observations"][0]["source"]["parent_ids"] = ["NOT-REAL"]
        with self.assertRaisesRegex(InputError, "Unknown source parent"):
            audit_observations(bad)
        bad = copy.deepcopy(self.manifest)
        bad["comparisons"].append({"reference_id": "SYN-B", "candidate_id": "SYN-A"})
        with self.assertRaisesRegex(InputError, "Repeated comparison"):
            audit_observations(bad)

    def test_declared_local_hash_verified_only_with_safe_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = b"FICTIONAL IMAGE BYTES - NOT AN AERIAL PHOTO"
            (root / "fake-image.bin").write_bytes(payload)
            a = self.manifest["observations"][0]["source"]
            a["image_sha256"] = hashlib.sha256(payload).hexdigest()
            a["local_file"] = "fake-image.bin"
            _, audit = audit_observations(self.manifest, root=root)
            self.assertEqual(audit["observations"][0]["file_check"],
                             "bytes_match_declared_sha256_only")
            a["image_sha256"] = "c" * 64
            with self.assertRaisesRegex(InputError, "SHA-256 mismatch"):
                audit_observations(self.manifest, root=root)
            a["image_sha256"] = hashlib.sha256(payload).hexdigest()
            a["local_file"] = "../escaped.bin"
            with self.assertRaisesRegex(InputError, "escapes"):
                audit_observations(self.manifest, root=root)

    def test_cli_generates_auditable_report(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            self.assertEqual(main(["crop-audit", str(FIXTURE), "--out", str(out)]), 0)
            for name in ("evidence-bundle.json", "source-audit.json",
                         "triage-report.json", "triage-report.html"):
                self.assertTrue((out / name).is_file(), name)
            audit = json.loads((out / "source-audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["input_sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
            self.assertEqual(audit["counts"]["eligible_support"], 0)
            self.assertEqual(main(["check", str(out / "evidence-bundle.json"),
                                   str(out / "triage-report.json")]), 0)


if __name__ == "__main__":
    unittest.main()

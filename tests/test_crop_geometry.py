"""Offline acceptance tests for PhiMathAtelier crop-comparison bridge."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from phidiscovery.cli import main
from phidiscovery.crop_geometry import import_comparison, sha256_bytes
from phidiscovery.engine import InputError, analyze, validate_bundle


FIXTURE = Path(__file__).resolve().parent.parent / "examples" / "synthetic-crop-comparison-r04.json"


class CropGeometryBridgeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_inconclusive_synthetic_and_stable_report(self):
        source_hash = sha256_bytes(FIXTURE.read_bytes())
        bundle, audit = import_comparison(self.fixture, source_hash)
        validate_bundle(bundle)
        self.assertEqual(bundle["project"]["domain"], "crop_geometry")
        self.assertEqual(bundle["evidence"][0]["relation"], "inconclusive")
        self.assertEqual(bundle["evidence"][0]["source"]["type"], "synthetic")
        self.assertEqual(bundle["evidence"][0]["source"]["locator"], "sha256:" + source_hash)
        self.assertFalse(audit["claim_validated"])
        self.assertFalse(audit["communication_decoded"])
        self.assertEqual(audit["independent_support_records"], 0)
        self.assertEqual(audit["derived_comparison"]["score_0_100_descriptive_only"], 100)
        report = analyze(bundle)
        self.assertEqual(report["results"][0]["stage"], "insufficient_evidence")
        self.assertEqual(report["results"][0]["eligible_support_count"], 0)
        self.assertEqual(report["counts"]["synthetic_evidence"], 1)
        self.assertEqual(analyze(bundle), report)

    def test_non_synthetic_still_inconclusive(self):
        doc = copy.deepcopy(self.fixture)
        doc["reference"]["sourceType"] = "local-image-cv"
        doc["candidate"]["sourceType"] = "published-secondary"
        bundle, audit = import_comparison(doc)
        self.assertEqual(bundle["evidence"][0]["source"]["type"], "other")
        self.assertEqual(bundle["evidence"][0]["relation"], "inconclusive")
        self.assertEqual(analyze(bundle)["results"][0]["stage"], "insufficient_evidence")
        self.assertEqual(audit["source_verification"], "unverified")
        self.assertIn("Independence", " ".join(audit["derived_comparison"]["warnings"]))

    def test_reject_tampered_score(self):
        doc = copy.deepcopy(self.fixture)
        doc["comparison"]["score"] = 44
        with self.assertRaisesRegex(InputError, "recomputation"):
            import_comparison(doc)

    def test_reject_tampered_geometry_and_lineage(self):
        bad = copy.deepcopy(self.fixture)
        bad["reference"]["normalizedRadii"] = [0.9, 0.9, 0.9, 1]
        with self.assertRaisesRegex(InputError, "conflicts"):
            import_comparison(bad)
        bad = copy.deepcopy(self.fixture)
        bad["candidate"]["ringCount"] = 7
        with self.assertRaisesRegex(InputError, "ringCount"):
            import_comparison(bad)
        bad = copy.deepcopy(self.fixture)
        bad["candidate"]["radii"] = [36, 36, 120, 200]
        with self.assertRaisesRegex(InputError, "distinct"):
            import_comparison(bad)
        bad = copy.deepcopy(self.fixture)
        bad["comparison"]["ringCounts"] = [4, 3]
        with self.assertRaisesRegex(InputError, "ring counts"):
            import_comparison(bad)
        bad = copy.deepcopy(self.fixture)
        bad["comparison"]["first"] = "Different name"
        with self.assertRaisesRegex(InputError, "names"):
            import_comparison(bad)

    def test_reject_invalid_inputs_and_low_information(self):
        for bad in ([], {"schema": "wrong"}, {"schema": "phi-crop-geometry-comparison/v0.3"}):
            with self.assertRaises(InputError):
                import_comparison(bad)
        bad = copy.deepcopy(self.fixture)
        bad["reference"]["radii"] = [18, 100]
        bad["reference"]["normalizedRadii"] = [0.18, 1]
        bad["reference"]["ringCount"] = 2
        bad["comparison"]["ringCounts"] = [2, 4]
        # Recomputed pair score is different; recomputation must catch it before promotion.
        with self.assertRaisesRegex(InputError, "recomputation"):
            import_comparison(bad)
        with self.assertRaises(InputError):
            import_comparison(self.fixture, "not-a-hash")

    def test_cli_emits_four_files_without_support(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "output"
            rc = main(["crop-import", str(FIXTURE), "--out", str(out)])
            self.assertEqual(rc, 0)
            for filename in ("evidence-bundle.json", "adapter-audit.json",
                             "triage-report.json", "triage-report.html"):
                self.assertTrue((out / filename).is_file(), filename)
            report = json.loads((out / "triage-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["results"][0]["stage"], "insufficient_evidence")
            bundle = json.loads((out / "evidence-bundle.json").read_text(encoding="utf-8"))
            self.assertEqual(bundle["evidence"][0]["source"]["type"], "synthetic")
            self.assertEqual(main(["validate", str(out / "evidence-bundle.json")]), 0)
            self.assertEqual(main(["check", str(out / "evidence-bundle.json"),
                                   str(out / "triage-report.json")]), 0)


if __name__ == "__main__":
    unittest.main()

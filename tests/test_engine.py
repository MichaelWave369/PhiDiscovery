import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from phidiscovery.engine import InputError, analyze, validate_bundle, verify_report
from phidiscovery.report import html_report

ROOT = Path(__file__).resolve().parents[1]


def pilot():
    return json.loads((ROOT / "examples" / "cannabinoid-pilot.json").read_text(encoding="utf-8"))


def source(group, locator, type_="instrument"):
    return {"type": type_, "locator": locator, "independence_group": group}


def evidence(id_, cid, kind="ms2", relation="supports", group="lab-a", locator="file://a", type_="instrument"):
    return {"id": id_, "candidate_id": cid, "kind": kind, "relation": relation, "statement": "Test record", "source": source(group, locator, type_)}


class EngineTests(unittest.TestCase):
    def test_fixture_is_not_a_discovery(self):
        r = analyze(pilot(), ROOT / "examples")
        self.assertEqual(r["counts"]["synthetic_evidence"], 4)
        self.assertTrue(all(c["stage"] == "insufficient_evidence" for c in r["results"]))
        self.assertIn("Potential isomer", " ".join(r["results"][0]["flags"]))
        self.assertTrue(any("outside" in f for f in r["results"][2]["flags"]))

    def test_generalized_domain(self):
        b = json.loads((ROOT / "examples" / "geology-pilot.json").read_text())
        self.assertEqual(analyze(b)["project"]["domain"], "geology")

    def test_reproducible_independent_of_input_order(self):
        b = pilot()
        r = analyze(b)
        b["candidates"].reverse()
        b["evidence"].reverse()
        # Report hash changes when raw input order changes; deterministic for same input.
        self.assertEqual([x["id"] for x in r["results"]], [x["id"] for x in analyze(b)["results"]])
        self.assertEqual(r, analyze(pilot()))
        self.assertTrue(verify_report(r, pilot()))
        self.assertFalse(verify_report(r, b))

    def test_real_independent_multimodal_evidence_reaches_review_not_discovery(self):
        b = pilot()
        b["evidence"] = [evidence("a", "CB-CBD", "ms2", group="lab-a", locator="file://ms2"),
                         evidence("b", "CB-CBD", "nmr", group="lab-b", locator="file://nmr")]
        c = analyze(b)["results"][0]
        self.assertEqual(c["stage"], "candidate_for_expert_review")
        self.assertEqual(c["independent_groups"], 2)
        self.assertNotIn("confirmed", json.dumps(c))

    def test_duplicate_sources_not_independent(self):
        b = pilot()
        b["evidence"] = [evidence("a", "CB-CBD"), evidence("b", "CB-CBD")]
        c = analyze(b)["results"][0]
        self.assertEqual(c["stage"], "early_signal")
        self.assertTrue(any("Repeated provenance" in f for f in c["flags"]))

    def test_contradiction_is_veto(self):
        b = pilot()
        b["evidence"] = [evidence("a", "CB-CBD"), evidence("b", "CB-CBD", relation="contradicts", group="lab-b")]
        self.assertEqual(analyze(b)["results"][0]["stage"], "contested")

    def test_ms1_outside_tolerance_cannot_support(self):
        b = pilot()
        ev = evidence("a", "CB-CBD", kind="ms1")
        ev["measurement"] = {"observed_mz": 500.0, "expected_mz": 315.2, "tolerance_ppm": 5}
        b["evidence"] = [ev]
        self.assertEqual(analyze(b)["results"][0]["eligible_support_count"], 0)

    def test_artifact_hash_verified_and_tamper_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            path = base / "raw.txt"
            path.write_text("raw instrument output", encoding="utf-8")
            b = pilot()
            ev = evidence("a", "CB-CBD")
            ev["source"]["artifact_path"] = "raw.txt"
            ev["source"]["artifact_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            b["evidence"] = [ev]
            report = analyze(b, base)
            self.assertEqual(report["evidence_audit"][0]["artifact_integrity"], "verified_bytes")
            path.write_text("tampered", encoding="utf-8")
            self.assertFalse(verify_report(report, b, base))
            self.assertEqual(analyze(b, base)["results"][0]["stage"], "insufficient_evidence")

    def test_path_traversal_refused(self):
        b = pilot()
        ev = evidence("a", "CB-CBD")
        ev["source"]["artifact_path"] = "../../secret"
        ev["source"]["artifact_sha256"] = "a" * 64
        b["evidence"] = [ev]
        with tempfile.TemporaryDirectory() as tmp:
            r = analyze(b, Path(tmp))
            self.assertEqual(r["evidence_audit"][0]["artifact_integrity"], "invalid")

    def test_bad_reference_rejected(self):
        b = pilot()
        b["evidence"][0]["candidate_id"] = "missing"
        with self.assertRaises(InputError):
            validate_bundle(b)

    def test_bad_measurement_rejected(self):
        b = pilot()
        b["evidence"][0]["measurement"]["expected_mz"] = 0
        with self.assertRaises(InputError):
            validate_bundle(b)

    def test_artifact_sha_requires_path(self):
        b = pilot()
        b["evidence"][0]["source"]["artifact_sha256"] = "a" * 64
        with self.assertRaises(InputError):
            validate_bundle(b)

    def test_html_escapes_untrusted_input(self):
        b = pilot()
        b["candidates"][0]["label"] = "<script>alert(1)</script>"
        text = html_report(analyze(b))
        self.assertNotIn("<script>alert(1)</script>", text)
        self.assertIn("&lt;script&gt;", text)


if __name__ == "__main__":
    unittest.main()

"""Assumption Challenger regression tests. No external services or models."""
import copy
import json
import unittest
from pathlib import Path

from phidiscovery.challenge import challenge
from phidiscovery.engine import InputError

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return json.loads((ROOT / "examples" / "assumption-challenge.json").read_text(encoding="utf-8"))


class ChallengeTests(unittest.TestCase):
    def test_synthetic_example_remains_unconfirmed(self):
        report = challenge(fixture())
        self.assertEqual(report["counts"]["candidates"], 2)
        first = report["candidates"][0]
        self.assertEqual(first["current_evidence_stage"], "insufficient_evidence")
        self.assertEqual(first["evidence_index"]["eligible_support_ids"], [])
        self.assertEqual(first["evidence_index"]["synthetic_ids"], ["E-1", "E-2"])
        self.assertEqual(len(first["discriminating_tests"]), 1)
        self.assertIn("No eligible non-synthetic supporting evidence", first["open_issues"])

    def test_unstated_assumptions_and_alternatives_are_visible(self):
        item = challenge(fixture())["candidates"][1]
        self.assertIn("No explicit assumptions declared", item["open_issues"])
        self.assertIn("No competing explanation declared", item["open_issues"])
        self.assertTrue(any("discriminating test" in issue for issue in item["open_issues"]))

    def test_contradictions_never_disappear(self):
        b = fixture()
        b["evidence"][1]["source"]["type"] = "publication"
        result = challenge(b)["candidates"][0]
        self.assertEqual(result["evidence_index"]["contradiction_ids"], ["E-2"])
        self.assertIn("Contradictory records require independent review; provenance may be synthetic or unverified",
                      result["open_issues"])

    def test_reordered_input_stable_except_receipt(self):
        a = fixture()
        b = copy.deepcopy(a)
        b["candidates"].reverse()
        b["evidence"].reverse()
        one, two = challenge(a), challenge(b)
        self.assertEqual(one["candidates"], two["candidates"])
        self.assertNotEqual(one["input_sha256"], two["input_sha256"])
        self.assertEqual(one, challenge(a))

    def test_rejects_malformed_declarations(self):
        for field, bad in [("assumptions", "one string"),
                           ("alternatives", [""]),
                           ("discriminating_tests", [{"id": "t"}])]:
            b = fixture()
            b["candidates"][0][field] = bad
            with self.subTest(field=field), self.assertRaises(InputError):
                challenge(b)

    def test_rejects_duplicate_test_identifiers(self):
        b = fixture()
        b["candidates"][0]["discriminating_tests"] *= 2
        with self.assertRaises(InputError):
            challenge(b)

    def test_duplicate_supporting_group_not_independent(self):
        b = fixture()
        b["evidence"] = [{
            "id": name, "candidate_id": "C-1", "kind": "ms2", "relation": "supports",
            "statement": "Illustrative external record",
            "source": {"type": "publication", "locator": name, "independence_group": "same"}
        } for name in ("X-1", "X-2")]
        item = challenge(b)["candidates"][0]
        self.assertEqual(item["evidence_index"]["declared_support_independence_groups"], ["same"])
        self.assertIn("Supporting evidence does not declare two independent groups", item["open_issues"])


if __name__ == "__main__":
    unittest.main()

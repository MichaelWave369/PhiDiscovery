"""Offline tests for role isolation, provenance, and loopback-only opt-in."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from phidiscovery.cli import main
from phidiscovery.engine import InputError
from phidiscovery.reviewers import (
    ROLES, compare, create_packets, execute_local, save_private_receipt,
)

ROOT = Path(__file__).resolve().parents[1]


def example():
    return json.loads((ROOT / "examples" / "assumption-challenge.json").read_text(encoding="utf-8"))


def fake(packet, model, port):
    role = packet["role"]
    stance = "challenge" if role == "assumption_challenger" else "unresolved"
    return {
        "stance": stance,
        "analysis": "An untested alternative could explain this result.",
        "counterexample": "Consider a measurement outside the simple model domain.",
        "discriminating_prediction": "The models predict different observations.",
        "test_design": "Preregister measurement intervals and compare held-out trials.",
        "cited_evidence_ids": [x["id"] for x in packet["context"]["evidence"][:1]],
        "uncertainties": ["Nothing in the fictional fixture is physical evidence."],
    }, model


class ReviewersTests(unittest.TestCase):
    def test_packets_are_role_blind_and_deterministic(self):
        pack = create_packets(example())
        self.assertEqual(pack, create_packets(example()))
        self.assertEqual(len(pack["packets"]), 2 * len(ROLES))
        self.assertEqual(len(set(p["packet_id"] for p in pack["packets"])), 6)
        for packet in pack["packets"]:
            self.assertNotIn("peer", packet)
            self.assertNotIn("other_review", json.dumps(packet))
            self.assertEqual(packet["context"]["evidence_stage"], "insufficient_evidence")

    def test_local_mock_outputs_are_not_scientific_evidence(self):
        b = example()
        receipt = execute_local(b, "test-local-model", transport=fake)
        self.assertFalse(receipt["scientific_evidence_produced"])
        self.assertTrue(receipt["human_review_required"])
        r = compare(b, receipt)
        self.assertFalse(r["claim_verified"])
        c1 = r["comparisons"][0]
        self.assertEqual(c1["reviewer_coverage"], 3)
        self.assertEqual(c1["evidence_stage_unchanged"], "insufficient_evidence")
        self.assertTrue(c1["disagreement_flag"])
        self.assertEqual(c1["missing_roles"], [])

    def test_reviewer_hallucinated_citation_is_blocked(self):
        def fake_bad(packet, model, port):
            response, reported = fake(packet, model, port)
            response["cited_evidence_ids"] = ["invented-paper"]
            return response, reported

        with self.assertRaises(InputError):
            execute_local(example(), "test-local-model", transport=fake_bad)

    def test_tampered_receipt_is_rejected(self):
        b = example()
        receipt = execute_local(b, "test-local-model", transport=fake)
        altered = copy.deepcopy(receipt)
        altered["receipts"][0]["review"]["analysis"] = "Rewritten conclusion."
        with self.assertRaises(InputError):
            compare(b, altered)
        altered = copy.deepcopy(receipt)
        altered["input_sha256"] = "0" * 64
        with self.assertRaises(InputError):
            compare(b, altered)
        altered = copy.deepcopy(receipt)
        altered["receipts"][1]["packet_id"] = altered["receipts"][0]["packet_id"]
        with self.assertRaises(InputError):
            compare(b, altered)

    def test_partial_reviews_are_visible(self):
        b = example()
        receipt = execute_local(b, "test-local-model", transport=fake)
        receipt["receipts"] = receipt["receipts"][:1]
        r = compare(b, receipt)
        self.assertEqual(r["comparisons"][0]["reviewer_coverage"], 1)
        self.assertEqual(len(r["comparisons"][0]["missing_roles"]), 2)

    def test_local_output_is_exclusive_and_private(self):
        receipt = execute_local(example(), "test-local-model", transport=fake)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "review.json"
            save_private_receipt(receipt, target)
            self.assertEqual(json.loads(target.read_text())["schema"], receipt["schema"])
            with self.assertRaises(InputError):
                save_private_receipt(receipt, target)

    def test_no_inference_without_approval_flags(self):
        source = ROOT / "examples" / "assumption-challenge.json"
        with patch("phidiscovery.reviewers._ollama_chat") as runner:
            rc = main(["review-local", str(source), "--model", "dummy", "--out", "private.json"])
            self.assertEqual(rc, 2)
            runner.assert_not_called()

    def test_reject_invalid_port(self):
        with self.assertRaises(InputError):
            execute_local(example(), "test-local-model", port=0, transport=fake)

    def test_review_input_bounded(self):
        b = example()
        b["candidates"][0]["hypothesis"] = "X" * 21000
        with self.assertRaises(InputError):
            create_packets(b)


if __name__ == "__main__":
    unittest.main()

"""Offline contract tests for Agentora research-review interchange."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from phidiscovery.agentora_bridge import execute_agentora
from phidiscovery.cli import main
from phidiscovery.engine import InputError
from phidiscovery.reviewers import compare, save_private_receipt

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "assumption-challenge.json"
KEY = "local-test-key-that-is-long-enough"


def bundle():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def models():
    return {
        "assumption_challenger": "model-A",
        "alternative_builder": "model-B",
        "experiment_auditor": "model-C",
    }


def fake(packet, model, port, key):
    assert port == 8088 and key == KEY
    assert model == models()[packet["role"]]
    assert not any(k in packet for k in ("peer_reviews", "previous_review", "other_answers"))
    return {
        "schema": "agentora.discovery-review.v0.3",
        "packet_id": packet["packet_id"], "candidate_id": packet["candidate_id"],
        "role": packet["role"], "model_requested": model,
        "model_reported_unverified": model,
        "source_class": "LOCAL_OLLAMA_SELF_REPORTED_NOT_ATTESTED",
        "tool_calls": 0, "memory_used": False,
        "evidence_verified": False, "human_review_required": True,
        "review": {
            "stance": "challenge" if packet["role"] == "assumption_challenger" else "unresolved",
            "analysis": "A hypothesis was examined as text, not verified experimentally.",
            "counterexample": "A boundary case might differ.",
            "discriminating_prediction": "Alternative predicts distinct observations.",
            "test_design": "Compare preregistered predictions with held-out data.",
            "cited_evidence_ids": [],
            "uncertainties": ["No independent measurement performed."],
        },
    }


class BridgeTests(unittest.TestCase):
    def test_three_roles_receipts_reconcile_without_evidence_upgrade(self):
        b = bundle()
        receipt = execute_agentora(b, models(), operator_key=KEY, transport=fake)
        self.assertEqual(len(receipt["receipts"]), 6)
        self.assertFalse(receipt["scientific_evidence_produced"])
        self.assertFalse(receipt["receipt_independence_attested"])
        result = compare(b, receipt)
        self.assertFalse(result["claim_verified"])
        self.assertTrue(result["comparisons"][0]["disagreement_flag"])
        self.assertEqual(result["comparisons"][0]["evidence_stage_unchanged"], "insufficient_evidence")
        self.assertEqual({x["model_requested"] for x in receipt["receipts"]}, set(models().values()))

    def test_changed_envelope_rejected(self):
        b = bundle()
        for field, value in [
            ("packet_id", "0" * 64), ("role", "experiment_auditor"),
            ("model_requested", "unknown"), ("tool_calls", 1),
            ("memory_used", True), ("evidence_verified", True),
            ("human_review_required", False), ("source_class", "CERTIFIED"),
        ]:
            def broken(packet, model, port, key):
                r = fake(packet, model, port, key)
                r[field] = value
                return r
            with self.subTest(field=field), self.assertRaises(InputError):
                execute_agentora(b, models(), operator_key=KEY, transport=broken)

    def test_unapproved_and_missing_key_rejected_without_network(self):
        with patch("phidiscovery.agentora_bridge._post_packet") as post:
            self.assertEqual(main(["review-agentora", str(SAMPLE),
                                   "--model", "test", "--out", "private.json"]), 2)
            post.assert_not_called()
        with self.assertRaises(InputError):
            execute_agentora(bundle(), models(), operator_key="", transport=fake)

    def test_unknown_source_evidence_cannot_be_cited(self):
        def hallucination(packet, model, port, key):
            r = fake(packet, model, port, key)
            r["review"]["cited_evidence_ids"] = ["E-NOT-REAL"]
            return r
        with self.assertRaises(InputError):
            execute_agentora(bundle(), models(), operator_key=KEY, transport=hallucination)

    def test_receipt_is_private_and_deterministic(self):
        b = bundle()
        one = execute_agentora(b, models(), operator_key=KEY, transport=fake)
        self.assertEqual(one, execute_agentora(b, models(), operator_key=KEY, transport=fake))
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "test-private.json"
            save_private_receipt(one, target)
            self.assertEqual(json.loads(target.read_text())["schema"], one["schema"])
            with self.assertRaises(InputError):
                save_private_receipt(one, target)

    def test_invalid_mapping_fails_before_transport(self):
        with self.assertRaises(InputError):
            execute_agentora(bundle(), {"assumption_challenger": "A"}, operator_key=KEY, transport=fake)
        with self.assertRaises(InputError):
            execute_agentora(bundle(), models(), port=0, operator_key=KEY, transport=fake)


if __name__ == "__main__":
    unittest.main()

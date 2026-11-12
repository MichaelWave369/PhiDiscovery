"""Second Map R0.4: two-round adversarial review and revision audit tests.

All reviewed text in tests is synthetic. No external model is invoked.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from phidiscovery.cli import main
from phidiscovery.debate import (
    debate_packets, execute_debate_local, reconcile_debate, str_bytes,
)
from phidiscovery.engine import InputError, sha256
from phidiscovery.reviewers import create_packets, execute_local, save_private_receipt

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "assumption-challenge.json"


def bundle():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def first_model(packet, model, port):
    return {
        "stance": "challenge" if packet["role"] == "assumption_challenger" else "unresolved",
        "analysis": "This is a simulated first-pass research critique.",
        "counterexample": "A boundary condition could invalidate the generalization.",
        "discriminating_prediction": "One prediction changes with measured amplitude.",
        "test_design": "Conduct controlled measurements with held-out repeats.",
        "cited_evidence_ids": [],
        "uncertainties": ["This is synthetic demonstration text."],
    }, model


def second_model(packet, model, port):
    assert "own_first_pass" in packet["context"]
    assert len(packet["context"]["peer_first_pass"]) == 2
    # Force one stance revision to exercise transition reporting.
    changed = packet["role"] == "assumption_challenger"
    return {
        "stance": "unresolved" if changed else "challenge",
        "analysis": "After peer criticism, I would revise the claim while preserving uncertainty.",
        "counterexample": "Independent controlled trials could contradict the toy model.",
        "discriminating_prediction": "A new measured boundary case would discriminate models.",
        "test_design": "Preregister error bars, controls and independent replication.",
        "cited_evidence_ids": [],
        "uncertainties": ["No real experiments were performed."],
    }, model


def sealed():
    return execute_local(bundle(), "synthetic-first-pass", transport=first_model)


class DebateTests(unittest.TestCase):
    def test_sealed_first_round_and_peer_visibility(self):
        b, first = bundle(), sealed()
        initial_packets = create_packets(b)["packets"]
        self.assertTrue(all("peer_first_pass" not in p["context"] for p in initial_packets))
        pack = debate_packets(b, first)
        self.assertEqual(len(pack["packets"]), 6)
        for packet in pack["packets"]:
            self.assertEqual(len(packet["context"]["peer_first_pass"]), 2)
            self.assertNotIn(packet["role"], [p["role"] for p in packet["context"]["peer_first_pass"]])
            self.assertEqual(packet["context"]["candidate_id"], packet["candidate_id"])
            self.assertEqual(packet["packet_id"], sha256({k: v for k, v in packet.items() if k != "packet_id"}))
        self.assertEqual(pack, debate_packets(b, first))

    def test_two_round_ledger_is_deterministic_and_evidence_unchanged(self):
        b, original = bundle(), sealed()
        snapshot = copy.deepcopy(original)
        models = {role: "synthetic-second-pass" for role in
                  ("assumption_challenger", "alternative_builder", "experiment_auditor")}
        second = execute_debate_local(b, original, models, transport=second_model)
        ledger = reconcile_debate(b, original, second)
        self.assertEqual(original, snapshot)
        self.assertFalse(ledger["scientific_evidence_produced"])
        self.assertTrue(ledger["human_review_required"])
        self.assertEqual(ledger["counts"]["events"], 12)
        self.assertEqual(ledger["counts"]["roles"], 6)
        self.assertEqual(ledger["counts"]["stance_changed"], 4)
        self.assertEqual(ledger, reconcile_debate(b, original, second))
        prev = ledger["seed_sha256"]
        for item in ledger["events"]:
            self.assertEqual(item["previous_event_sha256"], prev)
            self.assertEqual(item["event_sha256"], sha256({
                k: v for k, v in item.items() if k != "event_sha256"
            }))
            prev = item["event_sha256"]
        self.assertEqual(prev, ledger["last_event_sha256"])

    def test_missing_first_pass_is_refused(self):
        original = sealed()
        original["receipts"].pop()
        with self.assertRaises(InputError):
            debate_packets(bundle(), original)

    def test_first_pass_tamper_is_refused(self):
        original = sealed()
        original["receipts"][0]["review"]["analysis"] = "tampered"
        with self.assertRaises(InputError):
            debate_packets(bundle(), original)

    def test_debate_rejects_fabricated_citations(self):
        def hallucination(packet, model, port):
            output, reported = second_model(packet, model, port)
            output["cited_evidence_ids"] = ["PAPER-DOES-NOT-EXIST"]
            return output, reported

        with self.assertRaises(InputError):
            execute_debate_local(
                bundle(), sealed(),
                {r: "mock" for r in ("assumption_challenger", "alternative_builder", "experiment_auditor")},
                transport=hallucination,
            )

    def test_tampered_second_pass_is_refused(self):
        b, original = bundle(), sealed()
        models = {r: "mock" for r in ("assumption_challenger", "alternative_builder", "experiment_auditor")}
        second = execute_debate_local(b, original, models, transport=second_model)
        altered = copy.deepcopy(second)
        altered["receipts"][0]["review"]["analysis"] = "tampered"
        with self.assertRaises(InputError):
            reconcile_debate(b, original, altered)
        altered = copy.deepcopy(second)
        altered["first_pass_sha256"] = "0" * 64
        with self.assertRaises(InputError):
            reconcile_debate(b, original, altered)
        altered = copy.deepcopy(second)
        altered["receipts"][0]["role"] = "alternative_builder"
        with self.assertRaises(InputError):
            reconcile_debate(b, original, altered)

    def test_no_local_inference_without_two_flags(self):
        with patch("phidiscovery.debate._ollama_chat") as model:
            self.assertEqual(main(["debate-local", str(EXAMPLE),
                                   "missing-first-pass.json", "--model", "mock",
                                   "--out", "private.json"]), 2)
            model.assert_not_called()

    def test_finite_cap_and_exclusive_private_receipts(self):
        b, original = bundle(), sealed()
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "debate-pack.json"
            save_private_receipt(debate_packets(b, original), target)
            self.assertTrue(json.loads(target.read_text())["packets"])
            with self.assertRaises(InputError):
                save_private_receipt(debate_packets(b, original), target)
        big = copy.deepcopy(original)
        big["receipts"][0]["review"]["analysis"] = "x" * 50000
        with self.assertRaises(InputError):
            debate_packets(b, big)

    def test_same_data_without_new_receipts_does_not_create_revisions(self):
        with self.assertRaises(InputError):
            reconcile_debate(bundle(), sealed(), {"schema": "wrong"})


if __name__ == "__main__":
    unittest.main()

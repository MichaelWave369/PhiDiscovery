"""R1.2: signed multi-observer checkpoint gossip and conflict audit tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from examples.demo_gossip_r12 import build_demo
from phidiscovery.cli import main
from phidiscovery.engine import InputError
from phidiscovery.gossip import audit_gossip, draft_observation


class GossipAuditTests(unittest.TestCase):
    def test_same_size_different_signed_roots_detected(self):
        bundle, trust = build_demo("conflict")
        r = audit_gossip(bundle, trust)
        self.assertEqual(r["status"], "CONFLICTING_SIGNED_ROOTS_SAME_SIZE")
        self.assertEqual(r["counts"]["signed_observations"], 2)
        self.assertEqual(r["counts"]["distinct_observers"], 2)
        self.assertEqual(r["counts"]["same_size_conflicts"], 1)
        self.assertEqual(r["counts"]["cross_size_unresolved"], 0)
        self.assertEqual(len(r["same_size_conflicts"]), 1)
        self.assertFalse(r["observer_identities_authenticated_out_of_band"])
        self.assertFalse(r["observation_times_verified"])
        self.assertFalse(r["global_non_equivocation_proven"])
        self.assertFalse(r["hypothesis_validated"])
        self.assertEqual(r, audit_gossip(bundle, trust))

    def test_cross_size_without_proof_remains_unresolved(self):
        bundle, trust = build_demo("unresolved")
        r = audit_gossip(bundle, trust)
        self.assertEqual(r["status"], "CROSS_SIZE_CONSISTENCY_UNRESOLVED")
        self.assertEqual(r["counts"]["cross_size_unresolved"], 1)
        self.assertEqual(r["counts"]["same_size_conflicts"], 0)
        self.assertEqual(r["counts"]["cross_size_verified"], 0)

    def test_cross_size_with_r11_proof_is_verified(self):
        bundle, trust = build_demo("consistent")
        r = audit_gossip(bundle, trust)
        self.assertEqual(
            r["status"],
            "NO_CONFLICT_IN_SUPPLIED_SIGNED_VIEWS__INDEPENDENCE_UNVERIFIED",
        )
        self.assertEqual(r["counts"]["cross_size_unresolved"], 0)
        self.assertEqual(r["counts"]["cross_size_verified"], 1)
        self.assertTrue(r["signed_observer_statements_valid"])
        self.assertTrue(r["signed_log_checkpoints_valid"])
        self.assertFalse(r["global_non_equivocation_proven"])

    def test_malformed_or_forged_observer_signatures_rejected(self):
        bundle, trust = build_demo("conflict")
        tests = [
            lambda b: b["observations"][0].__setitem__(
                "signature_base64", b["observations"][1]["signature_base64"]),
            lambda b: b["observations"][0]["claim"].__setitem__(
                "observer_id", "observer-B"),
            lambda b: b["observations"][0]["claim"].__setitem__(
                "claimed_seen_at", "2040-01-01T00:00:00Z"),
            lambda b: b["observations"][0]["claim"].__setitem__(
                "checkpoint_envelope_sha256", "0" * 64),
            lambda b: b["observations"][0].__setitem__("observer_id", "unknown"),
            lambda b: b["observations"][0]["checkpoint"]["checkpoint"].__setitem__(
                "root_sha256", "0" * 64),
            lambda b: b.__setitem__("log_id", "wrong-log"),
            lambda b: b.__setitem__("schema", "wrong-version"),
        ]
        for change in tests:
            changed = copy.deepcopy(bundle)
            change(changed)
            with self.subTest(change=str(change)), self.assertRaises(InputError):
                audit_gossip(changed, trust)

    def test_unpinned_or_reused_observer_keys_rejected(self):
        bundle, trust = build_demo("consistent")
        changed = copy.deepcopy(trust)
        changed["observer_keys"][1]["key"]["public_key_base64"] = (
            changed["observer_keys"][0]["key"]["public_key_base64"])
        with self.assertRaises(InputError):
            audit_gossip(bundle, changed)
        changed = copy.deepcopy(trust)
        changed["observer_keys"][1]["key"]["public_key_base64"] = (
            changed["log_trust"]["key"]["public_key_base64"])
        with self.assertRaises(InputError):
            audit_gossip(bundle, changed)
        changed = copy.deepcopy(trust)
        changed["observer_keys"][1]["observer_id"] = "observer-A"
        with self.assertRaises(InputError):
            audit_gossip(bundle, changed)
        changed = copy.deepcopy(trust)
        changed["observer_keys"][0]["key"]["public_key_base64"] = (
            changed["observer_keys"][0]["key"]["public_key_base64"][:-2] + "==")
        with self.assertRaises(InputError):
            audit_gossip(bundle, changed)
        changed = copy.deepcopy(trust)
        changed["log_trust"]["minimum_tree_size"] = 4
        with self.assertRaises(InputError):
            audit_gossip(bundle, changed)
        changed = copy.deepcopy(trust)
        changed["log_trust"]["minimum_tree_size"] = "1"
        with self.assertRaises(InputError):
            audit_gossip(bundle, changed)

    def test_duplicate_observation_and_single_observer_rejected(self):
        bundle, trust = build_demo("consistent")
        changed = copy.deepcopy(bundle)
        changed["observations"].append(copy.deepcopy(changed["observations"][0]))
        with self.assertRaises(InputError):
            audit_gossip(changed, trust)
        changed = copy.deepcopy(bundle)
        changed["observations"] = changed["observations"][:1]
        with self.assertRaises(InputError):
            audit_gossip(changed, trust)
        changed = copy.deepcopy(bundle)
        changed["observations"][1]["observer_id"] = "observer-A"
        with self.assertRaises(InputError):
            audit_gossip(changed, trust)

    def test_invalid_r11_path_is_rejected_not_silently_downgraded(self):
        bundle, trust = build_demo("consistent")
        changed = copy.deepcopy(bundle)
        changed["consistency_proofs"][0]["proof"][
            "consistency_path_sha256"][0] = "0" * 64
        with self.assertRaises(InputError):
            audit_gossip(changed, trust)
        changed = copy.deepcopy(bundle)
        changed["consistency_proofs"].append(copy.deepcopy(
            changed["consistency_proofs"][0]))
        with self.assertRaises(InputError):
            audit_gossip(changed, trust)

    def test_output_does_not_upgrade_scientific_or_real_world_trust(self):
        for case in ("conflict", "consistent", "unresolved"):
            bundle, trust = build_demo(case)
            output = audit_gossip(bundle, trust)
            self.assertFalse(output["checkpoint_retention_history_verified"])
            self.assertFalse(output["different_key_owners_verified"])
            self.assertFalse(output["global_non_equivocation_proven"])
            self.assertFalse(output["hypothesis_validated"])

    def test_draft_signature_message_uses_observer_and_checkpoint(self):
        bundle, _ = build_demo("conflict")
        cp = bundle["observations"][0]["checkpoint"]
        a = draft_observation(cp, "observer-A", "2000-01-01T00:00:00Z")
        b = draft_observation(cp, "observer-B", "2000-01-01T00:00:00Z")
        self.assertNotEqual(a, b)
        self.assertEqual(a, bundle["observations"][0]["claim"])
        with self.assertRaises(InputError):
            draft_observation(cp, "observer-A", "not-a-timestamp")

    def test_cli_private_report_and_no_overwrite(self):
        bundle, trust = build_demo("conflict")
        with tempfile.TemporaryDirectory() as td:
            bundle_path = Path(td) / "gossip.json"
            trust_path = Path(td) / "trusted.json"
            report_path = Path(td) / "report.json"
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            trust_path.write_text(json.dumps(trust), encoding="utf-8")
            cmd = ["gossip-audit", str(bundle_path), str(trust_path),
                   "--out", str(report_path)]
            self.assertEqual(main(cmd), 0)
            self.assertTrue(json.loads(report_path.read_text())[
                "counts"]["same_size_conflicts"])
            self.assertEqual(main(cmd), 2)


if __name__ == "__main__":
    unittest.main()

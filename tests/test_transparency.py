"""R1.0 signed transparency log and Merkle inclusion verification tests.

All keys are ephemeral test keys. They do not certify any real timestamp,
public log, independently operated witness, or scientific discovery.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from phidiscovery.cli import main
from phidiscovery.engine import InputError, sha256, stable_bytes
from phidiscovery.provenance import (
    ANCHOR_SCHEMA, TRUST_SCHEMA as R09_TRUST,
    draft_publisher_claim, draft_witness_claim,
)
from phidiscovery.predictions import register
from phidiscovery.transparency import (
    LOG_ENTRY_SCHEMA, PROOF_SCHEMA, CHECKPOINT_SCHEMA, TRUST_SCHEMA,
    leaf_hash, node_hash, entry_for, reconstruct_root, verify_log_inclusion,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "examples" / "prediction-plan-r05.json"


def b64(payload):
    return base64.b64encode(payload).decode("ascii")


def public(key):
    return b64(key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw))


def signed_fixture():
    artifact = register(json.loads(PLAN.read_text(encoding="utf-8")))
    pubkey, witkey = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    claim = draft_publisher_claim(artifact)
    pubsig = b64(pubkey.sign(stable_bytes(claim)))
    wclaim = draft_witness_claim(artifact, claim, pubsig, "2026-11-12T00:00:00Z")
    anchor = {
        "schema": ANCHOR_SCHEMA,
        "publisher": {"key_id": "publisher-test", "claim": claim, "signature_base64": pubsig},
        "witness": {"key_id": "witness-test", "claim": wclaim,
                    "signature_base64": b64(witkey.sign(stable_bytes(wclaim)))},
    }
    trust = {
        "schema": R09_TRUST,
        "publisher": {"key_id": "publisher-test", "public_key_base64": public(pubkey)},
        "witness": {"key_id": "witness-test", "public_key_base64": public(witkey)},
    }
    return artifact, anchor, trust


def tree_root(digests):
    if len(digests) == 1:
        return digests[0]
    k = 1 << ((len(digests) - 1).bit_length() - 1)
    return node_hash(tree_root(digests[:k]), tree_root(digests[k:]))


def audit_path(digests, index):
    if len(digests) == 1:
        return []
    k = 1 << ((len(digests) - 1).bit_length() - 1)
    if index < k:
        return audit_path(digests[:k], index) + [tree_root(digests[k:])]
    return audit_path(digests[k:], index - k) + [tree_root(digests[:k])]


def log_fixture(size=5, index=3):
    artifact, anchor, trusted = signed_fixture()
    entry = entry_for(artifact, anchor, trusted)
    hashed = [leaf_hash({"schema": LOG_ENTRY_SCHEMA, "decoy": i})
              for i in range(size)]
    hashed[index] = leaf_hash(entry)
    logkey = Ed25519PrivateKey.generate()
    checkpoint = {
        "schema": CHECKPOINT_SCHEMA,
        "log_id": "fictional-checkpoint-log",
        "tree_size": size,
        "root_sha256": tree_root(hashed).hex(),
        "claimed_issued_at": "2000-01-01T00:00:00Z",
    }
    proof = {
        "schema": PROOF_SCHEMA,
        "leaf_index": index,
        "tree_size": size,
        "audit_path_sha256": [h.hex() for h in audit_path(hashed, index)],
        "checkpoint": checkpoint,
        "signature_base64": b64(logkey.sign(stable_bytes(checkpoint))),
    }
    log_trust = {
        "schema": TRUST_SCHEMA,
        "log_id": "fictional-checkpoint-log",
        "key": {"key_id": "fictional-log-test", "public_key_base64": public(logkey)},
        "minimum_tree_size": 1,
    }
    return artifact, anchor, trusted, proof, log_trust


class MerkleLogTests(unittest.TestCase):
    def test_unbalanced_trees_all_indices_are_verified(self):
        for size in range(1, 18):
            for index in range(size):
                digests = [hashlib.sha256(f"leaf-{i}".encode()).digest()
                           for i in range(size)]
                self.assertEqual(
                    reconstruct_root(digests[index], index, size,
                                     audit_path(digests, index)),
                    tree_root(digests),
                )

    def test_signed_log_checkpoint_and_inclusion_but_no_time_attestation(self):
        artifact, anchor, trusted, proof, log_trust = log_fixture()
        result = verify_log_inclusion(artifact, anchor, trusted, proof, log_trust)
        self.assertTrue(result["publisher_witness_signatures_valid"])
        self.assertTrue(result["log_checkpoint_signature_valid"])
        self.assertTrue(result["merkle_inclusion_valid"])
        self.assertTrue(result["three_distinct_public_keys_used"])
        self.assertEqual(result["tree_size"], 5)
        self.assertEqual(result["leaf_index"], 3)
        self.assertFalse(result["independent_log_operator_identity_verified"])
        self.assertFalse(result["external_time_source_verified"])
        self.assertFalse(result["append_only_consistency_verified"])
        self.assertFalse(result["equivocation_excluded"])
        self.assertFalse(result["hypothesis_validated"])
        self.assertEqual(result["checkpoint_issued_at_claim_unverified"],
                         "2000-01-01T00:00:00Z")
        self.assertEqual(result, verify_log_inclusion(artifact, anchor, trusted,
                                                     proof, log_trust))

    def test_merkle_tampering_rejected(self):
        artifact, anchor, trust, proof, log_trust = log_fixture()
        changes = [
            lambda p: p["audit_path_sha256"].__setitem__(0, "0" * 64),
            lambda p: p["audit_path_sha256"].pop(),
            lambda p: p["audit_path_sha256"].append("0" * 64),
            lambda p: p.__setitem__("leaf_index", 2),
            lambda p: p.__setitem__("tree_size", 4),
            lambda p: p["checkpoint"].__setitem__("root_sha256", "0" * 64),
            lambda p: p["checkpoint"].__setitem__("log_id", "wrong-log"),
            lambda p: p["checkpoint"].__setitem__("claimed_issued_at",
                                                    "2030-01-01T00:00:00Z"),
            lambda p: p.__setitem__("signature_base64", b64(b"\x00" * 64)),
            lambda p: p.__setitem__("unregistered_field", True),
        ]
        for change in changes:
            changed = copy.deepcopy(proof)
            change(changed)
            with self.subTest(change=repr(change)), self.assertRaises(InputError):
                verify_log_inclusion(artifact, anchor, trust, changed, log_trust)

    def test_publisher_anchor_and_trust_tampering_rejected(self):
        artifact, anchor, trust, proof, log_trust = log_fixture()
        changed = copy.deepcopy(artifact)
        changed["note"] = "Tampered"
        with self.assertRaises(InputError):
            verify_log_inclusion(changed, anchor, trust, proof, log_trust)
        changed = copy.deepcopy(anchor)
        changed["witness"]["signature_base64"] = b64(b"\x00" * 64)
        with self.assertRaises(InputError):
            verify_log_inclusion(artifact, changed, trust, proof, log_trust)
        changed = copy.deepcopy(trust)
        changed["witness"]["public_key_base64"] = public(Ed25519PrivateKey.generate())
        with self.assertRaises(InputError):
            verify_log_inclusion(artifact, anchor, changed, proof, log_trust)

    def test_trust_policy_pinning_rejects_untrusted_keys(self):
        artifact, anchor, trust, proof, log_trust = log_fixture()
        changed = copy.deepcopy(log_trust)
        changed["key"]["public_key_base64"] = public(Ed25519PrivateKey.generate())
        with self.assertRaises(InputError):
            verify_log_inclusion(artifact, anchor, trust, proof, changed)
        changed = copy.deepcopy(log_trust)
        changed["key"]["public_key_base64"] = trust["publisher"]["public_key_base64"]
        with self.assertRaises(InputError):
            verify_log_inclusion(artifact, anchor, trust, proof, changed)
        changed = copy.deepcopy(log_trust)
        changed["key"]["key_id"] = trust["witness"]["key_id"]
        with self.assertRaises(InputError):
            verify_log_inclusion(artifact, anchor, trust, proof, changed)

    def test_floor_rejects_rollback_and_malformed_numeric_fields(self):
        artifact, anchor, trust, proof, log_trust = log_fixture()
        changed = copy.deepcopy(log_trust)
        changed["minimum_tree_size"] = 6
        with self.assertRaises(InputError):
            verify_log_inclusion(artifact, anchor, trust, proof, changed)
        for bad in (True, 0, 1.0, "5", -1):
            changed = copy.deepcopy(proof)
            changed["tree_size"] = bad
            with self.subTest(size=bad), self.assertRaises(InputError):
                verify_log_inclusion(artifact, anchor, trust, changed, log_trust)

    def test_single_entry_log_and_repeated_check(self):
        artifact, anchor, trusted, proof, log_trust = log_fixture(1, 0)
        self.assertEqual(proof["audit_path_sha256"], [])
        result = verify_log_inclusion(artifact, anchor, trusted, proof, log_trust)
        self.assertTrue(result["inclusion_in_supplied_signed_checkpoint_verified"])

    def test_cli_valid_uses_private_report_and_refuses_overwrite(self):
        artifact, anchor, trust, proof, log_trust = log_fixture(7, 5)
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder) / n for n in
                     ("artifact.json", "anchor.json", "trust.json",
                      "proof.json", "log-trust.json")]
            for path, payload in zip(paths, (artifact, anchor, trust, proof, log_trust)):
                path.write_text(json.dumps(payload), encoding="utf-8")
            out = Path(folder) / "report.json"
            args = ["log-verify", *(str(p) for p in paths),
                    "--out", str(out)]
            self.assertEqual(main(args), 0)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(report["merkle_inclusion_valid"])
            self.assertFalse(report["append_only_consistency_verified"])
            self.assertEqual(main(args), 2)


if __name__ == "__main__":
    unittest.main()

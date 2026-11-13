"""R1.1: verify append-only consistency between two signed Merkle roots.

Synthetic logs use ephemeral keys, not a trusted external log service or
timestamp. The test proof generator independently follows RFC 9162's
recursive SUBPROOF construction, separate from the production verifier.
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
from phidiscovery.consistency import (
    PROOF_SCHEMA, REPORT_SCHEMA, validate_consistency_path, verify_consistency
)
from phidiscovery.engine import InputError, stable_bytes
from phidiscovery.transparency import (
    CHECKPOINT_SCHEMA, TRUST_SCHEMA, node_hash,
)


def b64(data):
    return base64.b64encode(data).decode("ascii")


def public(key):
    return b64(key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw))


def leaves(n):
    return [hashlib.sha256(b"\x00" + f"FICTIONAL-leaf-{i}".encode()).digest()
            for i in range(n)]


def root(nodes):
    if len(nodes) == 1:
        return nodes[0]
    k = 1 << ((len(nodes) - 1).bit_length() - 1)
    return node_hash(root(nodes[:k]), root(nodes[k:]))


def generate_proof(m, nodes, complete=True):
    """Independent RFC9162 §2.1.4.1 reference proof construction."""
    n = len(nodes)
    if m == n:
        return [] if complete else [root(nodes)]
    k = 1 << ((n - 1).bit_length() - 1)
    if m <= k:
        return generate_proof(m, nodes[:k], complete) + [root(nodes[k:])]
    return generate_proof(m - k, nodes[k:], False) + [root(nodes[:k])]


def signed_fixture(old_size=3, new_size=7, tampered_history=False):
    signer = Ed25519PrivateKey.generate()
    old = leaves(old_size)
    newer_leaves = leaves(new_size)
    if tampered_history:
        newer_leaves[0] = hashlib.sha256(b"\\x00rewritten-first-record").digest()
    old_root, new_root = root(old), root(newer_leaves)
    old_cp = {
        "schema": CHECKPOINT_SCHEMA,
        "log_id": "synthetic-consistency-log",
        "tree_size": old_size,
        "root_sha256": old_root.hex(),
        "claimed_issued_at": "2000-01-01T00:00:00Z",
    }
    new_cp = {
        "schema": CHECKPOINT_SCHEMA,
        "log_id": "synthetic-consistency-log",
        "tree_size": new_size,
        "root_sha256": new_root.hex(),
        "claimed_issued_at": "2000-01-01T00:00:00Z",
    }
    old_envelope = {
        "checkpoint": old_cp,
        "signature_base64": b64(signer.sign(stable_bytes(old_cp))),
    }
    new_envelope = {
        "checkpoint": new_cp,
        "signature_base64": b64(signer.sign(stable_bytes(new_cp))),
    }
    proof = {
        "schema": PROOF_SCHEMA,
        "log_id": "synthetic-consistency-log",
        "older_size": old_size,
        "newer_size": new_size,
        "consistency_path_sha256": (
            [x.hex() for x in generate_proof(old_size, leaves(new_size))]
            if old_size < new_size else []
        ),
    }
    policy = {
        "schema": TRUST_SCHEMA,
        "log_id": "synthetic-consistency-log",
        "key": {"key_id": "synthetic-log-key",
                "public_key_base64": public(signer)},
        "minimum_tree_size": 1,
    }
    return old_envelope, new_envelope, proof, policy


class MerkleConsistencyTests(unittest.TestCase):
    def test_all_sizes_and_positions_up_to_32(self):
        for n in range(2, 33):
            items = leaves(n)
            new_root = root(items)
            for m in range(1, n):
                path = generate_proof(m, items)
                with self.subTest(older=m, newer=n):
                    validate_consistency_path(m, n, root(items[:m]), new_root, path)

    def test_valid_signed_roots_and_unverified_provenance(self):
        older, newer, proof, policy = signed_fixture(3, 7)
        result = verify_consistency(older, newer, proof, policy)
        self.assertEqual(result["schema"], REPORT_SCHEMA)
        self.assertTrue(result["signed_checkpoints_valid"])
        self.assertTrue(result["merkle_consistency_valid"])
        self.assertTrue(result["tree_growth_proven"])
        self.assertTrue(result["history_consistent_between_supplied_signed_roots"])
        self.assertFalse(result["older_checkpoint_independently_retained_verified"])
        self.assertFalse(result["cross_client_non_equivocation_verified"])
        self.assertFalse(result["entire_log_lifetime_append_only_verified"])
        self.assertFalse(result["external_time_verified"])
        self.assertFalse(result["hypothesis_validated"])
        self.assertEqual(result, verify_consistency(older, newer, proof, policy))

    def test_forged_new_history_is_rejected_even_if_both_roots_signed(self):
        older, newer, proof, policy = signed_fixture(3, 7, tampered_history=True)
        with self.assertRaises(InputError):
            verify_consistency(older, newer, proof, policy)

    def test_altered_consistency_path_and_sizes_rejected(self):
        older, newer, proof, policy = signed_fixture(3, 7)
        for operation in (
            lambda p: p["consistency_path_sha256"].pop(),
            lambda p: p["consistency_path_sha256"].append("0" * 64),
            lambda p: p["consistency_path_sha256"].__setitem__(0, "0" * 64),
            lambda p: p.__setitem__("older_size", 2),
            lambda p: p.__setitem__("newer_size", 6),
            lambda p: p.__setitem__("log_id", "wrong-log"),
            lambda p: p.__setitem__("schema", "wrong"),
            lambda p: p.__setitem__("extra", True),
        ):
            changed = copy.deepcopy(proof)
            operation(changed)
            with self.subTest(change=str(operation)), self.assertRaises(InputError):
                verify_consistency(older, newer, changed, policy)

    def test_malformed_hashes_and_boolean_sizes_rejected(self):
        older, newer, proof, policy = signed_fixture(2, 5)
        for bad in (True, 2.0, "2", -1, 0):
            changed = copy.deepcopy(proof)
            changed["older_size"] = bad
            with self.subTest(size=bad), self.assertRaises(InputError):
                verify_consistency(older, newer, changed, policy)
        changed = copy.deepcopy(proof)
        changed["consistency_path_sha256"] = ["bogus"]
        with self.assertRaises(InputError):
            verify_consistency(older, newer, changed, policy)

    def test_key_or_signed_root_substitution_rejected(self):
        older, newer, proof, policy = signed_fixture(3, 9)
        changed = copy.deepcopy(policy)
        changed["key"]["public_key_base64"] = public(Ed25519PrivateKey.generate())
        with self.assertRaises(InputError):
            verify_consistency(older, newer, proof, changed)
        changed = copy.deepcopy(newer)
        changed["checkpoint"]["root_sha256"] = "0" * 64
        with self.assertRaises(InputError):
            verify_consistency(older, changed, proof, policy)
        changed = copy.deepcopy(older)
        changed["signature_base64"] = b64(b"\x00" * 64)
        with self.assertRaises(InputError):
            verify_consistency(changed, newer, proof, policy)

    def test_rollback_floor_and_reverse_order_rejected(self):
        older, newer, proof, policy = signed_fixture(3, 7)
        changed = copy.deepcopy(policy)
        changed["minimum_tree_size"] = 8
        with self.assertRaises(InputError):
            verify_consistency(older, newer, proof, changed)
        with self.assertRaises(InputError):
            verify_consistency(newer, older, proof, policy)

    def test_equal_tree_size_requires_identical_root_and_empty_proof(self):
        older, newer, proof, policy = signed_fixture(4, 4)
        result = verify_consistency(older, newer, proof, policy)
        self.assertFalse(result["tree_growth_proven"])
        changed = copy.deepcopy(proof)
        changed["consistency_path_sha256"] = ["0" * 64]
        with self.assertRaises(InputError):
            verify_consistency(older, newer, changed, policy)
        older, newer, proof, policy = signed_fixture(4, 4, tampered_history=True)
        with self.assertRaises(InputError):
            verify_consistency(older, newer, proof, policy)

    def test_power_of_two_prefix_and_one_leaf(self):
        for m, n in ((1, 2), (1, 15), (2, 3), (4, 9), (8, 17), (16, 31)):
            older, newer, proof, policy = signed_fixture(m, n)
            result = verify_consistency(older, newer, proof, policy)
            self.assertTrue(result["merkle_consistency_valid"])

    def test_cli_private_receipt_and_no_overwrite(self):
        older, newer, proof, policy = signed_fixture(4, 11)
        with tempfile.TemporaryDirectory() as folder:
            inputs = [(Path(folder) / name, data) for name, data in
                      (("old.json", older), ("new.json", newer),
                       ("proof.json", proof), ("log-trust.json", policy))]
            for path, payload in inputs:
                path.write_text(json.dumps(payload), encoding="utf-8")
            out = Path(folder) / "comparison.json"
            args = ["log-consistency"] + [str(path) for path, _ in inputs] + [
                "--out", str(out)]
            self.assertEqual(main(args), 0)
            self.assertTrue(json.loads(out.read_text())["merkle_consistency_valid"])
            self.assertEqual(main(args), 2)


if __name__ == "__main__":
    unittest.main()

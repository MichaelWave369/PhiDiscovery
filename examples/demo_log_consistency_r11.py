"""Create a SYNTHETIC two-checkpoint Merkle consistency demonstration.

Both checkpoints are signed by one ephemeral local key. There is no real
third-party log, independent historical copy or authenticated clock. No
signing keys are saved. This demo is NOT evidence of real-world chronology.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from phidiscovery.consistency import PROOF_SCHEMA
from phidiscovery.engine import stable_bytes
from phidiscovery.reviewers import save_private_receipt, validate_private_path
from phidiscovery.transparency import CHECKPOINT_SCHEMA, TRUST_SCHEMA, node_hash


def root(digests):
    if len(digests) == 1:
        return digests[0]
    k = 1 << ((len(digests) - 1).bit_length() - 1)
    return node_hash(root(digests[:k]), root(digests[k:]))


def reference_subproof(m, digests, complete=True):
    """Minimal consistency path per RFC 9162, independent of verifier code."""
    if m == len(digests):
        return [] if complete else [root(digests)]
    k = 1 << ((len(digests) - 1).bit_length() - 1)
    if m <= k:
        return reference_subproof(m, digests[:k], complete) + [root(digests[k:])]
    return reference_subproof(m - k, digests[k:], False) + [root(digests[:k])]


def make_envelope(private_key, size, leaves):
    checkpoint = {
        "schema": CHECKPOINT_SCHEMA,
        "log_id": "synthetic-r11-two-checkpoint-demo",
        "tree_size": size,
        "root_sha256": root(leaves[:size]).hex(),
        # Deliberately false: key possession does not prove a real clock.
        "claimed_issued_at": "2000-01-01T00:00:00Z",
    }
    signature = private_key.sign(stable_bytes(checkpoint))
    return {
        "checkpoint": checkpoint,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Create fictitious old/new signed roots, not a real log history")
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="Existing private folder outside repository")
    args = parser.parse_args()
    out = {
        "old": args.out_dir / "demo-r11-older.json",
        "new": args.out_dir / "demo-r11-newer.json",
        "proof": args.out_dir / "demo-r11-proof.json",
        "trust": args.out_dir / "demo-r11-log-trust.json",
    }
    for destination in out.values():
        validate_private_path(destination)

    old_size, new_size = 3, 7
    leaves = [hashlib.sha256(b"\x00" + f"FICTIONAL-LOG-RECORD-{i}".encode()).digest()
              for i in range(new_size)]
    signer = Ed25519PrivateKey.generate()
    old_env = make_envelope(signer, old_size, leaves)
    new_env = make_envelope(signer, new_size, leaves)
    proof = {
        "schema": PROOF_SCHEMA,
        "log_id": old_env["checkpoint"]["log_id"],
        "older_size": old_size,
        "newer_size": new_size,
        "consistency_path_sha256": [
            value.hex() for value in reference_subproof(old_size, leaves)
        ],
    }
    pub = signer.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    trust = {
        "schema": TRUST_SCHEMA,
        "log_id": old_env["checkpoint"]["log_id"],
        "key": {
            "key_id": "synthetic-r11-ephemeral-signing-key",
            "public_key_base64": base64.b64encode(pub).decode("ascii"),
        },
        "minimum_tree_size": old_size,
    }
    for name, payload in (
        ("old", old_env), ("new", new_env), ("proof", proof), ("trust", trust)
    ):
        save_private_receipt(payload, out[name])
    print("SYNTHETIC only: two checkpoint signatures valid, "
          "old root NOT independently retained, date 2000 is NOT real.")
    print("Use these private test files with: python -m phidiscovery log-consistency")


if __name__ == "__main__":
    main()

"""Generate a synthetic, signed log checkpoint with ephemeral log key.

WARNING: THIS IS NOT A REAL TRANSPARENCY LOG OR EXTERNAL TIMESTAMP.
Both checkpoint and key are produced locally; no public witness exists.
No private keys are persisted. Only use fictional/test-only artifacts.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from phidiscovery.engine import stable_bytes
from phidiscovery.provenance import load_strict_json
from phidiscovery.reviewers import save_private_receipt, validate_private_path
from phidiscovery.transparency import (
    CHECKPOINT_SCHEMA, LOG_ENTRY_SCHEMA, PROOF_SCHEMA, TRUST_SCHEMA,
    entry_for, leaf_hash, node_hash,
)


def root(leaves):
    if len(leaves) == 1:
        return leaves[0]
    split = 1 << ((len(leaves) - 1).bit_length() - 1)
    return node_hash(root(leaves[:split]), root(leaves[split:]))


def path(leaves, index):
    if len(leaves) == 1:
        return []
    split = 1 << ((len(leaves) - 1).bit_length() - 1)
    if index < split:
        return path(leaves[:split], index) + [root(leaves[split:])]
    return path(leaves[split:], index - split) + [root(leaves[:split])]


def main():
    parser = argparse.ArgumentParser(
        description="Synthetic R1.0 log inclusion fixture, NOT an independent external anchor")
    parser.add_argument("artifact", type=Path)
    parser.add_argument("anchor", type=Path)
    parser.add_argument("publisher_trust", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    proof_dest = args.out_dir / "demo-log-proof.json"
    trust_dest = args.out_dir / "demo-log-trust.json"
    validate_private_path(proof_dest)
    validate_private_path(trust_dest)

    artifact = load_strict_json(args.artifact)
    anchor = load_strict_json(args.anchor)
    publisher_trust = load_strict_json(args.publisher_trust)
    entry = entry_for(artifact, anchor, publisher_trust)
    leaves = [leaf_hash({"schema": LOG_ENTRY_SCHEMA, "synthetic_decoy": i})
              for i in range(5)]
    leaves[3] = leaf_hash(entry)
    signer = Ed25519PrivateKey.generate()
    public = signer.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    checkpoint = {
        "schema": CHECKPOINT_SCHEMA,
        "log_id": "synthetic-r10-local-log",
        "tree_size": len(leaves),
        "root_sha256": root(leaves).hex(),
        "claimed_issued_at": "2000-01-01T00:00:00Z",
    }
    proof = {
        "schema": PROOF_SCHEMA,
        "leaf_index": 3, "tree_size": len(leaves),
        "audit_path_sha256": [value.hex() for value in path(leaves, 3)],
        "checkpoint": checkpoint,
        "signature_base64": base64.b64encode(
            signer.sign(stable_bytes(checkpoint))).decode("ascii"),
    }
    trust = {
        "schema": TRUST_SCHEMA,
        "log_id": "synthetic-r10-local-log",
        "key": {"key_id": "synthetic-r10-log-key",
                "public_key_base64": base64.b64encode(public).decode("ascii")},
        "minimum_tree_size": 1,
    }
    save_private_receipt(proof, proof_dest)
    save_private_receipt(trust, trust_dest)
    print("TEST-ONLY synthetic signed checkpoint, false claimed clock, "
          "no independent operator and NO authenticated timestamp.")
    print(f"Proof: {proof_dest}")
    print(f"Untrusted test log key: {trust_dest}")


if __name__ == "__main__":
    main()

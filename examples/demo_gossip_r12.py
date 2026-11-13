"""Synthetic cross-observer log gossip scenarios. No real observers or clocks.

The log signing key and both observer keys are generated inside one process.
This is ONLY a software test of mathematical signatures and conflict rules.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from phidiscovery.engine import sha256, stable_bytes
from phidiscovery.gossip import (
    GOSSIP_SCHEMA, TRUST_SCHEMA, draft_observation,
)
from phidiscovery.consistency import PROOF_SCHEMA
from phidiscovery.reviewers import save_private_receipt, validate_private_path
from phidiscovery.transparency import CHECKPOINT_SCHEMA, TRUST_SCHEMA as LOG_TRUST, node_hash


def b64(value):
    return base64.b64encode(value).decode("ascii")


def pub(key):
    return b64(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def root(values):
    if len(values) == 1:
        return values[0]
    k = 1 << ((len(values) - 1).bit_length() - 1)
    return node_hash(root(values[:k]), root(values[k:]))


def subproof(m, values, complete=True):
    if m == len(values):
        return [] if complete else [root(values)]
    k = 1 << ((len(values) - 1).bit_length() - 1)
    if m <= k:
        return subproof(m, values[:k], complete) + [root(values[k:])]
    return subproof(m - k, values[k:], False) + [root(values[:k])]


def signed_checkpoint(signing_key, values):
    checkpoint = {
        "schema": CHECKPOINT_SCHEMA,
        "log_id": "fictional-shared-log",
        "tree_size": len(values),
        "root_sha256": root(values).hex(),
        "claimed_issued_at": "2000-01-01T00:00:00Z",
    }
    return {
        "checkpoint": checkpoint,
        "signature_base64": b64(signing_key.sign(stable_bytes(checkpoint))),
    }


def build_demo(scenario="conflict"):
    if scenario not in ("conflict", "unresolved", "consistent"):
        raise ValueError("Expected conflict, unresolved, or consistent demo")
    log_key = Ed25519PrivateKey.generate()
    observer_a, observer_b = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    records = [hashlib.sha256(f"FICTIONAL-LOG-{i}".encode()).digest()
               for i in range(7)]
    older = signed_checkpoint(log_key, records[:3])
    if scenario == "conflict":
        modified = records[:3]
        modified[1] = hashlib.sha256(b"FICTIONAL-REWRITTEN").digest()
        newer = signed_checkpoint(log_key, modified)
    else:
        newer = signed_checkpoint(log_key, records)
    receipts = []
    for oid, key, cp in (
        ("observer-A", observer_a, older), ("observer-B", observer_b, newer)
    ):
        claim = draft_observation(cp, oid, "2000-01-01T00:00:00Z")
        receipts.append({
            "checkpoint": cp,
            "observer_id": oid,
            "claim": claim,
            "signature_base64": b64(key.sign(stable_bytes(claim))),
        })
    proofs = []
    if scenario == "consistent":
        proofs.append({
            "older_checkpoint_sha256": sha256(older),
            "newer_checkpoint_sha256": sha256(newer),
            "proof": {
                "schema": PROOF_SCHEMA,
                "log_id": "fictional-shared-log",
                "older_size": 3,
                "newer_size": 7,
                "consistency_path_sha256": [
                    h.hex() for h in subproof(3, records)
                ],
            },
        })
    bundle = {
        "schema": GOSSIP_SCHEMA,
        "log_id": "fictional-shared-log",
        "observations": receipts,
        "consistency_proofs": proofs,
    }
    trust = {
        "schema": TRUST_SCHEMA,
        "log_trust": {
            "schema": LOG_TRUST,
            "log_id": "fictional-shared-log",
            "key": {
                "key_id": "fictional-log-operator-key",
                "public_key_base64": pub(log_key),
            },
            "minimum_tree_size": 1,
        },
        "observer_keys": [
            {"observer_id": "observer-A", "key": {
                "key_id": "fictional-observer-a-key",
                "public_key_base64": pub(observer_a),
            }},
            {"observer_id": "observer-B", "key": {
                "key_id": "fictional-observer-b-key",
                "public_key_base64": pub(observer_b),
            }},
        ],
    }
    return bundle, trust


def main():
    parser = argparse.ArgumentParser(description="Create fictional signed cross-observer log views")
    parser.add_argument("--scenario", choices=("conflict", "unresolved", "consistent"),
                        default="conflict")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    out_bundle = args.out_dir / f"demo-r12-{args.scenario}-gossip.json"
    out_trust = args.out_dir / f"demo-r12-{args.scenario}-trust.json"
    validate_private_path(out_bundle)
    validate_private_path(out_trust)
    bundle, trust = build_demo(args.scenario)
    save_private_receipt(bundle, out_bundle)
    save_private_receipt(trust, out_trust)
    print(f"Created SYNTHETIC {args.scenario} demo with ephemeral keys and fake clock.")
    print("No observer independence, public log, or real timestamp is verified.")


if __name__ == "__main__":
    main()

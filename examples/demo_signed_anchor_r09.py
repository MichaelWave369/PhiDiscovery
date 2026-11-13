"""TEST-ONLY generator of an R0.9 signed anchor.

Both keys are generated in the SAME process and discarded. This does NOT
constitute an independent witness or externally verified timestamp. Do not
use it to establish preregistration chronology or scientific provenance.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from phidiscovery.engine import stable_bytes
from phidiscovery.provenance import (
    ANCHOR_SCHEMA, TRUST_SCHEMA, draft_publisher_claim, draft_witness_claim,
)
from phidiscovery.reviewers import save_private_receipt, validate_private_path


def b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def public(key: Ed25519PrivateKey) -> str:
    return b64(key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Synthetic signature demo; NOT a credible independent timestamp.")
    ap.add_argument("artifact", type=Path, help="Existing PhiDiscovery receipt JSON")
    ap.add_argument("--out-dir", type=Path, required=True,
                    help="Existing private directory outside Git")
    args = ap.parse_args()
    anchor_path = args.out_dir / "demo-anchor.json"
    trust_path = args.out_dir / "demo-trust.json"
    validate_private_path(anchor_path)
    validate_private_path(trust_path)

    raw = args.artifact.read_bytes()
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("Artifact exceeds 20 MiB cap")
    artifact = json.loads(raw)
    claim = draft_publisher_claim(artifact)
    publisher_key, witness_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    pub_signature = b64(publisher_key.sign(stable_bytes(claim)))
    # Deliberately implausible signed timestamp: signatures cannot prove a real clock.
    witness_claim = draft_witness_claim(
        artifact, claim, pub_signature, "2000-01-01T00:00:00Z")
    anchor = {
        "schema": ANCHOR_SCHEMA,
        "publisher": {
            "key_id": "SYNTHETIC-publisher-ephemeral",
            "claim": claim,
            "signature_base64": pub_signature,
        },
        "witness": {
            "key_id": "SYNTHETIC-witness-ephemeral",
            "claim": witness_claim,
            "signature_base64": b64(witness_key.sign(stable_bytes(witness_claim))),
        },
    }
    trust = {
        "schema": TRUST_SCHEMA,
        "publisher": {
            "key_id": "SYNTHETIC-publisher-ephemeral",
            "public_key_base64": public(publisher_key),
        },
        "witness": {
            "key_id": "SYNTHETIC-witness-ephemeral",
            "public_key_base64": public(witness_key),
        },
    }
    save_private_receipt(anchor, anchor_path)
    save_private_receipt(trust, trust_path)
    print("TEST-ONLY SIGNATURES CREATED. Keys and clock are not independently trusted.")
    print(f"Signed sample: {anchor_path}")
    print(f"Untrusted demo public keys: {trust_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

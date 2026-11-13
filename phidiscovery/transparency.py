"""ΦDiscovery R1.0: signed transparency checkpoint and Merkle inclusion proof.

Offline verification of a separately pinned Ed25519 log signer and a Merkle
proof binding an existing R0.9 signed research anchor to the signed log root.

No proof of real log independence, actual time, append-only consistency,
signer identity, or scientific validity. No remote calls or key generation.
"""
from __future__ import annotations

import hashlib

from .engine import InputError, sha256, stable_bytes
from .predictions import _keys, _text
from .provenance import (
    _b64, _digest, _timestamp, _trust_key, _verify_signature, verify_anchor,
)

LOG_ENTRY_SCHEMA = "phidiscovery.log-entry.v1.0"
PROOF_SCHEMA = "phidiscovery.log-inclusion.v1.0"
CHECKPOINT_SCHEMA = "phidiscovery.log-checkpoint.v1.0"
TRUST_SCHEMA = "phidiscovery.log-trust.v1.0"
REPORT_SCHEMA = "phidiscovery.log-verification.v1.0"
MAX_TREE_SIZE = 1_000_000
MAX_PATH = 64


def _strict_int(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise InputError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def entry_for(artifact: dict, anchor: dict, publisher_trust: dict) -> dict:
    """Canonical log entry binds the receipt and the entire R0.9 trust policy."""
    # Never create a meaningful log leaf for an unverified publisher/witness.
    verified = verify_anchor(artifact, anchor, publisher_trust)
    return {
        "schema": LOG_ENTRY_SCHEMA,
        "artifact_sha256": verified["artifact_sha256"],
        "anchor_sha256": verified["anchor_sha256"],
        "publisher_trust_sha256": verified["trust_policy_sha256"],
    }


def leaf_hash(entry: dict) -> bytes:
    """RFC6962-style leaf hash, using canonical UTF-8 JSON as the leaf payload."""
    return hashlib.sha256(b"\x00" + stable_bytes(entry)).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    """Domain-separated RFC6962-style internal hash."""
    return hashlib.sha256(b"\x01" + left + right).digest()


def _largest_power_less_than(n: int) -> int:
    return 1 << ((n - 1).bit_length() - 1)


def reconstruct_root(leaf_digest: bytes, index: int, size: int,
                     path: list[bytes]) -> bytes:
    """Reconstruct an unbalanced RFC6962 Merkle inclusion root.

    The audit path is ordered from the leaf upward. Each recursive branch
    consumes precisely one sibling after reconstructing its lower subtree.
    """
    _strict_int(size, "tree size", 1, MAX_TREE_SIZE)
    _strict_int(index, "leaf index", 0, size - 1)
    if type(leaf_digest) is not bytes or len(leaf_digest) != 32:
        raise InputError("Leaf digest must be 32 bytes")
    if type(path) is not list or len(path) > MAX_PATH or any(
        type(p) is not bytes or len(p) != 32 for p in path
    ):
        raise InputError("Audit path contains invalid binary digest(s)")
    cursor = iter(path)

    def walk(m: int, n: int) -> bytes:
        if n == 1:
            return leaf_digest
        k = _largest_power_less_than(n)
        if m < k:
            child = walk(m, k)
            try:
                sibling = next(cursor)
            except StopIteration as exc:
                raise InputError("Merkle path is missing a sibling hash") from exc
            return node_hash(child, sibling)
        child = walk(m - k, n - k)
        try:
            sibling = next(cursor)
        except StopIteration as exc:
            raise InputError("Merkle path is missing a sibling hash") from exc
        return node_hash(sibling, child)

    root = walk(index, size)
    if next(cursor, None) is not None:
        raise InputError("Merkle path has extra sibling hashes")
    return root


def verify_log_inclusion(
    artifact: dict, anchor: dict, publisher_trust: dict,
    proof: dict, log_trust: dict,
) -> dict:
    """Verify R0.9 signatures, log signature and exact Merkle inclusion.

    The log's public key is explicitly pinned by operator, never inferred from
    the proof; distinct keys are necessary but insufficient for independence.
    """
    entry = entry_for(artifact, anchor, publisher_trust)
    _keys(log_trust, {"schema", "log_id", "key", "minimum_tree_size"},
          "log trust policy")
    if log_trust["schema"] != TRUST_SCHEMA:
        raise InputError("Unsupported log trust-policy schema")
    log_id = _text(log_trust["log_id"], "log_id", cap=120)
    key_id, key = _trust_key(log_trust["key"], "log key")
    minimum = _strict_int(log_trust["minimum_tree_size"],
                          "minimum_tree_size", 1, MAX_TREE_SIZE)
    publisher = _trust_key(publisher_trust["publisher"], "publisher")
    witness = _trust_key(publisher_trust["witness"], "witness")
    if key in (publisher[1], witness[1]) or key_id in (publisher[0], witness[0]):
        raise InputError("Log signer must use a distinct key and key ID")
    _keys(proof, {"schema", "leaf_index", "tree_size", "audit_path_sha256",
                  "checkpoint", "signature_base64"}, "log inclusion proof")
    if proof["schema"] != PROOF_SCHEMA:
        raise InputError("Unsupported inclusion proof schema")
    size = _strict_int(proof["tree_size"], "tree_size", 1, MAX_TREE_SIZE)
    index = _strict_int(proof["leaf_index"], "leaf_index", 0, size - 1)
    if size < minimum:
        raise InputError("Checkpoint is below the independently retained minimum tree size")
    path_values = proof["audit_path_sha256"]
    if type(path_values) is not list or len(path_values) > MAX_PATH:
        raise InputError("Merkle path exceeds bounded sibling count")
    path = [bytes.fromhex(_digest(value, "audit path hash")) for value in path_values]
    checkpoint = proof["checkpoint"]
    _keys(checkpoint, {"schema", "log_id", "tree_size", "root_sha256",
                       "claimed_issued_at"}, "log checkpoint")
    if checkpoint["schema"] != CHECKPOINT_SCHEMA:
        raise InputError("Unsupported log checkpoint schema")
    if type(checkpoint["log_id"]) is not str or checkpoint["log_id"] != log_id:
        raise InputError("Checkpoint log does not match pinned log identifier")
    if type(checkpoint["tree_size"]) is not int or checkpoint["tree_size"] != size:
        raise InputError("Signed checkpoint tree size and proof size differ")
    claimed_at = checkpoint["claimed_issued_at"]
    _timestamp(claimed_at)
    _digest(checkpoint["root_sha256"], "checkpoint root")
    signature = _b64(proof["signature_base64"], 64, "log checkpoint signature")
    _verify_signature(key, signature, checkpoint)

    calculated = reconstruct_root(leaf_hash(entry), index, size, path)
    if calculated.hex() != checkpoint["root_sha256"]:
        raise InputError("Merkle inclusion proof does not match signed log root")

    return {
        "schema": REPORT_SCHEMA,
        "artifact_sha256": entry["artifact_sha256"],
        "anchor_sha256": entry["anchor_sha256"],
        "publisher_trust_sha256": entry["publisher_trust_sha256"],
        "entry_sha256": sha256(entry),
        "merkle_leaf_sha256": leaf_hash(entry).hex(),
        "proof_sha256": sha256(proof),
        "log_trust_sha256": sha256(log_trust),
        "log_id": log_id,
        "log_key_id": key_id,
        "log_public_key_sha256": hashlib.sha256(key).hexdigest(),
        "checkpoint_root_sha256": checkpoint["root_sha256"],
        "tree_size": size,
        "leaf_index": index,
        "minimum_tree_size_enforced": minimum,
        "publisher_witness_signatures_valid": True,
        "log_checkpoint_signature_valid": True,
        "merkle_inclusion_valid": True,
        "three_distinct_public_keys_used": True,
        "inclusion_in_supplied_signed_checkpoint_verified": True,
        "independent_log_operator_identity_verified": False,
        "checkpoint_issued_at_claim_unverified": claimed_at,
        "external_time_source_verified": False,
        "append_only_consistency_verified": False,
        "equivocation_excluded": False,
        "real_world_preregistration_verified": False,
        "hypothesis_validated": False,
        "verification_status": "SIGNED_CHECKPOINT_AND_INCLUSION_VALID__IDENTITY_TIME_CONSISTENCY_UNVERIFIED",
        "note": (
            "The receipt is mathematically included in a checkpoint signed by "
            "the operator-pinned log key. A signed root does not establish "
            "log independence, an honest clock, public availability, "
            "append-only behavior, consistency across checkpoints, or "
            "scientific validity. The operator must independently obtain and "
            "authenticate the log trust key and checkpoint context."
        ),
    }

"""Second Map R1.1: verify append-only consistency across TWO signed log roots.

Checks RFC 9162 Section 2.1.4 consistency proof math for the SHA-256
RFC6962-style Merkle tree used by PhiDiscovery R1.0. No external log server,
witness gossip, source identity or trusted timestamp is contacted or verified.
"""
from __future__ import annotations

import hashlib

from .engine import InputError, sha256
from .predictions import _keys, _text
from .provenance import _b64, _digest, _timestamp, _trust_key, _verify_signature
from .transparency import (
    CHECKPOINT_SCHEMA, TRUST_SCHEMA, MAX_TREE_SIZE, MAX_PATH,
    _strict_int, node_hash,
)

PROOF_SCHEMA = "phidiscovery.log-consistency.v1.1"
REPORT_SCHEMA = "phidiscovery.consistency-verification.v1.1"


def _signed_checkpoint(envelope: object, log_id: str, key: bytes) -> dict:
    """Validate exact signed R1.0 checkpoint under a separately pinned log key."""
    _keys(envelope, {"checkpoint", "signature_base64"}, "signed checkpoint envelope")
    checkpoint = envelope["checkpoint"]
    _keys(checkpoint, {"schema", "log_id", "tree_size", "root_sha256",
                       "claimed_issued_at"}, "checkpoint")
    if checkpoint["schema"] != CHECKPOINT_SCHEMA:
        raise InputError("Unsupported checkpoint schema")
    if type(checkpoint["log_id"]) is not str or checkpoint["log_id"] != log_id:
        raise InputError("Signed checkpoint refers to a different log")
    _strict_int(checkpoint["tree_size"], "checkpoint.tree_size", 1, MAX_TREE_SIZE)
    _digest(checkpoint["root_sha256"], "checkpoint.root_sha256")
    _timestamp(checkpoint["claimed_issued_at"])
    sig = _b64(envelope["signature_base64"], 64, "checkpoint signature")
    _verify_signature(key, sig, checkpoint)
    return checkpoint


def validate_consistency_path(old_size: int, new_size: int,
                              old_root: bytes, new_root: bytes,
                              path: list[bytes]) -> None:
    """RFC 9162 §2.1.4.2 consistency verification, no log/network operations."""
    _strict_int(old_size, "old_size", 1, MAX_TREE_SIZE)
    _strict_int(new_size, "new_size", old_size, MAX_TREE_SIZE)
    if any(type(d) is not bytes or len(d) != 32 for d in (old_root, new_root)):
        raise InputError("Consistency roots must be 32-byte digests")
    if type(path) is not list or len(path) > MAX_PATH or any(
        type(x) is not bytes or len(x) != 32 for x in path
    ):
        raise InputError("Malformed consistency audit path")
    if old_size == new_size:
        if path or old_root != new_root:
            raise InputError("Equal-size signed checkpoints require identical roots and empty path")
        return
    if not path:
        raise InputError("Growing trees require a nonempty Merkle consistency path")

    # For a power-of-two prefix, the old root is the first known subtree
    # and must be prepended, per RFC 9162 §2.1.4.2.
    nodes = ([old_root] if old_size & (old_size - 1) == 0 else []) + path
    fn, sn = old_size - 1, new_size - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    fr = sr = nodes[0]
    for sibling in nodes[1:]:
        if sn == 0:
            raise InputError("Consistency path has extra nodes")
        if (fn & 1) or (fn == sn):
            fr = node_hash(sibling, fr)
            sr = node_hash(sibling, sr)
            if not (fn & 1):
                while fn != 0 and not (fn & 1):
                    fn >>= 1
                    sn >>= 1
        else:
            sr = node_hash(sr, sibling)
        fn >>= 1
        sn >>= 1
    if sn != 0 or fr != old_root or sr != new_root:
        raise InputError("Consistency proof does not bind BOTH signed Merkle roots")


def verify_consistency(older: dict, newer: dict, proof: dict,
                       log_trust: dict) -> dict:
    """Verify same pinned log key signed two roots and proof links their history.

    The older checkpoint MUST have been acquired and retained independently
    before the newer one to supply a meaningful historical anchor. This
    function cannot authenticate when files were acquired or whether all
    clients saw the same checkpoints.
    """
    _keys(log_trust, {"schema", "log_id", "key", "minimum_tree_size"},
          "log trust policy")
    if log_trust["schema"] != TRUST_SCHEMA:
        raise InputError("Unsupported log trust policy")
    log_id = _text(log_trust["log_id"], "log_id", cap=120)
    key_id, pub = _trust_key(log_trust["key"], "log key")
    minimum = _strict_int(log_trust["minimum_tree_size"],
                          "minimum_tree_size", 1, MAX_TREE_SIZE)
    old_cp = _signed_checkpoint(older, log_id, pub)
    new_cp = _signed_checkpoint(newer, log_id, pub)
    old_size = old_cp["tree_size"]
    new_size = new_cp["tree_size"]
    if new_size < old_size:
        raise InputError("Newer checkpoint is smaller than the retained older checkpoint")
    if new_size < minimum:
        raise InputError("Newer checkpoint violates the pinned tree-size floor")
    _keys(proof, {"schema", "log_id", "older_size", "newer_size",
                  "consistency_path_sha256"}, "consistency proof")
    if proof["schema"] != PROOF_SCHEMA:
        raise InputError("Unsupported consistency proof schema")
    if type(proof["log_id"]) is not str or proof["log_id"] != log_id:
        raise InputError("Consistency proof refers to another log")
    if type(proof["older_size"]) is not int or proof["older_size"] != old_size:
        raise InputError("Consistency proof older size differs from signed checkpoint")
    if type(proof["newer_size"]) is not int or proof["newer_size"] != new_size:
        raise InputError("Consistency proof newer size differs from signed checkpoint")
    raw_nodes = proof["consistency_path_sha256"]
    if type(raw_nodes) is not list or len(raw_nodes) > MAX_PATH:
        raise InputError("Consistency proof path exceeds limits")
    path = [bytes.fromhex(_digest(x, "consistency path digest")) for x in raw_nodes]
    validate_consistency_path(
        old_size, new_size,
        bytes.fromhex(old_cp["root_sha256"]),
        bytes.fromhex(new_cp["root_sha256"]),
        path,
    )
    return {
        "schema": REPORT_SCHEMA,
        "log_id": log_id,
        "log_key_id": key_id,
        "log_public_key_sha256": hashlib.sha256(pub).hexdigest(),
        "log_trust_sha256": sha256(log_trust),
        "older_checkpoint_sha256": sha256(older),
        "newer_checkpoint_sha256": sha256(newer),
        "consistency_proof_sha256": sha256(proof),
        "older_tree_size": old_size,
        "newer_tree_size": new_size,
        "older_root_sha256": old_cp["root_sha256"],
        "newer_root_sha256": new_cp["root_sha256"],
        "minimum_tree_size_enforced": minimum,
        "signed_checkpoints_valid": True,
        "merkle_consistency_valid": True,
        "tree_growth_proven": new_size > old_size,
        "history_consistent_between_supplied_signed_roots": True,
        "older_checkpoint_independently_retained_verified": False,
        "log_operator_identity_verified": False,
        "log_key_uncompromised_verified": False,
        "external_time_verified": False,
        "cross_client_non_equivocation_verified": False,
        "entire_log_lifetime_append_only_verified": False,
        "experimental_evidence_verified": False,
        "hypothesis_validated": False,
        "claimed_older_issued_at_unverified": old_cp["claimed_issued_at"],
        "claimed_newer_issued_at_unverified": new_cp["claimed_issued_at"],
        "status": "SIGNED_ROOTS_CONSISTENT__INDEPENDENT_HISTORY_NOT_ATTESTED",
        "note": (
            "The two signed roots are append-only consistent under the pinned "
            "public key according to the supplied Merkle proof. This does not "
            "establish when either checkpoint existed, whether the older checkpoint "
            "was independently retained, real-world log identity, log continuity "
            "outside this interval, or absence of split views."
        ),
    }

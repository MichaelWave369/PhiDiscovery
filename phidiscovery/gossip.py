"""PhiDiscovery R1.2: offline cross-observer signed-checkpoint gossip audit.

Verifies observer-signed statements about separately supplied log-signed
checkpoints, detects *same-size* incompatible roots, and reconciles
different-size checkpoints ONLY when an R1.1 consistency proof is supplied.
Signatures are not evidence of real identities, trusted timestamps, or
historical independence. No network, signers or scientific experiments.
"""
from __future__ import annotations

from itertools import combinations

from .engine import InputError, sha256
from .predictions import _keys, _text
from .provenance import _b64, _timestamp, _trust_key, _verify_signature
from .transparency import TRUST_SCHEMA as LOG_TRUST_SCHEMA
from .consistency import _signed_checkpoint, verify_consistency

GOSSIP_SCHEMA = "phidiscovery.observer-gossip.v1.2"
CLAIM_SCHEMA = "phidiscovery.observer-claim.v1.2"
TRUST_SCHEMA = "phidiscovery.observer-trust.v1.2"
REPORT_SCHEMA = "phidiscovery.gossip-report.v1.2"
MAX_OBSERVERS = 16
MAX_OBSERVATIONS = 64
MAX_PROOFS = 128


def draft_observation(checkpoint_envelope: dict, observer_id: str,
                      claimed_seen_at: str) -> dict:
    """Canonical claim to sign offline with an observer-owned Ed25519 key."""
    _text(observer_id, "observer_id", cap=120)
    _timestamp(claimed_seen_at)
    if type(checkpoint_envelope) is not dict:
        raise InputError("Checkpoint envelope must be an object")
    return {
        "schema": CLAIM_SCHEMA,
        "observer_id": observer_id,
        "checkpoint_envelope_sha256": sha256(checkpoint_envelope),
        "claimed_seen_at": claimed_seen_at,
    }


def audit_gossip(bundle: dict, trust: dict) -> dict:
    """Validate signed observations and optionally prove cross-size history.

    A conflict is signed by the pinned *log key*, not proof of two honest
    real-world observers. A signature over a claim proves only that the
    corresponding observer private key was used to sign that claim.
    """
    _keys(trust, {"schema", "log_trust", "observer_keys"}, "gossip trust policy")
    if trust["schema"] != TRUST_SCHEMA:
        raise InputError("Unsupported gossip trust policy")
    log_trust = trust["log_trust"]
    _keys(log_trust, {"schema", "log_id", "key", "minimum_tree_size"}, "log trust")
    if log_trust["schema"] != LOG_TRUST_SCHEMA:
        raise InputError("Unsupported log trust schema")
    log_id = _text(log_trust["log_id"], "log_id", cap=120)
    log_key_id, log_pub = _trust_key(log_trust["key"], "log key")

    keys = trust["observer_keys"]
    if type(keys) is not list or not 2 <= len(keys) <= MAX_OBSERVERS:
        raise InputError("Require 2..16 distinct pinned observer keys")
    pinned = {}
    ids, pubkeys = {log_key_id}, {log_pub}
    for item in keys:
        _keys(item, {"observer_id", "key"}, "observer trust")
        oid = _text(item["observer_id"], "observer_id", cap=120)
        kid, key = _trust_key(item["key"], "observer key")
        if oid in pinned or kid in ids or key in pubkeys:
            raise InputError("Observer and log keys/IDs must be distinct")
        ids.add(kid)
        pubkeys.add(key)
        pinned[oid] = (kid, key)

    _keys(bundle, {"schema", "log_id", "observations", "consistency_proofs"},
          "gossip bundle")
    if bundle["schema"] != GOSSIP_SCHEMA or bundle["log_id"] != log_id:
        raise InputError("Gossip bundle schema or log ID mismatch")
    observations = bundle["observations"]
    if type(observations) is not list or not 2 <= len(observations) <= MAX_OBSERVATIONS:
        raise InputError("Expected 2..64 signed observations")
    proof_rows = bundle["consistency_proofs"]
    if type(proof_rows) is not list or len(proof_rows) > MAX_PROOFS:
        raise InputError("Expected at most 128 consistency proofs")

    seen = set()
    checkpoints = {}
    observations_summary = []
    observed_ids = set()
    for row in observations:
        _keys(row, {"checkpoint", "observer_id", "claim", "signature_base64"},
              "observer receipt")
        oid = _text(row["observer_id"], "observer_id", cap=120)
        if oid not in pinned:
            raise InputError("Untrusted observer ID")
        cp = _signed_checkpoint(row["checkpoint"], log_id, log_pub)
        if cp["tree_size"] < log_trust["minimum_tree_size"]:
            raise InputError("Checkpoint below pinned tree-size floor")
        claim = row["claim"]
        _keys(claim, {"schema", "observer_id", "checkpoint_envelope_sha256",
                      "claimed_seen_at"}, "observer claim")
        if claim["schema"] != CLAIM_SCHEMA:
            raise InputError("Unexpected observer claim schema")
        expected = draft_observation(
            row["checkpoint"], oid, claim["claimed_seen_at"])
        if claim != expected:
            raise InputError("Observer claim mismatches checkpoint digest or identity")
        sig = _b64(row["signature_base64"], 64, "observer signature")
        _verify_signature(pinned[oid][1], sig, claim)
        envelope_hash = sha256(row["checkpoint"])
        receipt_key = (oid, envelope_hash)
        if receipt_key in seen:
            raise InputError("Duplicate observer/checkpoint receipt")
        seen.add(receipt_key)
        observed_ids.add(oid)
        checkpoints[envelope_hash] = row["checkpoint"]
        observations_summary.append({
            "observer_id": oid,
            "observer_key_id": pinned[oid][0],
            "checkpoint_envelope_sha256": envelope_hash,
            "tree_size": cp["tree_size"],
            "root_sha256": cp["root_sha256"],
            "claimed_seen_at_unverified": claim["claimed_seen_at"],
            "observer_signature_valid": True,
            "log_signature_valid": True,
        })
    if len(observed_ids) < 2:
        raise InputError("Need signed receipts from at least two distinct observers")

    # Compare every DISTINCT checkpoint view. If two signed tree roots share
    # the same size but disagree, a valid Merkle consistency proof cannot
    # reconcile them; preserve the signed conflict for independent review.
    unique = sorted(checkpoints.items())
    info = {digest: envelope["checkpoint"] for digest, envelope in unique}
    proof_map = {}
    for item in proof_rows:
        _keys(item, {"older_checkpoint_sha256", "newer_checkpoint_sha256",
                      "proof"}, "gossip consistency proof")
        older, newer = item["older_checkpoint_sha256"], item["newer_checkpoint_sha256"]
        if (type(older) is not str or type(newer) is not str or
                older not in checkpoints or newer not in checkpoints or older == newer):
            raise InputError("Gossip proof references unknown or identical checkpoints")
        if info[older]["tree_size"] >= info[newer]["tree_size"]:
            raise InputError("Consistency proof requires strict old-to-new size order")
        pair = (older, newer)
        if pair in proof_map:
            raise InputError("Duplicate consistency proof for a checkpoint pair")
        # Reuse R1.1 actual cryptographic verification, not an asserted flag.
        verify_consistency(checkpoints[older], checkpoints[newer],
                           item["proof"], log_trust)
        proof_map[pair] = sha256(item["proof"])

    conflicts, unresolved, consistent_pairs = [], [], []
    for (ah, a), (bh, b) in combinations(unique, 2):
        left, right = a["checkpoint"], b["checkpoint"]
        if left["tree_size"] == right["tree_size"]:
            if left["root_sha256"] != right["root_sha256"]:
                conflicts.append({
                    "tree_size": left["tree_size"],
                    "root_a_sha256": left["root_sha256"],
                    "root_b_sha256": right["root_sha256"],
                    "checkpoint_a_sha256": ah,
                    "checkpoint_b_sha256": bh,
                    "note": "Different signed roots for the same tree size under the pinned log key",
                })
        else:
            old, new = ((ah, bh) if left["tree_size"] < right["tree_size"]
                        else (bh, ah))
            if (old, new) in proof_map:
                consistent_pairs.append({
                    "older_checkpoint_sha256": old,
                    "newer_checkpoint_sha256": new,
                    "verified_proof_sha256": proof_map[(old, new)],
                })
            else:
                unresolved.append({
                    "older_checkpoint_sha256": old,
                    "newer_checkpoint_sha256": new,
                    "reason": "Different tree sizes require an R1.1 consistency proof",
                })
    if conflicts:
        status = "CONFLICTING_SIGNED_ROOTS_SAME_SIZE"
    elif unresolved:
        status = "CROSS_SIZE_CONSISTENCY_UNRESOLVED"
    else:
        status = "NO_CONFLICT_IN_SUPPLIED_SIGNED_VIEWS__INDEPENDENCE_UNVERIFIED"

    return {
        "schema": REPORT_SCHEMA,
        "log_id": log_id,
        "log_trust_sha256": sha256(log_trust),
        "observer_trust_sha256": sha256(trust),
        "gossip_bundle_sha256": sha256(bundle),
        "status": status,
        "counts": {
            "signed_observations": len(observations),
            "distinct_observers": len(observed_ids),
            "distinct_signed_checkpoints": len(checkpoints),
            "same_size_conflicts": len(conflicts),
            "cross_size_unresolved": len(unresolved),
            "cross_size_verified": len(consistent_pairs),
        },
        "observer_receipts": sorted(
            observations_summary,
            key=lambda x: (x["observer_id"], x["tree_size"],
                           x["checkpoint_envelope_sha256"])),
        "same_size_conflicts": conflicts,
        "unresolved_cross_size_pairs": unresolved,
        "verified_consistency_pairs": consistent_pairs,
        "signed_observer_statements_valid": True,
        "signed_log_checkpoints_valid": True,
        "observer_identities_authenticated_out_of_band": False,
        "different_key_owners_verified": False,
        "observation_times_verified": False,
        "checkpoint_retention_history_verified": False,
        "global_non_equivocation_proven": False,
        "hypothesis_validated": False,
        "note": (
            "Same-size conflicting signed roots are strong cryptographic evidence "
            "of incompatible supplied log views under the pinned key, not proof "
            "of malicious intent or independent witnesses. Missing cross-size "
            "consistency proofs leave relationships unresolved. No network "
            "gossip, trusted clock, identity registry or real-world provenance "
            "is independently verified."
        ),
    }

"""R0.9: verification of signed, externally supplied research anchor claims.

Public-key cryptography verifies signature/key binding, not a signer's honesty,
institutional identity, actual clock, scientific result, or independent chronology.
This module never generates or stores a private key and makes no network calls.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hashlib
import re

from .engine import InputError, sha256, stable_bytes
from .predictions import _keys, _text

REQUEST_SCHEMA = "phidiscovery.publisher-claim.v0.9"
WITNESS_SCHEMA = "phidiscovery.witness-claim.v0.9"
ANCHOR_SCHEMA = "phidiscovery.signed-anchor.v0.9"
TRUST_SCHEMA = "phidiscovery.trust-policy.v0.9"
REPORT_SCHEMA = "phidiscovery.anchor-verification.v0.9"
ARTIFACT_SCHEMAS = frozenset({
    "phidiscovery.prediction-commitment.v0.5",
    "phidiscovery.prediction-score.v0.5",
    "phidiscovery.replication-score.v0.6",
    "phidiscovery.manifest-leakage-audit.v0.7",
    "phidiscovery.content-overlap-audit.v0.8",
    "phidiscovery.revision-ledger.v0.4",
})
SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")
UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _digest(value: object, name: str) -> str:
    if type(value) is not str or not SHA_PATTERN.fullmatch(value):
        raise InputError(f"{name} must be lowercase SHA-256 hex")
    return value


def _b64(value: object, size: int, name: str) -> bytes:
    if type(value) is not str or len(value) > 200:
        raise InputError(f"{name} must be canonical base64")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise InputError(f"{name} is not base64") from exc
    if len(raw) != size or base64.b64encode(raw).decode("ascii") != value:
        raise InputError(f"{name} must decode to exactly {size} bytes and be canonical")
    return raw


def _public_key(value: object, name: str) -> bytes:
    return _b64(value, 32, name)


def _verify_signature(public_bytes: bytes, signature: bytes, message: dict) -> None:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise InputError("Signed provenance verification needs the optional cryptography package; install phidiscovery[provenance]") from exc
    try:
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature, stable_bytes(message))
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise InputError("Ed25519 signature verification failed") from exc


def draft_publisher_claim(artifact: object) -> dict:
    """Return exact canonical payload to be signed by an out-of-band publisher."""
    if type(artifact) is not dict:
        raise InputError("The research artifact must be a JSON object")
    schema = artifact.get("schema")
    if type(schema) is not str or schema not in ARTIFACT_SCHEMAS:
        raise InputError("Only recognized PhiDiscovery research receipts can be anchored")
    try:
        fingerprint = sha256(artifact)
    except (ValueError, TypeError, UnicodeError, OverflowError) as exc:
        raise InputError("Research artifact cannot be canonically serialized") from exc
    return {
        "schema": REQUEST_SCHEMA,
        "artifact_schema": schema,
        "artifact_sha256": fingerprint,
    }


def draft_witness_claim(artifact: dict, publisher_claim: dict,
                        publisher_signature_b64: str, observed_at: str) -> dict:
    """Prepare a witness payload without signing or asserting actual time."""
    expected = draft_publisher_claim(artifact)
    if publisher_claim != expected:
        raise InputError("Publisher claim does not bind the supplied research artifact")
    signature = _b64(publisher_signature_b64, 64, "publisher.signature_b64")
    _timestamp(observed_at)
    return {
        "schema": WITNESS_SCHEMA,
        "artifact_sha256": expected["artifact_sha256"],
        "publisher_claim_sha256": sha256(publisher_claim),
        "publisher_signature_sha256": hashlib.sha256(signature).hexdigest(),
        "claimed_observed_at": observed_at,
    }


def _timestamp(value: object) -> None:
    if type(value) is not str or not UTC_PATTERN.fullmatch(value):
        raise InputError("Witness must claim an explicit UTC timestamp YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError("Witness timestamp is not a valid calendar time") from exc


def _trust_key(value: object, name: str) -> tuple[str, bytes]:
    _keys(value, {"key_id", "public_key_base64"}, name)
    kid = _text(value["key_id"], f"{name}.key_id", cap=120)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", kid):
        raise InputError("Trust policy key IDs may only contain letters, digits, '.', '_', '-'")
    return kid, _public_key(value["public_key_base64"], name + ".public_key_base64")


def verify_anchor(artifact: dict, anchor: object, trust_policy: object) -> dict:
    """Verify Ed25519 publisher and witness signatures with operator-pinned keys.

    An adversary controlling the witness private key can backdate an attestation.
    The returned time therefore remains a *signed claim*, not a certified
    external timestamp. The trust-policy file is explicitly operator-selected.
    """
    publisher_claim = draft_publisher_claim(artifact)
    _keys(trust_policy, {"schema", "publisher", "witness"}, "trusted public keys")
    if trust_policy["schema"] != TRUST_SCHEMA:
        raise InputError("Unsupported trust policy schema")
    pub_id, pub_key = _trust_key(trust_policy["publisher"], "publisher")
    wit_id, wit_key = _trust_key(trust_policy["witness"], "witness")
    if pub_id == wit_id or pub_key == wit_key:
        raise InputError("Publisher and witness must use separate key IDs and public keys")
    _keys(anchor, {"schema", "publisher", "witness"}, "signed anchor")
    if anchor["schema"] != ANCHOR_SCHEMA:
        raise InputError("Unsupported signed anchor schema")
    publisher = anchor["publisher"]
    witness = anchor["witness"]
    _keys(publisher, {"key_id", "claim", "signature_base64"}, "publisher signature")
    _keys(witness, {"key_id", "claim", "signature_base64"}, "witness signature")
    if type(publisher["key_id"]) is not str or publisher["key_id"] != pub_id:
        raise InputError("Publisher signer not pinned in trust policy")
    if type(witness["key_id"]) is not str or witness["key_id"] != wit_id:
        raise InputError("Witness signer not pinned in trust policy")
    if type(publisher["claim"]) is not dict or publisher["claim"] != publisher_claim:
        raise InputError("Publisher signature claims a different artifact or schema")
    pub_signature = _b64(publisher["signature_base64"], 64, "publisher signature")
    _verify_signature(pub_key, pub_signature, publisher_claim)
    witness_claim = witness["claim"]
    _keys(witness_claim, {
        "schema", "artifact_sha256", "publisher_claim_sha256",
        "publisher_signature_sha256", "claimed_observed_at",
    }, "witness claim")
    if witness_claim["schema"] != WITNESS_SCHEMA:
        raise InputError("Unsupported witness claim schema")
    _timestamp(witness_claim["claimed_observed_at"])
    expected_witness = draft_witness_claim(
        artifact, publisher_claim, publisher["signature_base64"],
        witness_claim["claimed_observed_at"])
    if witness_claim != expected_witness:
        raise InputError("Witness attests to a different publisher claim or signature")
    wit_signature = _b64(witness["signature_base64"], 64, "witness signature")
    _verify_signature(wit_key, wit_signature, witness_claim)
    return {
        "schema": REPORT_SCHEMA,
        "artifact_schema": artifact["schema"],
        "artifact_sha256": publisher_claim["artifact_sha256"],
        "anchor_sha256": sha256(anchor),
        "trust_policy_sha256": sha256(trust_policy),
        "publisher_key_id": pub_id,
        "publisher_public_key_sha256": hashlib.sha256(pub_key).hexdigest(),
        "witness_key_id": wit_id,
        "witness_public_key_sha256": hashlib.sha256(wit_key).hexdigest(),
        "publisher_ed25519_signature_valid": True,
        "witness_ed25519_signature_valid": True,
        "two_distinct_public_keys_used": True,
        "witness_claimed_observed_at_unverified": witness_claim["claimed_observed_at"],
        "witness_identity_verified_out_of_band": False,
        "witness_actual_time_verified": False,
        "independent_timestamp_authority_verified": False,
        "independent_experimental_validation": False,
        "hypothesis_validated": False,
        "verification_status": "SIGNATURES_VALID__TRUST_AND_CHRONOLOGY_UNVERIFIED",
        "note": (
            "These Ed25519 signatures cryptographically bind the supplied artifact "
            "to two operator-pinned public keys and a witness-signed timestamp CLAIM. "
            "They do not attest who controls the keys, key independence, honest clock "
            "or when data was collected. Verify witness identity and real-world "
            "timestamp externally before claiming independently anchored chronology."
        ),
    }

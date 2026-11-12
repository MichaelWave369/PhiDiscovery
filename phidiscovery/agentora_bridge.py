"""Explicit local Agentora bridge for PhiDiscovery isolated hypothesis reviewers.

This is a transport to Agentora's *new* opt-in /api/discovery/review endpoint,
not general Agentora team orchestration. All model statements remain unverified.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .engine import InputError, sha256
from .reviewers import (
    ROLES, RECEIPTS_SCHEMA, create_packets, validate_review,
)

MAX_RESPONSE_BYTES = 64 * 1024
BRIDGE_SCHEMA = "agentora.discovery-review.v0.3"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _must_text(value: object, label: str, cap: int = 120) -> str:
    if type(value) is not str or not value.strip() or len(value) > cap:
        raise InputError(f"{label} must be nonempty text within {cap} characters")
    return value.strip()


def _post_packet(packet: dict, model: str, port: int, key: str) -> dict:
    """Send only to fixed loopback Agentora research endpoint. No redirects."""
    data = json.dumps({"packet": packet, "model": model},
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(data) > 64 * 1024:
        raise InputError("Agentora reviewer request too large")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/discovery/review",
        data=data,
        headers={"Content-Type": "application/json", "X-Discovery-Review-Key": key},
        method="POST",
    )
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect).open(req, timeout=120) as reply:
            body = reply.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise InputError("Local Agentora reviewer unavailable or refused the call") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise InputError("Local Agentora reviewer response too large")
    try:
        output = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise InputError("Agentora returned invalid UTF-8 JSON") from exc
    if type(output) is not dict:
        raise InputError("Agentora reviewer response must be an object")
    return output


def _verify_envelope(packet: dict, model: str, envelope: object) -> dict:
    """Reject mistaken role, unexpected protocol, or asserted evidence/tool use."""
    if type(envelope) is not dict:
        raise InputError("Agentora review must be an object")
    required = {
        "schema": BRIDGE_SCHEMA,
        "packet_id": packet["packet_id"],
        "candidate_id": packet["candidate_id"],
        "role": packet["role"],
        "model_requested": model,
        "source_class": "LOCAL_OLLAMA_SELF_REPORTED_NOT_ATTESTED",
        "tool_calls": 0,
        "memory_used": False,
        "evidence_verified": False,
        "human_review_required": True,
    }
    for field, value in required.items():
        if field in ("tool_calls", "memory_used", "evidence_verified", "human_review_required"):
            if type(envelope.get(field)) is not type(value) or envelope[field] != value:
                raise InputError(f"Agentora reviewer rejected due to incompatible {field}")
        elif type(envelope.get(field)) is not str or envelope[field] != value:
            raise InputError(f"Agentora reviewer rejected due to mismatched {field}")
    report = _must_text(envelope.get("model_reported_unverified"), "model_reported_unverified")
    review = validate_review(envelope.get("review"), packet)
    return {"model_reported_unverified": report, "review": review}


def execute_agentora(bundle: dict, role_models: dict, *, port: int = 8088,
                     operator_key: str, root=None, transport=None) -> dict:
    """Operator-approved sequential requests with isolated per-role packets.

    The CLI requires two explicit flags before invoking this routine.
    Tests inject transport to avoid actual HTTP/network/model activity.
    """
    if type(port) is not int or not 1 <= port <= 65535:
        raise InputError("Agentora port must be 1..65535")
    if type(operator_key) is not str or len(operator_key) < 24:
        raise InputError("Agentora operator key must be configured and at least 24 characters")
    if type(role_models) is not dict or set(role_models) != set(ROLES):
        raise InputError("Must explicitly map every reviewer role to a local model")
    models = {role: _must_text(role_models[role], f"model for {role}") for role in ROLES}
    pack = create_packets(bundle, root=root)
    receipts = []
    for packet in pack["packets"]:
        role, model = packet["role"], models[packet["role"]]
        envelope = (transport or _post_packet)(packet, model, port, operator_key)
        checked = _verify_envelope(packet, model, envelope)
        review = checked["review"]
        receipts.append({
            "packet_id": packet["packet_id"],
            "candidate_id": packet["candidate_id"],
            "role": role,
            "model_requested": model,
            "model_reported_unverified": checked["model_reported_unverified"],
            "source_class": "AGENTORA_LOCAL_SELF_REPORTED_NOT_ATTESTED",
            "review": review,
            "review_sha256": sha256(review),
        })
    return {
        "schema": RECEIPTS_SCHEMA,
        "input_sha256": pack["input_sha256"],
        "packets_sha256": sha256(pack),
        "source_class": "AGENTORA_LOCAL_SELF_REPORTED_NOT_ATTESTED",
        "bridge_schema": BRIDGE_SCHEMA,
        "human_review_required": True,
        "scientific_evidence_produced": False,
        "agentora_reviewers_called": len(receipts),
        "receipt_independence_attested": False,
        "receipts": receipts,
    }

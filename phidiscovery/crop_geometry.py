"""Strict, offline crop-fingerprint comparison -> PhiDiscovery evidence adapter.

Imports a PhiMathAtelier Fingerprint Atlas v0.3 comparison. Never upgrades
descriptive ring similarity to scientific support or proof of communication.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

from .engine import InputError, validate_bundle

SCHEMA = "phi-crop-geometry-comparison/v0.3"
PROFILE_SCHEMA = "phi-crop-fingerprint/v0.3"
METHOD = "ordered-normalized-radii-v1"
GAP = 0.22
DIFF_WEIGHT = 1.7


def _obj(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise InputError(f"{label} must be an object")
    return value


def _finite(value: Any, label: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputError(f"{label} must be finite numeric")
    result = float(value)
    if minimum is not None and result < minimum:
        raise InputError(f"{label} must be >= {minimum}")
    return result


def _profile(value: Any, label: str) -> dict:
    obj = _obj(value, label)
    if obj.get("schema") != PROFILE_SCHEMA:
        raise InputError(f"{label}.schema must be {PROFILE_SCHEMA}")
    name = obj.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise InputError(f"{label}.name required (1–120 characters)")
    radii = obj.get("radii")
    if not isinstance(radii, list) or not 2 <= len(radii) <= 12:
        raise InputError(f"{label}.radii must be an array of 2–12 numbers")
    rr = sorted(_finite(v, f"{label}.radii[{i}]", 0.00000001) for i, v in enumerate(radii))
    if rr[-1] > 1_000_000 or any(b <= a for a, b in zip(rr, rr[1:])):
        raise InputError(f"{label}.radii must be positive, distinct, and <= 1000000")
    declared_count = obj.get("ringCount")
    if declared_count is not None and (type(declared_count) is not int or declared_count != len(rr)):
        raise InputError(f"{label}.ringCount differs from actual radii")
    normalized = [round(x / rr[-1], 6) for x in rr]
    provided = obj.get("normalizedRadii")
    if provided is not None:
        if not isinstance(provided, list) or len(provided) != len(rr):
            raise InputError(f"{label}.normalizedRadii has wrong length")
        for i, (expected, got) in enumerate(zip(normalized, provided)):
            if abs(_finite(got, f"{label}.normalizedRadii[{i}]") - expected) > 0.000002:
                raise InputError(f"{label}.normalizedRadii conflicts with the raw radii")
    source_type = obj.get("sourceType", "manual")
    if not isinstance(source_type, str) or not 1 <= len(source_type) <= 80:
        raise InputError(f"{label}.sourceType invalid")
    return {"name": name.strip(), "radii": rr, "normalized": normalized,
            "source_type": source_type, "count": len(rr),
            "lineage_provided": isinstance(obj.get("lineage"), dict),
            "source_url_provided": bool(obj.get("sourceUrl"))}


def _compare(left: dict, right: dict) -> dict:
    aa, bb = left["normalized"], right["normalized"]
    m, n = len(aa), len(bb)
    dp = [[0.0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        dp[i][0] = i * GAP
    for j in range(1, n + 1):
        dp[0][j] = j * GAP
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            match = min(GAP * 2, abs(aa[i - 1] - bb[j - 1]) * DIFF_WEIGHT)
            dp[i][j] = min(dp[i - 1][j] + GAP, dp[i][j - 1] + GAP,
                           dp[i - 1][j - 1] + match)
    distance = dp[m][n] / max(m, n)
    score = round(max(0.0, 100 * (1 - distance / GAP)), 2)
    return {"score": score, "distance": round(distance, 6), "counts": [m, n]}


def import_comparison(receipt: Any, original_sha256: str | None = None) -> tuple[dict, dict]:
    """Return (engine-compatible evidence bundle, skeptical adapter audit).

    Source metadata and reported Atlas scores are untrusted declarations;
    source independence and uncertainty cannot be verified from this receipt.
    """
    doc = _obj(receipt, "receipt")
    if doc.get("schema") != SCHEMA or doc.get("method") != METHOD:
        raise InputError("Expected Fingerprint Atlas comparison v0.3 with the known alignment method")
    left, right = _profile(doc.get("reference"), "reference"), _profile(doc.get("candidate"), "candidate")
    original = _obj(doc.get("comparison"), "comparison")
    if original.get("method") != METHOD:
        raise InputError("Reported comparison method conflicts with the adapter")
    computed = _compare(left, right)
    if abs(_finite(original.get("score"), "comparison.score", 0) - computed["score"]) > 0.021:
        raise InputError("Reported similarity score fails independent recomputation")
    if abs(_finite(original.get("normalizedDistance"), "comparison.normalizedDistance", 0) -
           computed["distance"]) > 0.000005:
        raise InputError("Reported normalized distance fails independent recomputation")
    counts = original.get("ringCounts")
    if counts != computed["counts"]:
        raise InputError("Reported ring counts differ from the input profiles")
    if original.get("first") != left["name"] or original.get("second") != right["name"]:
        raise InputError("Reported comparison names do not match the input profiles")
    if original_sha256 is not None and (not isinstance(original_sha256, str) or
        len(original_sha256) != 64 or any(c not in "0123456789abcdef" for c in original_sha256.lower())):
        raise InputError("Original SHA-256 must be a 64-character hex string")
    source_kind = "synthetic" if any(p["source_type"] == "synthetic"
                                      for p in (left, right)) else "other"
    integrity_locator = "sha256:" + original_sha256 if original_sha256 else "unverified-local-comparison"
    lower_info = min(left["count"], right["count"]) < 3
    audits = [
        "Similarity only; no inference of communication, intention or authorship",
        "Original image pixels, camera geometry, original measurement uncertainty and source licenses not verified",
        "Independence between photographs, derivatives, publications and observers not established",
        "Search over library candidates has no look-elsewhere correction",
        "External source provenance and capture dates not independently authenticated",
    ]
    if lower_info:
        audits.append("Fewer than three rings in one profile; low-information comparison")
    if source_kind == "synthetic":
        audits.append("At least one profile is synthetic; demo data cannot count as experimental support")
    if doc.get("nullSimulation") is not None:
        audits.append("Atlas toy null ignored for evidentiary significance; it is not a calibrated p-value")
    context = {
        "reference": left["name"], "comparison": right["name"],
        "score_0_100_descriptive_only": computed["score"],
        "normalized_distance": computed["distance"], "ring_counts": computed["counts"],
        "source_labels": [left["source_type"], right["source_type"]],
        "source_urls_supplied": [left["source_url_provided"], right["source_url_provided"]],
        "has_lineage": [left["lineage_provided"], right["lineage_provided"]],
        "measurement_uncertainty": "not provided",
        "independence": "unverified",
        "library_size_declared": doc.get("searchedLibrarySize")
        if type(doc.get("searchedLibrarySize")) is int and 0 <= doc["searchedLibrarySize"] <= 100
        else None,
        "input_receipt_sha256": original_sha256,
        "warnings": audits,
    }
    bundle = {
        "schema_version": "1.0",
        "project": {
            "name": "Crop geometry comparison (research triage)",
            "domain": "crop_geometry",
            "description": "Imported deterministic radial similarity; no message hypothesis validated."
        },
        "candidates": [{
            "id": "CROP-GEOMETRY-1",
            "label": "Unverified repeated geometry hypothesis",
            "hypothesis": "The selected concentric-ring similarity can be reproduced "
                          "from independently documented observations with declared uncertainty.",
            "assumptions": [
                "Ring boundaries and centers were measured consistently and independently",
                "Source files and derivative reconstructions do not overlap",
                "The candidate was not selected only after scanning numerous designs",
            ],
            "alternatives": [
                "Ordinary geometric design conventions explain the resemblance",
                "Detection and image perspective bias produce similar radii",
                "Chance resemblance under a realistic human-made design distribution",
            ],
            "discriminating_tests": [{
                "id": "CROP-TEST-1",
                "measurement": "Repeat ring measurements blind from licensed original images with uncertainty intervals",
                "prediction_if_claim": "Scale-normalized proportions agree within preregistered tolerance",
                "prediction_if_alternative": "Agreement weakens under independent tracing or relevant matched controls",
                "decision_rule": "Freeze analysis choices and compare on held-out observations; "
                                 "report all searched candidates and failures."
            }]
        }],
        "evidence": [{
            "id": "CROP-EVIDENCE-1",
            "candidate_id": "CROP-GEOMETRY-1",
            "kind": "derived_geometry_comparison",
            "relation": "inconclusive",
            "statement": (
                f"Unverified descriptive comparison: {left['name']} versus {right['name']}, "
                f"ring similarity {computed['score']}/100. Not independent confirmation."
            ),
            "source": {
                "type": source_kind,
                "locator": integrity_locator,
                "independence_group": "unverified-derived-comparison",
            },
            "measurement": context,
        }],
    }
    validate_bundle(bundle)
    audit = {"schema": "phi-crop-discovery-adapter/v0.4", "method": METHOD,
             "evidence_stage_floor": "insufficient_evidence", "independent_support_records": 0,
             "source_verification": "unverified", "derived_comparison": context,
             "claim_validated": False, "communication_decoded": False}
    return bundle, audit


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

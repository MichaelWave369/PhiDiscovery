"""ΦDiscovery R0.8: exact and whitespace-normalized content-overlap audit.

All source text and model dataset inventories are operator-supplied, untrusted
and unverified. Content matching never proves training exposure or science.
"""
from __future__ import annotations

import unicodedata

from .engine import InputError, sha256
from .manifest_audit import audit_manifest, validate_manifest
from .predictions import _keys, _text

CONTENT_SCHEMA = "0.8"
REPORT_SCHEMA = "phidiscovery.content-overlap-audit.v0.8"
TEXT_MEDIA = "text/plain"
MAX_RECORDS = 3000
MAX_RECORD_BYTES = 4096
MAX_MATCHES = 50


def _content(value: object) -> str:
    if type(value) is not str or not value.strip():
        raise InputError("Content record must contain nonempty UTF-8 text")
    try:
        data = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise InputError("Content record contains invalid Unicode") from exc
    if not 24 <= len(data) <= MAX_RECORD_BYTES:
        raise InputError("Content text must be 24..4096 UTF-8 bytes")
    return unicodedata.normalize("NFC", value)


def fingerprints(text: str) -> dict:
    """Compute two domain-separated digests, without storing text in output.

    Whitespace-folded matches are *candidates* only; folding can erase
    scientifically meaningful structure and cannot prove duplicated source.
    """
    raw = _content(text)
    folded = " ".join(raw.split())
    return {
        "exact_sha256": sha256({
            "schema": "phidiscovery.content-exact.v0.8",
            "media_type": TEXT_MEDIA, "content": raw,
        }),
        "whitespace_folded_sha256": sha256({
            "schema": "phidiscovery.content-whitespace.v0.8",
            "media_type": TEXT_MEDIA, "content": folded,
        }),
    }


def _record(row: object, fields: set, context: str) -> None:
    _keys(row, fields, context)
    for field in fields - {"content"}:
        _text(row[field], f"{context}.{field}", cap=256)
    if row["media_type"] != TEXT_MEDIA:
        raise InputError("R0.8 supports text/plain only; binary and JSON canonicalization are not claimed")
    _content(row["content"])


def validate_content_index(plan: dict, commitment: dict, holdout: dict,
                           manifest: dict, content_index: object) -> None:
    """Demand every holdout trial and a bounded subset of declared model records."""
    validate_manifest(plan, commitment, holdout, manifest)
    _keys(content_index, {"schema_version", "study_id", "holdout_id",
                          "identifier_namespace", "holdout_records",
                          "model_records"}, "content index")
    if content_index["schema_version"] != CONTENT_SCHEMA:
        raise InputError("Content index schema_version must be 0.8")
    if content_index["study_id"] != plan["study"]["id"] or (
            content_index["holdout_id"] != plan["study"]["holdout_id"]):
        raise InputError("Content index study/holdout does not match registered predictions")
    if content_index["identifier_namespace"] != manifest["identifier_namespace"]:
        raise InputError("Content and manifest identifier namespaces differ")
    trial_ids = {
        trial["id"] for group in holdout["observations"]
        for trial in group["replicates"]
    }
    hrows = content_index["holdout_records"]
    mrows = content_index["model_records"]
    if type(hrows) is not list or len(hrows) != len(trial_ids):
        raise InputError("Every holdout trial requires exactly one content record")
    if type(mrows) is not list or len(mrows) > MAX_RECORDS:
        raise InputError("Model content index exceeds record limit")
    seen_trials = set()
    for row in hrows:
        _record(row, {"trial_id", "media_type", "content"}, "holdout content")
        tid = row["trial_id"]
        if tid not in trial_ids or tid in seen_trials:
            raise InputError("Unknown or duplicate holdout trial content ID")
        seen_trials.add(tid)
    if seen_trials != trial_ids:
        raise InputError("Incomplete holdout content coverage")
    known = {
        (model["model_id"], dataset["dataset_id"], record_id)
        for model in manifest["model_datasets"]
        for dataset in model["datasets"]
        for record_id in dataset["record_ids"]
    }
    seen = set()
    for row in mrows:
        _record(row, {"model_id", "dataset_id", "record_id", "media_type", "content"},
                "model content")
        key = (row["model_id"], row["dataset_id"], row["record_id"])
        if key not in known or key in seen:
            raise InputError("Unknown or duplicate model/dataset/record content key")
        seen.add(key)


def audit_content(plan: dict, commitment: dict, holdout: dict,
                  manifest: dict, content_index: dict) -> dict:
    """Preserve R0.7 risks; add exact content and whitespace-folded candidates."""
    validate_content_index(plan, commitment, holdout, manifest, content_index)
    source = audit_manifest(plan, commitment, holdout, manifest)
    namespace = manifest["identifier_namespace"]
    holdout_by_exact, holdout_by_folded = {}, {}
    for record in content_index["holdout_records"]:
        digests = fingerprints(record["content"])
        holdout_by_exact.setdefault(digests["exact_sha256"], set()).add(record["trial_id"])
        holdout_by_folded.setdefault(digests["whitespace_folded_sha256"], set()).add(record["trial_id"])
    model_info = {
        row["model_id"]: row
        for row in manifest["model_datasets"]
    }
    manifest_keys = {
        mid: {
            (dataset["dataset_id"], record_id)
            for dataset in row["datasets"] for record_id in dataset["record_ids"]
        } for mid, row in model_info.items()
    }
    indexed = {mid: set() for mid in model_info}
    details = {mid: {"exact": set(), "folded": set(), "exact_digests": set(),
                     "folded_digests": set()} for mid in model_info}
    for record in content_index["model_records"]:
        mid = record["model_id"]
        indexed[mid].add((record["dataset_id"], record["record_id"]))
        found = details[mid]
        digests = fingerprints(record["content"])
        exact_matches = holdout_by_exact.get(digests["exact_sha256"], set())
        if exact_matches:
            found["exact"].update(exact_matches)
            found["exact_digests"].add(digests["exact_sha256"])
        else:
            folded_matches = holdout_by_folded.get(
                digests["whitespace_folded_sha256"], set())
            if folded_matches:
                found["folded"].update(folded_matches)
                found["folded_digests"].add(digests["whitespace_folded_sha256"])
    rows, risks = [], list(source["risk_reasons"])
    any_exact = False
    any_folded = False
    for mid in sorted(model_info):
        found = details[mid]
        missing = len(manifest_keys[mid] - indexed[mid])
        full = missing == 0
        has_exact = bool(found["exact"])
        has_folded = bool(found["folded"])
        any_exact |= has_exact
        any_folded |= has_folded
        issues = []
        if has_exact:
            issues.append("Exact declared content overlap with holdout, regardless of record ID")
        if has_folded:
            issues.append("Whitespace-normalized text similarity candidate requiring review")
        if not full:
            issues.append("Not all declared dataset records have inspectable text content")
        risks.extend(f"{mid}: {issue}" for issue in issues)
        rows.append({
            "model_id": mid,
            "declared_model_record_count": len(manifest_keys[mid]),
            "indexed_model_record_count": len(indexed[mid]),
            "missing_model_content_records": missing,
            "content_inventory_complete_relative_to_manifest": full,
            "exact_content_matched_holdout_trial_count": len(found["exact"]),
            "exact_matched_trial_ids_sample": sorted(found["exact"])[:MAX_MATCHES],
            "exact_match_digest_sample": sorted(found["exact_digests"])[:MAX_MATCHES],
            "whitespace_candidate_trial_count": len(found["folded"]),
            "whitespace_candidate_trial_ids_sample": sorted(found["folded"])[:MAX_MATCHES],
            "whitespace_candidate_digest_sample": sorted(found["folded_digests"])[:MAX_MATCHES],
            "matching_output_truncated": any(len(found[k]) > MAX_MATCHES for k in
                                             ("exact", "folded", "exact_digests", "folded_digests")),
            "issues": issues,
            "actual_model_training_verified": False,
        })
    if any_exact:
        status = "EXACT_CONTENT_OVERLAP_IN_SUPPLIED_RECORDS"
    elif any_folded:
        status = "WHITESPACE_SIMILARITY_CANDIDATE"
    elif risks:
        status = "INCOMPLETE_OR_DECLARED_RISK"
    else:
        status = "NO_CONTENT_MATCH_IN_SUPPLIED_RECORDS_UNVERIFIED"
    quarantined = bool(risks)
    if quarantined:
        source["descriptive_r06_diagnostics"]["descriptive_leaders_if_not_quarantined"] = None
    return {
        "schema": REPORT_SCHEMA,
        "study_id": plan["study"]["id"], "holdout_id": plan["study"]["holdout_id"],
        "plan_sha256": sha256(plan), "commitment_sha256": sha256(commitment),
        "holdout_sha256": sha256(holdout), "manifest_sha256": sha256(manifest),
        "content_index_sha256": sha256(content_index),
        "identifier_namespace": namespace,
        "status": status,
        "ranking_suppressed": quarantined,
        "risk_reasons": risks,
        "models": rows,
        "holdout_content_record_count": len(content_index["holdout_records"]),
        "hypothesis_validated": False,
        "actual_training_data_authenticated": False,
        "external_timestamp_verified": False,
        "provenance_receipt": {
            "input_digests_only": True,
            "signature_present": False,
            "third_party_anchor_verified": False,
            "note": "Store input files and this receipt securely; SHA-256 does not attest authorship or time.",
        },
        "interpretation": (
            "Offline comparison of operator-supplied text only. Exact content "
            "matches indicate possible repeated records despite renamed IDs; "
            "whitespace-normalized matches are weaker similarity leads. "
            "Neither proves model ingestion, data independence, timestamped "
            "preregistration, validated experiments, or a scientific discovery. "
            "A nonmatch never certifies an uncontaminated training corpus."
        ),
        "r07_diagnostics": source,
    }

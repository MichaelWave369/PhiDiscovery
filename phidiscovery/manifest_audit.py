"""ΦDiscovery R0.7: offline manifest cross-reference for repeated holdouts.

Exact identifier matching across operator-provided model data manifests and
holdout trial IDs. This is NOT model-weight introspection, proof of ingestion,
a trained-data audit, or automatic semantic/near-duplicate detection.
"""
from __future__ import annotations

from collections import defaultdict

from .engine import InputError, sha256
from .predictions import _keys, _text, verify_registration
from .replicates import score_replicates, validate_replicates

MANIFEST_VERSION = "0.7"
AUDIT_SCHEMA = "phidiscovery.manifest-leakage-audit.v0.7"
SPLITS = {"training", "evaluation", "reference", "other"}
MAX_DATASETS_PER_MODEL = 30
MAX_IDS_PER_DATASET = 2000
MAX_TOTAL_IDS = 30000
MAX_MATCHES_REPORTED = 50


def fingerprint(namespace: str, record_id: str) -> str:
    """Hash a stable identifier within an explicit, shared comparison namespace.

    This is *not* anonymization of low-entropy IDs; treat the input/output as
    potentially sensitive. A digest match is identifier overlap, not proof
    that the model memorized or ever encountered the record.
    """
    namespace = _text(namespace, "identifier_namespace", cap=160)
    record_id = _text(record_id, "record_id", cap=256)
    return sha256({"schema": "phidiscovery.record-identifier.v0.7",
                   "namespace": namespace, "record_id": record_id})


def validate_manifest(plan: dict, commitment: dict, holdout: dict, manifest: object) -> None:
    verify_registration(plan, commitment)
    validate_replicates(plan, holdout)
    _keys(manifest, {"schema_version", "study_id", "holdout_id",
                     "identifier_namespace", "model_datasets"},
          "model exposure manifest")
    if manifest["schema_version"] != MANIFEST_VERSION:
        raise InputError("Expected model exposure manifest schema_version 0.7")
    if (manifest["study_id"] != plan["study"]["id"] or
            manifest["holdout_id"] != plan["study"]["holdout_id"]):
        raise InputError("Exposure manifest targets the wrong registered study")
    namespace = _text(manifest["identifier_namespace"], "identifier_namespace", cap=160)
    items = manifest["model_datasets"]
    registered = {m["id"] for m in plan["models"]}
    if type(items) is not list or len(items) != len(registered):
        raise InputError("Every registered model needs one manifest entry")
    seen, total = set(), 0
    for model in items:
        _keys(model, {"model_id", "inventory_complete_declared", "datasets",
                      "notes"}, "model manifest")
        mid = model["model_id"]
        if type(mid) is not str or mid not in registered or mid in seen:
            raise InputError("Duplicate, absent or unknown model in manifest")
        seen.add(mid)
        if type(model["inventory_complete_declared"]) is not bool:
            raise InputError("inventory_complete_declared must be boolean")
        _text(model["notes"], f"model[{mid}].notes", cap=1000)
        datasets = model["datasets"]
        if type(datasets) is not list or not 1 <= len(datasets) <= MAX_DATASETS_PER_MODEL:
            raise InputError("Each model needs 1..30 finite dataset listings")
        seen_datasets = set()
        for dataset in datasets:
            _keys(dataset, {"dataset_id", "split", "record_ids"}, "dataset manifest")
            did = _text(dataset["dataset_id"], "dataset_id", cap=160)
            if did in seen_datasets:
                raise InputError("Dataset IDs cannot repeat within a model")
            seen_datasets.add(did)
            if type(dataset["split"]) is not str or dataset["split"] not in SPLITS:
                raise InputError("Dataset split must be training, evaluation, reference, or other")
            ids = dataset["record_ids"]
            if type(ids) is not list or len(ids) > MAX_IDS_PER_DATASET:
                raise InputError("Each dataset must list at most 2000 record IDs")
            checked = [_text(rid, "dataset record ID", cap=256) for rid in ids]
            if len(set(checked)) != len(checked):
                raise InputError("Duplicate record identifier inside dataset")
            total += len(checked)
            if total > MAX_TOTAL_IDS:
                raise InputError("Manifest exceeds 30000 record identifiers")
            # Fingerprints are derived locally. No untrusted hash algorithms or
            # user-supplied comparison digests may replace the canonical recipe.
            for rid in checked:
                fingerprint(namespace, rid)


def audit_manifest(plan: dict, commitment: dict, holdout: dict, manifest: dict) -> dict:
    """Cross-reference exact record IDs and quarantine any suspect ranking.

    The underlying R0.6 diagnostic scores are preserved. They are not
    significance tests. Unknown or incomplete model data inventories cannot
    receive clean status merely because an overlap was not found.
    """
    validate_manifest(plan, commitment, holdout, manifest)
    source = score_replicates(plan, commitment, holdout)
    namespace = manifest["identifier_namespace"]
    trials = {
        fingerprint(namespace, trial["id"]): (group["target_id"], trial["id"])
        for group in holdout["observations"] for trial in group["replicates"]
    }
    breakdown = []
    all_risks = list(source["leakage_audit"]["declared_risks"])
    for model in sorted(manifest["model_datasets"], key=lambda item: item["model_id"]):
        mid = model["model_id"]
        seen_hashes = defaultdict(set)
        match_hashes = set()
        matched_splits = set()
        n_listed = 0
        for dataset in model["datasets"]:
            split = dataset["split"]
            for record_id in dataset["record_ids"]:
                h = fingerprint(namespace, record_id)
                n_listed += 1
                seen_hashes[h].add(split)
                if h in trials:
                    match_hashes.add(h)
                    matched_splits.add(split)
        cross_split = sorted(h for h, splits in seen_hashes.items() if len(splits) > 1)
        empty = n_listed == 0
        complete = model["inventory_complete_declared"]
        issues = []
        if match_hashes:
            issues.append("Exact shared record identifiers found in model-declared datasets")
        if cross_split:
            issues.append("Same identifier appears in multiple declared dataset splits")
        if empty:
            issues.append("No record identifiers were supplied for this model")
        if not complete:
            issues.append("Model dataset inventory was not declared complete")
        if issues:
            all_risks.extend(f"{mid}: {issue}" for issue in issues)
        breakdown.append({
            "model_id": mid, "manifest_inventory_complete_declared": complete,
            "listed_dataset_count": len(model["datasets"]),
            "listed_record_count": n_listed,
            "matched_holdout_record_count": len(match_hashes),
            "matched_splits": sorted(matched_splits),
            "matched_record_digests_sample": sorted(match_hashes)[:MAX_MATCHES_REPORTED],
            "matched_record_digests_truncated": len(match_hashes) > MAX_MATCHES_REPORTED,
            "cross_split_identifier_count": len(cross_split),
            "cross_split_digests_sample": cross_split[:MAX_MATCHES_REPORTED],
            "issues": issues,
            "actual_model_training_corpus_verified": False,
        })
    risk = bool(all_risks)
    if any(x["matched_holdout_record_count"] for x in breakdown):
        status = "EXACT_IDENTIFIER_OVERLAP_DECLARED"
    elif risk:
        status = "INCOMPLETE_OR_UNCERTAIN_EXPOSURE"
    else:
        status = "NO_EXACT_MATCH_IN_SUPPLIED_MANIFESTS_UNVERIFIED"
    # Quarantine even synthetic training examples if overlap is intentionally
    # planted; do not expose a 'winner' in any nested diagnostic field.
    if risk:
        source["descriptive_leaders_if_not_quarantined"] = None
    return {
        "schema": AUDIT_SCHEMA,
        "study_id": plan["study"]["id"],
        "holdout_id": plan["study"]["holdout_id"],
        "plan_sha256": sha256(plan),
        "commitment_sha256": sha256(commitment),
        "holdout_sha256": sha256(holdout),
        "manifest_sha256": sha256(manifest),
        "identifier_namespace": namespace,
        "manifest_status": status,
        "ranking_suppressed": risk,
        "risk_reasons": all_risks,
        "holdout_trial_id_count": len(trials),
        "model_manifest_audit": breakdown,
        "hypothesis_validated": False,
        "proof_of_actual_training_exposure": False,
        "manifest_completeness_independently_verified": False,
        "external_chronology_verified": False,
        "interpretation": (
            "Offline exact identifier matching only across operator-supplied "
            "records and holdout trial IDs in one shared namespace. A matched "
            "ID flags possible contamination, not proof of model training. "
            "No match does NOT establish clean data: missing corpora, renamed "
            "records, semantic duplicates, unknown pretraining, or false "
            "declarations can escape detection. Neither statistical significance "
            "nor scientific validity is established."
        ),
        "descriptive_r06_diagnostics": source,
    }

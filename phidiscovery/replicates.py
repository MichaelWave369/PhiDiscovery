"""Second Map R0.6: repeated-trial holdout scoring and declared leakage review.

Works with unchanged R0.5 prediction plans and commitments. All measurements,
unblinding dates, and overlap assessments are user-supplied and unauthenticated.
No statistical significance, independent replication, or discovery is asserted.
"""
from __future__ import annotations

import math

from .engine import InputError, sha256
from .predictions import (
    SOURCE_TYPES, _keys, _number, _text, validate_plan, verify_registration
)

REPLICATE_SCHEMA = "0.6"
SCORE_SCHEMA = "phidiscovery.replication-score.v0.6"
MAX_REPLICATES = 30
ACCESS_STATES = {"no_access_declared", "known_access", "unknown"}
OVERLAP_STATES = {"none_declared", "known_overlap", "unknown"}


def validate_replicates(plan: dict, holdout: object) -> None:
    """Require complete, non-overlapping target IDs, replicates and exposure declarations."""
    validate_plan(plan)
    _keys(holdout, {"schema_version", "study_id", "holdout_id", "source",
                    "protocol", "model_exposure", "observations"}, "R0.6 holdout")
    if holdout["schema_version"] != REPLICATE_SCHEMA:
        raise InputError("R0.6 holdout schema_version must be '0.6'")
    study = plan["study"]
    if holdout["study_id"] != study["id"] or holdout["holdout_id"] != study["holdout_id"]:
        raise InputError("Study/holdout identity differs from registered prediction plan")
    source = holdout["source"]
    _keys(source, {"type", "locator", "independence_group"}, "source")
    if type(source["type"]) is not str or source["type"] not in SOURCE_TYPES:
        raise InputError("Invalid declared source type")
    _text(source["locator"], "source.locator")
    _text(source["independence_group"], "source.independence_group")
    protocol = holdout["protocol"]
    _keys(protocol, {"predictions_frozen_before_collection",
                     "holdout_blinded_until_commitment", "notes"}, "protocol")
    if type(protocol["predictions_frozen_before_collection"]) is not bool or type(
        protocol["holdout_blinded_until_commitment"]) is not bool:
        raise InputError("Protocol chronology assertions must be actual booleans")
    _text(protocol["notes"], "protocol.notes", cap=2000)

    model_ids = {m["id"] for m in plan["models"]}
    exposures = holdout["model_exposure"]
    if type(exposures) is not list or len(exposures) != len(model_ids):
        raise InputError("Exactly one leakage review for every registered model is required")
    seen_models = set()
    for item in exposures:
        _keys(item, {"model_id", "prior_outcome_access", "training_overlap", "notes"},
              "model exposure")
        mid = item["model_id"]
        if type(mid) is not str or mid not in model_ids or mid in seen_models:
            raise InputError("Missing, duplicate or unregistered model exposure review")
        seen_models.add(mid)
        if type(item["prior_outcome_access"]) is not str or item["prior_outcome_access"] not in ACCESS_STATES:
            raise InputError("Unknown prior-outcome-access classification")
        if type(item["training_overlap"]) is not str or item["training_overlap"] not in OVERLAP_STATES:
            raise InputError("Unknown training-overlap classification")
        _text(item["notes"], f"model_exposure[{mid}].notes", cap=1000)

    targets = {t["id"]: t for t in plan["targets"]}
    observations = holdout["observations"]
    if type(observations) is not list or len(observations) != len(targets):
        raise InputError("R0.6 holdout must cover every target exactly once")
    seen_targets, seen_trial_ids = set(), set()
    for item in observations:
        _keys(item, {"target_id", "quantity", "unit", "replicates"}, "observation group")
        tid = item["target_id"]
        if type(tid) is not str or tid not in targets or tid in seen_targets:
            raise InputError("Missing, duplicate or unregistered target in repeated holdout")
        seen_targets.add(tid)
        target = targets[tid]
        if item["quantity"] != target["quantity"] or item["unit"] != target["unit"]:
            raise InputError("Repeated holdout quantity/unit mismatch")
        trials = item["replicates"]
        if type(trials) is not list or not 2 <= len(trials) <= MAX_REPLICATES:
            raise InputError("Every target requires 2..30 separately identified trials")
        for trial in trials:
            _keys(trial, {"id", "value", "reported_uncertainty"}, "trial")
            trial_id = _text(trial["id"], "trial.id", cap=160)
            if trial_id in seen_trial_ids:
                raise InputError("Trial IDs must be globally unique, even across targets")
            seen_trial_ids.add(trial_id)
            _number(trial["value"], "trial.value")
            _number(trial["reported_uncertainty"], "trial.reported_uncertainty", nonnegative=True)
    if seen_targets != set(targets):
        raise InputError("One or more preregistered targets are missing")


def leakage_audit(plan: dict, holdout: dict) -> dict:
    """Risk classification from DECLARATIONS, not a true data-leakage detector."""
    protocol = holdout["protocol"]
    risks = []
    if not protocol["predictions_frozen_before_collection"]:
        risks.append("Operator did not assert predictions preceded measurement collection")
    if not protocol["holdout_blinded_until_commitment"]:
        risks.append("Operator did not assert holdout remained blinded until commitment")
    for item in sorted(holdout["model_exposure"], key=lambda x: x["model_id"]):
        if item["prior_outcome_access"] != "no_access_declared":
            risks.append(f"{item['model_id']}: {item['prior_outcome_access']} for target outcomes")
        if item["training_overlap"] != "none_declared":
            risks.append(f"{item['model_id']}: {item['training_overlap']} with holdout/training data")
    synthetic = holdout["source"]["type"] == "synthetic"
    status = ("SYNTHETIC_DEMONSTRATION" if synthetic and not risks else
              "DECLARED_LEAKAGE_RISK" if risks else "DECLARED_CLEAN_NOT_VERIFIED")
    return {
        "status": status,
        "declared_risks": risks,
        "ranking_suppressed": bool(risks),
        "synthetic_data": synthetic,
        "source_provenance_authenticated": False,
        "model_exposure_independently_verified": False,
        "prediction_chronology_independently_verified": False,
        "note": ("Review of self-reported exposure/chronology flags only. "
                 "Clean declarations cannot exclude training contamination, "
                 "prior access, collusion, or retrospectively chosen targets."),
    }


def _finite(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise InputError(f"{label} overflowed; scale or bound the observations")
    return value


def score_replicates(plan: dict, commitment: dict, holdout: dict) -> dict:
    """Equal-weight-per-target prediction comparison with descriptive uncertainty.

    SEM assumes independent trials and is therefore a descriptive number, not
    a verified standard error. Max operator-declared per-trial uncertainty is
    added conservatively as an uncertainty floor, not a confidence interval.
    """
    verify_registration(plan, commitment)
    validate_replicates(plan, holdout)
    audit = leakage_audit(plan, holdout)
    targets = {t["id"]: t for t in plan["targets"]}
    groups = {g["target_id"]: g for g in holdout["observations"]}
    model_ids = sorted(m["id"] for m in plan["models"])
    errors = {mid: [] for mid in model_ids}
    target_results = []
    for tid in sorted(targets):
        target, group = targets[tid], groups[tid]
        vals = [float(x["value"]) for x in group["replicates"]]
        n = len(vals)
        mean = _finite(math.fsum(vals) / n, "replicate mean")
        centered = [_finite(v - mean, "centered measurement") for v in vals]
        variance = _finite(math.fsum(_finite(x * x, "replicate square") for x in centered)
                           / (n - 1), "replicate sample variance")
        sd = _finite(math.sqrt(variance), "replicate standard deviation")
        sem = _finite(sd / math.sqrt(n), "descriptive standard error")
        uncertainty_floor = max(float(x["reported_uncertainty"])
                                for x in group["replicates"])
        margin = _finite(sem + uncertainty_floor, "combined descriptive uncertainty margin")
        tol = float(target["tolerance"])
        model_results = []
        for mid in model_ids:
            prediction = float(target["predictions"][mid])
            err = _finite(prediction - mean, "prediction error")
            abs_err = _finite(abs(err), "absolute error")
            sq = _finite(err * err, "squared error")
            within = abs_err <= tol
            uncertainty_adjusted = abs_err <= _finite(tol + margin, "tolerance plus margin")
            errors[mid].append((abs_err, sq, within, uncertainty_adjusted))
            model_results.append({
                "model_id": mid, "predicted": prediction,
                "signed_error_vs_mean": err, "absolute_error_vs_mean": abs_err,
                "within_preregistered_tolerance": within,
                "within_tolerance_plus_descriptive_margin": uncertainty_adjusted,
            })
        target_results.append({
            "target_id": tid, "quantity": target["quantity"], "unit": target["unit"],
            "condition": target["condition"], "replicate_count": n,
            "replicate_ids": sorted(x["id"] for x in group["replicates"]),
            "observed_mean": mean, "sample_std_dev": sd,
            "descriptive_sem_independence_unverified": sem,
            "max_declared_instrument_uncertainty": uncertainty_floor,
            "descriptive_margin_not_confidence_interval": margin,
            "preregistered_tolerance": tol,
            "uncertainty_margin_exceeds_tolerance": margin > tol,
            "models": model_results,
        })
    summaries = []
    for mid in model_ids:
        values = errors[mid]
        n = len(values)
        mae = _finite(math.fsum(x[0] for x in values) / n, "MAE")
        rmse = _finite(math.sqrt(math.fsum(x[1] for x in values) / n), "RMSE")
        summaries.append({
            "model_id": mid, "targets": n,
            "mean_absolute_error_of_target_means": mae,
            "root_mean_squared_error_of_target_means": rmse,
            "tolerance_hits": sum(x[2] for x in values),
            "tolerance_hit_rate": sum(x[2] for x in values) / n,
            "tolerance_plus_margin_hits": sum(x[3] for x in values),
        })
    baseline_id = plan["study"]["baseline_model_id"]
    baseline = next(m for m in summaries if m["model_id"] == baseline_id)
    for m in summaries:
        m["mae_improvement_vs_registered_baseline"] = _finite(
            baseline["mean_absolute_error_of_target_means"]
            - m["mean_absolute_error_of_target_means"], "baseline improvement")
    best = min(m["mean_absolute_error_of_target_means"] for m in summaries)
    return {
        "schema": SCORE_SCHEMA, "plan_sha256": sha256(plan),
        "commitment_sha256": sha256(commitment), "holdout_sha256": sha256(holdout),
        "study_id": plan["study"]["id"], "holdout_id": plan["study"]["holdout_id"],
        "baseline_model_id": baseline_id,
        "holdout_source_declared": dict(holdout["source"]),
        "leakage_audit": audit,
        "descriptive_leaders_if_not_quarantined": (
            None if audit["ranking_suppressed"] else
            [m["model_id"] for m in summaries
             if m["mean_absolute_error_of_target_means"] == best]
        ),
        "actual_instrument_execution_verified": False,
        "independent_replication_verified": False,
        "hypothesis_validated": False,
        "model_training_data_audited": False,
        "model_ran_in_this_process": False,
        "counts": {"targets": len(targets),
                   "trials": sum(t["replicate_count"] for t in target_results),
                   "models": len(model_ids)},
        "interpretation": (
            "Descriptive errors from self-supplied repeated measurements. "
            "Trial SEM assumes independence, which is not verified; the added "
            "instrument uncertainty floor is not a confidence interval. "
            "Exposure declarations cannot detect unknown leakage. "
            "No statistical significance, verified chronology, causal proof, "
            "or scientific discovery is established."
        ),
        "model_summary": summaries, "target_results": target_results,
    }

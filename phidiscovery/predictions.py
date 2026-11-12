"""Second Map R0.5: preregistered numeric predictions and blinded holdout scoring.

Offline, deterministic and dependency-free. This scorer measures agreement with
*supplied* observations; it cannot authenticate instruments, preregistration
chronology, model independence, or any scientific discovery.
"""
from __future__ import annotations

import math
from collections import defaultdict

from .engine import InputError, sha256

PLAN_VERSION = "0.5"
COMMIT_SCHEMA = "phidiscovery.prediction-commitment.v0.5"
SCORE_SCHEMA = "phidiscovery.prediction-score.v0.5"
SOURCE_TYPES = {"synthetic", "instrument", "publication", "database", "other"}
MAX_MODELS = 12
MAX_TARGETS = 200


def _keys(obj: object, required: set, label: str, optional: set = frozenset()):
    if type(obj) is not dict or not required <= set(obj) or not set(obj) <= required | optional:
        raise InputError(f"{label} must contain exactly required fields {sorted(required)}"
                         f" and optional {sorted(optional)}")


def _text(value: object, label: str, cap: int = 1000) -> str:
    if type(value) is not str or not value.strip() or len(value) > cap:
        raise InputError(f"{label} must be nonempty text <= {cap} characters")
    return value.strip()


def _number(value: object, label: str, *, positive=False, nonnegative=False) -> float:
    if type(value) not in (int, float):
        raise InputError(f"{label} must be a finite numeric value (not boolean)")
    try:
        numeric = float(value)
    except (ValueError, OverflowError) as exc:
        raise InputError(f"{label} must be a finite numeric value") from exc
    if not math.isfinite(numeric):
        raise InputError(f"{label} must be a finite numeric value")
    if (positive and numeric <= 0) or (nonnegative and numeric < 0):
        raise InputError(f"{label} is outside its allowed range")
    return numeric


def _ids(items: list, label: str):
    ids = [item["id"] for item in items]
    if len(set(ids)) != len(ids):
        raise InputError(f"{label} identifiers must be unique")


def validate_plan(plan: object) -> None:
    _keys(plan, {"schema_version", "study", "models", "targets"}, "prediction plan")
    if plan["schema_version"] != PLAN_VERSION:
        raise InputError("prediction plan schema_version must equal 0.5")
    study = plan["study"]
    _keys(study, {"id", "question", "measurement_protocol", "holdout_id",
                  "baseline_model_id"}, "study", {"review_ledger_sha256"})
    for field in ("id", "question", "measurement_protocol", "holdout_id", "baseline_model_id"):
        _text(study[field], f"study.{field}")
    if "review_ledger_sha256" in study:
        digest = study["review_ledger_sha256"]
        if type(digest) is not str or len(digest) != 64 or any(x not in "0123456789abcdef" for x in digest):
            raise InputError("study.review_ledger_sha256 must be a lowercase SHA-256 digest")
    models = plan["models"]
    targets = plan["targets"]
    if type(models) is not list or not 2 <= len(models) <= MAX_MODELS:
        raise InputError("prediction plan must contain 2..12 models (including a baseline)")
    if type(targets) is not list or not 1 <= len(targets) <= MAX_TARGETS:
        raise InputError("prediction plan must contain 1..200 held-out targets")
    for index, model in enumerate(models):
        _keys(model, {"id", "label", "hypothesis"}, f"models[{index}]")
        for field in ("id", "label", "hypothesis"):
            _text(model[field], f"models[{index}].{field}")
    _ids(models, "model")
    model_ids = {m["id"] for m in models}
    if study["baseline_model_id"] not in model_ids:
        raise InputError("study.baseline_model_id must name an included model")
    for index, target in enumerate(targets):
        _keys(target, {"id", "quantity", "unit", "condition", "tolerance", "predictions"},
              f"targets[{index}]")
        for field in ("id", "quantity", "unit", "condition"):
            _text(target[field], f"targets[{index}].{field}")
        _number(target["tolerance"], "target.tolerance", positive=True)
        prediction = target["predictions"]
        if type(prediction) is not dict or set(prediction) != model_ids:
            raise InputError("Each target needs one numeric prediction from every model")
        for model_id, value in prediction.items():
            _number(value, f"predictions[{model_id}]")
    _ids(targets, "target")
    # Raw MAE/RMSE across unrelated physical units is meaningless. R0.5
    # deliberately supports one measurable quantity and unit per study.
    if len({(t["quantity"], t["unit"]) for t in targets}) != 1:
        raise InputError("R0.5 requires all targets to share one measurable quantity and unit")
    # Predictions deliberately contain no observations. A separate holdout
    # document is required; do not add observed values to this contract.


def register(plan: dict) -> dict:
    """Commit to a complete prediction specification BEFORE viewing holdout data.

    This digest does NOT prove when the registration happened. Publish/anchor the
    SHA-256 externally with a trusted timestamp before exposing measurements.
    """
    validate_plan(plan)
    study = plan["study"]
    return {
        "schema": COMMIT_SCHEMA,
        "plan_sha256": sha256(plan),
        "study_id": study["id"], "holdout_id": study["holdout_id"],
        "baseline_model_id": study["baseline_model_id"],
        "target_ids": sorted(t["id"] for t in plan["targets"]),
        "model_ids": sorted(m["id"] for m in plan["models"]),
        "predeclared_metrics": ["mean_absolute_error", "root_mean_squared_error",
                                "tolerance_hit_rate"],
        "external_timestamp_verified": False,
        "empirical_evidence_verified": False,
        "note": ("Registration is a content fingerprint, not proof of preregistration "
                 "chronology. Independently timestamp the hash before seeing outcomes."),
    }


def verify_registration(plan: dict, commitment: dict) -> bool:
    """Reject changed plans, changed scoring tolerances or forged commitments."""
    validate_plan(plan)
    if type(commitment) is not dict or commitment != register(plan):
        raise InputError("Commitment no longer matches the exact registered prediction plan")
    return True


def validate_holdout(plan: dict, holdout: object) -> None:
    """Check coverage, units and declared provenance without asserting credibility."""
    validate_plan(plan)
    _keys(holdout, {"schema_version", "study_id", "holdout_id", "source",
                    "observations"}, "holdout")
    if holdout["schema_version"] != PLAN_VERSION:
        raise InputError("holdout schema_version must equal 0.5")
    study = plan["study"]
    if holdout["study_id"] != study["id"] or holdout["holdout_id"] != study["holdout_id"]:
        raise InputError("Holdout study identifier differs from preregistered study")
    source = holdout["source"]
    _keys(source, {"type", "locator", "independence_group"}, "holdout.source")
    if type(source["type"]) is not str or source["type"] not in SOURCE_TYPES:
        raise InputError("Unknown holdout source type")
    for field in ("locator", "independence_group"):
        _text(source[field], f"holdout.source.{field}")
    observations = holdout["observations"]
    if type(observations) is not list or len(observations) != len(plan["targets"]):
        raise InputError("Holdout must cover all and only preregistered targets")
    expected = {target["id"]: target for target in plan["targets"]}
    seen = set()
    for index, item in enumerate(observations):
        _keys(item, {"target_id", "quantity", "unit", "value", "uncertainty"},
              f"observations[{index}]")
        tid = item["target_id"]
        if type(tid) is not str or tid not in expected or tid in seen:
            raise InputError("Holdout contains unknown or duplicate target ID")
        seen.add(tid)
        target = expected[tid]
        if item["quantity"] != target["quantity"] or item["unit"] != target["unit"]:
            raise InputError("Observed quantity or units do not match the prediction")
        _number(item["value"], f"observations[{index}].value")
        _number(item["uncertainty"], f"observations[{index}].uncertainty", nonnegative=True)
    if seen != set(expected):
        raise InputError("A preregistered target is missing from the holdout")


def score(plan: dict, commitment: dict, holdout: dict) -> dict:
    """Compute descriptive prediction errors; never assert statistical significance."""
    verify_registration(plan, commitment)
    validate_holdout(plan, holdout)
    targets = {t["id"]: t for t in plan["targets"]}
    observations = {o["target_id"]: o for o in holdout["observations"]}
    errors = defaultdict(list)
    rows = []
    for tid in sorted(targets):
        target, obs = targets[tid], observations[tid]
        scoring = []
        for model_id in sorted(target["predictions"]):
            predicted = float(target["predictions"][model_id])
            observed = float(obs["value"])
            delta = predicted - observed
            absolute = abs(delta)
            tolerance = float(target["tolerance"])
            if not all(math.isfinite(x) for x in (delta, absolute, absolute / tolerance, delta * delta)):
                raise InputError("Prediction scoring overflowed; input magnitudes too large")
            within = absolute <= tolerance
            errors[model_id].append((absolute, delta * delta, within))
            scoring.append({
                "model_id": model_id, "predicted": predicted,
                "signed_error": delta, "absolute_error": absolute,
                "tolerance": tolerance, "within_tolerance": within,
            })
        rows.append({
            "target_id": tid,
            "quantity": target["quantity"], "unit": target["unit"],
            "condition": target["condition"],
            "observed": float(obs["value"]),
            "declared_measurement_uncertainty": float(obs["uncertainty"]),
            "uncertainty_exceeds_tolerance": obs["uncertainty"] > target["tolerance"],
            "results": scoring,
        })
    summaries = []
    for mid in sorted(errors):
        values = errors[mid]
        n = len(values)
        mae = sum(item[0] for item in values) / n
        rmse = math.sqrt(sum(item[1] for item in values) / n)
        if not all(math.isfinite(x) for x in (mae, rmse)):
            raise InputError("Aggregate score overflow")
        summaries.append({
            "model_id": mid, "n": n, "mean_absolute_error": mae,
            "root_mean_squared_error": rmse,
            "tolerance_hits": sum(item[2] for item in values),
            "tolerance_hit_rate": sum(item[2] for item in values) / n,
        })
    baseline_id = plan["study"]["baseline_model_id"]
    baseline = next(item for item in summaries if item["model_id"] == baseline_id)
    for item in summaries:
        item["mae_improvement_vs_baseline"] = baseline["mean_absolute_error"] - item["mean_absolute_error"]
    best_mae = min(s["mean_absolute_error"] for s in summaries)
    return {
        "schema": SCORE_SCHEMA,
        "plan_sha256": commitment["plan_sha256"],
        "commitment_sha256": sha256(commitment),
        "holdout_sha256": sha256(holdout),
        "study_id": plan["study"]["id"],
        "holdout_id": plan["study"]["holdout_id"],
        "baseline_model_id": baseline_id,
        "external_timestamp_verified": False,
        "holdout_source_declared": dict(holdout["source"]),
        "synthetic_holdout": holdout["source"]["type"] == "synthetic",
        "raw_measurements_authenticated": False,
        "study_design_independently_verified": False,
        "hypothesis_validated": False,
        "evidence_stage_modified": False,
        "interpretation": (
            "Descriptive scores on user-provided observations. Model rankings are "
            "not statistical significance, proof of causality, real preregistration, "
            "independent replication, or validation of physical laws. Source provenance "
            "and chronology require external verification."
        ),
        "counts": {"targets": len(targets), "models": len(summaries)},
        "lowest_mae_model_ids_descriptive_only": [
            item["model_id"] for item in summaries if item["mean_absolute_error"] == best_mae
        ],
        "model_summary": summaries, "target_results": rows,
    }

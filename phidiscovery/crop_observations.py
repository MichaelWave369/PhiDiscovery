"""Crop geometry R0.5: bounded, offline source-lineage and uncertainty sensitivity audit.

Does not authenticate observational independence, determine intention or infer messages.
The uniform perturbation is a *sensitivity exercise*, not a confidence interval.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
from pathlib import Path
from typing import Any

from .crop_geometry import _compare, METHOD
from .engine import InputError, validate_bundle, sha256

SCHEMA = "phi-crop-observation-manifest/v0.5"
AUDIT_SCHEMA = "phi-crop-observation-audit/v0.5"
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
TYPES = {"original_photo", "derived_image", "publication", "manual_trace", "synthetic"}
MAX_OBSERVATIONS = 50
MAX_COMPARISONS = 30
MAX_SAMPLES = 2000


def _mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise InputError(f"{label} must be a JSON object")
    return value


def _string(value: Any, label: str, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise InputError(f"{label} must be a nonempty string up to {limit} characters")
    return value.strip()


def _number(value: Any, label: str, zero_ok: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputError(f"{label} must be a finite number")
    num = float(value)
    if num < 0 if zero_ok else num <= 0:
        raise InputError(f"{label} must be {'nonnegative' if zero_ok else 'positive'}")
    return num


def _parse_observation(item: Any, index: int) -> dict:
    p = f"observations[{index}]"
    item = _mapping(item, p)
    identifier = _string(item.get("id"), p + ".id", 80)
    radii = item.get("radii")
    uncert = item.get("uncertainty_px")
    if not isinstance(radii, list) or not 3 <= len(radii) <= 12:
        raise InputError(f"{p}.radii requires 3–12 rings")
    if not isinstance(uncert, list) or len(uncert) != len(radii):
        raise InputError(f"{p}.uncertainty_px must match radii in length")
    rr = [_number(v, f"{p}.radii[{j}]") for j, v in enumerate(radii)]
    uu = [_number(v, f"{p}.uncertainty_px[{j}]", zero_ok=True) for j, v in enumerate(uncert)]
    if max(rr) > 1_000_000 or any(b <= a for a, b in zip(rr, rr[1:])):
        raise InputError(f"{p}.radii must be strictly increasing, distinct, <=1000000")
    if any(u >= r for r, u in zip(rr, uu)):
        raise InputError(f"{p} uncertainty must be smaller than each radius")
    src = _mapping(item.get("source"), p + ".source")
    kind = _string(src.get("type"), p + ".source.type", 40)
    if kind not in TYPES:
        raise InputError(f"{p}.source.type is not a supported source type")
    locator = _string(src.get("locator"), p + ".source.locator", 2048)
    parents = src.get("parent_ids", [])
    if not isinstance(parents, list) or len(parents) > MAX_OBSERVATIONS:
        raise InputError(f"{p}.source.parent_ids must be an array")
    parents = [_string(x, f"{p}.source.parent_ids", 80) for x in parents]
    if len(set(parents)) != len(parents) or identifier in parents:
        raise InputError(f"{p}.source.parent_ids has duplicate or self reference")
    sha = src.get("image_sha256")
    if sha is not None and (not isinstance(sha, str) or not HEX64.fullmatch(sha)):
        raise InputError(f"{p}.source.image_sha256 must be hex SHA-256")
    local = src.get("local_file")
    if local is not None:
        _string(local, p + ".source.local_file", 1024)
        if sha is None:
            raise InputError(f"{p}.source.local_file requires image_sha256")
    capture = src.get("capture_id")
    if capture is not None:
        capture = _string(capture, p + ".source.capture_id", 120)
    license_label = src.get("license")
    if license_label is not None:
        license_label = _string(license_label, p + ".source.license", 200)
    return {
        "id": identifier, "radii": rr, "uncertainty_px": uu,
        "analyst": _string(item.get("analyst"), p + ".analyst", 120),
        "source": {"type": kind, "locator": locator, "parent_ids": parents,
                   "image_sha256": sha.lower() if sha else None, "local_file": local,
                   "capture_id": capture, "license": license_label},
    }


def _parents_graph(items: dict[str, dict]) -> dict[str, set[str]]:
    def visit(current: str, trail: set[str]) -> set[str]:
        if current in trail:
            raise InputError("Cycle in declared source parent_ids")
        result = {current}
        for parent in items[current]["source"]["parent_ids"]:
            if parent not in items:
                raise InputError(f"Unknown source parent id: {parent}")
            result.update(visit(parent, trail | {current}))
        return result
    return {k: visit(k, set()) for k in items}


def _file_check(item: dict, root: Path | None) -> str:
    src = item["source"]
    local = src["local_file"]
    if local is None:
        return "source_bytes_not_provided"
    if root is None:
        return "source_bytes_not_checked"
    base = root.resolve()
    target = (base / local).resolve()
    if not target.is_relative_to(base):
        raise InputError("local_file escapes the manifest directory")
    if not target.is_file():
        raise InputError(f"local_file missing for {item['id']}")
    if target.stat().st_size > 25 * 1024 * 1024:
        raise InputError(f"local_file exceeds 25 MiB cap for {item['id']}")
    if hashlib.sha256(target.read_bytes()).hexdigest() != src["image_sha256"]:
        raise InputError(f"local_file SHA-256 mismatch for {item['id']}")
    return "bytes_match_declared_sha256_only"


def _pair_relation(a: dict, b: dict, ancestors: dict[str, set[str]]) -> tuple[str, list[str]]:
    sa, sb = a["source"], b["source"]
    reasons = []
    if sa["image_sha256"] and sa["image_sha256"] == sb["image_sha256"]:
        reasons.append("same_declared_image_sha256")
    if sa["locator"] == sb["locator"]:
        reasons.append("same_declared_locator")
    if sa["capture_id"] and sa["capture_id"] == sb["capture_id"]:
        reasons.append("same_declared_capture_id")
    if ancestors[a["id"]] & ancestors[b["id"]]:
        reasons.append("shared_declared_ancestor_or_derivative")
    return ("linked_or_duplicate" if reasons else "not_proven_independent", reasons)


def _score(radii_a: list[float], radii_b: list[float]) -> float:
    left = {"normalized": [round(r / radii_a[-1], 6) for r in radii_a]}
    right = {"normalized": [round(r / radii_b[-1], 6) for r in radii_b]}
    return _compare(left, right)["score"]


def _sensitivity(a: dict, b: dict, trials: int, seed: int) -> dict:
    observed = _score(a["radii"], b["radii"])
    uncertainty_nonzero = any(a["uncertainty_px"] + b["uncertainty_px"])
    if not uncertainty_nonzero:
        return {"observed_score": observed, "sensitivity_band": None,
                "sample_count": 0, "ring_order_crossings": 0,
                "note": "All uncertainty bounds were zero; uncertainty has NOT been assessed."}
    rng = random.Random(seed)
    values = []
    crossings = 0
    for _ in range(trials):
        perturbed = []
        for obs in (a, b):
            raw = [r + rng.uniform(-u, u) for r, u in
                   zip(obs["radii"], obs["uncertainty_px"])]
            if any(y <= x for x, y in zip(raw, raw[1:])):
                crossings += 1
            perturbed.append(sorted(raw))
        values.append(_score(*perturbed))
    values.sort()
    pick = lambda q: values[int((len(values) - 1) * q)]
    return {"observed_score": observed, "sensitivity_band": {
            "p05": pick(0.05), "median": pick(0.50), "p95": pick(0.95),
            "lowest": values[0], "highest": values[-1],
            "model": "independent-uniform-plus-minus-declared-bounds-not-confidence-interval"},
            "sample_count": trials, "ring_order_crossings": crossings,
            "note": "A seeded, assumption-dependent perturbation exercise, not an empirically calibrated 90% confidence interval."}


def audit_observations(manifest: Any, *, root: Path | None = None,
                       input_sha256: str | None = None) -> tuple[dict, dict]:
    manifest = _mapping(manifest, "manifest")
    if manifest.get("schema") != SCHEMA:
        raise InputError(f"Expected {SCHEMA}")
    raw = manifest.get("observations")
    pairs = manifest.get("comparisons")
    if not isinstance(raw, list) or not 2 <= len(raw) <= MAX_OBSERVATIONS:
        raise InputError("Expected 2–50 observations")
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= MAX_COMPARISONS:
        raise InputError("Expected 1–30 comparisons")
    trials = manifest.get("sensitivity_trials", 512)
    seed = manifest.get("seed", 369)
    if type(trials) is not int or not 100 <= trials <= MAX_SAMPLES:
        raise InputError("sensitivity_trials must be 100–2000")
    if type(seed) is not int or not 0 <= seed <= 2**32-1:
        raise InputError("seed must be an unsigned 32-bit integer")
    parsed = [_parse_observation(item, index) for index, item in enumerate(raw)]
    by_id = {o["id"]: o for o in parsed}
    if len(by_id) != len(parsed):
        raise InputError("Duplicate observation ID")
    ancestors = _parents_graph(by_id)
    checks = {key: _file_check(value, root) for key, value in by_id.items()}
    comparisons = []
    evidence, candidates = [], []
    seen_pairs: set[tuple[str, str]] = set()
    for index, entry in enumerate(pairs):
        pair = _mapping(entry, f"comparisons[{index}]")
        a_id = _string(pair.get("reference_id"), "reference_id", 80)
        b_id = _string(pair.get("candidate_id"), "candidate_id", 80)
        if a_id not in by_id or b_id not in by_id or a_id == b_id:
            raise InputError("Comparison IDs must identify two distinct known observations")
        key = tuple(sorted((a_id, b_id)))
        if key in seen_pairs:
            raise InputError("Repeated comparison pair")
        seen_pairs.add(key)
        a, b = by_id[a_id], by_id[b_id]
        independence, reasons = _pair_relation(a, b, ancestors)
        sensitivity = _sensitivity(a, b, trials, (seed + index * 10007) % (2**32))
        synthetic = a["source"]["type"] == "synthetic" or b["source"]["type"] == "synthetic"
        comparison = {
            "reference_id": a_id, "candidate_id": b_id, "method": METHOD,
            "independence": independence, "link_reasons": reasons,
            "source_file_checks": {a_id: checks[a_id], b_id: checks[b_id]},
            "source_license_labels": {a_id: a["source"]["license"], b_id: b["source"]["license"]},
            "source_lineage_is_self_reported": True, "synthetic": synthetic,
            "uncertainty": sensitivity,
            "conclusion": "inconclusive_geometry_only",
        }
        comparisons.append(comparison)
        candidate_id = f"CROP-R05-{index+1}"
        candidates.append({
            "id": candidate_id,
            "label": f"Geometry reproducibility: {a_id} vs {b_id}",
            "hypothesis": "A geometric match remains reproducible on blinded, independent, licensed images with measured uncertainty."
        })
        evidence.append({
            "id": f"CROP-MEASUREMENT-{index+1}", "candidate_id": candidate_id,
            "kind": "derived_geometry_with_sensitivity", "relation": "inconclusive",
            "statement": f"Observed descriptive ring similarity {sensitivity['observed_score']}/100; "
                         f"source relation {independence}; uncertainties are not calibrated.",
            "source": {
                "type": "synthetic" if synthetic else "other",
                "locator": f"manifest:{input_sha256 or 'unverified'}#comparison-{index+1}",
                "independence_group": "unverified-derived-crop-observations",
            },
            "measurement": {"score_descriptive_only": sensitivity["observed_score"],
                            "sensitivity_band": sensitivity["sensitivity_band"],
                            "independence_status": independence,
                            "source_bytes_checked": checks[a_id] == "bytes_match_declared_sha256_only"
                                                    and checks[b_id] == "bytes_match_declared_sha256_only"},
        })
    bundle = {"schema_version": "1.0", "project": {
        "name": "Crop observation uncertainty and lineage audit R0.5",
        "domain": "crop_geometry",
        "description": "Geometry sensitivity and declared source relationships; no message validated."},
        "candidates": candidates, "evidence": evidence}
    validate_bundle(bundle)
    audit = {
        "schema": AUDIT_SCHEMA,
        "input_sha256": input_sha256,
        "method": METHOD,
        "sensitivity_model": "independent uniform perturbations within explicitly declared pixel bounds",
        "observations": [{"id": o["id"], "source_type": o["source"]["type"],
            "source_locator": o["source"]["locator"], "image_sha256_declared": o["source"]["image_sha256"],
            "file_check": checks[o["id"]], "parent_ids": o["source"]["parent_ids"],
            "capture_id_declared": o["source"]["capture_id"],
            "license_declared_not_verified": o["source"]["license"]}
            for o in parsed],
        "comparisons": comparisons,
        "counts": {"observations": len(parsed), "comparisons": len(comparisons),
                   "linked_or_duplicate": sum(c["independence"] == "linked_or_duplicate"
                                              for c in comparisons),
                   "unproven_independent": sum(c["independence"] == "not_proven_independent"
                                              for c in comparisons),
                   "eligible_support": 0},
        "limitations": [
            "Equal image SHA-256 shows matching bytes; different hashes do NOT prove independence",
            "Parent IDs and capture IDs are declarations and may be incomplete or incorrect",
            "Local byte matching does not prove the photograph is original, licensed, or geolocated",
            "Pixel uncertainty inputs are operator-provided, not empirically calibrated",
            "Uniform perturbation quantiles are sensitivity bands, not statistical confidence intervals",
            "No multiple-testing correction, message decoding, map fit, nonhuman origin or scientific corroboration",
        ],
        "claim_validated": False, "communication_decoded": False,
    }
    return bundle, audit

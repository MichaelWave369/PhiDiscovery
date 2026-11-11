"""Deterministic evidence pipeline. Never confuses computation with experimental proof."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import __version__

SUPPORTED_RELATIONS = {"supports", "contradicts", "inconclusive"}
SOURCE_TYPES = {"synthetic", "publication", "instrument", "database", "repository", "other"}


class InputError(ValueError):
    """Input bundle does not satisfy the contract."""


def stable_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(stable_bytes(value)).hexdigest()


def _required_string(obj: dict, field: str, where: str) -> None:
    if not isinstance(obj.get(field), str) or not obj[field].strip():
        raise InputError(f"{where}.{field} must be a nonempty string")


def validate_bundle(bundle: Any) -> None:
    if not isinstance(bundle, dict):
        raise InputError("Root must be a JSON object")
    if bundle.get("schema_version") != "1.0":
        raise InputError("schema_version must equal 1.0")
    project = bundle.get("project")
    if not isinstance(project, dict):
        raise InputError("project must be an object")
    _required_string(project, "name", "project")
    _required_string(project, "domain", "project")
    candidates, evidence = bundle.get("candidates"), bundle.get("evidence")
    if not isinstance(candidates, list) or not isinstance(evidence, list):
        raise InputError("candidates and evidence must be arrays")
    if len(candidates) > 10000 or len(evidence) > 100000:
        raise InputError("Input exceeds protective record limits")
    ids = set()
    for idx, item in enumerate(candidates):
        where = f"candidates[{idx}]"
        if not isinstance(item, dict):
            raise InputError(f"{where} must be an object")
        for field in ("id", "label", "hypothesis"):
            _required_string(item, field, where)
        if item["id"] in ids:
            raise InputError(f"Duplicate candidate id: {item['id']}")
        ids.add(item["id"])
    seen = set()
    for idx, item in enumerate(evidence):
        where = f"evidence[{idx}]"
        if not isinstance(item, dict):
            raise InputError(f"{where} must be an object")
        for field in ("id", "candidate_id", "kind", "relation", "statement"):
            _required_string(item, field, where)
        if item["id"] in seen:
            raise InputError(f"Duplicate evidence id: {item['id']}")
        seen.add(item["id"])
        if item["candidate_id"] not in ids:
            raise InputError(f"{where} refers to unknown candidate: {item['candidate_id']}")
        if item["relation"] not in SUPPORTED_RELATIONS:
            raise InputError(f"{where}.relation not in {sorted(SUPPORTED_RELATIONS)}")
        src = item.get("source")
        if not isinstance(src, dict):
            raise InputError(f"{where}.source must be an object")
        for field in ("type", "locator", "independence_group"):
            _required_string(src, field, f"{where}.source")
        if src["type"] not in SOURCE_TYPES:
            raise InputError(f"{where}.source.type not in {sorted(SOURCE_TYPES)}")
        if ("artifact_sha256" in src) != ("artifact_path" in src):
            raise InputError(f"{where}.source.artifact_path and artifact_sha256 must appear together")
        if src.get("artifact_sha256") is not None:
            val = src["artifact_sha256"]
            if not isinstance(val, str) or len(val) != 64 or any(ch not in '0123456789abcdefABCDEF' for ch in val):
                raise InputError(f"{where}.source.artifact_sha256 must be a hex SHA-256")
            _required_string(src, "artifact_path", f"{where}.source")
        measurement = item.get("measurement")
        if measurement is not None:
            if not isinstance(measurement, dict):
                raise InputError(f"{where}.measurement must be an object")
            # A measurement can be modality-specific; validate known MS1 fields together.
            if any(k in measurement for k in ("observed_mz", "expected_mz", "tolerance_ppm")):
                for k in ("observed_mz", "expected_mz", "tolerance_ppm"):
                    val = measurement.get(k)
                    if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val <= 0:
                        raise InputError(f"{where}.measurement.{k} must be a finite positive number")
    # No machine-produced proof/novelty claims are allowed in the input contract.


def _artifact_check(source: dict, root: Path | None) -> tuple[str, list[str]]:
    """Verify a supplied LOCAL raw-data artifact, not scientific truth."""
    rel = source.get("artifact_path")
    if not rel:
        return "not_supplied", []
    if root is None:
        return "not_checked", ["Artifact hash not checked: input directory unavailable"]
    base = root.resolve()
    path = (base / rel).resolve()
    if not path.is_relative_to(base):
        return "invalid", ["Artifact path escapes the input directory"]
    if not path.is_file():
        return "missing", ["Referenced local artifact missing"]
    if path.stat().st_size > 100 * 1024 * 1024:
        return "too_large", ["Artifact over 100 MiB verification limit"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest.lower() != source.get("artifact_sha256", "").lower():
        return "mismatch", ["Raw-data artifact SHA-256 mismatch"]
    return "verified_bytes", []


def _measurement_checks(ev: dict) -> tuple[dict | None, list[str]]:
    m = ev.get("measurement", {})
    if not isinstance(m, dict) or "observed_mz" not in m:
        return None, []
    ppm = 1_000_000 * (m["observed_mz"] - m["expected_mz"]) / m["expected_mz"]
    passed = abs(ppm) <= m["tolerance_ppm"]
    details = {"observed_mz": m["observed_mz"], "expected_mz": m["expected_mz"],
               "ppm_error": round(ppm, 4), "tolerance_ppm": m["tolerance_ppm"], "within_tolerance": passed}
    flags = [] if passed else ["Precursor m/z outside declared tolerance: this evidence cannot support the assignment"]
    if ev.get("kind", "").lower() == "ms1":
        flags.append("MS1 precursor mass alone cannot distinguish molecular isomers or confirm a structure")
    return details, flags



def analyze(bundle: dict, root: Path | None = None) -> dict:
    validate_bundle(bundle)
    from .domains import get_rule
    domain_rule = get_rule(bundle["project"]["domain"])
    candidates = sorted(bundle["candidates"], key=lambda x: x["id"])
    evidence = sorted(bundle["evidence"], key=lambda x: x["id"])
    by_candidate = defaultdict(list)
    audits = {}
    for ev in evidence:
        status, issues = _artifact_check(ev["source"], root)
        measurement, mflags = _measurement_checks(ev)
        invalid_support = measurement is not None and not measurement["within_tolerance"]
        audit = {"id": ev["id"], "candidate_id": ev["candidate_id"],
                 "synthetic": ev["source"]["type"] == "synthetic", "artifact_integrity": status,
                 "measurement": measurement, "flags": issues + mflags,
                 "eligible_support": ev["relation"] == "supports" and not invalid_support and status not in {"invalid", "missing", "mismatch", "too_large"} and ev["source"]["type"] != "synthetic"}
        audits[ev["id"]] = audit
        by_candidate[ev["candidate_id"]].append(ev)

    results = []
    for candidate in candidates:
        entries = by_candidate[candidate["id"]]
        valid = [e for e in entries if audits[e["id"]]["eligible_support"]]
        contradiction = [e for e in entries if e["relation"] == "contradicts" and e["source"]["type"] != "synthetic"]
        unique_sources = {(e["source"]["type"], e["source"]["locator"], e["source"]["independence_group"]) for e in valid}
        groups = {e["source"]["independence_group"] for e in valid}
        modalities = {e["kind"].lower() for e in valid}
        flags = []
        if not entries:
            flags.append("No evidence records")
        if entries and all(e["source"]["type"] == "synthetic" for e in entries):
            flags.append("Fixture-only evidence: demonstrates the engine, not an actual research finding")
        if len(groups) <= 1 and valid:
            flags.append("Insufficient independently sourced evidence groups")
        if len(unique_sources) < len(valid):
            flags.append("Repeated provenance cannot count as independent corroboration")
        if any(e["kind"].lower() == "ms1" for e in entries) and not modalities.intersection({"ms2", "nmr", "xray"}):
            flags.append("No independently traceable structural characterization beyond precursor mass")
        if contradiction:
            flags.append("Contradictory evidence present: requires adjudication")
        for e in entries:
            for flag in audits[e["id"]]["flags"]:
                if flag not in flags:
                    flags.append(flag)
        if domain_rule is not None:
            flags += domain_rule(candidate, entries, candidates)
        if contradiction:
            stage = "contested"
        elif len(groups) >= 2 and len(unique_sources) >= 2 and modalities.intersection({"ms2", "nmr", "xray"}):
            stage = "candidate_for_expert_review"
        elif valid:
            stage = "early_signal"
        else:
            stage = "insufficient_evidence"
        results.append({"id": candidate["id"], "label": candidate["label"],
                        "hypothesis": candidate["hypothesis"], "stage": stage,
                        "evidence_count": len(entries), "eligible_support_count": len(valid),
                        "independent_groups": len(groups), "provenance_sources": len(unique_sources),
                        "modalities": sorted(modalities), "flags": list(dict.fromkeys(flags)),
                        "evidence_ids": [e["id"] for e in entries]})
    return {"schema_version": "1.0", "engine_version": __version__,
            "project": bundle["project"], "input_sha256": sha256(bundle),
            "interpretation": "Automated triage only. No compound identity, novelty, efficacy, safety, or discovery is scientifically confirmed by this report.",
            "counts": {"candidates": len(candidates), "evidence": len(evidence),
                       "synthetic_evidence": sum(x["synthetic"] for x in audits.values()),
                       "stages": dict(sorted(Counter(r["stage"] for r in results).items()))},
            "results": results, "evidence_audit": [audits[e["id"]] for e in evidence]}


def verify_report(report: dict, bundle: dict, root: Path | None = None) -> bool:
    return report == analyze(bundle, root=root)

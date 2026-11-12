"""Assumption Challenger: deterministic, offline epistemic audit.

This module generates a *question ledger*, never scientific conclusions or
machine-discovered laws. All provenance/independence claims remain user-supplied.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from .engine import InputError, analyze, sha256, validate_bundle

MAX_ITEMS = 100
MAX_TEXT = 10000
TEST_FIELDS = ("id", "measurement", "prediction_if_claim",
               "prediction_if_alternative", "decision_rule")


def _texts(candidate: dict, field: str) -> list[str]:
    """Validate optional candidate declarations without changing bundle v1.0."""
    values = candidate.get(field, [])
    if not isinstance(values, list) or len(values) > MAX_ITEMS:
        raise InputError(f"{candidate['id']}.{field} must be an array of at most {MAX_ITEMS} strings")
    for value in values:
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
            raise InputError(f"{candidate['id']}.{field} entries must be nonempty strings of at most {MAX_TEXT} characters")
    return [value.strip() for value in values]


def _tests(candidate: dict) -> list[dict]:
    values = candidate.get("discriminating_tests", [])
    if not isinstance(values, list) or len(values) > MAX_ITEMS:
        raise InputError(f"{candidate['id']}.discriminating_tests must be an array of at most {MAX_ITEMS} objects")
    seen = set()
    tests = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            raise InputError(f"{candidate['id']}.discriminating_tests[{index}] must be an object")
        for field in TEST_FIELDS:
            text = value.get(field)
            if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
                raise InputError(f"{candidate['id']}.discriminating_tests[{index}].{field} must be a nonempty string of at most {MAX_TEXT} characters")
        if value["id"] in seen:
            raise InputError(f"Duplicate discriminating test id for candidate {candidate['id']}: {value['id']}")
        seen.add(value["id"])
        tests.append({field: value[field].strip() for field in TEST_FIELDS})
    return sorted(tests, key=lambda item: item["id"])


def challenge(bundle: dict, root=None) -> dict[str, Any]:
    """Create a transparent challenge plan from a research evidence bundle.

    Does not execute tests, use an LLM, validate source independence, or
    establish a discovery. The existing evidence engine is authoritative for
    eligibility flags and reports.
    """
    validate_bundle(bundle)
    baseline = analyze(bundle, root=root)
    by_id = {item["id"]: item for item in baseline["results"]}
    audits = {item["id"]: item for item in baseline["evidence_audit"]}
    records = sorted(bundle["evidence"], key=lambda item: item["id"])
    items = []

    for candidate in sorted(bundle["candidates"], key=lambda item: item["id"]):
        cid = candidate["id"]
        assumptions = _texts(candidate, "assumptions")
        alternatives = _texts(candidate, "alternatives")
        tests = _tests(candidate)
        related = [ev for ev in records if ev["candidate_id"] == cid]
        supports = [ev["id"] for ev in related if audits[ev["id"]]["eligible_support"]]
        contradicts = [ev["id"] for ev in related if ev["relation"] == "contradicts"]
        inconclusive = [ev["id"] for ev in related if ev["relation"] == "inconclusive"]
        synthetic = [ev["id"] for ev in related if audits[ev["id"]]["synthetic"]]
        groups = sorted({ev["source"]["independence_group"] for ev in related
                         if audits[ev["id"]]["eligible_support"]})
        issues = []
        if not assumptions:
            issues.append("No explicit assumptions declared")
        if not alternatives:
            issues.append("No competing explanation declared")
        if not tests:
            issues.append("No prospective discriminating test with a decision rule declared")
        if not supports:
            issues.append("No eligible non-synthetic supporting evidence")
        if supports and len(groups) < 2:
            issues.append("Supporting evidence does not declare two independent groups")
        if contradicts:
            issues.append("Contradictory records require independent review; provenance may be synthetic or unverified")
        if related and len(synthetic) == len(related):
            issues.append("Only synthetic evidence supplied; this is a demonstration")
        tasks = [
            {"role": "assumption_challenger",
             "question": "Which declared or hidden assumptions, if false, would invalidate this hypothesis? Seek counterexamples."},
            {"role": "alternative_builder",
             "question": "Propose distinct explanations producing the same observations. State predictions that distinguish them."},
            {"role": "experiment_auditor",
             "question": "Assess measurement quality, source dependence, confounders, preregistered decision rules and independent replication."},
        ]
        items.append({
            "id": cid, "label": candidate["label"], "hypothesis": candidate["hypothesis"],
            "current_evidence_stage": by_id[cid]["stage"],
            "assumptions": assumptions, "alternatives": alternatives,
            "discriminating_tests": tests,
            "evidence_index": {
                "eligible_support_ids": supports,
                "contradiction_ids": contradicts,
                "inconclusive_ids": inconclusive,
                "synthetic_ids": synthetic,
                "declared_support_independence_groups": groups,
                "note": "Source independence is self-declared; contradictory records are indexed even if synthetic or invalid.",
            },
            "open_issues": issues,
            "collaborator_tasks": tasks,
        })
    return {
        "schema_version": "1.0",
        "report_type": "assumption_challenge_plan",
        "input_sha256": sha256(bundle),
        "interpretation": (
            "Hypothesis review plan only. No physical experiment, AI inference, "
            "independent replication, or discovery was performed; predictions "
            "and sources require external validation."
        ),
        "counts": {
            "candidates": len(items),
            "with_explicit_assumptions": sum(bool(x["assumptions"]) for x in items),
            "with_alternatives": sum(bool(x["alternatives"]) for x in items),
            "with_discriminating_tests": sum(bool(x["discriminating_tests"]) for x in items),
            "open_issues": sum(len(x["open_issues"]) for x in items),
            "evidence_stages": dict(sorted(Counter(x["current_evidence_stage"] for x in items).items())),
        },
        "candidates": items,
    }

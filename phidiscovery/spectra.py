"""Offline, domain-neutral MGF read/compare adapter for mass spectrometry data.

Triage reference-similarity signals only; not a validated identification pipeline.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from .engine import InputError

MAX_SPECTRA = 10000
MAX_PEAKS = 5000


def _positive(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise InputError(f"{name} must be a finite positive number")
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"{name} must be a finite positive number") from exc
    if not math.isfinite(num) or num <= 0:
        raise InputError(f"{name} must be a finite positive number")
    return num


def _peaks_from(value: object, label: str) -> list[tuple[float, float]]:
    if not isinstance(value, list) or len(value) > MAX_PEAKS:
        raise InputError(f"{label}: expected <= {MAX_PEAKS} peaks")
    result = []
    for idx, p in enumerate(value):
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise InputError(f"{label} peak[{idx}] must be [mz, intensity]")
        result.append((_positive(p[0], "peak m/z"), _positive(p[1], "peak intensity")))
    return result


def read_mgf(path: Path) -> list[dict]:
    if path.stat().st_size > 100 * 1024 * 1024:
        raise InputError("MGF over 100 MiB protective cap")
    records = []
    reading = False
    title = None
    precursor = None
    ion_mode = None
    precursor_type = None
    peaks = []
    with path.open(encoding="utf-8-sig", errors="replace") as src:
        for line_number, raw in enumerate(src, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.upper() == "BEGIN IONS":
                if reading:
                    raise InputError(f"Nested BEGIN IONS at line {line_number}")
                reading, title, precursor, ion_mode, precursor_type, peaks = True, None, None, None, None, []
                continue
            if line.upper() == "END IONS":
                if not reading:
                    raise InputError(f"Orphan END IONS at line {line_number}")
                if precursor is None:
                    raise InputError(f"Missing PEPMASS in record at line {line_number}")
                if len(records) >= MAX_SPECTRA:
                    raise InputError("Too many spectra")
                records.append({"id": f"MGF-{len(records)+1:05d}", "title": title or f"Spectrum {len(records)+1}",
                                "precursor_mz": precursor, "ion_mode": ion_mode, "precursor_type": precursor_type, "peaks": peaks})
                reading = False
                continue
            if not reading:
                raise InputError(f"Unexpected MGF line outside record: {line_number}")
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip().upper() == "TITLE":
                    title = v.strip()[:200]
                elif k.strip().upper() == "PEPMASS":
                    precursor = _positive(v.split()[0], "PEPMASS")
                elif k.strip().upper() == "IONMODE":
                    mode = v.strip().upper()
                    if mode not in ("POSITIVE", "NEGATIVE"):
                        raise InputError(f"Unsupported IONMODE on line {line_number}")
                    if ion_mode and ion_mode != mode:
                        raise InputError("Conflicting MGF ion mode and charge")
                    ion_mode = mode
                elif k.strip().upper() == "CHARGE":
                    charge = v.strip()
                    if charge not in ("1+", "1-"):
                        raise InputError(f"Unsupported CHARGE on line {line_number}; use 1+ or 1-")
                    charge_mode = "POSITIVE" if charge == "1+" else "NEGATIVE"
                    if ion_mode and ion_mode != charge_mode:
                        raise InputError("Conflicting MGF ion mode and charge")
                    ion_mode = charge_mode
                elif k.strip().upper() == "ADDUCT":
                    precursor_type = v.strip()[:80]
                continue
            parts = line.split()
            if len(parts) < 2:
                raise InputError(f"Bad peak at line {line_number}")
            peaks.append((_positive(parts[0], "peak m/z"), _positive(parts[1], "peak intensity")))
            if len(peaks) > MAX_PEAKS:
                raise InputError("Spectrum exceeds peak count limit")
    if reading:
        raise InputError("Unclosed BEGIN IONS record")
    return records


def _cosine(a: list[tuple[float, float]], b: list[tuple[float, float]], tol: float) -> tuple[float, int]:
    """Greedy, one-to-one fragment matching. Educational baseline, not spectral identity proof."""
    va = sorted(a, key=lambda p: -p[1])
    vb = sorted(b, key=lambda p: -p[1])
    norm_a = math.sqrt(sum(p[1]**2 for p in a))
    norm_b = math.sqrt(sum(p[1]**2 for p in b))
    if not norm_a or not norm_b:
        return 0.0, 0
    available = set(range(len(vb)))
    dot, hits = 0.0, 0
    for mz, intensity in va:
        matches = [j for j in available if abs(vb[j][0] - mz) <= tol]
        if not matches:
            continue
        j = min(matches, key=lambda z: (abs(vb[z][0] - mz), -vb[z][1]))
        available.remove(j)
        dot += intensity * vb[j][1]
        hits += 1
    return round(max(0.0, min(1.0, dot / (norm_a * norm_b))), 5), hits


def compare_mgf(path: Path, library: dict, precursor_ppm: float = 10.0,
                fragment_tol_da: float = 0.03, min_fragments: int = 3,
                min_similarity: float = 0.70) -> dict:
    for key, val in (("precursor_ppm", precursor_ppm), ("fragment_tol_da", fragment_tol_da),
                     ("min_similarity", min_similarity)):
        _positive(val, key)
    if min_similarity > 1:
        raise InputError("min_similarity must be between 0 and 1")
    if isinstance(min_fragments, bool) or not isinstance(min_fragments, int) or min_fragments < 1:
        raise InputError("min_fragments must be a positive integer")
    if not isinstance(library, dict) or not isinstance(library.get("references"), list):
        raise InputError("Library must be an object with references array")
    if len(library["references"]) > 10000:
        raise InputError("Too many reference spectra")
    refs = []
    seen = set()
    for idx, raw in enumerate(library["references"]):
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
            raise InputError("Reference must have nonempty id")
        if raw["id"] in seen:
            raise InputError("Duplicate reference id")
        seen.add(raw["id"])
        refs.append({"id": raw["id"], "label": str(raw.get("label") or raw["id"]),
                     "precursor_mz": _positive(raw.get("precursor_mz"), "reference precursor"),
                     "peaks": _peaks_from(raw.get("peaks"), f"reference[{idx}]"),
                     "ion_mode": raw.get("ion_mode"), "precursor_type": raw.get("precursor_type"),
                     "license": raw.get("license"), "source_sha256": raw.get("source_sha256")})
        if refs[-1]["ion_mode"] not in (None, "POSITIVE", "NEGATIVE"):
            raise InputError("Invalid reference ion_mode")
        if refs[-1]["precursor_type"] is not None and not isinstance(refs[-1]["precursor_type"], str):
            raise InputError("Invalid reference precursor_type")
    spectra = read_mgf(path)
    outcomes = []
    for spectrum in spectra:
        matches = []
        metadata_unverified = False
        for ref in refs:
            if ref["ion_mode"] and spectrum["ion_mode"] and ref["ion_mode"] != spectrum["ion_mode"]:
                continue
            if ref["precursor_type"] and spectrum["precursor_type"] and ref["precursor_type"] != spectrum["precursor_type"]:
                continue
            ppm = 1_000_000 * (spectrum["precursor_mz"] - ref["precursor_mz"]) / ref["precursor_mz"]
            if abs(ppm) > precursor_ppm:
                continue
            similarity, fragments = _cosine(spectrum["peaks"], ref["peaks"], fragment_tol_da)
            if fragments >= min_fragments and similarity >= min_similarity:
                metadata_complete = (not ref["ion_mode"] or spectrum["ion_mode"] == ref["ion_mode"]) and (
                    not ref["precursor_type"] or spectrum["precursor_type"] == ref["precursor_type"])
                if not metadata_complete:
                    metadata_unverified = True
                matches.append({"reference_id": ref["id"], "label": ref["label"],
                                "metadata_complete": metadata_complete, "license": ref["license"],
                                "reference_source_sha256": ref["source_sha256"],
                                "precursor_ppm_error": round(ppm, 3), "cosine_similarity": similarity,
                                "matched_fragments": fragments})
        matches.sort(key=lambda x: (-x["cosine_similarity"], -x["matched_fragments"], x["reference_id"]))
        # Similarity ties and near-ties are flagged rather than overstating identity.
        ambiguous = len(matches) > 1 and matches[0]["cosine_similarity"] - matches[1]["cosine_similarity"] <= 0.05
        stage = ("unassigned_feature" if not matches else "metadata_incomplete" if metadata_unverified
                 else "ambiguous_reference_match" if ambiguous else "tentative_reference_match")
        outcomes.append({"spectrum_id": spectrum["id"], "title": spectrum["title"],
                         "precursor_mz": spectrum["precursor_mz"], "ion_mode": spectrum["ion_mode"],
                         "precursor_type": spectrum["precursor_type"], "peak_count": len(spectrum["peaks"]),
                         "stage": stage, "matches": matches[:10],
                         "warning": "A reference similarity is NOT proof of identity; an unassigned feature is NOT proof of a novel compound."})
    return {"schema_version": "1.0", "adapter": "offline-mgf-cosine-baseline-v0.1",
            "source_name": path.name, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "reference_count": len(refs), "spectra_count": len(spectra),
            "parameters": {"precursor_ppm": precursor_ppm, "fragment_tol_da": fragment_tol_da,
                           "min_fragments": min_fragments, "min_similarity": min_similarity},
            "results": outcomes, "limitations": [
                "Cosine baseline only: not a validated library search, adduct resolver, or quantitative identification",
                "Missing MGF IONMODE/CHARGE or ADDUCT marks metadata_incomplete for matching typed references",
                "Source spectrum can contain noise, coelution, instrument effects, wrong adducts, or missing fragments",
                "An unassigned peak is not a new cannabinoid; manual instrument and scientific review required"
            ]}

"""Strict, offline MassBank MS2 reference importer.

Import only: users supply legally reusable, trusted reference files. No claim of
identity, plant origin, or novelty follows from a parsed reference spectrum.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .engine import InputError
from .spectra import MAX_PEAKS, _positive

MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_IMPORT_RECORDS = 250
ACCESSION = re.compile(r"^MSBNK-[A-Za-z0-9_]{1,32}-[A-Z0-9_]{1,64}$")


def parse_record(path: Path) -> dict:
    """Read a *single* MassBank text record into a traceable reference entry."""
    if not path.is_file() or path.stat().st_size > MAX_RECORD_BYTES:
        raise InputError(f"MassBank record must be an existing file <= {MAX_RECORD_BYTES} bytes: {path.name}")
    contents = path.read_bytes()
    try:
        data = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError(f"MassBank record is not valid UTF-8: {path.name}") from exc

    tags: dict[str, list[str]] = {}
    peaks: list[list[float]] = []
    in_peaks = False
    ended = False
    for line_number, line in enumerate(data.splitlines(), 1):
        stripped = line.strip()
        if stripped == "//":
            ended = True
            in_peaks = False
            continue
        if ended:
            if stripped:
                raise InputError(f"Trailing content or multiple records: {path.name}:{line_number}")
            continue
        if in_peaks and line[:1].isspace():
            if not stripped:
                continue
            fields = stripped.split()
            if len(fields) != 3:
                raise InputError(f"Malformed PK$PEAK entry: {path.name}:{line_number}")
            mz, intensity = _positive(fields[0], "MassBank peak m/z"), _positive(fields[1], "MassBank intensity")
            _positive(fields[2], "MassBank relative intensity")
            peaks.append([mz, intensity])
            if len(peaks) > MAX_PEAKS:
                raise InputError("MassBank reference exceeds peak limit")
            continue
        in_peaks = False
        if not stripped:
            continue
        if ": " not in line:
            if line[:1].isspace():
                continue
            raise InputError(f"Malformed MassBank tag at {path.name}:{line_number}")
        key, value = line.split(": ", 1)
        key, value = key.strip(), value.strip()
        if key == "PK$PEAK":
            if value != "m/z int. rel.int.":
                raise InputError("Unsupported PK$PEAK header")
            if "PK$PEAK" in tags:
                raise InputError("Duplicate PK$PEAK sections")
            in_peaks = True
        tags.setdefault(key, []).append(value)
    if not ended:
        raise InputError(f"Missing MassBank record terminator: {path.name}")

    def field(tag: str, *, required: bool = True) -> str:
        values = tags.get(tag, [])
        if len(values) != 1 or not values[0]:
            if required or values:
                raise InputError(f"Missing or ambiguous MassBank field {tag}: {path.name}")
            return ""
        return values[0]

    accession = field("ACCESSION")
    if not ACCESSION.fullmatch(accession):
        raise InputError(f"Invalid official MassBank accession: {accession}")
    ms_fields = tags.get("AC$MASS_SPECTROMETRY", [])
    ms_type = [v.split(" ", 1)[1] for v in ms_fields if v.startswith("MS_TYPE ")]
    ion_mode = [v.split(" ", 1)[1] for v in ms_fields if v.startswith("ION_MODE ")]
    if ms_type != ["MS2"] or len(ion_mode) != 1 or ion_mode[0] not in ("POSITIVE", "NEGATIVE"):
        raise InputError("Only MassBank MS2 records with explicit ion mode are supported")
    focus_fields = tags.get("MS$FOCUSED_ION", [])
    mz = [v.split(" ", 1)[1] for v in focus_fields if v.startswith("PRECURSOR_M/Z ")]
    adduct = [v.split(" ", 1)[1] for v in focus_fields if v.startswith("PRECURSOR_TYPE ")]
    if len(mz) != 1 or len(adduct) != 1 or not adduct[0]:
        raise InputError("MassBank MS2 requires one precursor m/z and precursor type")
    precursor = _positive(mz[0], "MassBank precursor m/z")
    if not adduct[0].endswith("+" if ion_mode[0] == "POSITIVE" else "-"):
        raise InputError("MassBank precursor charge conflicts with ion mode")
    if len(peaks) < 3:
        raise InputError("MassBank reference requires at least three peaks")
    num_peak = field("PK$NUM_PEAK")
    if not num_peak.isdecimal() or int(num_peak) != len(peaks):
        raise InputError("MassBank PK$NUM_PEAK mismatch")
    names = [value for value in tags.get("CH$NAME", []) if value]
    if not names:
        raise InputError("MassBank reference requires a compound name")
    name = names[0]
    license_name = field("LICENSE")
    if license_name not in ("CC0", "CC BY", "CC BY-SA", "CC BY-NC", "CC BY-NC-SA"):
        raise InputError(f"Unsupported or missing MassBank license: {license_name}")
    return {
        "id": accession,
        "label": name,
        "precursor_mz": precursor,
        "precursor_type": adduct[0],
        "ion_mode": ion_mode[0],
        "ms_type": "MS2",
        "license": license_name,
        "source_file": path.name,
        "source_sha256": hashlib.sha256(contents).hexdigest(),
        "peaks": peaks,
    }


def import_records(paths: list[Path]) -> dict:
    """Import local records without network calls or implicit recursive traversal."""
    if not paths or len(paths) > MAX_IMPORT_RECORDS:
        raise InputError(f"Specify 1 to {MAX_IMPORT_RECORDS} MassBank record files")
    if len(set(str(p.resolve()) for p in paths)) != len(paths):
        raise InputError("Duplicate MassBank input paths")
    references = [parse_record(p) for p in sorted(paths, key=lambda p: str(p))]
    ids = [item["id"] for item in references]
    if len(set(ids)) != len(ids):
        raise InputError("Duplicate MassBank accessions")
    return {
        "schema_version": "1.0",
        "source_format": "MassBank textual MS2 records",
        "importer": "massbank-offline-strict-v0.2",
        "references": references,
        "limitations": [
            "Import validity does not independently establish the accuracy of a deposited reference",
            "Experimental collision energy, instrument, and chromatography are not yet modeled in similarity scoring",
            "Matching an MS2 library record does not establish molecular identity, cannabis origin, or novelty",
        ],
    }

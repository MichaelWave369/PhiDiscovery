"""PhiDiscovery R0.2: offline controlled cross-machine initialization calibration.

No hardware origin inference. Hardware/software labels are self-reported and
not cryptographically authenticated. Synthetic demo is never real GPU evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path

from .checkpoint_lab import _digest, _pearson, _read_record, _save, _torch_tensor, _toy_value

CAPTURE_SCHEMA = "phi.checkpoint.calibration.capture.v1"
REPORT_SCHEMA = "phi.checkpoint.calibration.comparison.v1"
PYTORCH_PROTOCOL = "torch.empty_float32_normal_inplace_v1"
TOY_PROTOCOL = "synthetic_sha256_lanes_v1"
VALID_ROLES = ("target", "neighbor")
MAX_COUNT = 8192
MAX_REPEATS = 4
VALID_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def _guard_int(value: object, name: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"{name} must be an integer between {lo} and {hi}")
    return value


def _valid_label(value: object) -> str:
    if type(value) is not str or not VALID_LABEL.fullmatch(value):
        raise ValueError("capture label must be 1..64 alphanumeric, dot, underscore or hyphen characters")
    return value


def _create_record(label: str, protocol: str, data_class: str, device: dict,
                   software: dict, seed: int, rows: int, cols: int,
                   repeats: int, sample) -> dict:
    """The sample function must initialize independently for each invocation."""
    _valid_label(label)
    _guard_int(seed, "seed", 0, 2**63 - 2)
    _guard_int(rows, "rows", 1, MAX_COUNT)
    _guard_int(cols, "cols", 1, MAX_COUNT)
    _guard_int(repeats, "repeats", 2, MAX_REPEATS)
    count = rows * cols
    if count < 128 or count > MAX_COUNT:
        raise ValueError("capture must contain 128..8192 weights per tensor")
    trials = []
    for rep in range(repeats):
        for role in VALID_ROLES:
            role_seed = seed if role == "target" else seed + 1
            values = sample(role_seed, rows, cols)
            if len(values) != count:
                raise ValueError("capture sample returned wrong tensor size")
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
                raise ValueError("capture returned non-finite or non-numeric values")
            trials.append({
                "replicate": rep + 1, "role": role, "seed": role_seed,
                "values": values,
                "values_sha256_float64_le": _digest(values),
            })
    return {
        "schema": CAPTURE_SCHEMA,
        "data_class": data_class,
        "capture_label": label,
        "protocol": protocol,
        "tensor": {"rows": rows, "cols": cols, "dtype": "float32", "seed": seed},
        "repeats": repeats,
        "device_declaration_unverified": device,
        "software_declaration_unverified": software,
        "trials": trials,
        "hardware_identity_independently_verified": False,
        "source_timestamp_independently_verified": False,
    }


def capture_pytorch(label: str, seed: int = 369, rows: int = 32,
                    cols: int = 128, repeats: int = 3, device: str = "cuda") -> dict:
    """Capture actual PyTorch initialization on the device where this runs."""
    if device not in ("cuda", "cpu"):
        raise ValueError("device must be cpu or cuda")
    # Prevalidate before importing/initializing an accelerator.
    _valid_label(label)
    _guard_int(seed, "seed", 0, 2**63-2)
    _guard_int(rows, "rows", 1, MAX_COUNT)
    _guard_int(cols, "cols", 1, MAX_COUNT)
    _guard_int(repeats, "repeats", 2, MAX_REPEATS)
    if not 128 <= rows * cols <= MAX_COUNT:
        raise ValueError("tensor size out of bounds")
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("optional PyTorch package is required for real calibration") from exc
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available; refusing CPU fallback")
    if device == "cuda":
        props = torch.cuda.get_device_properties(0)
        d = {"kind": "cuda", "name": torch.cuda.get_device_name(0),
             "sm_count": props.multi_processor_count,
             "compute_capability": list(torch.cuda.get_device_capability(0))}
    else:
        d = {"kind": "cpu", "name": "CPU", "sm_count": None,
             "compute_capability": None}
    s = {"torch_version": str(torch.__version__),
         "cuda_runtime": torch.version.cuda}
    def sample(k: int, r: int, c: int):
        return _torch_tensor(k, r, c, device).cpu().flatten().tolist()
    return _create_record(label, PYTORCH_PROTOCOL, "CONTROLLED_LOCAL_CAPTURE",
                          d, s, seed, rows, cols, repeats, sample)


def synthetic_demo_capture(label: str, seed: int, lanes: int = 148,
                           rows: int = 32, cols: int = 128,
                           repeats: int = 3) -> dict:
    """Explicitly simulated calibration record for offline CI and demo only."""
    if lanes not in (132, 148, 152):
        raise ValueError("toy lanes must be 132, 148, or 152")
    d = {"kind": "synthetic", "name": f"SIMULATED_LANES_{lanes}",
         "sm_count": None, "compute_capability": None}
    s = {"torch_version": None, "cuda_runtime": None}
    def sample(k: int, r: int, c: int):
        return [_toy_value(k, lanes, i) for i in range(r * c)]
    return _create_record(label, TOY_PROTOCOL, "SYNTHETIC_FIXTURE_NOT_HARDWARE",
                          d, s, seed, rows, cols, repeats, sample)


def _validate_capture(record: dict) -> None:
    if type(record) is not dict or record.get("schema") != CAPTURE_SCHEMA:
        raise ValueError("input must be PhiDiscovery R0.2 calibration capture")
    _valid_label(record.get("capture_label"))
    kind = record.get("data_class")
    protocol = record.get("protocol")
    allowed = {
        "CONTROLLED_LOCAL_CAPTURE": PYTORCH_PROTOCOL,
        "SYNTHETIC_FIXTURE_NOT_HARDWARE": TOY_PROTOCOL,
    }
    if allowed.get(kind) != protocol:
        raise ValueError("capture data class/protocol mismatch")
    if record.get("hardware_identity_independently_verified") is not False:
        raise ValueError("capture must not claim authenticated hardware identity")
    if record.get("source_timestamp_independently_verified") is not False:
        raise ValueError("capture must not claim authenticated chronology")
    tensor = record.get("tensor")
    if type(tensor) is not dict or set(tensor) != {"rows", "cols", "dtype", "seed"}:
        raise ValueError("invalid tensor declaration")
    rows = _guard_int(tensor["rows"], "rows", 1, MAX_COUNT)
    cols = _guard_int(tensor["cols"], "cols", 1, MAX_COUNT)
    if not 128 <= rows * cols <= MAX_COUNT or tensor["dtype"] != "float32":
        raise ValueError("invalid tensor protocol parameters")
    seed = _guard_int(tensor["seed"], "seed", 0, 2**63-2)
    repeats = _guard_int(record.get("repeats"), "repeats", 2, MAX_REPEATS)
    dev = record.get("device_declaration_unverified")
    sw = record.get("software_declaration_unverified")
    if type(dev) is not dict or set(dev) != {"kind", "name", "sm_count", "compute_capability"}:
        raise ValueError("invalid device declaration")
    if (type(dev["name"]) is not str or not 1 <= len(dev["name"]) <= 160
            or dev["kind"] not in ("cuda", "cpu", "synthetic")):
        raise ValueError("invalid device name/kind")
    if type(sw) is not dict or set(sw) != {"torch_version", "cuda_runtime"}:
        raise ValueError("invalid software declaration")
    if kind == "CONTROLLED_LOCAL_CAPTURE":
        if dev["kind"] == "synthetic":
            raise ValueError("real capture cannot have synthetic device")
        if type(sw["torch_version"]) is not str or not 1 <= len(sw["torch_version"]) <= 128:
            raise ValueError("real capture missing PyTorch version")
        if sw["cuda_runtime"] is not None and (type(sw["cuda_runtime"]) is not str or len(sw["cuda_runtime"]) > 128):
            raise ValueError("invalid CUDA runtime version")
        if dev["kind"] == "cuda":
            _guard_int(dev["sm_count"], "sm_count", 1, 10000)
            cc = dev["compute_capability"]
            if type(cc) is not list or len(cc) != 2:
                raise ValueError("invalid declared CUDA compute capability")
            _guard_int(cc[0], "compute capability major", 1, 100)
            _guard_int(cc[1], "compute capability minor", 0, 100)
        elif dev["sm_count"] is not None or dev["compute_capability"] is not None:
            raise ValueError("CPU declaration must not claim CUDA metadata")
    else:
        if dev["kind"] != "synthetic" or dev["sm_count"] is not None or dev["compute_capability"] is not None:
            raise ValueError("synthetic record must not pretend to be hardware")
        if sw != {"torch_version": None, "cuda_runtime": None}:
            raise ValueError("synthetic record must not claim a PyTorch capture")
    trials = record.get("trials")
    if type(trials) is not list or len(trials) != 2 * repeats:
        raise ValueError("wrong number of calibration trials")
    expected = {(rep, role) for rep in range(1, repeats + 1) for role in VALID_ROLES}
    seen = set()
    for trial in trials:
        if type(trial) is not dict or set(trial) != {"replicate", "role", "seed", "values", "values_sha256_float64_le"}:
            raise ValueError("invalid trial record")
        key = (trial["replicate"], trial["role"])
        if key not in expected or key in seen:
            raise ValueError("duplicate or unsupported trial role/replicate")
        seen.add(key)
        if type(trial["seed"]) is not int or trial["seed"] != seed + (trial["role"] == "neighbor"):
            raise ValueError("trial seed does not match declared role")
        values = trial["values"]
        if type(values) is not list or len(values) != rows * cols:
            raise ValueError("wrong trial weight count")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError("non-numeric or non-finite trial weight")
        if type(trial["values_sha256_float64_le"]) is not str or trial["values_sha256_float64_le"] != _digest(values):
            raise ValueError("trial values digest mismatch")
    if seen != expected:
        raise ValueError("missing trial")


def _measure(a: list[float], b: list[float]) -> dict:
    diffs = [x - y for x, y in zip(a, b)]
    n = len(diffs)
    return {
        "pearson": round(_pearson(a, b), 9),
        "float_value_bitwise_equal_fraction": sum(
            struct.pack("<d", x) == struct.pack("<d", y) for x, y in zip(a, b)
        ) / n,
        "mean_absolute_error": math.fsum(abs(x) for x in diffs) / n,
        "root_mean_square_error": math.sqrt(math.fsum(x * x for x in diffs) / n),
    }


def _data_sha(record: dict) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False, ensure_ascii=False).encode("utf-8")).hexdigest()


def compare_captures(a: dict, b: dict) -> dict:
    """Descriptive cross-platform study. NEVER a real-world GPU attribution."""
    _validate_capture(a)
    _validate_capture(b)
    if (a["protocol"] != b["protocol"] or
            a["data_class"] != b["data_class"] or
            a["tensor"] != b["tensor"] or a["repeats"] != b["repeats"]):
        raise ValueError("comparison requires identical protocol, seed, dtype, shape and repeats")
    ta = {(t["replicate"], t["role"]): t["values"] for t in a["trials"]}
    tb = {(t["replicate"], t["role"]): t["values"] for t in b["trials"]}
    repeats = a["repeats"]
    cross = []
    negatives = []
    for rep in range(1, repeats + 1):
        for role in VALID_ROLES:
            cross.append({"replicate": rep, "role": role,
                          **_measure(ta[(rep, role)], tb[(rep, role)])})
        negatives.append({"replicate": rep,
                          "a_target_vs_b_neighbor": _measure(
                              ta[(rep, "target")], tb[(rep, "neighbor")]),
                          "a_neighbor_vs_b_target": _measure(
                              ta[(rep, "neighbor")], tb[(rep, "target")])})
    repeat_checks = []
    for name, trials in (("a", ta), ("b", tb)):
        for role in VALID_ROLES:
            for rep in range(2, repeats + 1):
                repeat_checks.append({"capture": name, "role": role, "replicate": rep,
                                      **_measure(trials[(1, role)], trials[(rep, role)])})
    all_exact = all(x["float_value_bitwise_equal_fraction"] == 1.0 for x in cross)
    local_repeat_exact = all(x["float_value_bitwise_equal_fraction"] == 1.0 for x in repeat_checks)
    same_mean = sum(x["pearson"] for x in cross) / len(cross)
    negative_mean = sum(
        (x["a_target_vs_b_neighbor"]["pearson"] + x["a_neighbor_vs_b_target"]["pearson"])
        for x in negatives
    ) / (2 * repeats)
    return {
        "schema": REPORT_SCHEMA,
        "evidence_class": ("SYNTHETIC_DEMO_ONLY" if a["data_class"] != "CONTROLLED_LOCAL_CAPTURE"
                           else "SELF_REPORTED_CONTROLLED_CAPTURE_COMPARISON"),
        "input_sha256": {"a": _data_sha(a), "b": _data_sha(b)},
        "captures": {
            "a": {"label": a["capture_label"], "device_declared": a["device_declaration_unverified"],
                  "software_declared": a["software_declaration_unverified"]},
            "b": {"label": b["capture_label"], "device_declared": b["device_declaration_unverified"],
                  "software_declared": b["software_declaration_unverified"]},
        },
        "tensor": a["tensor"],
        "protocol": a["protocol"],
        "cross_machine_same_seed": cross,
        "cross_machine_opposite_seed_controls": negatives,
        "within_capture_repeat_controls": repeat_checks,
        "descriptive_summary": {
            "all_cross_machine_values_bit_identical": all_exact,
            "all_within_capture_repeats_bit_identical": local_repeat_exact,
            "same_seed_mean_pearson": round(same_mean, 9),
            "opposite_seed_control_mean_pearson": round(negative_mean, 9),
            "difference_same_minus_control": round(same_mean - negative_mean, 9),
            "software_version_equal_as_declared": (
                a["software_declaration_unverified"] == b["software_declaration_unverified"]),
            "device_metadata_equal_as_declared": (
                a["device_declaration_unverified"] == b["device_declaration_unverified"]),
            "same_input_file_contents": _data_sha(a) == _data_sha(b),
        },
        "hardware_identity_verified": False,
        "cross_machine_independence_verified": False,
        "external_source_authenticated": False,
        "actual_training_hardware_verified": False,
        "export_control_violation_verified": False,
        "hardware_attribution": "NOT_PERFORMED",
        "note": "Matching or differing initialization values alone do not prove hardware make, "
                "training GPU, physical location, model lineage, or legal violations. "
                "Device/software labels and two-machine independence are unauthenticated.",
    }


def demo() -> dict:
    a = synthetic_demo_capture("synthetic-a", 369, lanes=148, rows=16, cols=32)
    b = synthetic_demo_capture("synthetic-b", 369, lanes=148, rows=16, cols=32)
    c = synthetic_demo_capture("synthetic-c", 369, lanes=132, rows=16, cols=32)
    return {"schema": "phi.checkpoint.calibration.demo.v1",
            "data_class": "SYNTHETIC_FIXTURE_NOT_HARDWARE",
            "same_simulated_layout": compare_captures(a, b),
            "different_simulated_layout": compare_captures(a, c)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="PhiDiscovery R0.2: controlled multi-machine calibration")
    sub = p.add_subparsers(dest="command", required=True)
    cp = sub.add_parser("capture", help="capture REAL local PyTorch CPU or CUDA initialization")
    cp.add_argument("--label", required=True, help="anonymous local label; no hostname collection")
    cp.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    cp.add_argument("--seed", type=int, default=369)
    cp.add_argument("--rows", type=int, default=32)
    cp.add_argument("--cols", type=int, default=128)
    cp.add_argument("--repeats", type=int, default=3)
    cp.add_argument("--out", type=Path, required=True)
    cmp = sub.add_parser("compare", help="compare two independently supplied local capture records")
    cmp.add_argument("a", type=Path)
    cmp.add_argument("b", type=Path)
    cmp.add_argument("--out", type=Path, required=True)
    dm = sub.add_parser("demo", help="pure-Python simulated same vs different layouts")
    dm.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.command == "capture":
            _save(args.out, capture_pytorch(args.label, args.seed, args.rows, args.cols,
                                           args.repeats, args.device))
            print(f"Saved controlled capture {args.out}; hardware origin NOT authenticated")
        elif args.command == "compare":
            _save(args.out, compare_captures(_read_record(args.a), _read_record(args.b)))
            print(f"Saved descriptive comparison {args.out}; hardware attribution NOT performed")
        else:
            _save(args.out, demo())
            print(f"Saved SYNTHETIC DEMO {args.out}; no real GPU measured")
        return 0
    except (ValueError, RuntimeError, OSError, ImportError, KeyError) as exc:
        p.exit(2, f"Calibration error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

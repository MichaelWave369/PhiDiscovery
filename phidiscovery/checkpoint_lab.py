"""Checkpoint Forensics Lab R0.1: controlled, evidence-limited experiments.

The toy generator intentionally is NOT Philox, cuRAND or PyTorch CUDA's layout.
The PyTorch path replays a small tensor on the CURRENT machine only; it cannot
identify the hardware that trained an externally published model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import struct
from pathlib import Path

SCHEMA_TOY = "phi.checkpoint.synthetic.v1"
SCHEMA_TORCH = "phi.checkpoint.torch_capture.v1"
SCHEMA_REPORT = "phi.checkpoint.analysis.v1"
MAX_VALUES = 262144
LANES = (132, 148, 152)


def _digest(values: list[float]) -> str:
    """Digest IEEE-754 float64 representation in the recorded order."""
    h = hashlib.sha256()
    for value in values:
        if not math.isfinite(value):
            raise ValueError("non-finite weight")
        h.update(struct.pack("<d", value))
    return h.hexdigest()


def _toy_value(seed: int, lanes: int, i: int) -> float:
    """Toy stream-per-lane layout: educational SHA256 PRNG, NOT CUDA Philox."""
    lane, counter = i % lanes, i // lanes
    raw = hashlib.sha256(struct.pack("<QQQ", seed, lane, counter)).digest()
    u = (int.from_bytes(raw[:8], "little") >> 11) / (1 << 53)
    return (u - 0.5) * math.sqrt(12.0)


def _check_size(n: int) -> None:
    if type(n) is not int or not 128 <= n <= MAX_VALUES:
        raise ValueError(f"number of weights must be 128..{MAX_VALUES}")


def make_synthetic(seed: int = 953049583, lanes: int = 148,
                   count: int = 8192, noise: float = 0.25,
                   noise_seed: int = 2718) -> dict:
    """Make a controlled fake checkpoint. Never interpret it as actual GPU data."""
    _check_size(count)
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("seed must be an unsigned 64-bit integer")
    if lanes not in LANES:
        raise ValueError(f"lanes must be one of {LANES}")
    if not math.isfinite(noise) or not 0 <= noise <= 100:
        raise ValueError("noise must be a finite value between 0 and 100")
    rng = random.Random(noise_seed)
    values = [_toy_value(seed, lanes, i) + noise * rng.gauss(0, 1)
              for i in range(count)]
    return {
        "schema": SCHEMA_TOY,
        "data_class": "SYNTHETIC_NOT_REAL_GPU",
        "generator": "SHA256 toy counter-per-lane; NOT PyTorch/cuRAND/Philox",
        "experimental_truth": {"seed": seed, "lanes": lanes,
                               "noise_std": noise, "noise_seed": noise_seed},
        "values": values,
        "values_sha256": _digest(values),
    }


def _pearson(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or len(a) < 3:
        raise ValueError("vectors require same length >= 3")
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    ca = [x - ma for x in a]
    cb = [x - mb for x in b]
    da, db = sum(x*x for x in ca), sum(x*x for x in cb)
    if da == 0 or db == 0:
        return 0.0
    return max(-1.0, min(1.0, sum(x*y for x, y in zip(ca, cb)) /
                         math.sqrt(da * db)))


def _holdout(n: int) -> tuple[list[int], list[int]]:
    indices = list(range(n))
    random.Random(369).shuffle(indices)
    stop = n // 5
    # Candidate selection sees only train; independent evaluation uses holdout.
    return sorted(indices[stop:]), sorted(indices[:stop])


def _rank(observed: list[float], candidates: list[tuple[int, int, list[float]]],
          permutations: int = 99) -> dict:
    train, holdout = _holdout(len(observed))
    ranked = []
    for seed, layout, guess in candidates:
        if len(guess) != len(observed):
            raise ValueError("candidate shape mismatch")
        ranked.append({
            "seed": seed,
            "layout": layout,
            "train_pearson": _pearson([observed[i] for i in train],
                                      [guess[i] for i in train]),
            "holdout_pearson": _pearson([observed[i] for i in holdout],
                                        [guess[i] for i in holdout]),
            "exact_count": sum(struct.pack("<d", observed[i]) ==
                               struct.pack("<d", guess[i]) for i in holdout),
        })
    # Only training scores determine selection, including handling tied scores.
    ranked.sort(key=lambda row: (-row["train_pearson"], row["seed"], row["layout"]))
    winner = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else None
    # Null distribution of the maximum across ALL tried candidates, not just winner.
    holdout_observed = [observed[i] for i in holdout]
    held_guesses = [[guess[i] for i in holdout] for _, _, guess in candidates]
    rng = random.Random(963)
    null_exceedances = 0
    for _ in range(permutations):
        shuffled = holdout_observed[:]
        rng.shuffle(shuffled)
        null_max = max(_pearson(shuffled, guess) for guess in held_guesses)
        if null_max >= winner["holdout_pearson"]:
            null_exceedances += 1
    p = (null_exceedances + 1) / (permutations + 1)
    gap = winner["train_pearson"] - (runner["train_pearson"] if runner else -1)
    return {
        "candidates_ranked_by_training_only": ranked,
        "selected_candidate": winner,
        "training_margin_vs_runner_up": round(gap, 6),
        "held_out_count": len(holdout),
        "training_count": len(train),
        "permutation_trials": permutations,
        "max_candidate_null_p_monte_carlo": p,
        "decision_thresholds_exploratory_not_calibrated": {
            "train_pearson_min": 0.7,
            "holdout_pearson_min": 0.7,
            "training_margin_min": 0.25,
            "permutation_p_max": 0.05,
        },
        "controlled_pattern_recovered": (
            winner["train_pearson"] >= 0.7
            and winner["holdout_pearson"] >= 0.7
            and gap >= 0.25 and p <= 0.05
        ),
    }


def analyze_synthetic(record: dict) -> dict:
    if type(record) is not dict or record.get("schema") != SCHEMA_TOY:
        raise ValueError("expected synthetic checkpoint lab record")
    values = record.get("values")
    if not isinstance(values, list):
        raise ValueError("missing values")
    _check_size(len(values))
    if not all(type(x) in (float, int) and math.isfinite(x) for x in values):
        raise ValueError("non-numeric or non-finite weights")
    if record.get("values_sha256") != _digest(values):
        raise ValueError("checkpoint values digest mismatch")
    truth = record["experimental_truth"]
    seed = truth["seed"]
    if type(seed) is not int or not 1 <= seed < 2**64-1:
        raise ValueError("invalid synthetic seed")
    if truth["lanes"] not in LANES:
        raise ValueError("unrecognized synthetic lane count")
    candidates = [
        (s, lanes, [_toy_value(s, lanes, i) for i in range(len(values))])
        for s in (seed-1, seed, seed+1) for lanes in LANES
    ]
    result = _rank(values, candidates)
    result.update({
        "schema": SCHEMA_REPORT,
        "experiment": "SYNTHETIC_LAYOUT_AND_SEED_RECOVERY",
        "input_values_sha256": record["values_sha256"],
        "candidate_search_space": "three disclosed neighboring seeds times three toy lane counts",
        "hardware_attribution": "NOT_PERFORMED",
        "published_model_provenance_verified": False,
        "training_hardware_verified": False,
        "export_control_violation_verified": False,
        "limits": "Toy SHA256 streams are NOT CUDA Philox; tests do not distinguish Hopper from Blackwell.",
    })
    return result


def _torch_tensor(seed: int, rows: int, cols: int, device: str):
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch required for opt-in torch-capture/torch-compare") from exc
    if device not in ("cpu", "cuda"):
        raise ValueError("device must be cpu or cuda")
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA not available; no fallback or fabricated GPU result")
    torch.manual_seed(seed)
    # Preserve the exact API and shape across capture and replay.
    return torch.empty((rows, cols), device=device, dtype=torch.float32).normal_(0, 1)


def capture_torch(seed: int, rows: int, cols: int, device: str = "cuda",
                  noise: float = 0.0) -> dict:
    import torch
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise ValueError("seed must fit in 63 bits")
    if type(rows) is not int or type(cols) is not int or rows < 1 or cols < 1:
        raise ValueError("rows and cols must be positive integers")
    _check_size(rows * cols)
    if not math.isfinite(noise) or not 0 <= noise <= 100:
        raise ValueError("invalid synthetic training drift")
    t = _torch_tensor(seed, rows, cols, device)
    values = t.cpu().reshape(-1).tolist()
    if noise:
        rng = random.Random(2718)
        values = [v + noise * rng.gauss(0, 1) for v in values]
    props = torch.cuda.get_device_properties(0) if device == "cuda" else None
    return {
        "schema": SCHEMA_TORCH,
        "data_class": "LOCAL_CONTROLLED_CAPTURE_NOT_EXTERNAL_MODEL",
        "capture_api": "torch.empty((rows,cols),dtype=float32).normal_(0,1)",
        "shape": [rows, cols],
        "seed_disclosed_controlled": seed,
        "device": device,
        "device_name": torch.cuda.get_device_name(0) if props else "CPU",
        "device_sm_count": props.multi_processor_count if props else None,
        "torch_version": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "synthetic_drift_std": noise,
        "values": values,
        "values_sha256": _digest(values),
    }


def compare_torch(record: dict, seeds: list[int], device: str = "cuda") -> dict:
    if type(record) is not dict or record.get("schema") != SCHEMA_TORCH:
        raise ValueError("only controlled local torch-capture records are supported")
    values = record.get("values")
    shape = record.get("shape")
    if not isinstance(values, list) or not isinstance(shape, list) or len(shape) != 2:
        raise ValueError("invalid captured checkpoint")
    rows, cols = shape
    if any(type(x) is not int or x <= 0 for x in shape):
        raise ValueError("invalid tensor shape")
    _check_size(rows * cols)
    if len(values) != rows * cols or not all(type(x) in (int, float) and
                                             math.isfinite(x) for x in values):
        raise ValueError("invalid tensor values")
    if record.get("values_sha256") != _digest(values):
        raise ValueError("checkpoint digest mismatch")
    if device != record.get("device"):
        raise ValueError("device differs from capture; no cross-device attribution")
    if not seeds or len(seeds) > 20 or len(set(seeds)) != len(seeds):
        raise ValueError("provide 1..20 distinct candidate seeds")
    if any(type(s) is not int or not 0 <= s < 2**63 for s in seeds):
        raise ValueError("invalid candidate seed")
    # Same-device replay only. No claims about an external model or its training GPUs.
    candidates = [(s, 0, _torch_tensor(s, rows, cols, device).cpu().reshape(-1).tolist())
                  for s in seeds]
    result = _rank(values, candidates)
    result.update({
        "schema": SCHEMA_REPORT,
        "experiment": "CONTROLLED_PYTORCH_SAME_DEVICE_REPLAY",
        "input_values_sha256": record["values_sha256"],
        "capture_device": record["device_name"],
        "capture_sm_count": record["device_sm_count"],
        "hardware_attribution": "NOT_PERFORMED",
        "published_model_provenance_verified": False,
        "training_hardware_verified": False,
        "export_control_violation_verified": False,
        "limits": "Replaying a controlled tensor on its declared device is NOT cross-hardware forensic attribution. Seed was disclosed at capture.",
    })
    return result


def _read_record(path: Path) -> dict:
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("input exceeds 20 MiB cap")
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError(f"duplicate JSON key: {k}")
            result[k] = v
        return result
    def invalid_constant(s):
        raise ValueError(f"invalid JSON constant {s}")
    record = json.loads(path.read_text(encoding="utf-8"),
                        object_pairs_hook=pairs, parse_constant=invalid_constant)
    if type(record) is not dict:
        raise ValueError("top-level input must be JSON object")
    return record


def _save(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never silently replace experimental evidence.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="PhiDiscovery Checkpoint Forensics R0.1")
    sub = p.add_subparsers(dest="command", required=True)
    toy = sub.add_parser("synthetic", help="toy layout and seed recovery; NOT a GPU fingerprint")
    toy.add_argument("--seed", type=int, default=953049583)
    toy.add_argument("--lanes", type=int, choices=LANES, default=148)
    toy.add_argument("--count", type=int, default=8192)
    toy.add_argument("--noise", type=float, default=0.25)
    toy.add_argument("--out", type=Path, required=True)
    capture = sub.add_parser("torch-capture", help="capture local PyTorch initial weights")
    capture.add_argument("--seed", type=int, required=True)
    capture.add_argument("--rows", type=int, default=64)
    capture.add_argument("--cols", type=int, default=128)
    capture.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    capture.add_argument("--noise", type=float, default=0.0)
    capture.add_argument("--out", type=Path, required=True)
    compare = sub.add_parser("torch-compare", help="replay known local capture on same device")
    compare.add_argument("input", type=Path)
    compare.add_argument("--seeds", nargs="+", type=int, required=True)
    compare.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    compare.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.command == "synthetic":
            record = make_synthetic(args.seed, args.lanes, args.count, args.noise)
            _save(args.out, {"checkpoint": record,
                             "analysis": analyze_synthetic(record)})
            status = "SYNTHETIC ONLY: no GPU attribution"
        elif args.command == "torch-capture":
            _save(args.out, capture_torch(args.seed, args.rows, args.cols,
                                          args.device, args.noise))
            status = "LOCAL CAPTURE ONLY: no external model attribution"
        else:
            report = compare_torch(_read_record(args.input), args.seeds, args.device)
            _save(args.out, report)
            status = "SAME-DEVICE REPLAY ONLY: no external GPU attribution"
        print(f"{status}. Saved {args.out}")
        return 0
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        p.exit(2, f"Checkpoint Lab error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

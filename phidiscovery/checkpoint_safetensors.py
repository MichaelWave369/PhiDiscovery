"""PhiDiscovery R0.3: conservative, offline, read-only safetensors archaeology.

This is a bounded file-format inspector, NOT a model loader or a hardware
fingerprint detector. It does not import torch, pickle or untrusted model code.
See https://github.com/huggingface/safetensors for the format specification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import stat
import struct
from pathlib import Path

from .checkpoint_lab import _read_record, _save

SCHEMA = "phi.checkpoint.safetensors.manifest.v1"
COMPARE_SCHEMA = "phi.checkpoint.safetensors.comparison.v1"
HEADER_MAX_BYTES = 8 * 1024 * 1024
MAX_TENSORS = 50000
MAX_DIMS = 16
MAX_SAMPLE_VALUES = 128
CHUNK = 1024 * 1024
MAX_SOURCE_LENGTH = 512
SHA256 = re.compile(r"[0-9a-f]{64}\Z")

# Conservative subset of common safetensors dtypes. Reject unknown formats.
DTYPE_BYTES = {
    "F64": 8, "F32": 4, "F16": 2, "BF16": 2,
    "I64": 8, "U64": 8, "I32": 4, "U32": 4,
    "I16": 2, "U16": 2, "I8": 1, "U8": 1, "BOOL": 1,
    "F8_E4M3FN": 1, "F8_E5M2": 1,
    "F8_E4M3FNUZ": 1, "F8_E5M2FNUZ": 1,
}
SAMPLE_DTYPES = {"F64", "F32", "F16", "BF16"}


def _pairs(items):
    result = {}
    for k, v in items:
        if k in result:
            raise ValueError(f"duplicate safetensors JSON key: {k[:80]}")
        result[k] = v
    return result


def _reject_constant(value):
    raise ValueError(f"invalid JSON numeric constant: {value}")


def _strict_json(raw: bytes) -> dict:
    if not raw.startswith(b"{"):
        raise ValueError("safetensors header must start with '{'")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                            parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid UTF-8 safetensors header JSON") from exc
    if type(result) is not dict:
        raise ValueError("safetensors header must be an object")
    return result


def _source_value(value: object, label: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or len(value) > MAX_SOURCE_LENGTH:
        raise ValueError(f"{label} must be a string <= {MAX_SOURCE_LENGTH} characters")
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} must not contain control characters")
    return value


def _tensor_header(name: str, item: object) -> dict:
    if type(name) is not str or not name or len(name) > 1024 or name == "__metadata__":
        raise ValueError("invalid tensor name")
    if type(item) is not dict or set(item) != {"dtype", "shape", "data_offsets"}:
        raise ValueError(f"invalid tensor declaration: {name[:80]}")
    dtype = item["dtype"]
    shape = item["shape"]
    offsets = item["data_offsets"]
    if type(dtype) is not str or dtype not in DTYPE_BYTES:
        raise ValueError(f"unsupported dtype in tensor {name[:80]}")
    if type(shape) is not list or len(shape) > MAX_DIMS:
        raise ValueError("invalid tensor dimensions")
    count = 1
    for dim in shape:
        if type(dim) is not int or dim < 0 or dim > 2**63 - 1:
            raise ValueError("invalid tensor dimension")
        count *= dim
        if count > 2**63 - 1:
            raise ValueError("tensor element count exceeds limit")
    if type(offsets) is not list or len(offsets) != 2:
        raise ValueError("tensor offsets must be a pair")
    start, end = offsets
    if type(start) is not int or type(end) is not int or start < 0 or end < start:
        raise ValueError("invalid tensor byte offsets")
    if count * DTYPE_BYTES[dtype] != end - start:
        raise ValueError(f"shape and byte size disagree for {name[:80]}")
    return {"name": name, "dtype": dtype, "shape": shape,
            "data_offsets": [start, end], "numel": count,
            "byte_length": end - start}


def _read_header(path: Path) -> tuple[dict, int, int, str]:
    if path.suffix.lower() != ".safetensors":
        raise ValueError("only .safetensors files are accepted; never pass pickle/checkpoint code")
    if path.is_symlink():
        raise ValueError("symlink input refused")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("input must be a regular file")
    if info.st_size < 10:
        raise ValueError("truncated safetensors file")
    with path.open("rb") as handle:
        prefix = handle.read(8)
        if len(prefix) != 8:
            raise ValueError("truncated safetensors prefix")
        length = struct.unpack("<Q", prefix)[0]
        if length < 2 or length > HEADER_MAX_BYTES:
            raise ValueError("safetensors header exceeds bounded size")
        if 8 + length > info.st_size:
            raise ValueError("truncated safetensors header")
        raw = handle.read(length)
        if len(raw) != length:
            raise ValueError("truncated safetensors header")
    return _strict_json(raw), 8 + length, info.st_size, hashlib.sha256(raw).hexdigest()


def _read_in_chunks(path: Path, absolute_start: int = 0,
                    absolute_end: int | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        handle.seek(absolute_start)
        remaining = (None if absolute_end is None else absolute_end - absolute_start)
        while remaining is None or remaining:
            block = handle.read(CHUNK if remaining is None else min(CHUNK, remaining))
            if not block:
                if remaining is not None:
                    raise ValueError("tensor or file truncated while hashing")
                break
            digest.update(block)
            if remaining is not None:
                remaining -= len(block)
    return digest.hexdigest()


def _format_float(value: float) -> float | str:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "+Infinity" if value > 0 else "-Infinity"
    return value


def _preview(path: Path, data_start: int, tensor: dict, limit: int) -> dict:
    if tensor["dtype"] not in SAMPLE_DTYPES:
        raise ValueError("preview supports only F16, BF16, F32 or F64 float tensors")
    if type(limit) is not int or not 1 <= limit <= MAX_SAMPLE_VALUES:
        raise ValueError(f"preview count must be 1..{MAX_SAMPLE_VALUES}")
    count = min(tensor["numel"], limit)
    byte_count = count * DTYPE_BYTES[tensor["dtype"]]
    with path.open("rb") as handle:
        handle.seek(data_start + tensor["data_offsets"][0])
        raw = handle.read(byte_count)
        if len(raw) != byte_count:
            raise ValueError("preview data truncated")
    dtype = tensor["dtype"]
    values = []
    if dtype == "BF16":
        for (bfloat,) in struct.iter_unpack("<H", raw):
            values.append(struct.unpack("<f", struct.pack("<I", bfloat << 16))[0])
    else:
        format_char = {"F16": "e", "F32": "f", "F64": "d"}[dtype]
        values = [v[0] for v in struct.iter_unpack("<" + format_char, raw)]
    return {
        "tensor": tensor["name"],
        "only_first_elements_sampled_not_representative": True,
        "sample_size": count,
        "sample_raw_byte_sha256": hashlib.sha256(raw).hexdigest(),
        "values": [_format_float(x) for x in values],
        "nonfinite_value_count": sum(not math.isfinite(x) for x in values),
    }


def inspect_file(path: Path, *, model_id: str | None = None,
                 revision: str | None = None, license_id: str | None = None,
                 hash_file: bool = False, hash_tensors: bool = False,
                 preview_tensor: str | None = None,
                 preview_count: int = 16) -> dict:
    """Inspect local safetensors bytes only; no import, inference or network."""
    path = Path(path)
    for label, value in (("model_id", model_id), ("revision", revision),
                         ("license", license_id)):
        _source_value(value, label)
    header, data_start, file_size, header_digest = _read_header(path)
    if len(header) > MAX_TENSORS + 1:
        raise ValueError("too many tensor header entries")
    metadata = header.pop("__metadata__", None)
    if metadata is not None:
        if type(metadata) is not dict or len(metadata) > 1000:
            raise ValueError("invalid safetensors string metadata")
        for key, value in metadata.items():
            if type(key) is not str or type(value) is not str:
                raise ValueError("safetensors metadata must be strings")
            if len(key) > 1024 or len(value) > 65536:
                raise ValueError("safetensors metadata entry is oversized")
    tensors = [_tensor_header(name, item) for name, item in header.items()]
    if len(tensors) > MAX_TENSORS:
        raise ValueError("tensor count exceeds safety limit")
    expected = 0
    for tensor in sorted(tensors, key=lambda t: (t["data_offsets"][0], t["data_offsets"][1])):
        start, end = tensor["data_offsets"]
        if start != expected:
            raise ValueError("tensor offsets overlap or leave gaps")
        expected = end
    if expected != file_size - data_start:
        raise ValueError("tensor buffer has trailing/undeclared bytes")
    if preview_tensor is not None:
        if type(preview_tensor) is not str or preview_tensor not in header:
            raise ValueError("preview tensor not in file")
    if type(hash_file) is not bool or type(hash_tensors) is not bool:
        raise ValueError("hash options must be booleans")
    if type(preview_count) is not int or not 1 <= preview_count <= MAX_SAMPLE_VALUES:
        raise ValueError("invalid preview count")
    tensors.sort(key=lambda t: t["name"])
    if hash_tensors:
        for tensor in tensors:
            start, end = tensor["data_offsets"]
            tensor["tensor_sha256"] = _read_in_chunks(path, data_start + start,
                                                       data_start + end)
    preview = None
    if preview_tensor is not None:
        preview = _preview(path, data_start,
                           next(t for t in tensors if t["name"] == preview_tensor),
                           preview_count)
    entire_digest = _read_in_chunks(path) if hash_file else None
    if path.stat().st_size != file_size:
        raise ValueError("file size changed during inspection")
    return {
        "schema": SCHEMA,
        "data_class": "LOCAL_FILE_SELF_DECLARED_UNVERIFIED_SOURCE",
        "file_basename": path.name,
        "file_size_bytes": file_size,
        "header_sha256": header_digest,
        "full_file_sha256": entire_digest,
        "full_file_hash_computed": hash_file,
        "tensor_hashes_computed": hash_tensors,
        "source_declaration_unverified": {
            "model_id": model_id, "revision": revision, "license": license_id,
        },
        "metadata_unverified": metadata,
        "tensor_count": len(tensors),
        "tensors": tensors,
        "preview_opt_in_first_values": preview,
        "hardware_attribution": "NOT_PERFORMED",
        "training_hardware_verified": False,
        "model_lineage_verified": False,
        "source_authenticity_verified": False,
        "licensing_verified": False,
        "export_control_violation_verified": False,
        "notes": "Header and optional tensor/file hashes represent local bytes inspected, not "
                 "cryptographic publisher authentication or proof of training origin. "
                 "File may change after inspection; retain the exact source file.",
    }


def _validated_manifest(record: object) -> dict:
    if type(record) is not dict or record.get("schema") != SCHEMA:
        raise ValueError("expected checkpoint R0.3 manifest")
    if record.get("source_authenticity_verified") is not False or \
            record.get("training_hardware_verified") is not False or \
            record.get("model_lineage_verified") is not False:
        raise ValueError("manifest may not claim external scientific validation")
    count = record.get("tensor_count")
    rows = record.get("tensors")
    if type(count) is not int or not 0 <= count <= MAX_TENSORS or \
            type(rows) is not list or count != len(rows):
        raise ValueError("invalid manifest tensor count")
    seen = set()
    for tensor in rows:
        if type(tensor) is not dict:
            raise ValueError("invalid tensor row")
        name = tensor.get("name")
        if type(name) is not str or name in seen:
            raise ValueError("duplicate tensor name in manifest")
        seen.add(name)
        descriptor = _tensor_header(name, {k: tensor.get(k) for k in
                                            ("dtype", "shape", "data_offsets")})
        if tensor.get("numel") != descriptor["numel"] or \
                tensor.get("byte_length") != descriptor["byte_length"]:
            raise ValueError("inconsistent manifest tensor descriptor")
        if "tensor_sha256" in tensor and (type(tensor["tensor_sha256"]) is not str or
                                          not SHA256.fullmatch(tensor["tensor_sha256"])):
            raise ValueError("invalid tensor SHA-256")
    if record.get("tensor_hashes_computed") is True and \
            any("tensor_sha256" not in t for t in rows):
        raise ValueError("incomplete manifest tensor hashes")
    if record.get("full_file_hash_computed") is True and not (
        type(record.get("full_file_sha256")) is str and
        SHA256.fullmatch(record["full_file_sha256"])
    ):
        raise ValueError("invalid full file SHA-256")
    return record


def compare_manifests(left: dict, right: dict) -> dict:
    """Descriptive comparison of manifests, NOT proof of common lineage."""
    a = _validated_manifest(left)
    b = _validated_manifest(right)
    aa = {x["name"]: x for x in a["tensors"]}
    bb = {x["name"]: x for x in b["tensors"]}
    names = sorted(aa.keys() & bb.keys())
    same_descriptor = []
    changed_descriptor = []
    exact_bytes = []
    different_bytes = []
    not_hashed = []
    for name in names:
        arow, brow = aa[name], bb[name]
        desc_a = (arow["dtype"], arow["shape"], arow["byte_length"])
        desc_b = (brow["dtype"], brow["shape"], brow["byte_length"])
        (same_descriptor if desc_a == desc_b else changed_descriptor).append(name)
        digest_a, digest_b = arow.get("tensor_sha256"), brow.get("tensor_sha256")
        if not digest_a or not digest_b:
            not_hashed.append(name)
        elif digest_a == digest_b:
            exact_bytes.append(name)
        else:
            different_bytes.append(name)
    a_full = a.get("full_file_sha256")
    b_full = b.get("full_file_sha256")
    return {
        "schema": COMPARE_SCHEMA,
        "evidence_class": "SELF_DECLARED_CHECKPOINT_MANIFEST_COMPARISON",
        "left_file_basename": a.get("file_basename"),
        "right_file_basename": b.get("file_basename"),
        "left_tensor_count": len(aa), "right_tensor_count": len(bb),
        "common_tensor_count": len(names),
        "only_left_names": sorted(aa.keys() - bb.keys()),
        "only_right_names": sorted(bb.keys() - aa.keys()),
        "common_same_dtype_shape_size": same_descriptor,
        "common_changed_dtype_shape_size": changed_descriptor,
        "common_exact_tensor_hash_matches": exact_bytes,
        "common_different_tensor_hashes": different_bytes,
        "common_without_both_tensor_hashes": not_hashed,
        "full_file_hash_equality_when_available": (
            a_full == b_full if a_full and b_full else None),
        "model_lineage_verified": False,
        "training_hardware_verified": False,
        "source_authenticity_verified": False,
        "hardware_attribution": "NOT_PERFORMED",
        "notes": "Exact hashes establish equality only of the bytes represented by supplied "
                 "manifests, assuming trusted collection. Shared weights alone do not prove "
                 "who trained a model, derived it, or where it ran.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only local safetensors checkpoint archaeology")
    sub = parser.add_subparsers(dest="command", required=True)
    ins = sub.add_parser("inspect", help="inspect local safetensors header and optionally hash bytes")
    ins.add_argument("file", type=Path)
    ins.add_argument("--model-id")
    ins.add_argument("--revision")
    ins.add_argument("--license", dest="license_id")
    ins.add_argument("--hash-file", action="store_true")
    ins.add_argument("--hash-tensors", action="store_true")
    ins.add_argument("--preview-tensor")
    ins.add_argument("--preview-count", type=int, default=16)
    ins.add_argument("--out", type=Path, required=True)
    cmp = sub.add_parser("compare", help="compare two previously generated manifests")
    cmp.add_argument("left", type=Path)
    cmp.add_argument("right", type=Path)
    cmp.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            report = inspect_file(args.file, model_id=args.model_id,
                                  revision=args.revision, license_id=args.license_id,
                                  hash_file=args.hash_file, hash_tensors=args.hash_tensors,
                                  preview_tensor=args.preview_tensor,
                                  preview_count=args.preview_count)
        else:
            report = compare_manifests(_read_record(args.left), _read_record(args.right))
        _save(args.out, report)
        print(f"Saved {args.out}; hardware attribution NOT performed")
        return 0
    except (ValueError, OSError, KeyError, UnicodeError, OverflowError) as exc:
        parser.exit(2, f"Checkpoint ingestion error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

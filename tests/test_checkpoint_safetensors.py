"""Offline safetensors R0.3 ingest, byte-integrity, parsing and negative controls."""
from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from phidiscovery.checkpoint_safetensors import (
    _read_header, compare_manifests, inspect_file, SCHEMA, COMPARE_SCHEMA,
)

ROOT = Path(__file__).resolve().parents[1]


def make_fixture(path, *, replacement=None, metadata=None):
    """Create format-conformant synthetic local bytes; no model or CUDA needed."""
    a = struct.pack("<ffff", 1.0, -0.0, float("nan"), 4.0)
    b = struct.pack("<HH", 0x3F80, 0xBF80)  # BF16 +1.0, -1.0
    if replacement is not None:
        a = struct.pack("<ffff", 1.0, 2.0, 3.0, replacement)
    header = {
        "layer.weight": {"dtype": "F32", "shape": [2, 2], "data_offsets": [0, len(a)]},
        "layer.bias": {"dtype": "BF16", "shape": [2], "data_offsets": [len(a), len(a) + len(b)]},
    }
    if metadata is not None:
        header["__metadata__"] = metadata
    raw = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + a + b)
    return path


def make_custom(path, header, body=b""):
    raw = (header if isinstance(header, bytes) else
           json.dumps(header, separators=(",", ":")).encode("utf-8"))
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + body)
    return path


class SafetensorsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.a = make_fixture(self.base / "weights.safetensors", metadata={"format": "pt"})

    def test_metadata_only_does_not_read_values_into_receipt(self):
        result = inspect_file(self.a, model_id="test/model", revision="main", license_id="mit")
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["tensor_count"], 2)
        self.assertEqual(result["metadata_unverified"], {"format": "pt"})
        self.assertFalse(result["full_file_hash_computed"])
        self.assertIsNone(result["full_file_sha256"])
        self.assertIsNone(result["preview_opt_in_first_values"])
        self.assertNotIn("tensor_sha256", result["tensors"][0])
        self.assertEqual(result["source_declaration_unverified"]["model_id"], "test/model")
        self.assertFalse(result["source_authenticity_verified"])
        self.assertFalse(result["model_lineage_verified"])
        self.assertEqual(result["hardware_attribution"], "NOT_PERFORMED")
        self.assertEqual(result["file_basename"], "weights.safetensors")

    def test_full_and_per_tensor_hash_match_original_bytes(self):
        result = inspect_file(self.a, hash_file=True, hash_tensors=True)
        self.assertEqual(result["full_file_sha256"], hashlib.sha256(self.a.read_bytes()).hexdigest())
        self.assertEqual(result["tensor_count"], 2)
        self.assertTrue(all(len(t["tensor_sha256"]) == 64 for t in result["tensors"]))
        self.assertEqual(len({t["tensor_sha256"] for t in result["tensors"]}), 2)

    def test_f32_preview_nonfinite_as_safe_json_string(self):
        result = inspect_file(self.a, preview_tensor="layer.weight", preview_count=4)
        preview = result["preview_opt_in_first_values"]
        self.assertEqual(preview["values"][:2], [1.0, -0.0])
        self.assertEqual(preview["values"][2], "NaN")
        self.assertEqual(preview["nonfinite_value_count"], 1)
        self.assertIn("NaN", json.dumps(result, allow_nan=False))

    def test_bf16_preview_correct_endianness(self):
        result = inspect_file(self.a, preview_tensor="layer.bias", preview_count=2)
        self.assertEqual(result["preview_opt_in_first_values"]["values"], [1.0, -1.0])

    def test_exact_and_changed_weights_are_different_from_genealogy_proof(self):
        b = make_fixture(self.base / "copy.safetensors", metadata={"format": "pt"})
        changed = make_fixture(self.base / "changed.safetensors", replacement=99)
        a_report = inspect_file(self.a, hash_tensors=True, hash_file=True)
        b_report = inspect_file(b, hash_tensors=True, hash_file=True)
        c_report = inspect_file(changed, hash_tensors=True, hash_file=True)
        identical = compare_manifests(a_report, b_report)
        self.assertEqual(identical["schema"], COMPARE_SCHEMA)
        self.assertTrue(identical["full_file_hash_equality_when_available"])
        self.assertEqual(len(identical["common_exact_tensor_hash_matches"]), 2)
        different = compare_manifests(a_report, c_report)
        self.assertEqual(different["common_different_tensor_hashes"], ["layer.weight"])
        self.assertEqual(different["common_exact_tensor_hash_matches"], ["layer.bias"])
        self.assertFalse(different["model_lineage_verified"])
        self.assertFalse(different["training_hardware_verified"])

    def test_comparison_does_not_invent_equality_without_hashing(self):
        a = inspect_file(self.a)
        b = inspect_file(make_fixture(self.base / "other.safetensors", replacement=99))
        report = compare_manifests(a, b)
        self.assertEqual(len(report["common_without_both_tensor_hashes"]), 2)
        self.assertIsNone(report["full_file_hash_equality_when_available"])
        self.assertFalse(report["model_lineage_verified"])

    def test_header_shape_size_mismatch_rejected(self):
        f = make_custom(self.base / "bad.safetensors",
                        {"x": {"dtype": "F32", "shape": [8], "data_offsets": [0, 4]}},
                        b"\x00" * 4)
        with self.assertRaisesRegex(ValueError, "shape and byte size"):
            inspect_file(f)

    def test_gap_overlap_and_extra_data_rejected(self):
        for name, offsets, body in [
            ("gap", [1, 5], b"\x00" * 5),
            ("overlap", [0, 8], b"\x00" * 8),
            ("extra", [0, 4], b"\x00" * 8),
        ]:
            with self.subTest(name=name):
                header = {"x": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
                          "y": {"dtype": "F32", "shape": [1], "data_offsets": offsets}}
                if name == "extra":
                    header = {"x": header["x"]}
                f = make_custom(self.base / f"{name}.safetensors", header, body)
                with self.assertRaisesRegex(ValueError, "offsets|undeclared"):
                    inspect_file(f)

    def test_reject_unexpected_dtype_and_header_fields(self):
        for row in [
            {"dtype": "FAKE", "shape": [1], "data_offsets": [0, 4]},
            {"dtype": "F32", "shape": [1], "data_offsets": [0, 4], "execute": "no"},
        ]:
            f = make_custom(self.base / "bad.safetensors", {"x": row}, b"\x00" * 4)
            with self.assertRaisesRegex(ValueError, "unsupported dtype|invalid tensor declaration"):
                inspect_file(f)

    def test_duplicate_json_keys_and_nonfinite_header_rejected(self):
        duplicate = b'{"x":{"dtype":"F32","shape":[1],"data_offsets":[0,4]},"x":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}}'
        f = make_custom(self.base / "duplicate.safetensors", duplicate, b"\x00" * 4)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            inspect_file(f)
        f = make_custom(self.base / "badjson.safetensors",
                        b'{"x":{"dtype":"F32","shape":[NaN],"data_offsets":[0,4]}}', b"\x00" * 4)
        with self.assertRaisesRegex(ValueError, "numeric constant"):
            inspect_file(f)

    def test_reject_oversized_header_and_truncation(self):
        f = self.base / "too-large.safetensors"
        f.write_bytes(struct.pack("<Q", 8 * 1024 * 1024 + 1) + b"{}")
        with self.assertRaisesRegex(ValueError, "bounded"):
            inspect_file(f)
        f.write_bytes(struct.pack("<Q", 20) + b"{}")
        with self.assertRaisesRegex(ValueError, "truncated"):
            inspect_file(f)

    def test_reject_pickle_extension_even_if_header_is_valid(self):
        f = self.base / "unsafe.pt"
        f.write_bytes(self.a.read_bytes())
        with self.assertRaisesRegex(ValueError, r"\.safetensors"):
            inspect_file(f)

    def test_preview_requires_explicit_existing_float_tensor(self):
        with self.assertRaisesRegex(ValueError, "not in file"):
            inspect_file(self.a, preview_tensor="missing")
        with self.assertRaisesRegex(ValueError, "preview count"):
            inspect_file(self.a, preview_tensor="layer.weight", preview_count=10000)

    def test_schema_and_tampered_manifest_rejected_before_diff(self):
        a = inspect_file(self.a, hash_tensors=True)
        b = inspect_file(self.a, hash_tensors=True)
        b["tensors"][0]["tensor_sha256"] = "0" * 7
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            compare_manifests(a, b)
        b = inspect_file(self.a)
        b["model_lineage_verified"] = True
        with self.assertRaisesRegex(ValueError, "scientific validation"):
            compare_manifests(a, b)

    def test_cli_end_to_end_offline_and_exclusive_create(self):
        first = self.base / "first.json"
        second = self.base / "second.json"
        diff = self.base / "comparison.json"
        def run(*args):
            return subprocess.run([sys.executable, "-m", "phidiscovery.checkpoint_safetensors", *args],
                                  cwd=ROOT, capture_output=True, text=True)
        x = run("inspect", str(self.a), "--hash-file", "--hash-tensors", "--out", str(first))
        self.assertEqual(x.returncode, 0, x.stderr)
        y = run("inspect", str(self.a), "--hash-tensors", "--out", str(second))
        self.assertEqual(y.returncode, 0, y.stderr)
        z = run("compare", str(first), str(second), "--out", str(diff))
        self.assertEqual(z.returncode, 0, z.stderr)
        data = json.loads(diff.read_text(encoding="utf-8"))
        self.assertEqual(len(data["common_exact_tensor_hash_matches"]), 2)
        self.assertNotEqual(run("inspect", str(self.a), "--out", str(first)).returncode, 0)


if __name__ == "__main__":
    unittest.main()

# Checkpoint Archaeology R0.3 — Read-only safetensors ingestion

**Status: early research tooling.** This release supports inspectable local checkpoint file bytes, not model execution, GPU fingerprint attribution, or a validated family tree.

Reference: [official safetensors format specification](https://github.com/huggingface/safetensors#format) and [Hugging Face metadata parsing](https://huggingface.co/docs/safetensors/en/metadata_parsing).

## Why this stage matters

R0.1 explored **controlled synthetic seed/layout recovery**. R0.2 collected **actual local PyTorch initialization captures** and negative controls. R0.3 now supports **already-downloaded, locally supplied open-weight files** using a conservative, dependency-free safetensors header parser. It can verify local file hashes, examine selected tensor names/shapes/dtypes, and compare two recorded tensor manifests.

This is the beginning of studying real checkpoints, not evidence that any model was trained on a particular GPU. We do **not** implement DePue's Philox reconstruction in R0.3.

## Safetensors-specific safety

- Reads only explicitly named local files ending in .safetensors. Does not import torch, pickle, transformers, or execute remote/custom code.
- No network connections or automatic downloads; the user must obtain permitted checkpoint files separately and comply with license terms.
- At most **8 MiB of header JSON**, **50,000 tensor definitions**, **16 dimensions per tensor**, and **128 requested preview values**.
- Parses UTF-8 JSON with duplicate-key rejection and rejects invalid tensor sizes, overlapping offsets, holes, trailing undeclared bytes, malformed dimensions, illegal metadata and unknown dtype labels.
- Recognizes a conservative byte-aligned subset of common safetensors formats. Unknown/new dtype formats fail closed rather than being interpreted optimistically. This is not a full implementation of every possible version of the official parser.
- Uses little-endian offsets relative to the tensor data segment. Empty tensors and scalar tensors are accommodated.
- Streams optional SHA-256 digests in bounded memory; large file/tensor hashing may take substantial time but never loads all weights at once.
- Refuses a symbolic-link input. File source/metadata/revision/license remain **unverified user declarations**.
- Outputs are create-only JSON; no overwrite. Reports include a filename basename, never a full machine path. No secrets or system identifiers are collected.
- Data from a file could change during inspection; a file hash authenticates **the observed bytes, not a publisher**, and repeated hashes do not create an outside time anchor.

## Commands

From a PhiDiscovery checkout with Python 3.10+:

**1. Inspect a local model file, metadata only.**

    python -m phidiscovery.checkpoint_safetensors inspect "D:\models\model.safetensors" --model-id "my/reference" --revision "main" --license "check-source" --out out/checkpoint-manifest.json

The model name, revision and license are *declared* by the operator and are **not** independently verified.

**2. Opt in to full byte integrity.**

    python -m phidiscovery.checkpoint_safetensors inspect "D:\models\model.safetensors" --hash-file --hash-tensors --out out/checkpoint-hashes.json

- The full-file SHA-256 covers the complete local file, including headers and all tensor bytes.
- Per-tensor SHA-256 covers the raw declared byte interval for each tensor.
- The default mode hashes only the header and does **not** claim to have hashed all weights.

**3. Opt in to preview a small number of values.**

    python -m phidiscovery.checkpoint_safetensors inspect "D:\models\model.safetensors" --preview-tensor "model.layers.0.mlp.down_proj.weight" --preview-count 16 --out out/checkpoint-preview.json

- Preview is supported only for F16/BF16/F32/F64.
- It reads **only the first few elements** of the named tensor, not a statistically representative sample and not an initialization fingerprint.
- Nonfinite floats are represented as strings to keep JSON valid. Raw values may reveal source content: share preview reports deliberately, not by default.

**4. Compare two previously generated manifests.**

    python -m phidiscovery.checkpoint_safetensors compare out/checkpoint-hashes.json out/checkpoint-hashes-other.json --out out/checkpoint-diff.json

The result separates common names, changed shapes/dtypes, matching full tensor digests, differing tensor digests and **unknown** results for tensors without hashes. Exact byte identity can rule out differences in those specific tensor intervals. It does **not** prove inheritance, training relationships, company identity or origin.

## What a result does and does not show

| Observation | Supported conclusion | Not supported |
|---|---|---|
| Valid file header and tensor offsets | Local file has a recognized safetensors structure | Trusted publisher |
| Full SHA-256 | Identifier of exact observed file bytes | Timestamp or provenance |
| Matching tensor hashes | Same raw tensor bytes, assuming trustworthy manifests | Training run lineage |
| Different tensor hashes | At least one recorded byte differs | Cause or direction of modification |
| Same tensor shape/dtype | Same structural descriptor | Same values or common source |
| Preview values | First N numeric entries for that tensor | GPU family or initialization seed |

Both the inspector and manifest comparator deliberately set hardware_attribution to NOT_PERFORMED and training_hardware_verified/model_lineage_verified/source_authenticity_verified to false.

## Tests

    python -m unittest discover -s tests -p "test_checkpoint_safetensors.py" -v
    python -m unittest discover -s tests -v

Test fixtures are **invented, tiny safetensors** created in temporary directories by the Python tests. No real checkpoint files, model weights or external accounts are used in CI.

## Next gates

1. Validate structural parsing against the official safetensors library on a set of authorized, known test fixtures. Compare behavior for edge cases and newer dtype variants.
2. Calibrate numerical weight sampling against the actual initialization protocol, rather than first-element previews, with frozen seeds and known architectures.
3. Record model revision digests, licenses and independent provenance attestations, and design consent-based sharing of manifests.
4. Add **held-out** model-lineage hypotheses with evidence grading and contradiction review in Agentora.
5. Build a static visualization that clearly distinguishes actual observations from inferred relationships.

**Evidence above assertions. Unknown stays unknown.**

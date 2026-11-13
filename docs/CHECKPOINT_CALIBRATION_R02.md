# Checkpoint Archaeology R0.2 — Cross-Machine Calibration

**Status: experimental, controlled, offline-first. No published-model GPU attribution.**

R0.1 established a synthetic seed/layout recovery exercise and optional same-device PyTorch replay. R0.2 adds a *controlled capture comparison* protocol that can measure similarities and differences between independently supplied PyTorch tensor initialization records.

**Primary caveat:** Self-reported GPU, software version, and capture independence are not authenticated. The analysis is descriptive, not a probabilistic hardware classifier. An initialization match cannot tell us which GPU subsequently trained a model, where a GPU is located, or whether export regulations were violated.

## PyTorch reference

- https://docs.pytorch.org/docs/stable/notes/randomness.html — PyTorch does not guarantee identical results across releases, platforms and CPUs/GPUs, even with the same seeds.
- https://docs.pytorch.org/docs/stable/generated/torch.manual_seed.html — initializes RNGs on supported devices.
- https://docs.pytorch.org/docs/stable/notes/numerical_accuracy.html — floating-point results may differ across implementations.

## What is controlled

The experiment always calls a fixed API for each replicate and seed:

    torch.manual_seed(seed)
    torch.empty((rows, cols), dtype=torch.float32, device=device).normal_(0, 1)

For each capture, the seed and its **seed + 1 negative control** are rerun from a fresh RNG seed on each replicate (default three repeats). Every vector is saved and hashed as little-endian IEEE-754 float64 values converted from the original FLOAT32 tensor. The digest is a replay/integrity check, **not proof of origin**.

Captures record declared device kind and name, streaming multiprocessor count / compute capability on CUDA, PyTorch version and CUDA runtime version. They deliberately do **not** collect hostnames, user accounts, IP addresses, serial numbers, CUDA device UUIDs, or a timestamp that might be mistaken for independent attestation. The user controls where the files go; no server or network access.

All tensor lengths are 128..8192, repetitions are 2..4, and input JSON is capped at 20 MiB by the existing strict JSON parser.

## Reproduce your first local capture

From your PhiDiscovery checkout on a CUDA-enabled Windows computer:

    python -m phidiscovery.checkpoint_calibration capture --label gpu-5070-a --device cuda --seed 369 --rows 32 --cols 128 --repeats 3 --out out/calibration-5070-a.json

To repeat the experiment in a fresh capture file:

    python -m phidiscovery.checkpoint_calibration capture --label gpu-5070-b --device cuda --seed 369 --rows 32 --cols 128 --repeats 3 --out out/calibration-5070-b.json

Then compare:

    python -m phidiscovery.checkpoint_calibration compare out/calibration-5070-a.json out/calibration-5070-b.json --out out/calibration-5070-compare.json

Running both captures on **one PC** checks reproducibility but **does not** give independent hardware validation.

To compare different GPUs or machines, transfer only the local JSON capture file manually (offline), use the **same seed, shape, dtype, PyTorch API, and repeat count**, and run the comparator on either computer. Version differences are shown explicitly rather than silently ignored. Any systematic differences should be replicated under version-matched software before making hardware hypotheses.

For an independent CPU baseline use --device cpu and an explicitly different output filename. The tool never silently falls back from CUDA to CPU.

## Pure-Python demonstration (does not use real GPUs)

    python -m phidiscovery.checkpoint_calibration demo --out out/calibration-demo.json

This compares two synthetic records generated with the same *toy* SHA-256 lane layout, and a third record generated using a different *toy* lane layout. It should show that same-layout values match, different-layout values do not, and off-by-one seed controls differ. The 132/148/152 lane values in R0.1/R0.2 are **not** a faithful cuRAND or CUDA thread mapping.

## Interpret carefully

- cross_machine_same_seed: observed correlations, bit-for-bit equality fraction and absolute/squared errors for matching seed roles, repeated independently.
- cross_machine_opposite_seed_controls: deliberately mismatched target/neighbor seeds to check that agreement is not a general artifact.
- within_capture_repeat_controls: checks repeated capture stability on each self-declared device.
- descriptive_summary: overall same/control separation and whether declared software and device metadata match.
- same_input_file_contents: highlights when someone compares a capture with an identical file; this is not independent evidence.
- hardware_identity_verified, cross_machine_independence_verified, external_source_authenticated, actual_training_hardware_verified, export_control_violation_verified: always **false**.

The stored raw values may be used for other exploratory statistical tests, but any claimed hardware classifier will require independent calibration, multiple GPUs of each architecture, held-out captures, and a false-positive model accounting for candidate-search size.

## Dependencies, tests and privacy

The pure-Python comparator and synthetic demo run without dependencies beyond Python 3.10+. A *real capture* requires PyTorch installed separately. No new global dependency is added.

    python -m unittest discover -s tests -p 'test_checkpoint_calibration.py' -v
    python -m unittest discover -s tests -v

The output files are exclusive-create. Use new names for follow-up runs, and keep experimental JSON files out of version control until explicitly inspected. Never commit outside model weights, proprietary checkpoint contents, or unreviewed system metadata.

## Next validation gates

1. Capture at least two runs on one GPU. Confirm internal and repeat-run determinism.
2. Collect **independent** runs on a second NVIDIA architecture and a CPU baseline with controlled framework versions.
3. Quantify seed and layout false positives with a preregistered held-out test, not a post-hoc eye test.
4. Implement safe bounded safetensors ingestion after calibrating protocol provenance and licensing.
5. Only then consider Philox/cuRAND-specific reconstruction and a model genealogy interface.

The calibration atlas will tell us what we measured, what is uncertain, and which alternate explanations survive, rather than naming a GPU on wishful thinking.

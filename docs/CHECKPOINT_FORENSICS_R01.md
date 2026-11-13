# Checkpoint Archaeology Lab R0.1

**Research status: controlled experiment only. No published model weights have been analyzed. No NVIDIA, AMD, or other training GPU has been attributed by this code.**

## Why this exists

Will DePue's November 12, 2026 report proposes that some released model checkpoints preserve traces of their original random initialization. NVIDIA CUDA/PyTorch initialization can distribute counter-based PRNG streams across threads in a hardware-dependent way. A preserved or weakly correlated subset of weights may identify an original seed and initialization thread layout.

Primary source: https://unemploymentlabs.com/checkpoint-forensics

Do NOT confuse these statements:

1. A weight pattern correlates with a candidate initialization seed/layout.
2. A known hardware/software stack reproduced that initialization.
3. The same hardware family was used for training.
4. The hardware was physically present in a particular country.
5. Export laws were violated.

These are progressively stronger and mostly independent assertions. An initialization fingerprint does not establish 3, 4, or 5. Neither does this lab currently establish 1 or 2 for an external model.

## What ships in R0.1

### A. Synthetic forensic sandbox (pure Python standard library)

- Generates fake checkpoints using per-lane deterministic SHA-256 streams and controlled Gaussian drift.
- Uses **132, 148 and 152 lanes as toy analogies**, not actual GPU kernels or actual CUDA thread counts.
- Searches neighboring seeds across all three lane choices.
- Selects a winner using 80% training indices, then evaluates untouched 20% holdout weights.
- Includes wrong-seed and wrong-layout alternatives, a permutation null test using the maximum of all searched candidates, exploratory thresholds, a SHA-256 digest of the recorded floating-point data, and report fields explicitly blocking real-world GPU claims.
- Uses no network access, proprietary weights or model downloads.

This is an educational analog. Actual CUDA initialization uses Philox/cuRAND in PyTorch, **not the SHA-256 generator** in this experiment. Do not publish a synthetic match as a hardware attribution.

### B. Optional REAL PyTorch local capture/replay

- Creates a FLOAT32 tensor using the current installed PyTorch API and specified local CPU or CUDA device.
- Captures framework version, GPU device name, SM count (when CUDA), tensor shape and SHA-256 data digest.
- Replays candidate seeds with the **same operation on the same device**.
- Reports held-out matches and correlations while retaining an explicit NOT_PERFORMED hardware-attribution status.
- Supports controlled Gaussian drift in captured values. It does not run training or authenticate an outside model's sources.

A locally captured CUDA tensor matching a locally replayed CUDA tensor demonstrates reproducibility on that hardware. It is not a cross-architecture classifier, and it does not reproduce DePue's six-trillion-combination search.

## Running it

From your PhiDiscovery checkout with Python 3.10 or newer:

    python -m phidiscovery.checkpoint_lab synthetic --seed 953049583 --lanes 148 --noise 0.25 --out out/checkpoint-synthetic.json

Change seed, lane count or noise and watch held-out correlation. Very high noise should lead to a non-recovery verdict.

On a machine where a compatible PyTorch/CUDA installation already works:

    python -m phidiscovery.checkpoint_lab torch-capture --seed 42 --rows 64 --cols 128 --device cuda --out out/torch-capture.json
    python -m phidiscovery.checkpoint_lab torch-compare out/torch-capture.json --seeds 41 42 43 --device cuda --out out/torch-replay.json

For a CPU-only experiment, substitute --device cpu in both commands. No automatic CUDA-to-CPU fallback is permitted. Outputs are create-only, so use a fresh path for each experiment. The Python core is dependency-free; PyTorch is required only for local capture/replay. Values are capped at 262,144 and JSON inputs at 20 MiB.

Regression suite:

    python -m unittest discover -s tests -p 'test_checkpoint_lab.py' -v
    python -m unittest discover -s tests -v

## Interpreting receipts

- The flag controlled_pattern_recovered only means that this specific controlled test recovered a pattern under **uncalibrated exploratory thresholds**.
- train_pearson and holdout_pearson are empirical correlations, not an independently calibrated hardware likelihood.
- max_candidate_null_p_monte_carlo is limited by 99 shuffles, is tied to this prespecified tiny candidate set, and is **not** a six-trillion-search familywise correction.
- values_sha256 checks integrity of values in the current JSON, not source authenticity, trusted chronology, model lineage or real hardware.
- Reports never claim published_model_provenance_verified, training_hardware_verified or export_control_violation_verified.

## Roadmap toward actual checkpoint forensics

**R0.2: independent calibration.** Capture the same PyTorch release, operation, shape and seed on multiple physically distinct documented CPU/GPU systems. Record driver, compiler, CUDA and framework versions. Measure how often different devices match, including negative controls and runtime changes. A local RTX 5070 can contribute a calibration reference but cannot impersonate an H100 or GB200.

**R0.3: read-only external checkpoints.** Add bounded safetensors/weight-slice ingestion with model revision, file SHA-256, parameter name, shape, dtype and license. User-provided metadata is unverified. Never execute untrusted pickle checkpoints or remote code. No default network downloads.

**R0.4: faithful Philox/CUDA candidate generator.** Implement exact thread-layout and counter assignment from calibrated versions of PyTorch/cuRAND. Distinguish initialization algorithms, source tensor layout, dtype, reinitialized layers and transformations. A thread-count equivalence class is not necessarily a unique chip identity.

**R0.5: blinded reconstruction and calibrated null.** Freeze candidate selection before holdout testing; calibrate look-elsewhere false positives against every tested seed and layout. Include independently produced checkpoints, quantization, continued training, merging, inherited weights and erased fingerprints.

**R0.6: PhiStream + Agentora.** Register observations, candidates, contradictions, source digests, provenance and negative results. Have separate skeptical agents attack the conclusion rather than vote it into existence. Keep raw data under user control.

## Non-goals

This is not a way to locate people, reconstruct secret infrastructure, make allegations of smuggling, or prove which GPU trained an entire model. It does not infer consciousness, private training data or legal liability from a fingerprint. Unknown/unsupported is a legitimate result.

**Rule: the ledger must distinguish what was measured, what was inferred, and what remains unknown.**

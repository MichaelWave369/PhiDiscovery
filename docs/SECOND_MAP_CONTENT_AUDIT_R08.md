# ΦDiscovery Second Map R0.8: Content Fingerprints Across Renamed Records

**Status:** offline text-only comparison of supplied source excerpts, not a verified audit of hidden model training corpora. R0.8 is additive and preserves the existing R0.5 plan/commitment, R0.6 repeated-trial holdout and R0.7 dataset manifest formats.

## Why this exists

R0.7 compares record IDs. If a training dataset and an experimental holdout contain the **same underlying text** under different IDs, identifier matching can miss it. R0.8 adds a separate, bounded **content index** containing operator-supplied excerpts from both sets, and compares content fingerprints.

It produces two deliberately different findings:

- **Exact text-content match:** Unicode NFC-normalized text is identical, including whitespace. This is a possible shared-source clue even if the record IDs differ.
- **Whitespace-folded text candidate:** the texts are not exact but become equal after treating sequences of whitespace as single spaces. This is a **weaker heuristic**, because whitespace can be meaningful in scientific data, code and structured documents.

No fuzzy semantic, visual, binary, paraphrase or near-duplicate model is claimed. These are exact digest comparisons of two clearly defined text transformations.

## Contract

Input `schema_version: "0.8"` and the matching `study_id`, `holdout_id` and `identifier_namespace` from your R0.5, R0.6 and R0.7 inputs.

The index requires:
- `holdout_records`: **exactly one** `{trial_id, media_type, content}` per R0.6 holdout trial.
- `model_records`: a bounded list of `{model_id, dataset_id, record_id, media_type, content}`. Each tuple must actually exist in the R0.7 declared manifest; duplicates or unknown IDs are refused.

Only `media_type: "text/plain"` is supported. Text is UTF-8, 24–4096 bytes per record. This prevents accidentally calling generic JSON or binary serialization a standardized scientific fingerprint. Model content entries can be incomplete, but incomplete coverage is reported and **quarantines the descriptive model leader**.

Full input indices are limited to 3000 model record excerpts, in addition to the complete (already bounded) holdout trial set. For other modalities, future adapters must define explicit schemas and reproducible byte-normalization methods before any matching.

## Run the fictional pilot on Windows

Run from your updated PhiDiscovery checkout. Create a private folder outside your Git repository:

```powershell
New-Item -ItemType Directory -Force "$HOME\PhiPrivateReviews"

python -m phidiscovery predict-register examples/prediction-plan-r05.json `
  --out "$HOME\PhiPrivateReviews\r08-lock.json"

python -m phidiscovery content-audit examples/prediction-plan-r05.json `
  "$HOME\PhiPrivateReviews\r08-lock.json" `
  examples/synthetic-replicates-r06.json `
  examples/synthetic-manifest-r08.json `
  examples/synthetic-content-index-r08.json `
  --out "$HOME\PhiPrivateReviews\r08-content-report.json"
```

The intentionally **fabricated** data includes a model training entry `alias-renamed-40-b`, whose content exactly matches holdout trial `toy40-b`. Another declared evaluation excerpt only differs from `toy05-a` by whitespace. Neither ID appears directly in the corresponding holdout under the same name.

Expected output:
- R0.7 source report: `NO_EXACT_MATCH_IN_SUPPLIED_MANIFESTS_UNVERIFIED`.
- R0.8 report: `EXACT_CONTENT_OVERLAP_IN_SUPPLIED_RECORDS`.
- Nonlinear model: **1** exact-content-matched holdout trial and **1** whitespace candidate.
- `ranking_suppressed: true`; no simulated model is scientifically validated.

The test is about how **software behaves**, not proof of a leak from any real LLM or measurement campaign.

## Output and integrity

The private JSON receipt binds SHA-256 digests for the registered plan, commitment, held-out trials, R0.7 manifest and full R0.8 content index. It includes per-model match counts and bounded digest/ID samples. It deliberately does **not** copy the supplied content excerpts into the result.

**Do not treat SHA-256 as anonymization** for low-entropy or predictable contents; someone with plausible guesses can hash those guesses. Only place non-sensitive examples in public Git. Protect original private input documents and reports. Generated files are exclusive-created outside the repo and will not silently overwrite earlier receipts.

The report's `third_party_anchor_verified` and `external_timestamp_verified` flags remain **false**. This release neither creates a cryptographic signature nor checks an independently timestamped publication. Hashes bind submitted bits but cannot establish source authenticity or when a model learned a record.

## Interpreting results

The audit preserves the R0.7 identifier/manifest and R0.6 self-declared exposure risks. Any content overlap, whitespace candidate, incomplete supplied content inventory, or preexisting R0.7 risk **suppresses the descriptive leader** while retaining target-by-target scoring diagnostics for analysis.

An exact content match is evidence only that two *provided text excerpts* match. It does not prove that underlying files are authentic or that the model encountered them. A missing match is never a clean bill of health: private pretraining, paraphrases, encoding differences, omitted data and manipulated manifests can still conceal overlap.

If your source data is numeric, structured, image, spectral or binary, don't shoehorn it into `text/plain` and pretend this is scientifically reliable. Define an appropriate canonical representation first.

## Validation

```bash
python -m unittest discover -s tests -v
python -m unittest tests.test_content_audit -v
```

CI runs the entire sequence against synthetic fixtures, verifies renamed-content overlap, and asserts the leader is quarantined. It does not invoke actual Ollama models, GPUs, experimental instruments, or third-party timestamping services.

## R0.9 direction

External anchor verification using authenticated receipts and timestamps, reproducible structured-data canonicalization, and *cautious* near-duplicate candidates with independent human review. No model consensus, fingerprint similarity, or software test can replace actual experiments and separately checked source provenance.

**Ledger Above Ego. Predictions Above Persuasion.**

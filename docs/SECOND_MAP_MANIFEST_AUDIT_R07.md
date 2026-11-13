# ΦDiscovery Second Map R0.7: Manifest-Based Data Leakage Review

**Offline pilot, not a verified model-training audit.** R0.7 checks for exact shared record identifiers between a model's *operator-supplied* training/evaluation/reference dataset manifests and the holdout's individual R0.6 trial IDs. A detected match is an actionable **possible contamination flag**, not proof that a model trained on, memorized, or read an observation.

A clean-looking comparison cannot exclude renamed records, semantically duplicate data, undocumented pretraining, omitted datasets, or false/incomplete manifests. It cannot introspect model weights or private training corpora. Never describe this tool as certifying independence.

## Pipeline and isolation

1. Create a numeric R0.5 prediction plan with no outcomes and freeze it using `predict-register`.
2. Create a separate R0.6 repeated-trial holdout, with two or more uniquely named trials for every registered target.
3. Curate one R0.7 model-data manifest record for **every model**, including its known training/evaluation/reference datasets and their canonical record IDs.
4. Run `manifest-audit`. It validates all three inputs, derives canonical SHA-256 fingerprints inside an explicit shared `identifier_namespace`, compares the **R0.6 trial record IDs** against the model-declared records, and reports overlap/split/inventory risks.
5. Review the diagnostic model errors separately. A contamination, overlap, missing-inventory, or earlier R0.6 exposure flag **suppresses the descriptive leader field** in the R0.7 report; it does not delete numeric diagnostics.

This release retains the original R0.5 plans and R0.6 holdouts unchanged. R0.7 is an additive audit, not a model execution interface.

## Windows PowerShell: synthetic demonstration

From your PhiDiscovery checkout:

```powershell
New-Item -ItemType Directory -Force "$HOME\PhiPrivateReviews"

python -m phidiscovery predict-register examples/prediction-plan-r05.json `
  --out "$HOME\PhiPrivateReviews\r07-prediction-lock.json"

python -m phidiscovery manifest-audit examples/prediction-plan-r05.json `
  "$HOME\PhiPrivateReviews\r07-prediction-lock.json" `
  examples/synthetic-replicates-r06.json `
  examples/synthetic-manifest-r07.json `
  --out "$HOME\PhiPrivateReviews\r07-manifest-audit.json"
```

This **fictional** example intentionally includes the trial ID `toy70-a` in the alternative model's claimed training **and** evaluation datasets. The R0.7 output should flag:

- `manifest_status = EXACT_IDENTIFIER_OVERLAP_DECLARED`
- `ranking_suppressed = true`
- the nonlinear model has one unique matched trial identifier; that identifier also occurs in two declared dataset splits.
- `descriptive_r06_diagnostics.descriptive_leaders_if_not_quarantined = null`.
- `hypothesis_validated = false` and `proof_of_actual_training_exposure = false`.

These results verify the **software contract**, not any genuine model leak or scientific outcome.

## R0.7 manifest schema

```json
{
  "schema_version": "0.7",
  "study_id": "study-1",
  "holdout_id": "blind-set-A",
  "identifier_namespace": "lab-site-1.instrument-stream-v1",
  "model_datasets": [
    {
      "model_id": "baseline",
      "inventory_complete_declared": false,
      "notes": "Only locally available reference and fine-tuning data are listed",
      "datasets": [
        {
          "dataset_id": "local-training-v1",
          "split": "training",
          "record_ids": ["sample-001-run-a", "sample-002-run-b"]
        }
      ]
    },
    {
      "model_id": "alternative",
      "inventory_complete_declared": false,
      "notes": "Pretraining data cannot be audited",
      "datasets": [
        {
          "dataset_id": "local-evaluation-v1",
          "split": "evaluation",
          "record_ids": ["sample-003-run-c"]
        }
      ]
    }
  ]
}
```

The `model_id` values **must match the registered prediction plan exactly**. Each model needs 1–30 distinct dataset listings. Each listing has a declared `training`, `evaluation`, `reference`, or `other` split, with at most 2,000 record IDs per dataset and 30,000 total IDs per audit.

The holdout trial IDs and dataset record IDs must use **the same canonical identification scheme and `identifier_namespace`**. Otherwise comparisons are not meaningful. A `model_id` represents the hypothesis/predictor registered in the plan, and only maps to an actual model checkpoint if your external documentation establishes that relationship.

A manifest with `inventory_complete_declared: true` is **still not authenticated**. Empty inventories and incomplete declarations suppress the leaderboard. Raw identifiers and model inventory details can be sensitive. Store actual manifests and audit outputs privately outside public Git repositories. Generated SHA-256 digests are deterministic and are **not irreversible anonymization** for predictable IDs.

## Meaning of findings

- `EXACT_IDENTIFIER_OVERLAP_DECLARED`: a model listing contains the same canonical trial ID as the holdout. The overlap warrants investigation and suppresses the descriptive leader. This alone does **not** demonstrate that the model ever consumed the underlying data.
- `INCOMPLETE_OR_UNCERTAIN_EXPOSURE`: no exact trial overlap detected, but one or more declared inventories are empty/incomplete, two splits reuse an identifier, or R0.6 already reported compromised/unknown exposure or blinding.
- `NO_EXACT_MATCH_IN_SUPPLIED_MANIFESTS_UNVERIFIED`: supplied identifiers did not match and no other declared concerns were reported. This is **not a clean bill of health**. It does not prove a comprehensive, honest dataset inventory.
- The full numeric R0.6 diagnostic report remains available; its leader field is nulled if the new manifest audit quarantines the result.

## Limitations and next step

Only exact identifier equality is tested. This release cannot recognize near-duplicate records, content copied under different IDs, training corpora the operator lacks access to, or correlated artifacts that bias repeated trials. It does not establish laboratory independence, preregistration timing, factual source authenticity, statistically significant results, or a discovered physical law. **Do not interpret zero matches as evidence of zero contamination.**

For a real study, retain the original prediction receipt, independently anchored registration timestamp, raw data/instrument logs, source manifests, checkpoint metadata, and all review output. R0.8 can add content-level fingerprints, provenance attestations, and cautious near-duplicate review without automatically reclassifying claims as scientific truths.

## Validation

```bash
python -m unittest discover -s tests -v
python -m unittest tests.test_manifest_audit -v
```

CI uses **fictional data and no GPUs, external services, or model inference**.

**Ledger Above Ego. Predictions Above Persuasion.**

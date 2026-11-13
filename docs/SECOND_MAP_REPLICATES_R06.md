# ΦDiscovery Second Map R0.6: Repeated Trials and Leakage Review

**Research prototype.** This increment adds measured-trial repetitions, descriptive variability, and a structured **self-declared** exposure audit to the R0.5 locked-predictions workflow. It does **not** collect measurements, authenticate instruments, prove chronology, inspect model training sets, run AI models, or certify a discovery.

## Why

A single measurement per target can conceal unstable experimental conditions. Likewise, models may appear accurate because the holdout leaked into training or development. R0.6 keeps the already committed **R0.5 numeric prediction plan unchanged**, and scores a separate **R0.6 repeated-trial holdout**.

Every registered target must have 2–30 globally uniquely identified trials. The scorer uses the *mean observation per target*, with **each target receiving one equal weight** in the model's mean absolute error (MAE), root mean squared error (RMSE) and tolerance-hit rate. The extra trials do **not** falsely inflate the number of independent prediction targets.

## Additional metrics

For each target, the scorer reports:

- Trial count, trial IDs, arithmetic mean and sample standard deviation.
- A descriptive standard error of the mean (SEM), computed as sample SD divided by square-root of trial count. **That SEM assumes independent trials**; instrument reuse, batch effects or shared conditions can violate the assumption.
- The **largest operator-declared trial uncertainty**, used as an added floor in a conservative `SEM + max_uncertainty` descriptive margin. This is **not a confidence interval** or statistical coverage guarantee.
- Absolute prediction error versus the trial mean, whether it meets the locked R0.5 tolerance, and whether it meets the tolerance plus the descriptive margin. The latter is diagnostic only; it must never replace the preregistered primary tolerance.

Overall model comparison aggregates the target-level errors equally, not every single trial as if it were an unrelated validation sample.

## Leakage review contract

The R0.6 holdout requires:

- `protocol.predictions_frozen_before_collection` and `protocol.holdout_blinded_until_commitment`, both strict boolean *operator assertions* with a nonempty note.
- Exactly one `model_exposure` record per model from the registered plan.
- `prior_outcome_access`: `no_access_declared`, `known_access`, or `unknown`.
- `training_overlap`: `none_declared`, `known_overlap`, or `unknown`, with a note.
- A declared source `type`, `locator`, and `independence_group`.

When any access/overlap classification is known or unknown, or when chronology/blinding was not asserted, `leakage_audit.status` becomes `DECLARED_LEAKAGE_RISK` and the descriptive *leader* is suppressed. **Error diagnostics remain available** for investigation. A clean declaration reports `DECLARED_CLEAN_NOT_VERIFIED`; the synthetic fixture reports `SYNTHETIC_DEMONSTRATION` if it has no reported risks.

This is a **declaration audit**, not automatic data contamination detection. A model could have seen training records without the operator knowing. Even if all checkboxes say clean, independent verification remains necessary.

## Offline Windows PowerShell exercise

From the PhiDiscovery repository, make a private folder outside Git:

```powershell
New-Item -ItemType Directory -Force "$HOME\PhiPrivateReviews"
```

If you have not created a new commitment for this illustrative plan:

```powershell
python -m phidiscovery predict-register examples/prediction-plan-r05.json `
  --out "$HOME\PhiPrivateReviews\predictions-r06-lock.json"
```

Then run:

```powershell
python -m phidiscovery replicate-score examples/prediction-plan-r05.json `
  "$HOME\PhiPrivateReviews\predictions-r06-lock.json" `
  examples/synthetic-replicates-r06.json `
  --out "$HOME\PhiPrivateReviews\replicate-score-r06.json"
```

The fixture contains **nine invented numbers grouped into three fictional pendulum targets**, with explicitly fictional provenance. The result showcases error/uncertainty calculations only. It does **not** establish new physics.

All generated receipts are exclusive-created and should be stored outside the checkout. Use new names for repeat runs; neither scores nor private source data should be automatically committed to the repository.

## Distinguishing actual scientific evidence from software tests

An externally timestamped prediction commitment is necessary for verified preregistration, but it is **not implemented** here. Git commit order and a plan hash alone cannot attest to hidden experimental knowledge. Likewise, `source.type = instrument` is an unverified claim, not an authenticated instrument result.

Statistical significance, noise models, effective sample size, correlated trial effects, model calibration, leakage scans of actual training corpora, raw-instrument provenance, and independent laboratories are beyond R0.6. Rankings on synthetic fixtures are demonstration-only.

All targets still share one physical quantity and unit, inherited from the R0.5 plan gate. Mixed-unit comparisons must use a separately preregistered, justified normalization scheme in a future increment.

## Validation

```bash
python -m unittest discover -s tests -v
python -m unittest tests.test_replicates -v
```

CI exercises a full offline `predict-register` → `replicate-score` cycle and checks that the synthetic outcome is not reported as a scientific discovery. No external model, GPU, physical device or cloud inference is used.

## Future R0.7

Add more robust handling of within-target correlated trials, independent holdout provenance, explicit leakage cross-reference checks against training/evaluation manifests, and verifiable external anchoring of commitment digests. **Predictive performance and evidence integrity remain separate from model confidence.**

**Ledger Above Ego. Predictions Above Persuasion.**

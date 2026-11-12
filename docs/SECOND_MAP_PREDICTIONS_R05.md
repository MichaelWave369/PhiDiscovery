# ΦDiscovery Second Map R0.5: Preregistered Predictions and Holdout Scoring

**Status:** an offline, deterministic prediction-comparison pilot. It scores **user-supplied** observations and does not prove scientific laws, external preregistration chronology, source authenticity, statistical significance, or model intelligence.

## Why R0.5 exists

R0.4 can record whether reviewers **changed their arguments** after criticism. But even perfect-sounding arguments can be wrong. R0.5 asks an independent next question: **What specific numbers did competing explanations predict before test outcomes were known, and how closely did those numbers match held-out observations?**

The registration and scoring inputs are kept separate. The registration includes predicted values, conditions, units, tolerances, a baseline model and a measurement protocol. The holdout contains observations and declared source information, never given to the registration code.

## Three new offline commands

1. `predict-register` validates a prediction plan and creates a SHA-256 commitment, including hashes of all target values, tolerances, model identifiers, study and holdout identifiers.
2. `predict-check` verifies that a plan still matches its original commitment.
3. `predict-score` accepts the plan, matching commitment, and a separate holdout. It refuses changed plans, mismatched study/target IDs, missing or extra target outcomes, duplicate observations, malformed values, or different measurement units.

The scorer reports **mean absolute error (MAE), root mean squared error (RMSE), and tolerance-hit rate** for every declared model against the **same, complete set of targets**. It compares each model's MAE with the explicitly registered baseline. Its lowest-MAE field is a descriptive summary, **not a certified winner or a significance test**.

All targets in R0.5 must measure one physical quantity in one unit, for example seconds. Otherwise comparing raw MAE across kilograms and milliseconds would be meaningless. Multi-domain normalized scoring, uncertainty propagation and distributional models are future work.

## Windows PowerShell: synthetic exercise

From the PhiDiscovery repo, create a private output folder **outside your checkout**:

```powershell
New-Item -ItemType Directory -Force "$HOME\PhiPrivateReviews"
```

Register the predictions **without opening the holdout data**:

```powershell
python -m phidiscovery predict-register examples/prediction-plan-r05.json `
  --out "$HOME\PhiPrivateReviews\prediction-lock-r05.json"
```

For an actual prospective experiment, immediately **publish or independently timestamp the commitment SHA-256** before collecting or unblinding measurements. The local receipt's `external_timestamp_verified: false` is intentional. A hash alone cannot prove when you wrote it.

Verify the commitment later:

```powershell
python -m phidiscovery predict-check examples/prediction-plan-r05.json `
  "$HOME\PhiPrivateReviews\prediction-lock-r05.json"
```

After an independently collected holdout is available, run the scorer. The provided example holdout is **entirely fictional demonstration data**:

```powershell
python -m phidiscovery predict-score examples/prediction-plan-r05.json `
  "$HOME\PhiPrivateReviews\prediction-lock-r05.json" `
  examples/synthetic-holdout-r05.json `
  --out "$HOME\PhiPrivateReviews\prediction-report-r05.json"
```

Review the private report. The nonlinear illustrative model should have lower absolute prediction error on the **fabricated** large-angle samples. This result only proves the test scorer can differentiate deliberately supplied values. It demonstrates **no new scientific finding**.

**All receipts use exclusive-create paths.** Use a new name for each run. Never commit private measurements, identifiers or model outputs to the public repository.

## Prediction-plan contract

```json
{
  "schema_version": "0.5",
  "study": {
    "id": "study-1",
    "question": "Can two competing models predict a held-out observable?",
    "measurement_protocol": "Controls, sampling, blinding, calibration, timing and stopping rule",
    "holdout_id": "blind-set-A",
    "baseline_model_id": "baseline"
  },
  "models": [
    {"id": "baseline", "label": "Existing model", "hypothesis": "Reference explanation"},
    {"id": "alternative", "label": "Proposed model", "hypothesis": "Competing explanation"}
  ],
  "targets": [
    {
      "id": "sample-001",
      "quantity": "period",
      "unit": "s",
      "condition": "Angle=5 degrees, fixed length and gravity",
      "tolerance": 0.02,
      "predictions": {"baseline": 2.0, "alternative": 2.01}
    }
  ]
}
```

Study may optionally include `review_ledger_sha256`, a lowercase 64-character SHA-256 string referencing an R0.4 ledger. That link is **operator-declared provenance metadata**. R0.5 does not automatically fetch, authenticate, or execute the previous debate ledger. Store and verify the underlying ledger separately.

The holdout has matching `study_id` and `holdout_id`, a declared source `{type, locator, independence_group}`, and one `{target_id, quantity, unit, value, uncertainty}` record per registered target. All numeric values must be finite. Prediction tolerances must be positive; declared measurement uncertainty is nonnegative and is flagged if greater than the registered tolerance. Uncertainty is not yet incorporated into MAE/RMSE.

## Limits and evidence integrity

- No hidden network calls, Ollama inference, source fetches, experimental measurements, or physical-device operation.
- R0.5 does not prove measurements were collected **after** predictions were committed. For a genuine preregistration, anchor the digest using an independent timestamp and safeguard the holdout until registration is complete.
- Source type and independence group are **self-declared**; values labeled `instrument` are not automatically verified or authenticated. Synthetic values remain synthetic.
- The comparison does not estimate p-values, confidence intervals, statistical power, model calibration, noise models, causal validity, or preregistered primary endpoints beyond its fixed descriptive metrics.
- Each target currently accepts one observation and declared uncertainty. No repeated trials or hierarchical measurements yet.
- The baseline is set in advance; the scorer refuses missing models, incomplete holdouts, mixed units and silently cherry-picked targets.
- A model having smaller error on three artificial datapoints is not evidence of new laws, better cognitive ability, or independent scientific validation.
- For future PhiStream/Agentora coupling, they can propose numerical predictions **before** holdout release; scores must be computed in this deterministic engine, never returned by the models themselves.

## Testing

```bash
python -m unittest discover -s tests -v
python -m unittest tests.test_predictions -v
```

**Next milestone (R0.6):** measurable uncertainty models, multiple trials, external anchor verification, independent holdouts, and error comparisons robust to data leakage. Keep experimental instruments and source auditing separate from hypothetical model conversations.

**Ledger Above Ego. Predictions Above Persuasion.**

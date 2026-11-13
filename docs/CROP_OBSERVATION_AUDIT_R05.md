# Crop Observation Source & Uncertainty Audit · R0.5

**Experimental, entirely offline.** The ΦMathAtelier Fingerprint Atlas comparison importer from R0.4 remains supported. R0.5 adds a separately declared observation manifest for source relationships and uncertainty sensitivity. It **does not** verify original capture authenticity, research independence, decoded messages, or nonhuman origin.

## Run a synthetic demonstration

```bash
python -m phidiscovery crop-audit examples/synthetic-crop-observations-r05.json --out out/crop-r05
python -m phidiscovery check out/crop-r05/evidence-bundle.json out/crop-r05/triage-report.json
python -m unittest tests.test_crop_observations -v
```

This fixture contains three **fictional** observations. A and B intentionally declare identical SHA-256 labels, a shared capture ID, and a derivative relationship. C has no stated link to A, but its independence **cannot be inferred**. Two comparisons exercise both states, and every associated PhiDiscovery evidence record is **inconclusive** with zero eligible support.

## Manifest contract

Top-level `schema`: `phi-crop-observation-manifest/v0.5`.

```json
{
  "schema": "phi-crop-observation-manifest/v0.5",
  "seed": 369,
  "sensitivity_trials": 512,
  "observations": [
    {
      "id": "A",
      "analyst": "Observer 1",
      "radii": [18, 40, 60, 100],
      "uncertainty_px": [1, 2, 2, 3],
      "source": {
        "type": "manual_trace",
        "locator": "local-source-A",
        "image_sha256": null,
        "capture_id": "capture-A",
        "parent_ids": [],
        "license": "permission requires verification"
      }
    },
    {
      "id": "B",
      "analyst": "Observer 2",
      "radii": [20, 39, 64, 105],
      "uncertainty_px": [2, 2, 3, 3],
      "source": {
        "type": "manual_trace",
        "locator": "local-source-B",
        "image_sha256": null,
        "capture_id": "capture-B",
        "parent_ids": [],
        "license": "permission requires verification"
      }
    }
  ],
  "comparisons": [{"reference_id": "A", "candidate_id": "B"}]
}
```

The example above is a **schema illustration only**, not a verified case or invitation to claim two captures are independent. Radii and uncertainties must be in **pixels on a comparable analysis plane**, with 3–12 positive, distinct, strictly increasing radii per observation. Uncertainty bounds must be finite, nonnegative, smaller than their associated radii, and in the same pixel units. Collect those bounds from repeat observations or a documented detector-error study rather than inventing them.

An optional `source.local_file` can reference a file **inside the manifest's directory** and requires a declared `source.image_sha256`. If supplied, its bytes are hashed and checked. Files larger than 25 MiB, missing paths, invalid SHA-256, and paths escaping that directory fail closed. A valid hash establishes byte equality to the declaration only. It does not authenticate author, capture date, license, original image, or field location. Actual local image bytes are **never copied into the report**.

Supported source types: `original_photo`, `derived_image`, `publication`, `manual_trace`, and `synthetic`. Source identifiers, capture IDs, and parent graph are declared by whoever prepares the manifest; they are not independently authenticated. To audit derivatives, put parent observation IDs in `source.parent_ids`. Parents must exist in the same manifest; cycles are rejected.

## Computation

- Detect obvious links from exact matching declared image SHA-256, repeated source locator, repeated declared capture ID, or an overlap in declared parent/ancestor chains.
- An unmatched pair receives `not_proven_independent`, **never** `independent`. Different hashes, image crops, and filenames do not establish independence.
- Reuse the R0.4 ordered normalized-radius similarity method.
- For each compared observation, draw 100–2,000 fixed-seed samples, independently and **uniformly** perturbing each radius within its declared ±pixel bound.
- Score the perturbed, reordered radii, report min, max, and 5th/50th/95th percentile **sensitivity** scores. Count samples in which original ring order crosses.
- If all uncertainties are zero, report **uncertainty not assessed**; never a precise confidence interval.
- Audit records retain per-pair sources, declared licenses, byte check status, independence flags and all warnings. No hidden data retrieval or model inference occurs.

These percentiles are **not empirical confidence intervals, Bayesian posteriors, proof of geometric matching, or evidence of messages**. The uniform error assumption is a user-selected exploratory model. Compare using preregistered thresholds and independent human-made controls before considering statistical significance. Multiple-comparison and perspective effects are not corrected in this version.

## Outputs

- `source-audit.json`: source and image-integrity notes, linkage checks, and sensitivity curves
- `evidence-bundle.json`: ordinary domain-neutral PhiDiscovery candidate/evidence bundle with *only inconclusive evidence*
- `triage-report.json`, `triage-report.html`: standard evidence triage

No author, intent, or communication claims are advanced. Every candidate stays at `insufficient_evidence`; source pairing is **not** affirmative scientific evidence.

## Next

Build a visual r0.5 manifest exporter in Fingerprint Atlas, then collect licensed independent aerial sources and repeat annotations. Follow with uncertainty calibration against held-out human-made designs and explicit look-elsewhere controls. Geographic and celestial map analysis comes **after** those prerequisites.

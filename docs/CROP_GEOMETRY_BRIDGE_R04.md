# Crop Circle Observatory ↔ PhiDiscovery · R0.4 Bridge

**Status: offline research interface, not a validated crop-circle message detector.**

The [PhiMathAtelier Fingerprint Atlas](https://github.com/MichaelWave369/PhiMathAtelier/pull/21) exports a `phi-crop-geometry-comparison/v0.3` JSON receipt. Its local, scale-normalized ring comparison is useful for exploring geometric resemblance, but its 0–100 similarity score is **not** evidence of purposeful communication or nonhuman authorship.

PhiDiscovery now imports that receipt into the existing domain-neutral `schema_version: "1.0"` evidence pipeline, re-derives the score from original radii, and refuses to count the derived comparison as independent, affirmative scientific support.

## Workflow

1. In PhiMathAtelier's **Fingerprint Atlas**, load user-supplied concentric ring radii or an r0.2 Observatory detection JSON receipt.
2. Select a reference/candidate and **Export comparison**.
3. In a local checkout of PhiDiscovery, run:

```bash
python -m phidiscovery crop-import /path/to/crop-geometry-comparison.json --out out/crop-geometry
python -m phidiscovery validate out/crop-geometry/evidence-bundle.json
python -m phidiscovery check out/crop-geometry/evidence-bundle.json out/crop-geometry/triage-report.json
```

The import writes four files:

- `evidence-bundle.json`: normal PhiDiscovery 1.0 bundle with one candidate, **one inconclusive evidence record**, and research assumptions/alternatives/discriminating tests.
- `adapter-audit.json`: raw-input SHA-256, recomputed similarity and explicit unverified provenance/uncertainty/independence warnings.
- `triage-report.json` + `triage-report.html`: existing deterministic evidence review outputs. Expected stage is **insufficient_evidence**, with **zero eligible support records**.

The source file's SHA-256 records **byte integrity only**. It is *not* a license check, independent witness, chronology proof, or authentication of the original aerial image. The local receipt, not the crop-circle photograph, is hashed in this version.

## Security and data fidelity

- No network traffic, model calls, upload, or image transfer is performed.
- Input JSON size is bounded to 2 MiB.
- Only Atlas **comparison** receipts in schema `phi-crop-geometry-comparison/v0.3` with `ordered-normalized-radii-v1` are accepted. A raw Observatory image-receipt or a fingerprint **library** is not directly accepted; export a selected Atlas comparison first.
- Both profiles require 2–12 positive distinct ring radii. The bridge recomputes normalized radii and rejects contradictory ring counts, declared normalized sequences, scored similarities, names, or edit distances.
- One or more synthetic profiles classify the lone evidence record as synthetic; other cases use `source.type: other`, but **all** are `relation: inconclusive`.
- Source URLs and lineage are only *user-declared*, and no two measurements are ever counted as independent corroboration by this adapter.
- The optional random-radii toy null is **not** interpreted as statistical significance; searching many formations, orientations and possible encodings requires a preregistered, realistic multiple-hypothesis study.

## Verification

```bash
python -m unittest tests.test_crop_geometry -v
python -m unittest discover -s tests -v
python -m phidiscovery crop-import examples/synthetic-crop-comparison-r04.json --out out/crop-fixture
```

Tests cover synthetic scale copies, invalid/tampered scores and normalized radii, synthetic versus observational labels, no-support enforcement, and CLI reports. The fixture is **completely fictional**.

## What R0.4 does *not* prove

Neither the crop-circle origin nor an intentional numerical message. There is no calibrated probability of a message, no sky-map or geographic projection analysis, and no validation on independent raw aerial photographs. Ring alignment excludes noncircular design elements, image perspective and measurement uncertainty.

### Next experiments

- Attach original licensed photographs, content hashes, camera/perspective data, dates and independent measurements.
- Repeat blind annotations; measure between-operator variance, detector precision and failure modes.
- Use realistic control sets of human-made designs and preregister multiple-testing corrections.
- Investigate spatial or celestial mapping only with frozen projections, catalogs, tolerances and held-out examples.
- Add optional PhiStream model *hypothesis reviewers* without permitting model text to raise PhiDiscovery's evidence stage.

# ΦDiscovery Engine

**General-purpose, offline-first, evidence-driven scientific discovery triage.**

Status: **research prototype, not an autonomous scientist or validated analytical instrument.** The cannabinoid dataset included in this repository is **entirely synthetic teaching data**. No cannabinoids have been discovered or identified using this prototype. Results are preliminary machine-generated *hypothesis triage*, never proof of identity, novelty, biological effect, or safety.

## Philosophy

Build the general research engine before specializing it. Domain-specific analysis belongs in optional rules, not the core pipeline. Every supported claim must be traceable to its origin; independence, contradictions, data integrity, and uncertainty must be visible. We keep a skeptical agent in every run.

## Capabilities in v0.1.0

1. **Input contract:** JSON evidence bundles containing hypotheses, findings, declared source independence, data modalities and (optionally) local raw-data hashes.
2. **Deterministic analysis:** validate, sort, compute evidence admissibility, and assign non-affirmative review stages.
3. **Cross-source audit:** trace distinct sources and independence groups. Source duplication doesn't become corroboration.
4. **Skeptical checks:** contradictory evidence, unsupported precursor-mass identifications, mass accuracy/tolerance mismatch, synthetic fixture exclusion, and cannabinoid mass ambiguity.
5. **Reproducibility:** JSON receipt with input SHA-256, per-record analysis, and a `check` command to recompute it. Optional local artifact SHA-256 checks.
6. **Accessible reporting:** self-contained HTML dashboard, no server required.
7. **Local spectral adapter:** parse MGF spectra and compare to declared JSON reference peaks by precursor m/z, fragment tolerance, and baseline cosine similarity. Distinguish tentative matches, ambiguous matches, and unassigned features. All example spectra/reference fragments are fictional. A spectral match is not molecular identification.
8. **Optional reference enrichment:** read-only PubChem PUG REST lookups via a separate explicit command. Never invoked during a local run.
9. **Domain separation:** cannabinoid-specific ambiguity checks are registered in `phidiscovery/domains/` and run only for the cannabinoid domain; `examples/geology-pilot.json` demonstrates that the same core accepts a different scientific domain.

**Not yet implemented:** full validated raw LC-MS/MS workflows (mzML/mzXML processing), GNPS/MassBank retrieval, validated spectral library identification with calibrated error models, molecular formula inference, real sample-to-candidate discovery, AI model agents, automation of scientific literature review, docking, biosynthetic predictions, PhiStream integration, or formal external expert confirmation. These require validated reference data, appropriate error models, benchmarks, and explicit human review.

## v0.2: local MassBank reference import (Pilot One preparation)

ΦDiscovery can now parse licensed, locally supplied MassBank MS2 text records into a traceable spectral library using `massbank-import`. The original record accession, license, precursor/adduct, polarity, and SHA-256 digest are retained. Comparing the resulting library to experimental MGF data now filters conflicting polarity/adduct declarations and marks missing metadata as `metadata_incomplete`.

This is **an ingestion and evidence-triage capability, not a scientific identification or newly discovered cannabinoid**. No live external sample dataset is bundled or analyzed by CI. See [MassBank Pilot v0.2](docs/MASSBANK_PILOT_R02.md) for exact commands, licensing, experimental safeguards, and acceptance criteria.

```bash
python -m phidiscovery massbank-import tests/fixtures/synthetic-massbank.txt --out out/massbank-test-library.json
python -m unittest discover -s tests -v
```

## Assumption Challenger R0.1 (second-map pilot)

A new offline epistemic audit makes a candidate's assumptions, competing explanations, predeclared discriminating tests, contradictions, and missing evidence visible. It derives current evidence stages from the existing deterministic triage engine rather than substituting model opinions for measurements.

```bash
python -m phidiscovery challenge examples/assumption-challenge.json --out out/assumptions.json
```

The demo evidence is **entirely fictional**. This command produces a structured question/review plan only: it **does not run agents, perform experiments, verify scientific laws, or establish discoveries**. See [Assumption Challenger guide](docs/ASSUMPTION_CHALLENGER_R01.md) for the optional candidate metadata contract, review roles and next milestones.

## Second Map R0.2: isolated computational reviewers

Three role-blind reviewer packets can now be generated offline from an Assumption Challenger bundle. Optional **explicitly approved** local Ollama inference and receipt comparison preserve disagreements without upgrading research claims into established facts.

```bash
python -m phidiscovery review-pack examples/assumption-challenge.json --out out/review-packets.json
```

The Ollama path uses the same local chat protocol as Agentora, but **does not call Agentora or PhiStream directly**. See [Second Map R0.2](docs/SECOND_MAP_REVIEWERS_R02.md) for safe local execution, private output, portable Agentora-style receipts, and limits.

## Second Map R0.3: real Agentora local model transport

ΦDiscovery now supports an optional **real, independently gated local Agentora** reviewer bridge. It uses an explicit `review-agentora` command to dispatch role-isolated question packets through Agentora's new `/api/discovery/review` endpoint (Ollama structured chat, no normal Agentora team/memory/tools). Models can differ by role, but all statements remain unverified and cannot change scientific evidence stages.

Both repositories need their respective R0.3 updates; the default remains entirely offline. See [Second Map Agentora R0.3](docs/SECOND_MAP_AGENTORA_R03.md) for the two-step operator opt-in, local secret, private receipt handling, and exact commands.

## Second Map R0.4: scientific debate and revision ledger

A sealed round-two debate now lets each reviewer examine the **other two first-pass reviews only after the original three assessments are complete and hash-validated**. The new offline commands `debate-pack` and `debate-ledger`, plus an explicitly approved local Ollama `debate-local` runner, preserve initial and revised positions with linked event hashes. This is model argumentation, **not empirical confirmation**.

See [Second Map Debate R0.4](docs/SECOND_MAP_DEBATE_R04.md) for the full private PowerShell workflow and scientific limits.

## Second Map R0.5: preregistered predictions versus held-out measurements

Debate is not evidence. The new offline `predict-register`, `predict-check`, and `predict-score` commands freeze complete numeric predictions and tolerances into a SHA-256 commitment, then descriptively score all registered models on the exact same held-out targets. The scorer reports MAE, RMSE and tolerance-hit rate without pretending that model votes establish physical laws.

```bash
python -m unittest tests.test_predictions -v
```

The included pendulum plan/holdout is **entirely fictional**. A local digest is **not an independently timestamped preregistration**, and user-supplied observations are not automatically authenticated. See [Second Map Prediction Holdout R0.5](docs/SECOND_MAP_PREDICTIONS_R05.md) for a complete private-output PowerShell workflow and limitations.

## Second Map R0.6: repeated measurements and declared leakage review

Use an unchanged R0.5 preregistered prediction plan with a new R0.6 holdout containing 2–30 individually identified trials per target, declared uncertainty for each trial, and a required model-exposure/blinding review. `replicate-score` reports target-weighted errors, trial variability, and conservative diagnostic uncertainty margins. Rankings are suppressed when a declared leakage/chronology risk is present.

```bash
python -m unittest tests.test_replicates -v
```

**No experiment or independent provenance audit is performed**: leakage checks are operator declarations; clean flags cannot certify clean data. The example is intentionally fictional. See [Second Map R0.6](docs/SECOND_MAP_REPLICATES_R06.md) for the complete offline private-file workflow and limits.

## Second Map R0.7: training/evaluation manifest overlap audit

`manifest-audit` cross-references the **exact canonical trial IDs** from an R0.6 held-out measurement file against operator-supplied model dataset manifests. Shared identifiers, incomplete inventories and cross-split duplicates trigger explicit leakage flags and quarantine the descriptive model leader; raw prediction error diagnostics remain available.

```bash
python -m unittest tests.test_manifest_audit -v
```

This is an **offline record-identifier audit**, not an inspection of private model weights or full pretraining corpora. The deliberate overlap in the synthetic example only tests the software. A no-match result never verifies clean training data. See [Second Map Manifest Audit R0.7](docs/SECOND_MAP_MANIFEST_AUDIT_R07.md).

## Second Map R0.8: content overlap beyond renamed record identifiers

The offline `content-audit` command compares **operator-provided source excerpts** from held-out trials and declared training/evaluation data using exact and whitespace-normalized text fingerprints. Renamed record IDs can no longer conceal an *identical supplied text excerpt*. Incomplete, overlapping, or suspicious records quarantine descriptive rankings while retaining R0.7/R0.6 diagnostics.

**No actual training corpus or timestamp is authenticated.** The synthetic example deliberately plants a renamed text match, and whitespace candidates are weaker than exact matches. Full docs: [Second Map Content Audit R0.8](docs/SECOND_MAP_CONTENT_AUDIT_R08.md).

```bash
python -m unittest tests.test_content_audit -v
```

## Second Map R0.9: signed provenance receipts (optional Ed25519)

`anchor-draft` exports an unsigned, deterministic publisher claim for a PhiDiscovery research receipt. `anchor-verify` checks two separate Ed25519 signatures from a publisher and witness against **operator-pinned public keys**, and refuses tampering or mismatched artifacts. The core research workflow remains offline and dependency-free; the signature verifier uses the optional `cryptography` package:

```bash
python -m pip install ".[provenance]"
python -m unittest tests.test_provenance -v
```

**A valid signature does not prove identity, witness independence, actual observation time, or scientific truth.** The included demo intentionally signs a false historical timestamp to make that distinction impossible to miss. See [Second Map Signed Provenance R0.9](docs/SECOND_MAP_SIGNED_PROVENANCE_R09.md).

## Quick start

Requires **Python 3.10+**. No third-party dependencies for core analysis. From the repository directory:

```bash
python -m unittest discover -s tests -v
python -m phidiscovery validate examples/cannabinoid-pilot.json
python -m phidiscovery run examples/cannabinoid-pilot.json --out out
python -m phidiscovery check examples/cannabinoid-pilot.json out/report.json
python -m phidiscovery spectra examples/demo-spectra.mgf --library examples/demo-reference-spectra.json --out out/spectra-results.json
```

Open `out/report.html` in any modern browser. For Windows PowerShell, commands are identical, but you can open the report with `start out/report.html`.

To install the CLI command in your own Python environment:

```bash
python -m pip install -e .
phi-discovery run examples/cannabinoid-pilot.json --out out
```

Try the **same generic engine** on a different domain:

```bash
python -m phidiscovery run examples/geology-pilot.json --out geology-out
```

Optional **internet-enabled, read-only** identity lookup for registered compounds:

```bash
python -m phidiscovery pubchem cannabidiol --out out/pubchem-cannabidiol.json
python -m phidiscovery pubchem cannabigerol --out out/pubchem-cannabigerol.json
```

This command queries PubChem's name/property endpoint, doesn't alter the hypothesis bundle, and doesn't establish that a molecule is present in any sample. PubChem asks clients to stay below five requests per second; this CLI issues only one at a time, with limited retries/backoff on 429/503 responses. For bulk use, build a proper rate-limited batch adapter or use provider-approved bulk downloads.

## Spectrum reader and matching baseline

The optional `spectra` adapter accepts a local MGF file and an explicitly supplied library of experimental reference peaks. In the included examples **both the MGF peaks and the reference fragments are fictional**. The first feature demonstrates ambiguous matching to two identical fictional reference sets; the second demonstrates an unassigned feature, which emphatically does **not** mean a novel substance.

Reference file format:

```json
{"references": [{"id": "REFERENCE-1", "label": "Reference", "precursor_mz": 315.232, "peaks": [[91.055, 40], [123.08, 80], [174.1, 60]]}]}
```

Similarity is a simple one-to-one, intensity-weighted cosine baseline with user-settable precursor ppm and absolute fragment tolerances, requiring three fragment matches by default. It does not handle chromatography, complex adducts, collision-energy normalization, in-source fragmentation, FDR calibration, instrument correction, or structural proof. Results are never automatically counted as independent experimental evidence in the general engine. Pin trusted published spectra and assess licensing before using this on real data.

## Bundle contract v1.0

```json
{
  "schema_version": "1.0",
  "project": {"name": "Project label", "domain": "any-domain"},
  "candidates": [{"id": "C1", "label": "Candidate name", "hypothesis": "What is being tested?"}],
  "evidence": [{
    "id": "E1", "candidate_id": "C1", "kind": "ms2", "relation": "supports",
    "statement": "What was observed?",
    "source": {
      "type": "instrument", "locator": "lab-record:123", "independence_group": "lab-a",
      "artifact_path": "artifacts/raw.txt", "artifact_sha256": "64 lowercase hex characters"
    }
  }]
}
```

`artifact_path` and `artifact_sha256` are optional **together**. If supplied, the path must resolve within the directory containing the input JSON and the file must be 100 MiB or smaller. `verified_bytes` proves file bytes match the supplied hash, **not** that the measurement or interpretation is correct. Remote data source locators are labels, not silently fetched or validated. Source group independence is **self-declared** and needs human checking.

For an optional MS1 measurement, use:

```json
"kind": "ms1",
"measurement": {"observed_mz": 315.2321, "expected_mz": 315.232, "tolerance_ppm": 5}
```

This performs one simple precursor accuracy check only. It cannot determine compound identity, distinguish isomers, or replace LC-MS/MS and NMR. All supplied fixture values are invented for UI/integration testing.

## Output classifications

- `insufficient_evidence`: nothing traceable and eligible to support this candidate, or synthetic-only records.
- `early_signal`: some non-synthetic evidence, but insufficient independent and complementary support.
- `contested`: non-synthetic contradictory evidence exists; expert adjudication required.
- `candidate_for_expert_review`: at least two independently grouped evidence sources and at least one MS2/NMR/X-ray modality; **not confirmation**.

Even `candidate_for_expert_review` is a computational triage stage, not a standard chemical confidence level and not a validated novelty claim. Neither presence in cannabis nor any medical benefit is inferred automatically.

## Next-stage pilot criteria

**Pilot 1: real-data read-only evaluation.** Pin a public study accession plus license, retrieve raw data and documented reference spectra, parse standardized mzML/mzXML/MGF, use validated ppm/fragment similarity scoring, and benchmark against known controls. Keep blind holdouts. Compare against published identifications and alternate isomers; route ambiguous hits to professional reviewers.

**Pilot 2: multi-agent integration.** Add bounded worker interfaces for Literature, Spectral Matching, Biosynthetic Context, Alternative Hypothesis, and Independent Auditor. Keep deterministic checks as hard gates that agents cannot override. Use PhiStream only as an optional inference backend; do not bake inference code into this package.

**Pilot 3: scientific validation.** Collaborate with laboratory scientists for appropriate structure elucidation, including MS/MS and NMR where needed; investigate source provenance, reproducibility, contamination and analytical artifacts. Do not publicly label a substance a 'new cannabinoid' without validation.

## Safety, privacy and integrity

- The prototype operates on research metadata and public molecular information; it is **not** a guide for chemical synthesis or drug production.
- Core analysis is offline, no telemetry, no model downloads, no API keys or hidden automatic requests.
- The included pilot is synthetic, labeled as such in CLI output and HTML.
- HTML report escapes user text. Local artifact checks reject path traversal and hash mismatches.
- Future adapters must enforce licenses, personal-data minimization, sensible rate limits, and source-specific access controls.
- Source independence, genuine experimental replication, and biological safety require expert judgment.

License: MIT. Developed for the PHI369 Labs ecosystem. Inspired by the general idea of evidence-driven multi-agent research, without copying third-party implementations.

## Quantum Brain Lab (synthetic research sandbox)

PhiDiscovery now includes an optional offline educational model-comparison lab: a leaky integrate-and-fire neuron, an abstract classical two-state mixture, ideal quantum-inspired interference, and a hypothetical dephasing scenario. **This does not establish that brains perform quantum computation.** The report is self-contained and has interactive what-if controls.

~~~bash
python -m phidiscovery quantum-brain --out out/brain
~~~

Open `out/brain/quantum-brain.html` and read [the Quantum Brain Lab guide](docs/QUANTUM_BRAIN_LAB.md) for equations, limitations, and the experimental roadmap.

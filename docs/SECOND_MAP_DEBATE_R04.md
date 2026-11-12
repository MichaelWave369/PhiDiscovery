# ΦDiscovery Second Map R0.4: Scientific Debate and Revision Ledger

**Status:** implemented offline review-plan and hash-chain prototype. Neither round of model commentary proves a scientific law. No runtime GPU inference has been performed by GitHub CI.

R0.3 introduced three *blind first-pass* research roles through local Ollama or the separately gated Agentora endpoint. R0.4 adds an intentionally separate **second pass**. Only after all first-pass review receipts have passed integrity and completeness checks do reviewers see the first-pass responses of the other roles.

## Workflow

1. Freeze a research bundle and create complete first-pass receipts using `review-local` or `review-agentora`.
2. Use `debate-pack` to prepare three second-pass packets per candidate. Each includes the role's original assessment and both peers' original critiques, explicitly labeled as unverified model text.
3. Run `debate-local` with an already installed local Ollama model to ask reviewers whether they hold or revise their positions.
4. Use `debate-ledger` to verify both rounds and export a **hash-chained, ordered event ledger** recording original and revised opinions, specific stance changes, and the unaltered scientific evidence stage.

The system never overwrites first-round receipts. It does not silently promote model commentary to source evidence. Reviewers may reuse weights or training data: having different role prompts or model names is not independent laboratory replication.

## Example on Windows PowerShell

From a PhiDiscovery checkout, choose an existing **private directory outside Git**:

```powershell
New-Item -ItemType Directory -Force "$HOME\PhiPrivateReviews"
```

First pass, choose a model already installed in local Ollama:

```powershell
python -m phidiscovery review-local examples/assumption-challenge.json `
  --model qwen3:4b --execute-local --approve-local-inference `
  --out "$HOME\PhiPrivateReviews\round1.json"
```

Alternatively, produce round one via the R0.3 `review-agentora` endpoint with Agentora and its operator key/allowlist configured. R0.4 accepts either R0.2/R0.3 first-pass receipt format.

Prepare second-round packets (offline, no model call):

```powershell
python -m phidiscovery debate-pack examples/assumption-challenge.json `
  "$HOME\PhiPrivateReviews\round1.json" `
  --out "$HOME\PhiPrivateReviews\debate-plan.json"
```

Explicitly approve local second-pass inference:

```powershell
python -m phidiscovery debate-local examples/assumption-challenge.json `
  "$HOME\PhiPrivateReviews\round1.json" `
  --model qwen3:4b --execute-local --approve-local-inference `
  --out "$HOME\PhiPrivateReviews\round2.json"
```

Then reconcile without a model call:

```powershell
python -m phidiscovery debate-ledger examples/assumption-challenge.json `
  "$HOME\PhiPrivateReviews\round1.json" `
  "$HOME\PhiPrivateReviews\round2.json" `
  --out "$HOME\PhiPrivateReviews\revision-ledger.json"
```

**Use fresh file names for each run.** Private receipts and ledgers are exclusive-created and cannot be overwritten. They may contain private hypotheses and original model-generated text. Never commit them to the repo.

All steps use Python's standard library. Actual inference goes only to fixed loopback `127.0.0.1:11434/api/chat`, does not install or download models, blocks redirects, and is only invoked by the explicitly authorized command. R0.4's **second pass uses the local Ollama endpoint directly**; using Agentora as the second-pass orchestrator is not yet implemented.

## What is sealed?

The original PhiDiscovery input bundle is hashed. Round-one receipts contain bound role packets and per-response hashes. R0.4 demands **complete role coverage** and verifies the hashes. Each round-two prompt has a unique packet hash linked to the complete round-one receipt hash. Round-two receipts record their source packet hash and original response hash.

The reconciliation ledger contains original and revised response bodies, their hashes, provenance/binding details, current evidence stage, and a sequential event hash chain. Every event includes the previous event digest.

**A SHA-256 chain is not a digital signature** and does not prove authorship, honest model execution, independence of sources or scientific validity. It detects changes only relative to a separately retained trusted root and complete original inputs.

## Scientific safeguards

- The synthetic pendulum example is a toy demonstration, **not a new physics finding**.
- Full first-round coverage is mandatory. Partial or tampered receipts cannot start a valid debate.
- Model output cites only evidence IDs in the original research bundle. The existence of such an ID does not verify the original evidence.
- Reviewers see one another's opinions **only in round two**. The original review responses remain frozen.
- Revised stance labels are reported as `stance_changed`, while text changes can be reported separately. An identical stance does not guarantee unchanged meaning, and a changed stance is not a scientific discovery.
- An agent's account of why it changed positions is a **model-generated explanation**, not guaranteed insight into its internal processing.
- The revision ledger keeps `evidence_stage_unchanged` and `scientific_evidence_produced: false`.
- Local inference needs two independent command-line approval flags. No remote AI service, automatic evidence search, physical testing or publishing takes place.

## Acceptance tests

```bash
python -m unittest discover -s tests -v
```

The tests use injected synthetic model responses. They check sealed role coverage, tamper refusal, falsified citation rejection, deterministic reconciliation, linked event hashes, and separation of first and second passes. CI does **not** establish whether a model on an RTX 5070 or other physical GPU executed.

## Next step

R0.5 should add independently graded predictions and experiment preregistration, making the first meaningful yardstick *predictive performance on measurements the models have not seen*, rather than voting on which model sounds more convincing.

**Ledger Above Ego. Reality has the final say.**

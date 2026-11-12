# ΦDiscovery Second Map R0.2: Blind Computational Reviewers

This increment builds on the merged Assumption Challenger R0.1. It does **not** assert that a model has independently discovered a scientific fact. Rather, it lets separate reviewer roles inspect the same bounded research context before comparing their answers.

## Architecture

1. **PhiDiscovery** remains the deterministic scientific evidence gate and the source of truth for eligible evidence and review stage.
2. **Review packets** give the assumption challenger, alternative builder, and experiment auditor different task instructions. Each packet contains the research context but **never other reviewers' responses**.
3. **Local Ollama** is an optional explicitly approved execution backend. This is the same local `/api/chat` protocol used by Agentora's `OllamaClient`. It calls Ollama **directly** on `127.0.0.1`, not through Agentora; no Agentora server, PhiStream model, or GPU run is claimed to have executed.
4. **Comparison** validates receipt bindings, checksums, cited evidence IDs, and coverage, and highlights distinct reviewer stances. It does not pretend opinions constitute independently replicated experiments.

PhiStream's Nine Mind Feynman-style method prompts and Agentora's team orchestration provide natural future orchestration paths, but **neither is wired as a live provider in this increment**. The portable packet/receipt JSON is the first concrete interchange surface.

## Offline inspection (default)

Requires Python 3.10+, no third-party dependencies:

```powershell
python -m phidiscovery review-pack examples/assumption-challenge.json --out out/review-packets.json
python -m unittest discover -s tests -v
```

The two example hypotheses produce six role-specific packets. The example evidence is **synthetic/fictional**. This command never invokes Ollama, an API, or a scientific instrument.

## Operator-approved local model run

Start Ollama separately on the operator's machine and ensure the selected model is **already installed**. PhiDiscovery will not pull missing models or start services. Use an existing **private output directory outside the Git checkout**, not an upload-shared folder. For example:

```powershell
New-Item -ItemType Directory -Force "$HOME\PhiPrivateReviews"
python -m phidiscovery review-local examples/assumption-challenge.json `
  --model qwen3:4b --port 11434 `
  --execute-local --approve-local-inference `
  --out "$HOME\PhiPrivateReviews\review-2026-11-12.json"
```

The two flags intentionally separate local model execution from the offline-only default. The script contacts only `http://127.0.0.1:<port>/api/chat`, rejects redirects, disables streaming, limits payload and response sizes, and never falls back to a cloud endpoint. Output is exclusive-create and not silently overwritten. It may contain private hypotheses and generated text. Handle local files and Windows ACLs accordingly.

No runtime assertion about which GPU ran, model checkpoint hash, or whether the response is factual is independently authenticated. All outputs are **self-reported model statements requiring human review**.

## Reconcile and inspect disagreements

```powershell
python -m phidiscovery review-compare examples/assumption-challenge.json `
  "$HOME\PhiPrivateReviews\review-2026-11-12.json" `
  --out out/reviewer-comparison.json
```

A comparison flags disagreement when reviewer **stance labels** differ. It cannot reliably detect *semantic* disagreements hiding under a shared label. If roles agree, that also is **not independent experimental corroboration**.

The receipt schema includes `input_sha256`, `packets_sha256`, role/packet IDs, response checksums, the requested model name, and an untrusted model-reported name. Checksums detect ordinary edits and misbinding, **not malicious forgery or model authenticity**.

## Agentora adapter route

The export schema can be consumed by an Agentora team workflow or PhiStream evaluator:

- Dispatch `packets[]` to role-isolated workers without appending previous reviewers' outputs.
- Capture complete structured JSON as the `review` object with the seven required keys.
- Preserve `packet_id`, `candidate_id`, and `role` in their receipts. A bridge can construct the `reviewer-receipts.v0.2` envelope, with the matching `input_sha256`, `packets_sha256`, and response SHA-256.
- Keep external writes, calls, and permissions behind the orchestrator's own operator approval policy.
- Import with `review-compare`, then have a human decide whether to commission real experiments.

`review-compare` accepts schema-conformant imported receipts; it cannot independently establish that agents were truly isolated or ran on distinct models. Keep orchestration provenance separately and never promote agent reports to experimental evidence.

## Acceptance limits

- No auto-merge, auto-publish, code execution or web browsing by reviewer roles.
- No implicit use of Agentora's mock mode as real inference.
- No machine-created citations are admitted unless their IDs appear in the original bundle; appearing in a bundle still does not prove validity.
- At most 40 candidates, three fixed roles, and bounded packet/model outputs per run.
- Local inference may fail on unavailable models, malformed JSON, timeout, or large inputs; failure is reported and never silently treated as success.
- Reviews cannot change PhiDiscovery `current_evidence_stage` and do not establish discovery, efficacy, physical laws, or consciousness.

**Ledger Above Ego. The universe does not award bonus points for how many models agree.**

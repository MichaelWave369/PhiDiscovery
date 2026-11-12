# ΦDiscovery Second Map R0.3: Agentora local blind reviewer bridge

**Scope: an opt-in local transport adapter, not autonomous scientific discovery.** This bridge connects PhiDiscovery's existing immutable reviewer packets to the new, separately gated Agentora `POST /api/discovery/review` endpoint. Agentora uses its `OllamaClient.chat_structured` implementation to run one local model on one packet at a time. It never uses Agentora's normal team-run pipeline or memory/tools.

## Install/update both repositories

- Agentora must include its companion R0.3 review endpoint.
- PhiDiscovery must include `phidiscovery/agentora_bridge.py`.
- Run both on the *same trusted computer*, using local loopback only.
- Preinstall your chosen Ollama models. The bridge never pulls weights, installs packages, uploads records, or falls back to a cloud model.

## Start Agentora

Set private environment variables for Agentora (local `.env`, never commit credentials):

```dotenv
AGENTORA_DISCOVERY_REVIEW_ENABLED=true
AGENTORA_DISCOVERY_REVIEW_KEY=<unique-private-secret-at-least-24-characters>
AGENTORA_DISCOVERY_REVIEW_MODELS=qwen3:4b,gemma3:12b
AGENTORA_USE_MOCK_OLLAMA=false
OLLAMA_URL=http://127.0.0.1:11434
```

Start Agentora's local FastAPI server:

```powershell
uvicorn app.main:app --app-dir server --host 127.0.0.1 --port 8088
```

The API key must also be available in the ΦDiscovery terminal under **a different environment variable name**:

```powershell
$env:PHIDISCOVERY_AGENTORA_REVIEW_KEY = "<same-private-secret>"
```

## First real review (explicit opt-in)

From the PhiDiscovery checkout, use an existing private folder outside Git:

```powershell
New-Item -ItemType Directory -Force "$HOME\PhiPrivateReviews"
python -m phidiscovery review-agentora examples/assumption-challenge.json `
  --model qwen3:4b `
  --model-alternative gemma3:12b `
  --execute-local --approve-local-inference `
  --out "$HOME\PhiPrivateReviews\second-map-r03.json"
```

Each candidate produces **three first-pass reviewer statements**, separately prompted:
- `assumption_challenger`: challenge hidden assumptions.
- `alternative_builder`: produce a competing explanation.
- `experiment_auditor`: test how to distinguish them.

The three role/model settings can be explicitly overridden using `--model-challenger`, `--model-alternative` and `--model-auditor`; any unspecified role inherits `--model`. At minimum supply the common model or all three individual overrides.

The program sends one packet at a time. Previous responses are **never included in subsequent requests**, and every response is checked again against the candidate/role/packet digest, admitted evidence IDs and Agentora bridge flags. This isolates reviewers *at the prompt level*, but **does not establish independent training data, model identity, noncollusion, or independent experimental verification.**

## Inspect comparison

```powershell
python -m phidiscovery review-compare examples/assumption-challenge.json `
  "$HOME\PhiPrivateReviews\second-map-r03.json" `
  --out out/reviewer-comparison-r03.json
```

The comparison preserves each stance and original PhiDiscovery evidence stage. An agent's agreement, disagreement or cited source ID **does not promote a hypothesis to scientific truth**. The source data and statements need independently traceable experimental review.

## Safeguards

- Two CLI approval flags and separate server opt-in/configured key.
- Agentora server listens on loopback; endpoint verifies loopback client and Host, refuses browser Origin requests.
- Fixed local URL `127.0.0.1:8088`; configurable port only, not host or arbitrary URLs.
- Explicit model allowlist, server rejects mock model mode; no model downloads or remote fallback.
- No Agentora tool calls, SQLite writes, memory retrieval, jobs, browser automation or background tasks.
- Exclusive-create local JSON receipt outside repository checkout; no silent publishing.
- Offline unit tests use simulated model responses; GitHub CI **cannot prove actual hardware inference**.

## Future work

Add optional second-pass rebuttals **after** first-pass receipts are sealed, independent holdout experiments, stronger model provenance, and audit-log/revision graph integration with PhiStream and Agentora. No physical law should be changed based solely on language-model votes.

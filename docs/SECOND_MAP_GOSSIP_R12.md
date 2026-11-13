# ΦDiscovery Second Map R1.2: Cross-Observer Signed Checkpoint Gossip

**Offline cryptographic audit, not a live gossip network or independent identity service.** R1.2 compares how separately configured observers *claim* to have seen a pinned transparency log. R0.9 verifies signed research receipts, R1.0 verifies inclusion within a signed checkpoint, and R1.1 verifies a Merkle append-only consistency proof between two signed roots. R1.2 combines those ideas for multiple observer-signed sightings.

## What R1.2 actually tests

An operator supplies a JSON bundle containing **two or more observer-signed checkpoint receipts**, a trust file containing a pinned log public key and a different pinned public key for each observer, and optional R1.1 consistency proofs.

Every observer claim signs a canonical JSON object binding the observer ID, complete signed checkpoint envelope hash and **claimed** UTC observation time. The verifier checks:

- Each checkpoint has a valid Ed25519 signature from the operator-pinned **log key**.
- Each observation has a valid Ed25519 signature from the separately pinned **observer key**.
- Log and observer keys and key IDs are distinct, with at least two distinct observers. This **does not prove** separate people or institutions actually control the keys.
- Identical tree sizes with **different signed Merkle roots** are reported as `CONFLICTING_SIGNED_ROOTS_SAME_SIZE`. That is strong evidence that the supplied pinned signing key attested to incompatible roots, not proof of a trustworthy third-party observer or malicious intent.
- Different tree sizes are **not considered compatible** until a supplied R1.1 consistency proof passes cryptographic verification. Otherwise the relationship is `CROSS_SIZE_CONSISTENCY_UNRESOLVED`.
- A complete set of pairwise proven relationships with no same-size conflict produces `NO_CONFLICT_IN_SUPPLIED_SIGNED_VIEWS__INDEPENDENCE_UNVERIFIED`, **not** a proof that all clients globally saw the same history.

This audit is **read-only, offline and deterministic**. It does not fetch checkpoints, publish gossip messages, scan the internet, monitor a real log or generate real signing keys.

## The three synthetic scenarios

The included script can generate three fixtures using **ephemeral keys made by one Python process**. Its checkpoint dates deliberately claim **2000-01-01**, which is not a real observation time:

| Scenario | Signed views | Expected status |
| --- | --- | --- |
| `conflict` | 3-leaf tree versus a different 3-leaf root | `CONFLICTING_SIGNED_ROOTS_SAME_SIZE` |
| `unresolved` | 3-leaf root and a 7-leaf root, no consistency proof | `CROSS_SIZE_CONSISTENCY_UNRESOLVED` |
| `consistent` | 3-leaf and 7-leaf roots with a valid R1.1 proof | `NO_CONFLICT_IN_SUPPLIED_SIGNED_VIEWS__INDEPENDENCE_UNVERIFIED` |

The fake log, observers and timestamps mean this verifies **code behavior only**. It is not evidence of an actual transparency-log attack.

## Windows PowerShell, from your PhiDiscovery checkout

Install the same optional signing verifier used in R0.9–R1.1 and create an existing private directory outside the repository:

```powershell
python -m pip install ".[provenance]"
New-Item -ItemType Directory -Force "$HOME\PhiPrivateReviews"
```

Generate a fictional conflict, including its two untrusted observer keys:

```powershell
python examples/demo_gossip_r12.py --scenario conflict `
  --out-dir "$HOME\PhiPrivateReviews"
```

Run the audit:

```powershell
python -m phidiscovery gossip-audit `
  "$HOME\PhiPrivateReviews\demo-r12-conflict-gossip.json" `
  "$HOME\PhiPrivateReviews\demo-r12-conflict-trust.json" `
  --out "$HOME\PhiPrivateReviews\r12-conflict-report.json"
```

To test the other scenarios, pass `--scenario unresolved` or `--scenario consistent`, and use matching, new output filenames. Every receipt is exclusively created and **cannot silently overwrite** previous files. Keep real observer files and results outside public Git.

## JSON contract

The trust policy contains:

```json
{
  "schema": "phidiscovery.observer-trust.v1.2",
  "log_trust": {
    "schema": "phidiscovery.log-trust.v1.0",
    "log_id": "my-log",
    "key": {"key_id": "log-key", "public_key_base64": "actual_log_public_key"},
    "minimum_tree_size": 1
  },
  "observer_keys": [
    {"observer_id": "first-observer", "key": {
      "key_id": "observer-1", "public_key_base64": "actual_32_byte_ed25519_key_base64"
    }},
    {"observer_id": "second-observer", "key": {
      "key_id": "observer-2", "public_key_base64": "actual_32_byte_ed25519_key_base64"
    }}
  ]
}
```

The observer gossip bundle uses `schema: phidiscovery.observer-gossip.v1.2`, `log_id`, `observations` and `consistency_proofs`. A single observation has `checkpoint` (an R1.1 signed envelope), `observer_id`, `claim`, and `signature_base64`. The claim has:

```json
{
  "schema": "phidiscovery.observer-claim.v1.2",
  "observer_id": "first-observer",
  "checkpoint_envelope_sha256": "actual_64_character_lowercase_sha256",
  "claimed_seen_at": "2026-11-12T00:00:00Z"
}
```

An observer signs the exact canonical JSON claim bytes produced by `phidiscovery.engine.stable_bytes(claim)`, using its own private Ed25519 key. The `checkpoint_envelope_sha256` binds the **whole signed log checkpoint envelope**, including the log's signature. A proof entry has `older_checkpoint_sha256` and `newer_checkpoint_sha256` referencing the corresponding envelope digests, plus a valid R1.1 `proof` object.

**Keep the observers' private keys in separate secure custody.** The software does not implement key lifecycle management, identity verification or secure publication. An operator can invent two private keys and falsely claim they represent separate organizations, so a successful cryptographic check cannot certify independent witnesses.

## Output interpretation and guardrails

The report preserves digest-bound receipt metadata, counts and each observed tree root, as well as:

- `same_size_conflicts`: directly incompatible signed roots for the same size, independent of the observer labels.
- `unresolved_cross_size_pairs`: distinct-sized checkpoints lacking a valid supplied R1.1 consistency proof. The verifier does **not** assume they're consistent.
- `verified_consistency_pairs`: each pair whose specific R1.1 proof was validated.

It explicitly leaves `observer_identities_authenticated_out_of_band`, `different_key_owners_verified`, `observation_times_verified`, `checkpoint_retention_history_verified`, `global_non_equivocation_proven`, and `hypothesis_validated` set to **false**.

**A same-size signed-root conflict is important, but not yet a real-world attribution.** Establishing that a log actually served incompatible roots to separate people requires independent acquisition and chain-of-custody evidence, a trusted key registry, and ideally a publicly accessible gossip or witness mechanism.

Neither signatures nor consistency proofs reveal whether an AI model knew a held-out measurement, prove scientific findings, or verify a trusted timestamp. Those research evidence standards remain separate.

## Validation

```bash
python -m unittest discover -s tests -v
python -m unittest tests.test_gossip -v
```

CI generates test-only keys and exercises the `conflict`, `unresolved`, and `consistent` cases. It never calls a real log, network, GPU, model inference service or timestamp authority.

**Next R1.3:** authenticated observer identity registry, durable independent checkpoint journaling, and safe exchange of signed sightings between separate machines. Real cross-client auditing begins with genuine separate custodians, not more keys created in one process.

**Ledger Above Ego. Verification Above Confidence.**

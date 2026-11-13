# ΦDiscovery Second Map R1.1: Signed Log Consistency

**Status: offline cryptographic verifier, not a publicly monitored transparency-log service.**

R1.0 established inclusion of one research receipt in one signed Merkle checkpoint. R1.1 tests a different property: can the same log show a **valid append-only extension** between an older signed checkpoint and a newer signed checkpoint, without altering its earlier leaf sequence?

The verifier implements the recursive SHA-256 Merkle consistency-proof algorithm from [RFC 9162 §2.1.4](https://www.rfc-editor.org/rfc/rfc9162.html#section-2.1.4), compatible with the RFC6962-style unbalanced tree used in R1.0.

## What it checks

- **Both** old and new checkpoints are separately signed with the same operator-pinned Ed25519 log key.
- Same log ID, strict signed checkpoint shape, valid claimed UTC date strings, bounded sizes and hashes.
- Strict old/new size order, with a newer checkpoint not smaller than the old checkpoint or the independently configured minimum tree-size floor.
- A supplied **minimal Merkle consistency path** recomputes *both* original roots. A forged or altered old history fails this test.
- Equal-size checkpoints must have identical roots and an empty consistency path. This checks stability but is not proof of new leaf additions.
- All input files are parsed as strict UTF-8 JSON, refusing ambiguous duplicate keys or nonstandard numeric constants.
- A private result binds both signed checkpoint envelopes, proof and pinned log trust policy to SHA-256 digests. No output is silently overwritten.

The verifier does **not** fetch, contact, create, sign, or publish anything on an actual transparency log. It neither knows that the old checkpoint existed earlier nor that different clients saw the same log view.

## Full fictional PowerShell test

From a PhiDiscovery checkout with R1.1 merged:

```powershell
python -m pip install ".[provenance]"

New-Item -ItemType Directory -Force "$HOME\PhiPrivateReviews"

python examples/demo_log_consistency_r11.py `
  --out-dir "$HOME\PhiPrivateReviews"

python -m phidiscovery log-consistency `
  "$HOME\PhiPrivateReviews\demo-r11-older.json" `
  "$HOME\PhiPrivateReviews\demo-r11-newer.json" `
  "$HOME\PhiPrivateReviews\demo-r11-proof.json" `
  "$HOME\PhiPrivateReviews\demo-r11-log-trust.json" `
  --out "$HOME\PhiPrivateReviews\r11-consistency-report.json"
```

The demo creates seven **fictional** leaf hashes, signs one 3-leaf and one 7-leaf checkpoint, and generates the authentic Merkle proof connecting them. Both signatures are generated in one process using a temporary local private key. The checkpoint timestamps claim **2000-01-01**, deliberately demonstrating that signed dates are not authenticated. The demo has **no independent, historically retained older checkpoint**.

A successful test report says `signed_checkpoints_valid: true` and `merkle_consistency_valid: true`. It still correctly reports `older_checkpoint_independently_retained_verified: false`, `external_time_verified: false`, `cross_client_non_equivocation_verified: false`, and `hypothesis_validated: false`.

Use new filenames on repeat runs. Test receipts are exclusive-created and should remain in a private directory outside Git.

## Real-input JSON contract

For each checkpoint, provide an envelope:

```json
{
  "checkpoint": {
    "schema": "phidiscovery.log-checkpoint.v1.0",
    "log_id": "my-pinned-log",
    "tree_size": 3,
    "root_sha256": "a_real_lowercase_64_character_sha256_digest",
    "claimed_issued_at": "2026-11-12T00:00:00Z"
  },
  "signature_base64": "base64_of_the_64_byte_Ed25519_signature_on_the_canonical_checkpoint"
}
```

The newer envelope has the same `log_id`, larger `tree_size`, and its corresponding signed root. Its claimed date may be different but remains a signer's unverified claim. You can extract an R1.0 signed checkpoint envelope from its inclusion-proof JSON by preserving the `checkpoint` and `signature_base64` fields. The two signed envelopes must be obtained and retained through a separately trustworthy historical workflow for meaningful auditing.

The consistency proof is:

```json
{
  "schema": "phidiscovery.log-consistency.v1.1",
  "log_id": "my-pinned-log",
  "older_size": 3,
  "newer_size": 7,
  "consistency_path_sha256": ["valid_64_character_hex_sibling_hash"]
}
```

Here the array is illustrative, not a valid proof. Real proofs require every exact sibling digest in the bottom-up order specified by RFC 9162 §2.1.4. There is no generic hash list that can substitute for a genuine log-generated proof.

Reuse the R1.0 log trust policy with `schema: phidiscovery.log-trust.v1.0`, pinned log key and `minimum_tree_size`. Its key must be obtained from a trusted source outside the proof. The verifier refuses checkpoints violating the floor. Changing the policy locally can bypass that floor, so retain its digest or the trusted policy separately.

## What a success really means

For **these two exact, supplied signed roots**, the Merkle hashes prove that the older tree is a prefix of the newer tree, subject to the collision resistance of SHA-256 and the configured signature key trust.

It does **not** prove that the old root was retained before the new one existed. Someone with a compromised signing key can create a consistent, fictional past. Nor does it rule out a log showing *different valid histories* to different clients (equivocation), because that requires checkpoint sharing, gossip or independent witness monitoring.

R1.1 currently supports one log key for both checkpoints. Key rotation, revocation, cross-log comparisons, trusted timestamps, publication history and multi-observer monitoring need independent validation and later integrations.

The original R1.0 inclusion verifier remains unchanged: **inclusion** proves a particular leaf exists within a signed tree; **consistency** proves a signed tree extension preserves an earlier root. Both are necessary but neither alone proves scientific truth.

## Regression and CI

```bash
python -m unittest discover -s tests -v
python -m unittest tests.test_consistency -v
```

Tests cover every old/new tree-prefix combination for sizes up to 32, power-of-two and unbalanced trees, rewrites, altered paths, wrong keys, forged roots, rollback floors, malformed size fields, equal-size roots, and refusal to overwrite private receipts. CI also runs the full synthetic CLI workflow.

**R1.2 idea:** local retained-checkpoint journal with independently authenticated external checkpoint sources and cross-client comparison to detect conflicting signed roots. Genuine independent timestamp verification is still separate work.

**Ledger Above Ego. A Consistent Log Can Still Lie About Its Age.**

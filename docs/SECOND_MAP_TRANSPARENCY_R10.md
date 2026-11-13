# ΦDiscovery Second Map R1.0: Signed Transparency-Log Inclusion

**A cryptographic inclusion verifier, not yet an independently certified external timestamp service.** R1.0 is additive: it builds on the existing R0.9 publisher/witness signatures and requires a separately pinned log-signing public key. No live network service, timestamp authority, model or physical experiment is contacted automatically.

## The chain

```text
Frozen PhiDiscovery research receipt (R0.5–R0.8 or R0.4)
   -> R0.9 signed publisher claim + signed witness observation CLAIM
   -> R1.0 canonical log entry binding artifact + R0.9 anchor + trust policy digests
   -> domain-separated SHA-256 Merkle leaf
   -> RFC6962-style unbalanced Merkle inclusion proof
   -> Ed25519-signed log checkpoint containing tree size, root, log ID and claimed date
   -> separately operator-pinned log public key
   -> offline `log-verify` receipt
```

A successful verification proves, **relative to the supplied and operator-pinned keys**, that the exact receipt was included in the specific checkpoint whose root was signed by that key. It does not prove that the checkpoint was published externally, that a signer actually controls an identified institution, or that the log was append-only. Its `claimed_issued_at` timestamp is **not independently verified**.

### What is new

- `log-verify`: new CLI accepting six positional input files: `artifact`, `anchor`, `publisher_trust`, `proof`, `log_trust`; a private `--out` destination is also required.
- SHA-256 Merkle leaves are `SHA256(0x00 || canonical_json(log_entry))`. Internal nodes are `SHA256(0x01 || left_child || right_child)`. The audit path is bottom-up and the tree follows the RFC6962 recursive split at the largest power of two strictly less than the subtree's size.
- Verifier checks publisher and witness Ed25519 signatures using R0.9, plus the log's own Ed25519 checkpoint signature with a **distinct** public key and key ID.
- Includes a configurable, operator-pinned `minimum_tree_size` floor to refuse locally known smaller checkpoints. It is not an independently authenticated consistency proof.
- Strict validation for unique JSON keys, hexadecimal proof hashes, index bounds, tree size, checkpoint identity and signature payload.
- No hidden key creation, network access, data upload, log publication, or remote inference in the verifier.

## End-to-end synthetic PowerShell exercise

From the **updated PhiDiscovery repository** install the existing optional crypto extra, and prepare a private directory **outside your Git checkout**:

```powershell
python -m pip install ".[provenance]"
New-Item -ItemType Directory -Force "$HOME\PhiPrivateReviews"
```

Generate a **fictional** research commitment:

```powershell
python -m phidiscovery predict-register examples/prediction-plan-r05.json `
  --out "$HOME\PhiPrivateReviews\r10-lock.json"
```

Generate R0.9 test publisher/witness keys and a **fictional** signed anchor. These two private signing keys are ephemeral and created in the same process, so they are not independent:

```powershell
python examples/demo_signed_anchor_r09.py "$HOME\PhiPrivateReviews\r10-lock.json" `
  --out-dir "$HOME\PhiPrivateReviews"
```

Generate an R1.0 **fictional** signed five-leaf log checkpoint and matching Merkle path. The log key is also ephemeral:

```powershell
python examples/demo_log_inclusion_r10.py `
  "$HOME\PhiPrivateReviews\r10-lock.json" `
  "$HOME\PhiPrivateReviews\demo-anchor.json" `
  "$HOME\PhiPrivateReviews\demo-trust.json" `
  --out-dir "$HOME\PhiPrivateReviews"
```

Verify the complete chain:

```powershell
python -m phidiscovery log-verify `
  "$HOME\PhiPrivateReviews\r10-lock.json" `
  "$HOME\PhiPrivateReviews\demo-anchor.json" `
  "$HOME\PhiPrivateReviews\demo-trust.json" `
  "$HOME\PhiPrivateReviews\demo-log-proof.json" `
  "$HOME\PhiPrivateReviews\demo-log-trust.json" `
  --out "$HOME\PhiPrivateReviews\r10-log-report.json"
```

**All demonstrations are synthetic.** The checkpoint contains a signed **2000-01-01** claimed timestamp, intentionally impossible for this present-day demonstration. Even so, the signature and inclusion proof pass. The verifier correctly marks `external_time_source_verified: false`, `independent_log_operator_identity_verified: false`, `append_only_consistency_verified: false`, `equivocation_excluded: false`, and `hypothesis_validated: false`.

Use fresh private filenames for repeated runs. The code exclusively creates receipts and does not overwrite existing files.

## Signed proof and trust-policy contract

R1.0 inclusion proof:

```json
{
  "schema": "phidiscovery.log-inclusion.v1.0",
  "leaf_index": 3,
  "tree_size": 5,
  "audit_path_sha256": ["64_lowercase_hex_sibling_hashes_bottom_up"],
  "checkpoint": {
    "schema": "phidiscovery.log-checkpoint.v1.0",
    "log_id": "your-trusted-log-id",
    "tree_size": 5,
    "root_sha256": "64_lowercase_hex_merkle_root",
    "claimed_issued_at": "2026-11-12T12:34:56Z"
  },
  "signature_base64": "base64_of_64_bytes_signed_checkpoint"
}
```

Only `checkpoint` is signed with the separate Ed25519 log key. Because the proof is verified against its signed root and bound leaf, tampering with the path, index or leaf changes verification results even though those fields are not separately signed. Input is limited to a maximum of one million tree leaves and a maximum of 64 proof siblings.

Separate log trust-policy file:

```json
{
  "schema": "phidiscovery.log-trust.v1.0",
  "log_id": "your-trusted-log-id",
  "key": {
    "key_id": "separately-pinned-log-key-v1",
    "public_key_base64": "base64_of_32_raw_ed25519_public_key_bytes"
  },
  "minimum_tree_size": 1
}
```

The `log_id`, signing key, publisher and witness keys **must be established outside the submitted proof**, ideally from authenticated, separately maintained sources. A user can arbitrarily choose an unrelated log key and fabricate a signed root; the verifier cannot detect whether a real public service or independent observer participated.

The leaf entry binds the exact SHA-256 digests of the scientific artifact, R0.9 signed anchor, and R0.9 public-key trust policy. It does **not** include the model's actual weights or prove that a model read any real experimental data.

## Interpretation and security boundaries

What it **does** verify:
- R0.9 signatures bind the research receipt to two pinned public keys.
- A third, distinct pinned Ed25519 key signed a checkpoint that claims a particular Merkle root and tree size.
- The supplied bottom-up proof reconstructs that precise root for the research receipt leaf.
- A previously retained minimum tree size can refuse supplied checkpoints below that floor.

What it **cannot** verify:
- Real-world signer identity, institutional independence, uncompromised keys, revocation or historical publication time.
- Whether the signed log was publicly available, consistent with earlier checkpoints, append-only, or showed everyone the same root (equivocation).
- That a model did not see results before publishing the prediction, that source measurements are authentic, or that a hypothesis is correct.

**A signed checkpoint is not an RFC3161 timestamp token.** In a future externally integrated deployment, maintain out-of-band anchored trusted checkpoints, verify transparency-log consistency proofs across signed roots, pin operator identities and log public keys, and/or support a genuine independently validated timestamp authority. R1.0 only verifies the mathematical proof submitted to it.

## Verification

```bash
python -m pip install ".[provenance]"
python -m unittest discover -s tests -v
python -m unittest tests.test_transparency -v
```

CI generates ephemeral **test-only** keys and a fabricated checkpoint, verifies inclusion paths for multiple unbalanced tree sizes, rejects modified proofs and key substitutions, and explicitly asserts that genuine timestamping and scientific validation remain unverified.

**Ledger Above Ego. Signed Log Inclusion Does Not Mean Proven Scientific Truth.**

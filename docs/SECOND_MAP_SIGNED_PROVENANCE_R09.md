# ΦDiscovery Second Map R0.9: Signed Research Receipts

**Research provenance prototype, not an independently certified timestamp service.**

Earlier versions lock predictions, compare held-out measurements, and audit declared record/content overlap. R0.9 adds an **offline Ed25519 verifier** so a research receipt can be bound to a publisher's public key and a **separate witness public key**. The witness signs the publisher-claim digest, the exact publisher signature, the artifact digest and a **claimed** UTC observation time.

A valid signature says the corresponding private key signed a message. It does **not** establish that the person/institution controlling that key is who they say they are, that the witness is independent, that its clock is honest, or that the underlying scientific claim is true.

## Optional dependency

The earlier deterministic commands remain usable without third-party packages. For this R0.9 verifier, install:

```powershell
python -m pip install ".[provenance]"
```

The `provenance` extra adds `cryptography` to verify Ed25519 digital signatures. No private keys, witnesses, PKI credentials or remote services are silently created or contacted by the verifier.

## Two new commands

`anchor-draft` takes a recognized PhiDiscovery JSON receipt and exports a **canonical unsigned publisher claim**:

```powershell
python -m phidiscovery anchor-draft "$HOME\PhiPrivateReviews\r09-lock.json" `
  --out "$HOME\PhiPrivateReviews\r09-unsigned-claim.json"
```

The claim contains the artifact schema and SHA-256 of the canonical JSON artifact. Give the claim **only** to the publisher's external signer, whose Ed25519 signature will be supplied later.

`anchor-verify` accepts the original receipt, a signed-anchor envelope and a separately obtained trust policy containing **two pinned public keys**:

```powershell
python -m phidiscovery anchor-verify "$HOME\PhiPrivateReviews\r09-lock.json" `
  "$HOME\PhiPrivateReviews\r09-signed-anchor.json" `
  "$HOME\PhiPrivateReviews\r09-trust-policy.json" `
  --out "$HOME\PhiPrivateReviews\r09-verification.json"
```

Each result is exclusively created outside Git; no files or signatures are silently overwritten or published. Both commands use strict UTF-8 JSON parsing for provenance inputs, rejecting duplicate keys and nonstandard values such as `NaN` before canonical signatures are examined.

## End-to-end educational example: entirely fictional

From the PhiDiscovery checkout, ensure a private directory exists:

```powershell
New-Item -ItemType Directory -Force "$HOME\PhiPrivateReviews"

python -m phidiscovery predict-register examples/prediction-plan-r05.json `
  --out "$HOME\PhiPrivateReviews\r09-demo-lock.json"

python -m phidiscovery anchor-draft "$HOME\PhiPrivateReviews\r09-demo-lock.json" `
  --out "$HOME\PhiPrivateReviews\r09-demo-claim.json"

python examples/demo_signed_anchor_r09.py "$HOME\PhiPrivateReviews\r09-demo-lock.json" `
  --out-dir "$HOME\PhiPrivateReviews"

python -m phidiscovery anchor-verify "$HOME\PhiPrivateReviews\r09-demo-lock.json" `
  "$HOME\PhiPrivateReviews\demo-anchor.json" `
  "$HOME\PhiPrivateReviews\demo-trust.json" `
  --out "$HOME\PhiPrivateReviews\r09-demo-verification.json"
```

**WARNING: DEMONSTRATION ONLY.** The demo creates *both* signing keys in the same process and immediately discards the private keys. Neither identity nor independence is verified. The timestamp deliberately claims **2000-01-01T00:00:00Z**, which is blatantly not a verifiable observation time for this experiment. Nevertheless the two genuine signatures validate. That is the point: **cryptographically valid signatures do not establish that a signed claim is honest.**

Do not use these ephemeral keys to establish or publish real research provenance.

## Production-format protocol (not a turnkey independent TSA)

The separate publisher and witness must have independently established Ed25519 keys and an out-of-band trust relationship with the verifier. Real private keys must be stored by their rightful owners, protected according to their security policy, and never checked into Git.

The signed envelope shape:

```json
{
  "schema": "phidiscovery.signed-anchor.v0.9",
  "publisher": {
    "key_id": "publisher-v1",
    "claim": {
      "schema": "phidiscovery.publisher-claim.v0.9",
      "artifact_schema": "phidiscovery.prediction-commitment.v0.5",
      "artifact_sha256": "64_lowercase_hex_chars"
    },
    "signature_base64": "Ed25519_signature_base64"
  },
  "witness": {
    "key_id": "independent-witness-v1",
    "claim": {
      "schema": "phidiscovery.witness-claim.v0.9",
      "artifact_sha256": "64_lowercase_hex_chars",
      "publisher_claim_sha256": "64_lowercase_hex_chars",
      "publisher_signature_sha256": "64_lowercase_hex_chars",
      "claimed_observed_at": "2026-11-12T12:34:56Z"
    },
    "signature_base64": "Ed25519_signature_base64"
  }
}
```

The fields with explanatory placeholders above are not actual cryptographic values; use actual full SHA-256 strings and canonical base64 signatures. The publisher signs the **canonical UTF-8 JSON** of its `claim` using `phidiscovery.engine.stable_bytes(claim)`. The witness separately signs the canonical `witness.claim` prepared by `phidiscovery.provenance.draft_witness_claim(artifact, publisher_claim, publisher_signature_base64, claimed_observed_at)`.

The out-of-band trust policy:

```json
{
  "schema": "phidiscovery.trust-policy.v0.9",
  "publisher": {"key_id": "publisher-v1", "public_key_base64": "base64_of_32_raw_ed25519_public_key_bytes"},
  "witness": {"key_id": "independent-witness-v1", "public_key_base64": "base64_of_32_raw_ed25519_public_key_bytes"}
}
```

The public keys and key IDs must be different. The verifier will cryptographically reject missing or changed claims, swapped keys, malformed base64, signatures that don't match their payloads, invalid UTC clock strings, and changed artifact content. The output includes the SHA-256 of the trust policy and public keys so a human can compare **trusted fingerprints** through another channel.

**Key custody and identity are outside the software's trust boundary.** Anyone can manufacture a trust policy and two matching signatures, so successful verification alone is not independent testimony.

## Chronology and witness limitations

This is **not an RFC 3161 timestamp authority verifier**, a Sigstore transparency-log inclusion verifier, or an authenticated independent clock. The witness-signed `claimed_observed_at` is displayed as an **unverified timestamp claim**. R0.9 outputs:

- `publisher_ed25519_signature_valid: true`
- `witness_ed25519_signature_valid: true`
- `witness_actual_time_verified: false`
- `witness_identity_verified_out_of_band: false`
- `independent_timestamp_authority_verified: false`
- `hypothesis_validated: false`

An independently established witness identity plus independently checkable timestamp/inclusion proof remains future work. A signer's **private-key compromise** also cannot be detected by this verifier. Key revocation, certified timestamp policy, ledger immutability, certificate chains and authoritative cryptographic identities are not yet implemented.

R0.9 verifies **authenticity relative to operator-pinned keys**, not real-world historical truth. No physical experiment, trained model, trusted time service or independent institution participates in the CI demonstration.

## Testing

```bash
python -m unittest discover -s tests -v
python -m unittest tests.test_provenance -v
```

CI generates new temporary **test-only** Ed25519 keys and signs a fictional receipt, rejects tampered signatures/claims/keys, confirms the source artifact hash, and insists that chronology and scientific validation remain unverified.

**Next R1.0:** integrate a genuine independently-verifiable third-party timestamp proof (e.g. an RFC 3161 timestamp token with a pinned, verified CA chain and timestamp policy, or a signed transparency-log inclusion proof), replay resistance, revocation checks, and an explicit research source identity registry.

**Ledger Above Ego. Signed Does Not Mean True.**

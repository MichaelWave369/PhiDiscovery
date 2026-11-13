"""R0.9: offline signed provenance checks with generated TEST-ONLY keys.

No keys from this suite represent a real publisher, institution, or witness.
"""
from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from phidiscovery.cli import main
from phidiscovery.engine import InputError, sha256, stable_bytes
from phidiscovery.predictions import register
from phidiscovery.provenance import (
    ANCHOR_SCHEMA, TRUST_SCHEMA, draft_publisher_claim,
    draft_witness_claim, verify_anchor,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "examples" / "prediction-plan-r05.json"
OBSERVED = "2026-11-12T12:34:56Z"


def research_artifact():
    return register(json.loads(PLAN.read_text(encoding="utf-8")))


def b64(data):
    return base64.b64encode(data).decode("ascii")


def public_key(key):
    return b64(key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw))


def signed_fixture(artifact=None, timestamp=OBSERVED):
    artifact = research_artifact() if artifact is None else artifact
    p = Ed25519PrivateKey.generate()
    w = Ed25519PrivateKey.generate()
    claim = draft_publisher_claim(artifact)
    p_sig = b64(p.sign(stable_bytes(claim)))
    witness = draft_witness_claim(artifact, claim, p_sig, timestamp)
    anchor = {
        "schema": ANCHOR_SCHEMA,
        "publisher": {
            "key_id": "research-publisher-test",
            "claim": claim,
            "signature_base64": p_sig,
        },
        "witness": {
            "key_id": "witness-test",
            "claim": witness,
            "signature_base64": b64(w.sign(stable_bytes(witness))),
        },
    }
    policy = {
        "schema": TRUST_SCHEMA,
        "publisher": {
            "key_id": "research-publisher-test",
            "public_key_base64": public_key(p),
        },
        "witness": {
            "key_id": "witness-test",
            "public_key_base64": public_key(w),
        },
    }
    return artifact, anchor, policy


class SignedAnchorTests(unittest.TestCase):
    def test_valid_distinct_signatures_but_not_credible_timestamp(self):
        artifact, anchor, trust = signed_fixture()
        result = verify_anchor(artifact, anchor, trust)
        self.assertTrue(result["publisher_ed25519_signature_valid"])
        self.assertTrue(result["witness_ed25519_signature_valid"])
        self.assertTrue(result["two_distinct_public_keys_used"])
        self.assertEqual(result["artifact_sha256"], sha256(artifact))
        self.assertEqual(result["anchor_sha256"], sha256(anchor))
        self.assertEqual(result["trust_policy_sha256"], sha256(trust))
        self.assertEqual(result["witness_claimed_observed_at_unverified"], OBSERVED)
        self.assertFalse(result["witness_identity_verified_out_of_band"])
        self.assertFalse(result["witness_actual_time_verified"])
        self.assertFalse(result["independent_timestamp_authority_verified"])
        self.assertFalse(result["hypothesis_validated"])
        self.assertEqual(result, verify_anchor(artifact, anchor, trust))

    def test_changed_artifact_refused_even_with_correct_key(self):
        artifact, anchor, trust = signed_fixture()
        altered = copy.deepcopy(artifact)
        altered["note"] = "Tampered after signing."
        with self.assertRaises(InputError):
            verify_anchor(altered, anchor, trust)

    def test_fake_publisher_key_or_signature_refused(self):
        artifact, anchor, trust = signed_fixture()
        altered = copy.deepcopy(anchor)
        altered["publisher"]["signature_base64"] = b64(b"\x01" * 64)
        with self.assertRaises(InputError):
            verify_anchor(artifact, altered, trust)
        altered = copy.deepcopy(trust)
        altered["publisher"]["public_key_base64"] = public_key(Ed25519PrivateKey.generate())
        with self.assertRaises(InputError):
            verify_anchor(artifact, anchor, altered)

    def test_fake_witness_key_or_signature_refused(self):
        artifact, anchor, trust = signed_fixture()
        altered = copy.deepcopy(anchor)
        altered["witness"]["signature_base64"] = b64(b"\x00" * 64)
        with self.assertRaises(InputError):
            verify_anchor(artifact, altered, trust)
        altered = copy.deepcopy(trust)
        altered["witness"]["public_key_base64"] = public_key(Ed25519PrivateKey.generate())
        with self.assertRaises(InputError):
            verify_anchor(artifact, anchor, altered)

    def test_replaced_signed_time_refused(self):
        artifact, anchor, trust = signed_fixture()
        altered = copy.deepcopy(anchor)
        altered["witness"]["claim"]["claimed_observed_at"] = "2010-01-01T00:00:00Z"
        with self.assertRaises(InputError):
            verify_anchor(artifact, altered, trust)

    def test_malformed_date_and_offset_refused(self):
        artifact, anchor, trust = signed_fixture()
        for value in ("2026-02-30T00:00:00Z", "2026-11-12T12:34:56+00:00",
                      "2026-11-12", "2026-11-12T25:00:00Z"):
            with self.subTest(value=value), self.assertRaises(InputError):
                draft_witness_claim(artifact, anchor["publisher"]["claim"],
                                    anchor["publisher"]["signature_base64"], value)

    def test_same_key_or_same_key_id_refused(self):
        artifact, anchor, trust = signed_fixture()
        changed = copy.deepcopy(trust)
        changed["witness"]["public_key_base64"] = changed["publisher"]["public_key_base64"]
        with self.assertRaises(InputError):
            verify_anchor(artifact, anchor, changed)
        changed = copy.deepcopy(trust)
        changed["witness"]["key_id"] = changed["publisher"]["key_id"]
        with self.assertRaises(InputError):
            verify_anchor(artifact, anchor, changed)

    def test_unrecognized_artifact_schema_refused(self):
        with self.assertRaises(InputError):
            draft_publisher_claim({"schema": "phidiscovery.claimed-breakthrough.v9", "claims": []})
        with self.assertRaises(InputError):
            draft_publisher_claim([])

    def test_wrong_publisher_or_witness_identity_is_rejected(self):
        artifact, anchor, trust = signed_fixture()
        altered = copy.deepcopy(anchor)
        altered["publisher"]["key_id"] = "different"
        with self.assertRaises(InputError):
            verify_anchor(artifact, altered, trust)
        altered = copy.deepcopy(anchor)
        altered["witness"]["key_id"] = "different"
        with self.assertRaises(InputError):
            verify_anchor(artifact, altered, trust)

    def test_mismatched_claim_digests_rejected(self):
        artifact, anchor, trust = signed_fixture()
        altered = copy.deepcopy(anchor)
        altered["witness"]["claim"]["artifact_sha256"] = "0" * 64
        with self.assertRaises(InputError):
            verify_anchor(artifact, altered, trust)
        altered = copy.deepcopy(anchor)
        altered["publisher"]["claim"]["artifact_sha256"] = "0" * 64
        with self.assertRaises(InputError):
            verify_anchor(artifact, altered, trust)

    def test_bad_base64_or_unpinned_key_refused(self):
        artifact, anchor, trust = signed_fixture()
        changed = copy.deepcopy(anchor)
        changed["publisher"]["signature_base64"] = "!!!invalid"
        with self.assertRaises(InputError):
            verify_anchor(artifact, changed, trust)
        changed = copy.deepcopy(trust)
        changed["publisher"]["public_key_base64"] = b64(b"too-short")
        with self.assertRaises(InputError):
            verify_anchor(artifact, anchor, changed)
        changed = copy.deepcopy(trust)
        changed["publisher"]["key_id"] = "../../bad-key"
        with self.assertRaises(InputError):
            verify_anchor(artifact, anchor, changed)

    def test_claim_binds_exact_publisher_signature(self):
        artifact, anchor, trust = signed_fixture()
        witness_claim = draft_witness_claim(
            artifact, anchor["publisher"]["claim"],
            anchor["publisher"]["signature_base64"], OBSERVED)
        self.assertEqual(witness_claim, anchor["witness"]["claim"])
        self.assertNotIn("signature_base64", witness_claim)

    def test_cli_generate_unsigned_and_verify_private_receipt(self):
        artifact, anchor, trust = signed_fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifact_path, anchor_path = root / "artifact.json", root / "signed-anchor.json"
            trust_path, report_path, claim_path = (
                root / "trust.json", root / "report.json", root / "claim.json"
            )
            for path, value in ((artifact_path, artifact), (anchor_path, anchor),
                                (trust_path, trust)):
                path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(main(["anchor-draft", str(artifact_path), "--out", str(claim_path)]), 0)
            self.assertEqual(json.loads(claim_path.read_text()), draft_publisher_claim(artifact))
            self.assertEqual(main(["anchor-verify", str(artifact_path), str(anchor_path),
                                   str(trust_path), "--out", str(report_path)]), 0)
            self.assertFalse(json.loads(report_path.read_text())["witness_actual_time_verified"])
            self.assertEqual(main(["anchor-verify", str(artifact_path), str(anchor_path),
                                   str(trust_path), "--out", str(report_path)]), 2)
            self.assertEqual(main(["anchor-draft", str(artifact_path), "--out", str(claim_path)]), 2)


if __name__ == "__main__":
    unittest.main()

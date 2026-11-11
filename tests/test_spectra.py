import json
import tempfile
import unittest
from pathlib import Path

from phidiscovery.engine import InputError
from phidiscovery.spectra import compare_mgf, read_mgf

ROOT = Path(__file__).resolve().parents[1] / "examples"


class SpectraTests(unittest.TestCase):
    def test_demo_ambiguous_and_unknown(self):
        lib = json.loads((ROOT / "demo-reference-spectra.json").read_text())
        r = compare_mgf(ROOT / "demo-spectra.mgf", lib)
        self.assertEqual(r["spectra_count"], 2)
        self.assertEqual([x["stage"] for x in r["results"]], ["ambiguous_reference_match", "unassigned_feature"])
        self.assertEqual(len(r["results"][0]["matches"]), 2)
        self.assertEqual(len(r["results"][1]["matches"]), 0)

    def test_strict_precursor_rejects(self):
        lib = json.loads((ROOT / "demo-reference-spectra.json").read_text())
        lib["references"][0]["precursor_mz"] = 250.0
        lib["references"][1]["precursor_mz"] = 260.0
        r = compare_mgf(ROOT / "demo-spectra.mgf", lib)
        self.assertEqual(r["results"][0]["stage"], "unassigned_feature")

    def test_unclosed_mgf_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.mgf"
            p.write_text("BEGIN IONS\nPEPMASS=315\n91.0 12\n")
            with self.assertRaises(InputError):
                read_mgf(p)

    def test_bad_library_rejected(self):
        with self.assertRaises(InputError):
            compare_mgf(ROOT / "demo-spectra.mgf", {"references":[{"id":"a", "precursor_mz":0, "peaks":[]}]})


if __name__ == "__main__":
    unittest.main()

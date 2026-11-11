import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from phidiscovery.cli import main
from phidiscovery.engine import InputError
from phidiscovery.massbank import import_records, parse_record
from phidiscovery.spectra import compare_mgf

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic-massbank.txt"


class MassBankTests(unittest.TestCase):
    def test_import_preserves_accession_license_and_hash(self):
        lib = import_records([FIXTURE])
        r = lib["references"][0]
        self.assertEqual(r["id"], "MSBNK-PHI_FIXTURE-SYNTHETIC001")
        self.assertEqual(r["license"], "CC0")
        self.assertEqual(r["ion_mode"], "POSITIVE")
        self.assertEqual(r["precursor_type"], "[M+H]+")
        self.assertEqual(r["source_sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
        self.assertEqual(len(r["peaks"]), 3)

    def test_import_rejects_peak_count_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.txt"
            path.write_text(FIXTURE.read_text().replace("PK$NUM_PEAK: 3", "PK$NUM_PEAK: 4"))
            with self.assertRaises(InputError):
                parse_record(path)

    def test_import_rejects_duplicate_accessions(self):
        with tempfile.TemporaryDirectory() as d:
            other = Path(d) / "copy.txt"
            other.write_bytes(FIXTURE.read_bytes())
            with self.assertRaises(InputError):
                import_records([FIXTURE, other])

    def test_import_rejects_missing_license(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.txt"
            path.write_text(FIXTURE.read_text().replace("LICENSE: CC0", "LICENSE: unrestricted"))
            with self.assertRaises(InputError):
                parse_record(path)

    def _mgf(self, directory, metadata: str) -> Path:
        path = Path(directory) / "sample.mgf"
        path.write_text("BEGIN IONS\nTITLE=SYNTHETIC\nPEPMASS=315.232\n" + metadata +
                        "91.055 40\n123.080 80\n174.100 60\nEND IONS\n")
        return path

    def test_compatible_spectrum_remains_tentative(self):
        with tempfile.TemporaryDirectory() as d:
            mgf = self._mgf(d, "IONMODE=POSITIVE\nADDUCT=[M+H]+\n")
            report = compare_mgf(mgf, import_records([FIXTURE]))
            self.assertEqual(report["results"][0]["stage"], "tentative_reference_match")
            self.assertTrue(report["results"][0]["matches"][0]["metadata_complete"])
            self.assertEqual(report["results"][0]["matches"][0]["license"], "CC0")
            self.assertFalse("confirmed" in report["results"][0]["stage"])

    def test_missing_adduct_never_tentatively_identifies(self):
        with tempfile.TemporaryDirectory() as d:
            mgf = self._mgf(d, "IONMODE=POSITIVE\n")
            report = compare_mgf(mgf, import_records([FIXTURE]))
            self.assertEqual(report["results"][0]["stage"], "metadata_incomplete")
            self.assertFalse(report["results"][0]["matches"][0]["metadata_complete"])

    def test_wrong_polarity_is_not_match(self):
        with tempfile.TemporaryDirectory() as d:
            mgf = self._mgf(d, "CHARGE=1-\n")
            report = compare_mgf(mgf, import_records([FIXTURE]))
            self.assertEqual(report["results"][0]["stage"], "unassigned_feature")

    def test_conflicting_charge_must_fail(self):
        with tempfile.TemporaryDirectory() as d:
            mgf = self._mgf(d, "CHARGE=1+\nIONMODE=NEGATIVE\n")
            with self.assertRaises(InputError):
                compare_mgf(mgf, import_records([FIXTURE]))

    def test_cli_import_and_spectra(self):
        with tempfile.TemporaryDirectory() as d:
            library = Path(d) / "library.json"
            report = Path(d) / "results.json"
            self.assertEqual(main(["massbank-import", str(FIXTURE), "--out", str(library)]), 0)
            mgf = self._mgf(d, "IONMODE=POSITIVE\nADDUCT=[M+H]+\n")
            self.assertEqual(main(["spectra", str(mgf), "--library", str(library), "--out", str(report)]), 0)
            self.assertEqual(json.loads(report.read_text())["results"][0]["stage"], "tentative_reference_match")


if __name__ == "__main__":
    unittest.main()

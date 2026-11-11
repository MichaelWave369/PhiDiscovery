# ΦDiscovery v0.2: MassBank reference-ingestion pilot

**Status:** Offline reference import and preliminary spectra triage. This is not a validated molecular identification system, a cannabinoid discovery, or a bioactivity prediction engine.

## What changed

- Parse **one MassBank text record per file** with a strict 2 MiB/file and 250-file cap.
- Require an official-format accession, one MS2 precursor mass and adduct, ion polarity, a supported Creative Commons license, at least three peaks, and matching PK$NUM_PEAK.
- Preserve the original accession, compound name, adduct, ion polarity, license, source filename, and SHA-256 digest in the local library JSON.
- Reject duplicate accessions, malformed records, cross-polarity comparisons, and incompatible declared adducts. Missing MGF metadata produces **metadata_incomplete**, not a positive tentative-match label.
- Keep the core generic analysis engine and v0.1 synthetic pilot unchanged.

## First run (offline)

From the repository root, run:

```powershell
python -m unittest discover -s tests -v
python -m phidiscovery massbank-import tests/fixtures/synthetic-massbank.txt --out out/reference-library.json
```

This fixture is intentionally **synthetic**, with a deliberately fake accession and fictional peaks. It tests ingestion, not chemistry. For a genuine research pilot, first download one or more permitted MassBank text records **from their official provenance**:

- https://github.com/MassBank/MassBank-data
- https://massbank.eu/MassBank-api/ui/
- Format specification: https://github.com/MassBank/MassBank-documentation/blob/dev/MassBankRecordFormat.md

Inspect the individual record's license, original publication, instrument conditions, compound reference, and accession before use. The importer does **not** fetch the internet or verify depositor assertions.

```powershell
python -m phidiscovery massbank-import path/to/record1.txt path/to/record2.txt --out out/massbank-library.json
python -m phidiscovery spectra path/to/your-export.mgf --library out/massbank-library.json --out out/real-pilot-triage.json
```

Only use MGF exported from a source with suitable rights and known instrument metadata. When present, this adapter understands `IONMODE=POSITIVE` or `IONMODE=NEGATIVE`, `CHARGE=1+` or `CHARGE=1-`, and `ADDUCT=[M+H]+` (or the documented experimental precursor type). Those tags represent **declared metadata**; adding them manually without verified source information would falsify the analysis. Missing ion mode or adduct information marks the possible similarity **metadata_incomplete**. Mismatched declared polarities and adducts are filtered out.

## Interpretation

Results belong to these *software triage* stages:

| Stage | Meaning |
| --- | --- |
| `unassigned_feature` | Nothing exceeded the naive baseline criteria; **not proof of a new compound** |
| `metadata_incomplete` | Similar peaks exist, but measured polarity or adduct information is missing |
| `ambiguous_reference_match` | Two or more references have nearly tied similarity |
| `tentative_reference_match` | One best-scoring reference passed declared metadata and crude spectral gates; **not molecular identification** |

This version does not evaluate collision energy equivalence, chromatographic retention, ionization source settings, in-source fragmentation, mass-calibration error, sample controls, false discovery rates, or whether a reference is actually present in the plant. A spectrum cannot establish new chemical structure by itself. Have an analytical chemist review instrumental metadata and known isomers before treating any triage result as evidence.

## Pilot One acceptance gates

1. Pin a public dataset accession, download date, study source, record licenses, and SHA-256 digests.
2. Select known-positive, wrong-adduct, wrong-polarity, negative, and blinded control features **before** tuning similarity thresholds.
3. Evaluate precision/recall or identification error against published reference labels, not generated self-labels.
4. Record any unresolved cases and alternative explanations, including contamination, noise, adducts, and isomeric collisions.
5. Require independent expert review before making any cannabinoid-specific scientific claim.

**Scope boundary:** Chemical identification and biological effects are not inferred from similarity alone. Nothing in this pilot provides chemical synthesis, extraction, or production instructions.

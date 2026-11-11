"""Cannabinoid-specific ambiguity guard; never infers identity from precursor mass."""


def ambiguity_flags(candidate: dict, entries: list[dict], all_candidates: list[dict]) -> list[str]:
    expected = {e["measurement"]["expected_mz"] for e in entries
                if e["kind"].lower() == "ms1" and e.get("measurement") and "expected_mz" in e["measurement"]}
    others = [c["label"] for c in all_candidates
              if c["id"] != candidate["id"] and c.get("reference_mz") is not None
              and any(abs(c["reference_mz"] - mz) <= 0.002 for mz in expected)]
    return ["Potential isomer / exact-mass ambiguity with: " + ", ".join(sorted(set(others)))] if others else []

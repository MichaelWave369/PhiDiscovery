"""Optional read-only public chemical identity enrichment. Offline core never calls this."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


def lookup(name: str, retries: int = 2) -> dict:
    if not name.strip() or len(name) > 160:
        raise ValueError("Provide a compound name of 1–160 characters")
    path = urllib.parse.quote(name.strip(), safe="")
    url = f"{API}/compound/name/{path}/property/MolecularFormula,MolecularWeight,SMILES,InChIKey/JSON"
    request = urllib.request.Request(url, headers={"User-Agent": "PhiDiscovery/0.1 (research; low-volume)", "Accept": "application/json"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise ValueError("Response exceeds 1MiB protective cap")
                data = json.loads(raw)
                props = data["PropertyTable"]["Properties"]
                return {"query": name, "source": "PubChem PUG REST", "url": url,
                        "properties": props, "limitations": "Database identity lookup only; does not show presence in a plant sample or prove novelty."}
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == retries:
                raise RuntimeError(f"PubChem HTTP {exc.code}; lookup failed, no properties assumed") from exc
            time.sleep(min(2 ** attempt, 4))
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries:
                raise RuntimeError("Network lookup unavailable; offline analysis remains functional") from exc
            time.sleep(min(2 ** attempt, 4))
    raise RuntimeError("Unexpected lookup state")

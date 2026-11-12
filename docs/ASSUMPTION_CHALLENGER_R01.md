# ΦDiscovery Assumption Challenger R0.1

## Why it exists

The origin of a hypothesis should not place a ceiling on what can be learned about it. Equally, rephrasing an idea does not make it true. The Assumption Challenger is a deterministic, offline way to prepare claims for adversarial review and real-world testing.

It does not call an LLM, discover new physical laws, fetch citations, decide philosophical questions, or perform any physical experiment. Human-provided measurements and sources can be incorrect or intentionally misleading. The output is a **review plan**, not an evidentiary conclusion.

## Run

```bash
python -m phidiscovery challenge examples/assumption-challenge.json --out out/assumptions.json
python -m unittest discover -s tests -v
```

Any existing bundle v1.0 works. The additional metadata below is optional on each candidate and is validated by the challenge command:

```json
{
  "assumptions": ["State what the explanation relies on"],
  "alternatives": ["State a competing explanation that fits the evidence"],
  "discriminating_tests": [
    {
      "id": "T-1",
      "measurement": "Specify a replicable observation and controls",
      "prediction_if_claim": "Preregister the claimed model's prediction",
      "prediction_if_alternative": "Preregister a competing model's prediction",
      "decision_rule": "Specify how outcomes are compared before seeing data"
    }
  ]
}
```

## Interpretation

The JSON output includes a content hash of the submitted bundle, all explicit assumptions and alternatives, test designs, current stage from the existing PhiDiscovery evidence engine, indexed contradictory and synthetic records, and missing-information flags. Synthetic records never count as eligible supporting evidence. Independence groups are *self-declared*, not independently established.

The three collaborator tasks are **inert structured prompts** for a future system: assumption challenger, alternative builder, and experiment auditor. Their inputs must be treated as untrusted data. No agent execution occurs in R0.1.

## Next milestones

1. Connect optional PhiStream/Agentora agents with scoped roles and strict JSON outputs. Keep independent reviewers blind to each other's drafts until comparison.
2. Build a provenance-aware claim graph with historical revisions and signed/verifiable receipts.
3. Generate preregistered predictions, independent holdout evaluations, and experiment proposals for human approval.
4. Record replication failures, confounders, negative results, and corrections without silently erasing them.

**Success metric:** a reviewer can identify what would falsify a claim, how alternatives differ, which evidence is independent, and what remains untested. The number of exciting hypotheses generated is not a scientific validation metric.

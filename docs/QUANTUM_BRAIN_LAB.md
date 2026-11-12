# Quantum Brain Lab: model-comparison sandbox

**Status: synthetic educational software, not evidence of quantum neural computation.**

PhiDiscovery's optional Quantum Brain Lab creates an offline, deterministic JSON
receipt and a self-contained, interactive HTML report.

## Quick start

From the repository root (Python 3.10+, no third-party dependencies):

~~~bash
python -m phidiscovery quantum-brain --out out/brain
python -m unittest discover -s tests -v
~~~

Open out/brain/quantum-brain.html. Adjust the sliders in your browser to see
how changing an illustrative decoherence time, pulse delay, and rotation angle
affects the phase curves. Browser slider changes do not alter the saved JSON
receipt. For a reproducible run with different parameters:

~~~bash
python -m phidiscovery quantum-brain --t2-ms 0.1 --delay-ms 3 --pulse-angle-rad 1.57 --out out/brain-fast-decay
~~~

## Three tracks (not three competing measurements of the same thing)

1. **Classical neuron:** deterministic leaky integrate-and-fire membrane model
   with normalized voltage, constant drive, threshold, reset, and refractory period.
   Parameters are illustrative, not fitted to brain recordings.
2. **Classical two-state mixture versus quantum-inspired ideal:** a deliberately
   simplified two-pulse protocol. Each pulse rotates a two-state system about
   the x axis by theta; between pulses a relative phase phi accumulates.
   Incoherent classical probability = (sin(theta)^2)/2.
   Ideal coherent probability = (sin(theta)^2)/2 * (1 + cos(phi)).
3. **Hypothetical physical quantum processing:** same pulse sequence with
   phenomenological coherence visibility exp(-delay/T2), yielding
   P = (sin(theta)^2)/2 * (1 + exp(-delay/T2) * cos(phi)).
   Here T2 is a hypothetical parameter, NOT an observed coherence time in
   microtubules or neural tissue.

The neuron voltage and two-state measurement probability have different
interpretations and units. Comparing their chart shapes does NOT test whether
the brain uses quantum computation. The two-state models are coherent vs
incoherent alternatives for an abstract controlled pulse experiment.

## A pathway to meaningful tests

- Identify a specific biological substrate and the states that encode information.
- Derive a mechanism linking quantum-state dynamics to neural output.
- Establish measurable observables, experimental controls, and realistic temperature
  and noise constraints. Measure coherence independently rather than assuming T2.
- Pre-register predictions that separate quantum mechanisms from classical
  stochastic, biochemical, and network alternatives.
- Compare predictions using independent data and held-out conditions.
- Run replication and source audits through PhiDiscovery's general evidence engine.

A model fitting a curve is not evidence of quantum computation, entanglement,
consciousness, or any broader cosmic-consciousness interpretation.

## Provenance and constraints

The output JSON includes schema version, validated parameters, canonical
configuration SHA-256, deterministic neuron trace, phase sweep, and skeptical
interpretation notes. No network requests, patient data, or telemetry.

Input ranges, a maximum of 5000 neuron steps, and a maximum of 361 phase
samples prevent accidental oversized reports. This demonstration does not
claim research-grade numerical integration or physical accuracy for neurons
or quantum hardware.

## Proposed next stage

Add an optional, explicitly sourced experimental-data adapter with source
metadata, documented units, independent controls, model selection criteria,
and formal comparison metrics. Keep simulated inputs separate from measured
observations and require human review before elevating any claim.

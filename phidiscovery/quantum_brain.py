"""Quantum Brain Lab: reproducible, explicitly synthetic comparison models.

This is a modeling sandbox, not evidence that neural tissue supports quantum
information processing. The leaky integrate-and-fire trace and two-state
pulse probabilities are intentionally different observables.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class LabConfig:
    duration_ms: float = 160.0
    step_ms: float = 0.5
    membrane_tau_ms: float = 20.0
    stimulus: float = 1.35
    threshold: float = 1.0
    refractory_ms: float = 3.0
    pulse_angle_rad: float = math.pi / 2
    delay_ms: float = 1.0
    hypothetical_t2_ms: float = 3.0
    phase_samples: int = 81


def validate_config(c: LabConfig) -> None:
    limits = {
        "duration_ms": (1.0, 1000.0),
        "step_ms": (0.01, 5.0),
        "membrane_tau_ms": (0.1, 1000.0),
        "stimulus": (0.0, 20.0),
        "threshold": (0.01, 20.0),
        "refractory_ms": (0.0, 100.0),
        "pulse_angle_rad": (0.0, math.pi),
        "delay_ms": (0.0, 1000.0),
        "hypothetical_t2_ms": (0.001, 1000.0),
    }
    for name, (low, high) in limits.items():
        value = getattr(c, name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{name} must be finite and within [{low}, {high}]")
    if c.duration_ms / c.step_ms > 5000:
        raise ValueError("Time resolution exceeds the 5000-step safety limit")
    if not isinstance(c.phase_samples, int) or isinstance(c.phase_samples, bool) or not 9 <= c.phase_samples <= 361:
        raise ValueError("phase_samples must be an integer from 9 to 361")


def classical_neuron(c: LabConfig) -> dict:
    """Forward Euler LIF with constant, unitless drive and zero resting voltage."""
    voltage = 0.0
    refractory_until = -1.0
    trace = []
    spikes = []
    steps = int(c.duration_ms / c.step_ms) + 1
    for index in range(steps):
        t = round(index * c.step_ms, 6)
        if t < refractory_until:
            voltage = 0.0
        else:
            voltage += (c.step_ms / c.membrane_tau_ms) * (c.stimulus - voltage)
            if voltage >= c.threshold:
                spikes.append(t)
                voltage = 0.0
                refractory_until = t + c.refractory_ms
        trace.append({"time_ms": t, "voltage": round(voltage, 8), "spike": t in spikes[-1:]})
    return {"model": "leaky_integrate_and_fire", "spike_times_ms": spikes,
            "spike_count": len(spikes), "trace": trace, "voltage_units": "normalized"}


def two_pulse_probabilities(angle_rad: float, phase_rad: float, delay_ms: float, t2_ms: float) -> dict:
    """Two identical x-axis rotations with intervening z-phase.

    Incoherent Markov mixture: 0.5 sin(angle)^2.
    Coherent probability: mixture * (1 + cos(phase)).
    Toy pure-dephasing visibility: exp(-delay / T2).
    """
    mixture = 0.5 * math.sin(angle_rad) ** 2
    interference = math.cos(phase_rad)
    visibility = math.exp(-delay_ms / t2_ms)
    return {
        "classical_mixture": round(mixture, 10),
        "quantum_inspired": round(max(0.0, min(1.0, mixture * (1.0 + interference))), 10),
        "hypothetical_dephasing": round(max(0.0, min(1.0, mixture * (1.0 + visibility * interference))), 10),
    }


def run_lab(c: LabConfig | None = None) -> dict:
    c = c or LabConfig()
    validate_config(c)
    phases = [
        -math.pi + 2.0 * math.pi * i / (c.phase_samples - 1)
        for i in range(c.phase_samples)
    ]
    sweep = [
        {"phase_rad": round(phase, 9),
         **two_pulse_probabilities(c.pulse_angle_rad, phase, c.delay_ms, c.hypothetical_t2_ms)}
        for phase in phases
    ]
    config = asdict(c)
    digest = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema_version": "quantum-brain-lab/0.1",
        "status": "synthetic_illustrative_models_only",
        "config_sha256": digest,
        "config": config,
        "classical_neuron": classical_neuron(c),
        "two_state_phase_sweep": sweep,
        "interpretation": {
            "classical_mixture": "Incoherent two-pulse Markov baseline, not a neuron model.",
            "quantum_inspired": "Ideal coherent two-state pulse interference; no biological claim.",
            "hypothetical_dephasing": "Phenomenological pure dephasing, with an invented T2 parameter.",
        },
        "scientific_limits": [
            "These are toy models using synthetic parameters, not experimental measurements.",
            "The LIF voltage and two-state measurement probabilities are different observables; their curves are not directly comparable as brain predictions.",
            "The T2 value is illustrative and is not a measured neural or microtubule coherence time.",
            "Quantum-inspired patterns do not demonstrate entanglement, quantum computation, or consciousness.",
            "A biological mechanism, falsifiable predictions, and independent controls are necessary for any neural quantum claim.",
        ],
    }


def _polyline(values: list[float], width: int = 630, height: int = 220) -> str:
    return " ".join(
        f"{40 + i * (width - 60) / max(1, len(values) - 1):.2f},"
        f"{height - 28 - max(0.0, min(1.0, value)) * (height - 54):.2f}"
        for i, value in enumerate(values)
    )


def render_lab_html(result: dict) -> str:
    """Self-contained static chart with optional on-page interactive what-if controls."""
    c = result["config"]
    sweep = result["two_state_phase_sweep"]
    neurons = result["classical_neuron"]
    points = {
        "mixture": _polyline([r["classical_mixture"] for r in sweep]),
        "ideal": _polyline([r["quantum_inspired"] for r in sweep]),
        "dephase": _polyline([r["hypothetical_dephasing"] for r in sweep]),
    }
    v = [row["voltage"] / max(c["threshold"], 0.01) for row in neurons["trace"]]
    lif = _polyline(v)
    content = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PhiDiscovery | Quantum Brain Lab</title>
<style>
:root{color-scheme:dark;--bg:#090e1c;--card:#151e30;--muted:#b0c1d1;--line:#33445b;--mint:#69e1c4;--purple:#c19dff;--amber:#edc078}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 10% 0,#18304a,var(--bg) 55%);color:#f1f6fa;font:15px/1.55 system-ui,sans-serif}
main{max-width:1100px;margin:auto;padding:35px 20px 65px}h1{font-size:clamp(28px,5vw,48px);margin:8px 0}h2{margin-top:0}p{max-width:85ch}
.brand{letter-spacing:.15em;color:var(--mint);font-weight:700;text-transform:uppercase}
.warn{padding:15px 18px;border-left:4px solid var(--amber);background:#30291d;margin:20px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.card{border:1px solid var(--line);background:var(--card);border-radius:15px;padding:22px;min-width:0}
.chart{width:100%;height:auto;background:#10192a;border-radius:12px}
.axis{stroke:#718097;stroke-width:1}.muted,small{color:var(--muted)}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin:10px 0}.legend span:before{content:"";display:inline-block;width:12px;height:3px;vertical-align:middle;margin-right:6px;background:var(--sw)}
label{display:block;margin:10px 0}input[type=range]{width:100%;accent-color:var(--mint)}
.value{float:right;color:var(--mint);font-variant-numeric:tabular-nums}
code{color:#98dfe0;overflow-wrap:anywhere}footer{color:var(--muted);font-size:12px;margin-top:30px}
@media(max-width:600px){.card{padding:14px}}
</style></head><body><main>
<div class="brand">PhiDiscovery / Research sandbox</div>
<h1>Quantum Brain Lab</h1>
<p>Three reproducible educational models. Classical neuron dynamics, ideal two-state quantum interference, and a hypothetical dephasing scenario. This interface makes no claims about measured brain quantum computation.</p>
<div class="warn"><strong>Synthetic thought experiment, not biological evidence.</strong> The voltage trace and two-state probabilities represent different physical observables. They must not be interpreted as validated competing models of the same neural measurement.</div>
<div class="grid">
<section class="card">
<h2>Classical neural baseline</h2><p class="muted">Leaky integrate-and-fire model, normalized voltage vs. time. The horizontal line represents the firing threshold.</p>
<svg class="chart" viewBox="0 0 630 220" role="img" aria-label="Classical neuron voltage trace">
<path class="axis" d="M40 25 V192 H610"/><path stroke="#edc078" stroke-width="1" stroke-dasharray="5 5" d="M40 26 H610"/>
<polyline fill="none" stroke="#69e1c4" stroke-width="2" points="__LIF__"/>
<text x="42" y="17" fill="#c9d8e3" font-size="13">Threshold</text><text x="300" y="214" fill="#c9d8e3" font-size="13">Time (ms)</text>
</svg><p><strong>__SPIKES__</strong> spikes over __DURATION__ ms (constant dimensionless drive).</p>
</section>
<section class="card">
<h2>Two-state pulse comparison</h2><p class="muted">Probability of state |1&gt; after two pulse rotations. Phase is varied between the pulses.</p>
<svg id="phase-plot" class="chart" viewBox="0 0 630 220" role="img" aria-label="Two-state measurement probabilities over phase">
<path class="axis" d="M40 25 V192 H610"/>
<path stroke="#3d4f66" stroke-width="1" d="M40 109 H610 M40 26 H610"/>
<text x="9" y="29" fill="#c9d8e3" font-size="12">1.0</text><text x="9" y="113" fill="#c9d8e3" font-size="12">0.5</text><text x="9" y="191" fill="#c9d8e3" font-size="12">0</text>
<text x="40" y="213" fill="#c9d8e3" font-size="12">−π</text><text x="312" y="213" fill="#c9d8e3" font-size="12">0</text><text x="587" y="213" fill="#c9d8e3" font-size="12">+π</text>
<polyline id="line-mixture" fill="none" stroke="#edc078" stroke-width="2" points="__MIXTURE__"/>
<polyline id="line-ideal" fill="none" stroke="#c19dff" stroke-width="2.5" points="__IDEAL__"/>
<polyline id="line-dephase" fill="none" stroke="#69e1c4" stroke-width="2.5" points="__DEPHASE__"/>
</svg><div class="legend"><span style="--sw:#edc078">Classical mixture</span><span style="--sw:#c19dff">Ideal coherence</span><span style="--sw:#69e1c4">Hypothetical dephasing</span></div>
<label for="t2">Hypothetical T2, ms <span class="value" id="t2-value">__T2__</span></label>
<input id="t2" type="range" min="0.05" max="20" step="0.05" value="__T2__">
<label for="delay">Delay between pulses, ms <span class="value" id="delay-value">__DELAY__</span></label>
<input id="delay" type="range" min="0" max="20" step="0.1" value="__DELAY__">
<label for="angle">Pulse rotation angle, radians <span class="value" id="angle-value">__ANGLE__</span></label>
<input id="angle" type="range" min="0" max="3.14" step="0.01" value="__ANGLE__">
<p class="muted">Browser sliders explore illustrative curves only. The downloaded JSON retains the original, reproducible CLI configuration.</p>
</section>
</div>
<section class="card" style="margin-top:16px">
<h2>Interpretation and falsification</h2>
<p><strong>Classical mixture:</strong> ignores phase information. <strong>Ideal two-state:</strong> retains full phase coherence. <strong>Dephasing toy:</strong> interpolates with visibility exp(−delay/T2). Neither two-state model establishes that microtubules, neurons, or brains behave as qubits.</p>
<p>To turn this into neuroscience, define a biological encoding, measurable readout, plausible coherence time, pre-registered predictions, classical alternatives, and independent experiments. A fit to a curve alone is never proof of a quantum mechanism.</p>
<p class="muted">Configuration SHA-256: <code>__HASH__</code></p>
</section>
<footer>PhiDiscovery · offline-first · no telemetry or external dependencies · laboratory prototype 0.1</footer>
</main>
<script>
(function(){
"use strict";
var ids={t2:document.getElementById("t2"),delay:document.getElementById("delay"),angle:document.getElementById("angle")};
function points(fn){
 var values=[];for(var i=0;i<81;i++){var phase=-Math.PI+2*Math.PI*i/80;var p=Math.max(0,Math.min(1,fn(phase)));values.push((40+i*570/80).toFixed(2)+","+(192-p*166).toFixed(2));}
 return values.join(" ");
}
function draw(){
 var t2=Number(ids.t2.value),delay=Number(ids.delay.value),angle=Number(ids.angle.value),mix=0.5*Math.pow(Math.sin(angle),2),vis=Math.exp(-delay/t2);
 document.getElementById("line-mixture").setAttribute("points",points(function(){return mix;}));
 document.getElementById("line-ideal").setAttribute("points",points(function(p){return mix*(1+Math.cos(p));}));
 document.getElementById("line-dephase").setAttribute("points",points(function(p){return mix*(1+vis*Math.cos(p));}));
 for(var key in ids){document.getElementById(key+"-value").textContent=Number(ids[key].value).toFixed(2);}
}
Object.keys(ids).forEach(function(key){ids[key].addEventListener("input",draw);});
draw();
})();
</script></body></html>
"""
    replacements = {
        "__LIF__": lif,
        "__SPIKES__": str(neurons["spike_count"]),
        "__DURATION__": str(c["duration_ms"]),
        "__MIXTURE__": points["mixture"],
        "__IDEAL__": points["ideal"],
        "__DEPHASE__": points["dephase"],
        "__T2__": str(c["hypothetical_t2_ms"]),
        "__DELAY__": str(c["delay_ms"]),
        "__ANGLE__": str(round(c["pulse_angle_rad"], 2)),
        "__HASH__": html.escape(result["config_sha256"]),
    }
    for marker, replacement in replacements.items():
        content = content.replace(marker, replacement)
    return content


def save_lab(c: LabConfig, out: Path) -> tuple[Path, Path]:
    result = run_lab(c)
    out.mkdir(parents=True, exist_ok=True)
    json_path, html_path = out / "quantum-brain.json", out / "quantum-brain.html"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    html_path.write_text(render_lab_html(result), encoding="utf-8")
    return json_path, html_path

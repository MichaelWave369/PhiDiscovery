import math
import tempfile
import unittest
from pathlib import Path

from phidiscovery.quantum_brain import (
    LabConfig, classical_neuron, render_lab_html, run_lab, save_lab,
    two_pulse_probabilities, validate_config,
)
from phidiscovery.cli import main


class QuantumBrainLabTests(unittest.TestCase):
    def test_deterministic_receipt(self):
        self.assertEqual(run_lab(), run_lab())
        r = run_lab()
        self.assertEqual(r["status"], "synthetic_illustrative_models_only")
        self.assertEqual(len(r["two_state_phase_sweep"]), 81)
        self.assertEqual(len(r["config_sha256"]), 64)

    def test_classical_lif_spikes_only_above_threshold(self):
        self.assertGreater(classical_neuron(LabConfig())["spike_count"], 0)
        self.assertEqual(classical_neuron(LabConfig(stimulus=0.5))["spike_count"], 0)

    def test_phase_interference_versus_classical_mixture(self):
        at_zero = two_pulse_probabilities(math.pi / 2, 0, 0, 3)
        at_pi = two_pulse_probabilities(math.pi / 2, math.pi, 0, 3)
        self.assertAlmostEqual(at_zero["classical_mixture"], .5)
        self.assertAlmostEqual(at_zero["quantum_inspired"], 1.0)
        self.assertAlmostEqual(at_pi["quantum_inspired"], 0.0)
        self.assertEqual(at_zero["hypothetical_dephasing"], at_zero["quantum_inspired"])

    def test_long_dephasing_converges_on_mixture(self):
        r = two_pulse_probabilities(math.pi / 2, 0, 100, .01)
        self.assertAlmostEqual(r["hypothetical_dephasing"], r["classical_mixture"])

    def test_probability_bounds(self):
        for angle in (0, .3, math.pi / 2, math.pi):
            for phase in (-math.pi, -1, 0, 1, math.pi):
                for value in two_pulse_probabilities(angle, phase, 10, .1).values():
                    self.assertGreaterEqual(value, 0)
                    self.assertLessEqual(value, 1)

    def test_invalid_inputs_rejected(self):
        for config in (LabConfig(step_ms=0),
                       LabConfig(duration_ms=1000, step_ms=.01),
                       LabConfig(hypothetical_t2_ms=float("nan")),
                       LabConfig(phase_samples=10000)):
            with self.assertRaises(ValueError):
                validate_config(config)

    def test_html_and_cli_file_outputs(self):
        html = render_lab_html(run_lab())
        self.assertIn("Synthetic thought experiment", html)
        self.assertIn('id="line-dephase"', html)
        self.assertNotIn("__HASH__", html)
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["quantum-brain", "--out", tmp])
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "quantum-brain.json").exists())
            self.assertIn("Quantum Brain Lab", (Path(tmp) / "quantum-brain.html").read_text())
            self.assertEqual(save_lab(LabConfig(), Path(tmp))[0].name, "quantum-brain.json")


if __name__ == "__main__":
    unittest.main()

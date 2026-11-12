"""PhiDiscovery command line. Offline by default."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import InputError, analyze, validate_bundle, verify_report
from .report import save_report


def _json(path: Path) -> dict:
    if path.stat().st_size > 20 * 1024 * 1024:
        raise InputError("Input JSON exceeds protective 20 MiB cap")
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="phi-discovery", description="Evidence-first scientific discovery triage")
    commands = parser.add_subparsers(dest="command", required=True)
    cmd_v = commands.add_parser("validate", help="Validate a research evidence bundle")
    cmd_v.add_argument("input", type=Path)
    cmd_r = commands.add_parser("run", help="Analyze bundle and emit JSON + standalone HTML")
    cmd_r.add_argument("input", type=Path)
    cmd_r.add_argument("--out", type=Path, default=Path("out"))
    cmd_c = commands.add_parser("check", help="Recompute/verify a report using original input + artifacts")
    cmd_c.add_argument("input", type=Path)
    cmd_c.add_argument("report", type=Path)
    cmd_p = commands.add_parser("pubchem", help="Opt-in read-only PubChem identity lookup; network required")
    cmd_p.add_argument("name")
    cmd_p.add_argument("--out", type=Path)
    cmd_s = commands.add_parser("spectra", help="Compare local MGF peak lists with a JSON reference library")
    cmd_s.add_argument("mgf", type=Path)
    cmd_s.add_argument("--library", type=Path, required=True)
    cmd_s.add_argument("--out", type=Path, default=Path("out/spectra-results.json"))
    cmd_s.add_argument("--precursor-ppm", type=float, default=10.0)
    cmd_s.add_argument("--fragment-tol-da", type=float, default=0.03)
    cmd_mb = commands.add_parser("massbank-import", help="Convert local licensed MassBank MS2 records to a traceable reference library")
    cmd_mb.add_argument("records", type=Path, nargs="+")
    cmd_mb.add_argument("--out", type=Path, required=True)
    cmd_q = commands.add_parser("quantum-brain", help="Generate a synthetic Quantum Brain Lab report (offline)")
    cmd_q.add_argument("--out", type=Path, default=Path("out/brain"))
    cmd_q.add_argument("--duration-ms", type=float, default=160.0)
    cmd_q.add_argument("--step-ms", type=float, default=0.5)
    cmd_q.add_argument("--stimulus", type=float, default=1.35)
    cmd_q.add_argument("--t2-ms", type=float, default=3.0)
    cmd_q.add_argument("--delay-ms", type=float, default=1.0)
    cmd_q.add_argument("--pulse-angle-rad", type=float, default=1.5707963267948966)
    cmd_a = commands.add_parser("challenge", help="Audit assumptions, alternatives and falsification plans (offline)")
    cmd_a.add_argument("input", type=Path)
    cmd_a.add_argument("--out", type=Path, default=Path("out/assumptions.json"))
    cmd_rp = commands.add_parser("review-pack", help="Export isolated reviewer packets (offline, no model call)")
    cmd_rp.add_argument("input", type=Path)
    cmd_rp.add_argument("--out", type=Path, default=Path("out/review-packets.json"))
    cmd_rl = commands.add_parser("review-local", help="Opt-in, loopback Ollama research reviews; no external network fallback")
    cmd_rl.add_argument("input", type=Path)
    cmd_rl.add_argument("--model", required=True)
    cmd_rl.add_argument("--port", type=int, default=11434)
    cmd_rl.add_argument("--execute-local", action="store_true")
    cmd_rl.add_argument("--approve-local-inference", action="store_true")
    cmd_rl.add_argument("--out", type=Path, required=True, help="New private JSON receipt outside this repository")
    cmd_rc = commands.add_parser("review-compare", help="Compare role opinions without upgrading evidence (offline)")
    cmd_rc.add_argument("input", type=Path)
    cmd_rc.add_argument("receipts", type=Path)
    cmd_rc.add_argument("--out", type=Path, default=Path("out/reviewer-comparison.json"))
    cmd_ra = commands.add_parser("review-agentora", help="Explicit opt-in local Agentora blind research reviews")
    cmd_ra.add_argument("input", type=Path)
    cmd_ra.add_argument("--model", help="Use the same installed model for all three roles")
    cmd_ra.add_argument("--model-challenger", help="Override model for assumption challenger")
    cmd_ra.add_argument("--model-alternative", help="Override model for alternative builder")
    cmd_ra.add_argument("--model-auditor", help="Override model for experiment auditor")
    cmd_ra.add_argument("--port", type=int, default=8088)
    cmd_ra.add_argument("--execute-local", action="store_true")
    cmd_ra.add_argument("--approve-local-inference", action="store_true")
    cmd_ra.add_argument("--out", type=Path, required=True, help="New private receipt outside Git checkout")
    args = parser.parse_args(argv)
    try:
        if args.command == "quantum-brain":
            from .quantum_brain import LabConfig, save_lab
            config = LabConfig(duration_ms=args.duration_ms, step_ms=args.step_ms,
                               stimulus=args.stimulus, delay_ms=args.delay_ms,
                               hypothetical_t2_ms=args.t2_ms, pulse_angle_rad=args.pulse_angle_rad)
            json_path, html_path = save_lab(config, args.out)
            print(f"Saved synthetic lab outputs: {json_path} and {html_path}")
            return 0
        if args.command == "massbank-import":
            from .massbank import import_records
            result = import_records(args.records)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Imported {len(result['references'])} MassBank reference spectra to {args.out}")
            return 0
        if args.command == "spectra":
            from .spectra import compare_mgf
            report = compare_mgf(args.mgf, _json(args.library),
                                 precursor_ppm=args.precursor_ppm,
                                 fragment_tol_da=args.fragment_tol_da)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Saved {args.out}")
            for r in report["results"]:
                print(f"  {r['spectrum_id']}: {r['stage']} ({len(r['matches'])} reference matches)")
            return 0
        if args.command == "pubchem":
            from .pubchem import lookup
            result = lookup(args.name)
            result_text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(result_text, encoding="utf-8")
                print(f"Saved {args.out}")
            else:
                print(result_text)
            return 0
        bundle = _json(args.input)
        validate_bundle(bundle)
        if args.command == "review-agentora":
            import os
            from .agentora_bridge import execute_agentora
            from .reviewers import save_private_receipt, validate_private_path
            if not (args.execute_local and args.approve_local_inference):
                raise InputError("Agentora inference requires --execute-local and --approve-local-inference")
            role_models = {
                "assumption_challenger": args.model_challenger or args.model,
                "alternative_builder": args.model_alternative or args.model,
                "experiment_auditor": args.model_auditor or args.model,
            }
            key = os.environ.get("PHIDISCOVERY_AGENTORA_REVIEW_KEY", "")
            validate_private_path(args.out)
            receipts = execute_agentora(bundle, role_models, port=args.port,
                                       operator_key=key, root=args.input.parent)
            save_private_receipt(receipts, args.out)
            print(f"Saved private Agentora receipt with {len(receipts['receipts'])} model reviews; human review required")
            return 0
        if args.command in ("review-pack", "review-local", "review-compare"):
            from .reviewers import create_packets, execute_local, compare, save_private_receipt, validate_private_path
            if args.command == "review-pack":
                output = create_packets(bundle, root=args.input.parent)
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"Saved {args.out} ({len(output['packets'])} isolated packets; no model call)")
                return 0
            if args.command == "review-local":
                if not (args.execute_local and args.approve_local_inference):
                    raise InputError("Local inference requires both --execute-local and --approve-local-inference")
                validate_private_path(args.out)
                output = execute_local(bundle, args.model, port=args.port, root=args.input.parent)
                save_private_receipt(output, args.out)
                print(f"Saved private model receipt with {len(output['receipts'])} reviews; human review required")
                return 0
            output = compare(bundle, _json(args.receipts), root=args.input.parent)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Saved {args.out} ({len(output['comparisons'])} candidates; no claims verified)")
            return 0
        if args.command == "challenge":
            from .challenge import challenge
            plan = challenge(bundle, root=args.input.parent)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Saved {args.out} ({plan['counts']['candidates']} candidates, {plan['counts']['open_issues']} open issues)")
            return 0
        if args.command == "validate":
            print(f"PASS: {len(bundle['candidates'])} candidates, {len(bundle['evidence'])} evidence records")
            return 0
        if args.command == "check":
            report = _json(args.report)
            if verify_report(report, bundle, args.input.parent):
                print("PASS: report matches re-analysis of input and local artifacts")
                return 0
            print("FAIL: report differs from re-analysis", file=sys.stderr)
            return 2
        report = analyze(bundle, root=args.input.parent)
        args.out.mkdir(parents=True, exist_ok=True)
        result_path = args.out / "report.json"
        result_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        save_report(report, args.out / "report.html")
        print(f"Saved {result_path} and {args.out / 'report.html'}")
        for c in report["results"]:
            print(f"  {c['id']}: {c['stage']} ({c['eligible_support_count']} eligible support records)")
        return 0
    except (OSError, InputError, ValueError, KeyError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

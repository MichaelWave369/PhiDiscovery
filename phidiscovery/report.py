"""Generate a self-contained human-readable report with safely escaped inputs."""
from __future__ import annotations

import html
from pathlib import Path


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def html_report(report: dict) -> str:
    cards = []
    for r in report["results"]:
        flags = "".join(f"<li>{esc(f)}</li>" for f in r["flags"]) or "<li>No additional flags</li>"
        cards.append(f'''<section class="card"><div class="split"><h2>{esc(r['label'])}</h2><span class="status">{esc(r['stage'].replace('_',' '))}</span></div>
<p class="muted">{esc(r['id'])} · {esc(r['hypothesis'])}</p><div class="numbers"><div><b>{r['evidence_count']}</b><small>records</small></div><div><b>{r['eligible_support_count']}</b><small>eligible supports</small></div><div><b>{r['independent_groups']}</b><small>independent groups</small></div></div>
<h3>Scientific challenges</h3><ul>{flags}</ul><p class="muted">Evidence: {esc(', '.join(r['evidence_ids']) or 'none')}</p></section>''')
    audit = ''.join(f'''<tr><td>{esc(e['id'])}</td><td>{esc(e['candidate_id'])}</td><td>{'YES' if e['synthetic'] else 'NO'}</td><td>{esc(e['artifact_integrity'])}</td><td>{'YES' if e['eligible_support'] else 'NO'}</td></tr>''' for e in report['evidence_audit'])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PhiDiscovery | {esc(report['project']['name'])}</title><style>
:root{{--bg:#090f1b;--surface:#131e2e;--line:#2e4358;--bright:#e8f7f3;--muted:#a4babb;--accent:#66e1c3}}*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(ellipse at 15% 0%,#183c42 0%,var(--bg) 45%);color:var(--bright);font:15px/1.65 system-ui,-apple-system,Segoe UI,sans-serif}}main{{max-width:1150px;margin:auto;padding:42px 20px 80px}}header{{border-bottom:1px solid var(--line);padding-bottom:24px;margin-bottom:30px}}.brand{{color:var(--accent);font-weight:800;letter-spacing:.18em;text-transform:uppercase}}h1{{font-size:clamp(32px,5vw,58px);line-height:1.12;margin:12px 0}}h2{{font-size:22px;margin:0}}h3{{font-size:14px;margin-bottom:4px;color:var(--accent);text-transform:uppercase;letter-spacing:.09em}}.muted,small{{color:var(--muted)}}.warn{{padding:15px 20px;border-left:4px solid #edbb70;background:#302720;margin:20px 0 28px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(295px,1fr));gap:16px}}.card{{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:22px;min-width:0}}.split{{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap}}.status{{background:#28433d;color:#a5f3d6;border-radius:99px;padding:4px 10px;font-size:11px;text-transform:uppercase;font-weight:700;letter-spacing:.04em}}.numbers{{display:flex;gap:30px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:15px 0;margin:14px 0}}.numbers div{{display:flex;flex-direction:column}}.numbers b{{font-size:25px}}.numbers small{{font-size:11px}}ul{{padding-left:18px}}li{{margin:6px 0}}.tablewrap{{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:14px;margin-top:12px}}table{{border-collapse:collapse;width:100%}}th,td{{padding:12px 14px;text-align:left;border-bottom:1px solid var(--line)}}th{{color:var(--accent);font-size:12px;text-transform:uppercase}}code{{overflow-wrap:anywhere;color:#9edbe0}}footer{{color:var(--muted);font-size:12px;margin-top:35px}}
</style></head><body><main><header><div class="brand">ΦDiscovery Engine · Evidence-first research</div><h1>{esc(report['project']['name'])}</h1><p class="muted">Domain: {esc(report['project']['domain'])} · Engine {esc(report['engine_version'])} · {report['counts']['candidates']} candidates · {report['counts']['evidence']} evidence records</p></header>
<div class="warn"><b>Research status: not a validated discovery.</b><br>{esc(report['interpretation'])}{'<br><b>This run includes synthetic demonstration data.</b>' if report['counts']['synthetic_evidence'] else ''}</div>
<h2>Candidate triage</h2><div class="grid">{''.join(cards)}</div><h2 style="margin-top:32px">Evidence audit</h2><div class="tablewrap"><table><thead><tr><th>Record</th><th>Candidate</th><th>Synthetic?</th><th>Artifact integrity</th><th>Eligible support?</th></tr></thead><tbody>{audit}</tbody></table></div>
<footer>Reproducible input SHA-256: <code>{esc(report['input_sha256'])}</code><br>Independent experimental validation is required before scientific claims. Local artifact integrity checks verify bytes, not the accuracy of scientific conclusions.</footer></main></body></html>'''


def save_report(report: dict, path: Path) -> None:
    path.write_text(html_report(report), encoding="utf-8")

"""U1 proof receipt: re-check a published run offline, with no keys.

    python -m proofroom.verify data/cases/<case>/run-<n>

Checks the manifest and the SHA-256 of every file it lists, loads case.json as a
CaseRecord, re-runs the code gate on every emitted sentence (case.findings) and on
cited financing lines, and checks that every [E#]/[G#] citation in brief.md exists in
case.evidence.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from proofroom import store
from proofroom.gate import CITE_RE, GateResult, gate_sentence, normalize
from proofroom.models import CaseRecord

# Financing lines whose numbers are copied from the cited record rows. Other kinds
# (calculation, question, the pipeline's round_check, which quotes the announcement's
# figures next to the record's) are labelled text, not record quotes, so not re-gated.
GATED_FINANCING_KINDS = {"round", "indexed_round", "total"}


@dataclass
class Receipt:
    ok: bool
    lines: list[str] = field(default_factory=list)

    @property
    def failures(self) -> int:
        return sum(1 for ln in self.lines if ln.startswith("FAIL"))


def _counts(r: GateResult) -> str:
    c = r.counts or {}
    parts = []
    for kind in ("amounts", "dates", "percentages", "years"):
        ok, total = (c.get(kind) or [0, 0])
        if kind in ("amounts", "dates") or total:
            parts.append(f"{kind} {ok}/{total}")
    return " ".join(parts)


def verify_receipt(run_dir: Path) -> Receipt:
    run_dir = Path(run_dir)
    lines: list[str] = []
    man_path = run_dir / "manifest.json"
    try:
        man = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return Receipt(False, [f"FAIL manifest.json unreadable ({type(e).__name__})"])
    if man.get("delivery") == "DELIVERED":
        lines.append(f"PASS manifest delivery DELIVERED (brief status {man.get('brief_status', '?')})")
    else:
        lines.append(f"FAIL manifest delivery {man.get('delivery')!r}")
    files = man.get("files") or {}
    for name in store.FILES:
        if name not in files:
            lines.append(f"FAIL sha256 {name} (not in manifest)")
    for name, digest in files.items():
        try:
            actual = store.sha256_bytes((run_dir / name).read_bytes())
        except OSError:
            lines.append(f"FAIL sha256 {name} (missing)")
            continue
        lines.append(f"PASS sha256 {name}" if actual == digest else f"FAIL sha256 {name} (mismatch)")

    try:
        case = CaseRecord.model_validate_json((run_dir / "case.json").read_text(encoding="utf-8"))
        lines.append("PASS case.json loads as CaseRecord")
    except (OSError, ValueError) as e:
        lines.append(f"FAIL case.json does not load ({type(e).__name__})")
        return Receipt(False, lines)
    try:
        brief = (run_dir / "brief.md").read_text(encoding="utf-8")
    except OSError:
        brief = ""
    brief_norm = normalize(brief)

    ev = {e.id: e for e in case.evidence}
    for f in case.findings:
        r = gate_sentence(f.sentence, f.evidence_ids, ev)
        why = "" if r.clean else f" ({'; '.join(r.failures) or 'suppressed'})"
        in_brief = normalize(f.sentence) in brief_norm
        if not in_brief:
            why += " (sentence not found in brief.md)"
        verdict = "PASS" if r.clean and in_brief else "FAIL"
        lines.append(f"{verdict} {f.claim_id} {_counts(r)}{why}")

    for n, d in enumerate(case.financing):
        ids = [i for i in d.get("evidence_ids") or [] if i]
        if d.get("kind") not in GATED_FINANCING_KINDS or not ids:
            continue
        r = gate_sentence(str(d.get("line") or ""), ids, ev)
        why = "" if r.clean else f" ({'; '.join(r.failures)})"
        lines.append(f"{'PASS' if r.clean else 'FAIL'} financing[{n}] {_counts(r)}{why}")

    cited = CITE_RE.findall(brief)
    missing = sorted({c for c in cited if c not in ev})
    if missing:
        lines.append(f"FAIL citations in brief.md: unknown {', '.join(missing)}")
    else:
        lines.append(f"PASS citations {len(cited)}/{len(cited)} in brief.md exist in case.evidence")
    return Receipt(not any(ln.startswith("FAIL") for ln in lines), lines)


def format_receipt(r: Receipt) -> str:
    tail = "RECEIPT OK" if r.ok else f"RECEIPT FAILED ({r.failures or 1})"
    return "\n".join(r.lines + [tail]) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m proofroom.verify <run folder>", file=sys.stderr)
        return 2
    r = verify_receipt(Path(args[0]))
    sys.stdout.write(format_receipt(r))
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

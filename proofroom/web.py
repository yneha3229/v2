"""Web UI (plan v2 §8.2 progressive UI, §8.5 run modes and "Load demo case (no keys)").

    uvicorn proofroom.web:app

Runs execute in-process (`asyncio.create_task(pipeline.run(...))`); the page polls
`GET /api/runs/{token}` once a second. Published runs are rendered from their run
folder, so `/runs/<case_id>/<n>` works after a restart. All source-derived text is
escaped: fetched pages are untrusted data, never markup or instructions.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from proofroom import config, exceptions, pipeline, store
from proofroom.models import CaseRecord

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
CASE_RE = re.compile(r"[a-z0-9-]{1,120}")
CITE_RE = re.compile(r"\[([EG]\d{1,4})\]")
DEMOS = {"koah": ("Koah", "koahlabs.com"), "linear": ("Linear", "linear.app"),
         "attio": ("Attio", "attio.com")}
MAX_URLS = 3
MAX_TEXT = 200_000

app = FastAPI(title="Proofroom", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
_env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=True)
templates = Jinja2Templates(env=_env)


# ---- Safe markdown subset ------------------------------------------------------------

def _inline(text: str) -> str:
    """`text` is already HTML-escaped. Adds code, bold, italic, links, citations."""
    codes: list[str] = []

    def keep(m: re.Match) -> str:
        codes.append(f"<code>{m.group(1)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", keep, text)

    def link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        if re.match(r"^(https?://|#)", url, re.I):
            return (f'<a href="{url}" rel="noopener noreferrer nofollow" '
                    f'target="_blank">{label}</a>')
        return f"{label} ({url})"

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    text = CITE_RE.sub(lambda m: f'<a class="cite" href="#ev-{m.group(1)}" '
                                 f'data-ev="{m.group(1)}">[{m.group(1)}]</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def _cells(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)]


def md_to_html(md: str) -> str:
    """A small, safe markdown converter: escape everything first, then render headings,
    paragraphs, bold/italic/code, lists, tables, block quotes, rules and http(s) links.
    Raw HTML in the input is never passed through (comment lines are dropped)."""
    out: list[str] = []
    lines = (md or "").replace("\r\n", "\n").split("\n")
    i, para, lst = 0, [], ""

    def flush_para() -> None:
        if para:
            out.append("<p>" + "<br>".join(_inline(p) for p in para) + "</p>")
            para.clear()

    def close_list() -> None:
        nonlocal lst
        if lst:
            out.append(f"</{lst}>")
            lst = ""

    while i < len(lines):
        raw = lines[i]
        if re.fullmatch(r"\s*<!--.*-->\s*", raw):
            i += 1
            continue
        line = html.escape(raw, quote=True)
        s = line.strip()
        if s.startswith("```"):
            flush_para(); close_list()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(html.escape(lines[i], quote=True))
                i += 1
            out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
            i += 1
            continue
        if not s:
            flush_para(); close_list()
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush_para(); close_list()
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
            i += 1
            continue
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s):
            flush_para(); close_list()
            out.append("<hr>")
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and re.fullmatch(
                r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", lines[i + 1].strip()):
            flush_para(); close_list()
            head = _cells(s)
            body = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                body.append(_cells(html.escape(lines[i], quote=True)))
                i += 1
            t = ['<div class="table-wrap"><table><thead><tr>']
            t += [f"<th>{_inline(c)}</th>" for c in head]
            t.append("</tr></thead><tbody>")
            for r in body:
                t.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table></div>")
            out.append("".join(t))
            continue
        m = re.match(r"^(?:[-*+])\s+(.*)$", s)
        m2 = re.match(r"^\d+[.)]\s+(.*)$", s)
        if m or m2:
            flush_para()
            kind = "ul" if m else "ol"
            if lst != kind:
                close_list()
                out.append(f"<{kind}>")
                lst = kind
            out.append(f"<li>{_inline((m or m2).group(1))}</li>")
            i += 1
            continue
        if s.startswith("&gt;"):
            flush_para(); close_list()
            out.append(f"<blockquote>{_inline(s[4:].strip())}</blockquote>")
            i += 1
            continue
        close_list()
        para.append(s)
        i += 1
    flush_para(); close_list()
    return "\n".join(out)


def cite_html(text: Any) -> Markup:
    """Escape plain text, then turn [E1]/[G3] into evidence-drawer links."""
    esc = html.escape(str(text or ""), quote=True)
    return Markup(CITE_RE.sub(lambda m: f'<a class="cite" href="#ev-{m.group(1)}" '
                                        f'data-ev="{m.group(1)}">[{m.group(1)}]</a>', esc))


def safe_url(url: Any) -> str:
    u = str(url or "")
    return u if re.match(r"^https?://", u, re.I) else ""


_env.filters["cite"] = cite_html
_env.filters["safe_url"] = safe_url
_env.filters["md"] = lambda s: Markup(md_to_html(s or ""))


# ---- Paths and run folders ------------------------------------------------------------

def _store() -> store.Store:
    return store.Store()  # reads config.DATA_DIR at call time (tests monkeypatch it)


def run_path(case_id: str, n: int) -> Path:
    """The run folder for validated params, or 404. Blocks traversal by construction."""
    if not CASE_RE.fullmatch(case_id or "") or not (1 <= int(n) <= 1_000_000):
        raise HTTPException(404, "no such run")
    root = _store().root.resolve()
    p = (root / case_id / f"run-{int(n)}").resolve()
    if p.parent.parent != root or not p.is_dir():
        raise HTTPException(404, "no such run")
    return p


def _read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_json(p: Path) -> Any:
    t = _read(p)
    if t is None:
        return None
    try:
        return json.loads(t)
    except ValueError:
        return None


def _load_case(p: Path) -> CaseRecord | None:
    t = _read(p / "case.json")
    if t is None:
        return None
    try:
        return CaseRecord.model_validate_json(t)
    except ValueError as e:
        log.warning("case.json in %s does not load: %s", p, e)
        return None


def waiting_for_model(run_dir: str | Path | None) -> str | None:
    """The newest `<name>.request.json` in `<run_dir>/model/` with no response yet."""
    if not run_dir:
        return None
    d = Path(run_dir) / "model"
    try:
        reqs = sorted(d.glob("*.request.json"), key=lambda q: q.stat().st_mtime, reverse=True)
    except OSError:
        return None
    for q in reqs:
        name = q.name[: -len(".request.json")]
        if not (d / f"{name}.response.json").exists():
            return name
    return None


def recent_runs(limit: int = 25) -> list[dict]:
    root = _store().root
    rows: list[tuple[float, dict]] = []
    try:
        cases = [c for c in root.iterdir() if c.is_dir() and CASE_RE.fullmatch(c.name)]
    except OSError:
        return []
    for c in cases:
        for r in c.iterdir():
            m = re.fullmatch(r"run-(\d+)", r.name)
            if not m or not r.is_dir():
                continue
            man = _read_json(r / "manifest.json")
            failed = (r / "failed.json").exists()
            if not man and not failed:
                continue
            try:
                mtime = r.stat().st_mtime
            except OSError:
                mtime = 0.0
            info = {"case_id": c.name, "run": int(m.group(1)),
                    "delivery": (man or {}).get("delivery") or ("FAILED" if failed else "—"),
                    "status": (man or {}).get("brief_status") or ("FAILED" if failed else "—"),
                    "when": datetime.fromtimestamp(mtime).strftime("%d %b %H:%M"),
                    "run_mode": "", "profile": "", "model_source": "", "domain": c.name}
            case = _read_json(r / "case.json") if man else None
            if isinstance(case, dict):
                info["run_mode"] = case.get("run_mode", "")
                info["domain"] = (case.get("input") or {}).get("domain", c.name)
                st = case.get("stats") or {}
                info["profile"] = st.get("profile", "")
                info["model_source"] = st.get("model_source", "")
            rows.append((mtime, info))
    rows.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in rows[:limit]]


# ---- Derived views (render is imported lazily; panels hide if it is missing) ------------

def _render_fn(name: str):
    try:
        from proofroom import render
    except Exception as e:  # noqa: BLE001 - another agent's module may be mid-edit
        log.warning("render unavailable: %s", e)
        return None
    return getattr(render, name, None)


def _try(name: str, *args: Any, **kw: Any) -> Any:
    fn = _render_fn(name)
    if fn is None:
        return None
    try:
        return fn(*args, **kw)
    except Exception as e:  # noqa: BLE001 - a panel failing must not break the page
        log.warning("render.%s failed: %s", name, e)
        return None


def _desk(case: CaseRecord) -> list[dict]:
    items = case.stats.get("exceptions")
    if isinstance(items, list):
        return [i for i in items if isinstance(i, dict)]
    try:
        return [d.as_dict() for d in exceptions.exception_desk(case)]
    except Exception:  # noqa: BLE001
        return []


def _to_day(value: str) -> int | None:
    v = (value or "").strip()
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", v)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)).toordinal()
    except ValueError:
        return None


CLOCKS = ("event", "published", "updated", "refreshed", "retrieved")


def timeline(rows: list[dict] | None) -> list[dict]:
    """Four-clocks rows with a horizontal position (percent) for each point."""
    if not rows:
        return []
    pts: list[tuple[dict, dict]] = []
    for row in rows:
        for clock in CLOCKS:
            vals = row.get(clock)
            vals = [vals] if isinstance(vals, dict) else (vals or [])
            for v in vals:
                if isinstance(v, dict) and v.get("value"):
                    pts.append((row, {"clock": clock, "value": str(v.get("value")),
                                      "precision": str(v.get("precision") or "unknown"),
                                      "evidence_id": str(v.get("evidence_id") or ""),
                                      "day": _to_day(str(v.get("value")))}))
    days = [p["day"] for _, p in pts if p["day"] is not None]
    lo, hi = (min(days), max(days)) if days else (0, 0)
    out: list[dict] = []
    for row in rows:
        mine = [p for r, p in pts if r is row]
        for p in mine:
            p["left"] = (50.0 if p["day"] is None or hi == lo
                         else round(4 + 92 * (p["day"] - lo) / (hi - lo), 2))
        out.append({"claim_id": str(row.get("claim_id", "")), "points": mine})
    span = (date.fromordinal(lo).isoformat(), date.fromordinal(hi).isoformat()) if days else ("", "")
    return [{"span": span, "rows": out}]


def _clock(value: str) -> dict:
    fn = _render_fn("clock_value")
    if fn:
        try:
            return fn(value)
        except Exception:  # noqa: BLE001
            pass
    return {"value": value, "precision": ""}


def evidence_rows(case: CaseRecord) -> list[dict]:
    """Evidence rows for the drawer, each with its four clocks (doc fallback)."""
    docs = {d.id: d for d in case.documents}
    by_src = {d.source: d for d in case.documents}
    rows = []
    for e in case.evidence:
        doc = None
        if e.kind == "source_passage":
            doc = docs.get(re.split(r"[\[:]", e.locator or "", maxsplit=1)[0]) or by_src.get(e.source)
        clocks = []
        for c in ("published", "updated", "refreshed", "retrieved"):
            v = getattr(e, c) or (getattr(doc, c, "") if doc and c != "refreshed" else "")
            clocks.append({"clock": c, **(_clock(v) if v else {"value": "", "precision": ""})})
        rows.append({"id": e.id, "kind": e.kind, "source": e.source, "url": safe_url(e.source),
                     "locator": e.locator, "value": e.value, "subject_basis": e.subject_basis,
                     "origin": e.origin, "clocks": clocks,
                     "doc_title": doc.title if doc else ""})
    return rows


def result_for(case: CaseRecord | None, run_dir: Path | None, brief: str = "") -> dict:
    """The poll `result` block for a finished run."""
    rd = Path(run_dir) if run_dir else None
    brief_md = (_read(rd / "brief.md") if rd else None) or brief or ""
    questions = _read(rd / "questions.md") if rd else None
    email = _read(rd / "founder_email.md") if rd else None
    om = _try("origin_map", case) if case else None
    res = {
        "brief_md": brief_md,
        "brief_html": md_to_html(brief_md),
        "case": case.model_dump(mode="json") if case else None,
        "questions_md": questions if questions is not None else (_try("questions_md", case) if case else None),
        "founder_email_md": email,
        "exceptions": _desk(case) if case else [],
        "origin_map": om,
        "four_clocks": _try("four_clocks", case) if case else None,
        "evidence": evidence_rows(case) if case else [],
        "run_url": (f"/runs/{case.case_id}/{case.run}" if case else None),
    }
    return res


# ---- In-memory run registry -------------------------------------------------------------

@dataclass
class LiveRun:
    token: str
    domain: str
    started: float = field(default_factory=time.monotonic)
    events: list[dict] = field(default_factory=list)
    status: str = "RUNNING"
    run_dir: str | None = None
    error: str = ""
    result: dict | None = None
    task: asyncio.Task | None = None


RUNS: dict[str, LiveRun] = {}
_TASKS: set[asyncio.Task] = set()


def _summary(stage: str, payload: dict) -> dict:
    keep = {
        "start": ("run_dir", "run", "model_source", "profile", "mode", "domain"),
        "identity": ("g1", "team"),
        "packet": ("documents", "injection_notes"),
        "claims": ("claims",),
        "assessed": ("findings",),
        "checked": ("kept", "suppressed"),
        "published": ("status", "run"),
    }.get(stage)
    items = payload.items() if keep is None else ((k, payload.get(k)) for k in keep if k in payload)
    return jsonable_encoder({k: v for k, v in items if k != "elapsed"})


async def _drive(lr: LiveRun, req: "pipeline.RunRequest") -> None:
    async def on_progress(stage: str, payload: dict) -> None:
        payload = payload or {}
        if stage == "start" and payload.get("run_dir"):
            lr.run_dir = str(payload["run_dir"])
        el = payload.get("elapsed")
        lr.events.append({"stage": stage,
                          "elapsed": el if isinstance(el, (int, float))
                          else round(time.monotonic() - lr.started, 2),
                          **_summary(stage, payload)})

    try:
        outcome = await pipeline.run(req, on_progress=on_progress)
    except asyncio.CancelledError:
        lr.status, lr.error = "FAILED", "run cancelled"
        raise
    except Exception as e:  # noqa: BLE001 - a pipeline bug must never crash the server
        log.exception("run %s crashed", lr.token)
        lr.status, lr.error = "FAILED", f"{type(e).__name__}: {e}"
        return
    if outcome.run_dir:
        lr.run_dir = str(outcome.run_dir)
    lr.error = outcome.error or ""
    try:
        if outcome.case is not None:
            lr.result = result_for(outcome.case, outcome.run_dir, outcome.brief)
    except Exception as e:  # noqa: BLE001
        log.exception("result build failed")
        lr.error = lr.error or f"result unavailable: {type(e).__name__}: {e}"
    lr.status = outcome.status or "FAILED"


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = v.splitlines()
    if not isinstance(v, (list, tuple)):
        raise HTTPException(422, "expected a list or newline-separated text")
    return [str(x).strip() for x in v if str(x).strip()]


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def build_request(data: dict) -> "pipeline.RunRequest":
    """Validate UI input into a RunRequest (422 on bad input)."""
    demo = str(data.get("demo") or "").strip().lower()
    if demo:
        if demo not in DEMOS:
            raise HTTPException(422, f"unknown demo case {demo!r}")
        return pipeline.RunRequest(domain=DEMOS[demo][1], run_mode="FIXTURE",
                                   provider="fixture", fixture=demo,
                                   profile=str(data.get("profile") or "FULL").upper(),
                                   email=_bool(data.get("email")))
    domain = str(data.get("domain") or "").strip()
    if not domain or len(domain) > 253 or not re.fullmatch(
            r"(https?://)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}/?", domain):
        raise HTTPException(422, "enter a company domain such as example.com")
    urls = _as_list(data.get("urls"))[:MAX_URLS + 1]
    if len(urls) > MAX_URLS:
        raise HTTPException(422, f"at most {MAX_URLS} URLs")
    for u in urls:
        if not re.match(r"^https?://[^\s<>\"']+$", u) or len(u) > 2000:
            raise HTTPException(422, f"not an http(s) URL: {u[:80]}")
    pasted_raw = data.get("pasted")
    pasted = ([pasted_raw.strip()] if isinstance(pasted_raw, str) and pasted_raw.strip()
              else _as_list(pasted_raw) if not isinstance(pasted_raw, str) else [])
    sentence = str(data.get("sentence") or "").strip()
    focus = str(data.get("focus_note") or "").strip()
    if sum(len(p) for p in pasted) > MAX_TEXT or len(sentence) > 2000 or len(focus) > 2000:
        raise HTTPException(422, "input text is too long")
    run_mode = str(data.get("run_mode") or "CACHED").upper()
    if run_mode not in ("LIVE", "CACHED"):
        raise HTTPException(422, "run mode must be LIVE or CACHED (use the demo selector "
                                 "for FIXTURE)")
    profile = str(data.get("profile") or "FULL").upper()
    provider = str(data.get("provider") or "auto").lower()
    if provider not in ("auto", "anthropic", "session"):
        raise HTTPException(422, "provider must be auto, anthropic or session")
    req = pipeline.RunRequest(
        domain=domain, input_mode="B" if (pasted or urls or sentence) else "A",
        run_mode=run_mode, profile=profile, provider=provider, focus_note=focus,
        urls=urls, pasted=pasted, sentence=sentence, email=_bool(data.get("email")))
    try:
        req.normalized()
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return req


# ---- Routes ----------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    demos = [{"key": k, "label": lbl, "domain": d,
              "available": (config.FIXTURES_DIR / k).is_dir()} for k, (lbl, d) in DEMOS.items()]
    return templates.TemplateResponse(request, "index.html",
                                      {"demos": demos, "runs": recent_runs()})


@app.post("/api/runs")
async def start_run(request: Request) -> JSONResponse:
    ctype = request.headers.get("content-type", "")
    try:
        if "application/json" in ctype:
            data = await request.json()
        else:
            form = await request.form()
            data = {k: (form.getlist(k) if k == "urls" else form.get(k)) for k in form.keys()}
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, "body must be JSON or a form") from None
    if not isinstance(data, dict):
        raise HTTPException(422, "body must be a JSON object")
    req = build_request(data)
    token = secrets.token_urlsafe(12)
    lr = LiveRun(token=token, domain=req.domain)
    RUNS[token] = lr
    lr.task = asyncio.create_task(_drive(lr, req))
    _TASKS.add(lr.task)
    lr.task.add_done_callback(_TASKS.discard)
    if len(RUNS) > 200:  # forget the oldest finished runs
        for t in [t for t, r in RUNS.items() if r.status != "RUNNING"][:50]:
            RUNS.pop(t, None)
    return JSONResponse({"token": token})


@app.get("/api/runs/{token}")
async def poll_run(token: str) -> JSONResponse:
    lr = RUNS.get(token)
    if lr is None:
        raise HTTPException(404, "unknown run token")
    running = lr.status == "RUNNING"
    return JSONResponse({
        "token": token, "domain": lr.domain, "status": lr.status,
        "elapsed": round(time.monotonic() - lr.started, 1),
        "events": lr.events, "run_dir": lr.run_dir, "error": lr.error or None,
        "waiting_for_model": waiting_for_model(lr.run_dir) if running else None,
        "result": None if running else lr.result,
        "run_url": _run_url(lr.run_dir),
    })


def _run_url(run_dir: str | None) -> str | None:
    if not run_dir:
        return None
    p = Path(run_dir)
    m = re.fullmatch(r"run-(\d+)", p.name)
    if not m or not CASE_RE.fullmatch(p.parent.name):
        return None
    return f"/runs/{p.parent.name}/{m.group(1)}"


@app.get("/runs/{case_id}/{n}", response_class=HTMLResponse)
async def run_page(request: Request, case_id: str, n: int) -> HTMLResponse:
    p = run_path(case_id, n)
    man = _read_json(p / "manifest.json")
    rd = store.RunDir(case_id, n, p)
    verified = bool(man) and man.get("delivery") == "DELIVERED" and store.verify_run(rd)
    case = _load_case(p) if man else None
    failed = _read_json(p / "failed.json")
    ctx: dict[str, Any] = {"case_id": case_id, "n": n, "manifest": man, "verified": verified,
                           "case": case, "failed": failed if isinstance(failed, dict) else None,
                           "waiting": waiting_for_model(p) if not man else None}
    if case is not None:
        brief = _read(p / "brief.md") or ""
        om = _try("origin_map", case)
        svg = _try("origin_map_svg", om) if om is not None else None
        ctx.update({
            "brief_html": Markup(md_to_html(brief)),
            "questions_html": Markup(md_to_html(q)) if (q := _read(p / "questions.md")) else None,
            "email_html": Markup(md_to_html(em)) if (em := _read(p / "founder_email.md")) else None,
            "desk": _desk(case),
            "evidence": evidence_rows(case),
            "findings": {f.claim_id: f for f in case.findings},
            "origin_svg": Markup(svg) if isinstance(svg, str) and svg.lstrip().startswith("<svg") else None,
            "origin_count": (om or {}).get("independent_origin_count") if isinstance(om, dict) else None,
            "timeline": timeline(_try("four_clocks", case)),
            "profile": str(case.stats.get("profile") or "FULL"),
            "model_source": str(case.stats.get("model_source") or "unknown"),
            "failed_attempts": sum(1 for a in case.attempts if _attempt_failed(a)),
        })
    return templates.TemplateResponse(request, "run.html", ctx)


def _attempt_failed(a: Any) -> bool:
    st = str(getattr(a, "status", "")).lower()
    return bool(getattr(a, "error", None)) or not (st in ("ok", "end_turn") or st.startswith("2"))


_env.tests["failed_attempt"] = _attempt_failed


@app.get("/api/verify/{case_id}/{n}")
async def verify_run(case_id: str, n: int) -> JSONResponse:
    p = run_path(case_id, n)
    try:
        from proofroom import verify as _verify
        r = _verify.verify_receipt(p)
        text = _verify.format_receipt(r)
        return JSONResponse({"ok": bool(r.ok), "lines": text.rstrip("\n").split("\n")})
    except (ImportError, AttributeError):
        ok = store.verify_run(store.RunDir(case_id, n, p))
        return JSONResponse({"ok": ok, "lines": [
            ("PASS" if ok else "FAIL") + " manifest DELIVERED and every file matches its SHA-256",
            "RECEIPT OK" if ok else "RECEIPT FAILED"]})
    except Exception as e:  # noqa: BLE001
        log.exception("verify failed")
        return JSONResponse({"ok": False, "lines": [f"FAIL receipt error: {type(e).__name__}"]})


@app.get("/runs/{case_id}/{n}/report", response_class=HTMLResponse)
async def run_report(case_id: str, n: int) -> HTMLResponse:
    """U9: the printable three-page diligence report, as published (hash-checked)."""
    p = run_path(case_id, n) / "report.html"
    if not p.is_file():
        raise HTTPException(404, "this run has no report")
    return HTMLResponse(p.read_text(encoding="utf-8"))


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}

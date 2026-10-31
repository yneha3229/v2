# PROGRESS: Proofroom build

*The single source of truth for where the build stands. A new session reads this first (CLAUDE.md §1) and updates it after every step and every 15 minutes of work (CLAUDE.md §2).*

*This file is authoritative at `C:\dev\proofroom\PROGRESS.md`. The copy in `proofroom\build-kit\` is a snapshot from 31 Oct 01:30 IST.*

---

## Prompts

**Start or resume a session.** Open Claude Code in the repository root and paste:

```text
Resume the Proofroom build. Follow CLAUDE.md §1 (session start protocol) exactly: check the clock,
read PROGRESS.md, check git status and log, re-verify the last DONE step, log this session, then
continue from "Next action". Work one step at a time, checkpoint every 15 minutes, and keep
PROGRESS.md current. If you approach your context or usage limit, do the CLAUDE.md §7 handoff
before anything else.
```

**Wrap up a session that is near its limit.** Paste:

```text
Stop feature work now. Do the CLAUDE.md §7 handoff: update the Current state block in PROGRESS.md
(step, what works with verify commands, what is half-done by file/function, the exact next action,
blockers), then commit with "handoff: S<n> <state>". Reply with the Next action line only.
```

**Several people in parallel** (one session each):

```text
Resume the Proofroom build as owner ‹A|B|C|D›. Follow CLAUDE.md §1, then claim step ‹S#› in
PROGRESS.md (IN PROGRESS, your owner letter, time), commit and push PROGRESS.md, and work only on that step.
```

---

## Current state

*Overwrite this block at every handoff. Keep it under 10 lines.*

- **Updated:** 12:06 IST by Session 1 (Neha). **Build complete through S12; next is S13 freeze checks.**
- **Works (verified):** `pytest -q` → 204 passed. No-key demos: `python -m proofroom run --fixture koah|linear|attio` → DELIVERED; `python -m proofroom verify <run>` → RECEIPT OK for all three. Web UI `uvicorn proofroom.web:app` (Playwright-checked). Secrets scan clean (12:05).
- **Model:** session provider (D15/D20): the pipeline writes `<run>/model/<call>.request.json`; an agent writes `<call>.response.json`. No API key.
- **Not done:** S13 clean-clone quickstart + unseen selection (Prep_03 §2) · S14 recording (user: screen capture + Loom) · S15 submit form (user) · S16 stage kit. FAST profile not yet timed on a live run.
- **Next action:** S13: `git clone` to a temp dir, follow README quickstart with no keys (`run --fixture koah`), then run the predeclared unseen-selection search after the freeze and pick candidate 1.
- **Blockers / decisions:** the unseen run needs an agent to answer 3 model calls live on camera (≈1–3 min). Recorder test (0.5) still undone by the user.

---

## Before 10:30: morning checklist (no code)

| Time | Do | Done? |
|---|---|---|
| 08:00–08:30 | Set `$env:ANTHROPIC_API_KEY`. Run the 0.6 one-liner in `proofroom\Day_Check_Report.md`; it must print `claude-sonnet-5-5`. | ☐ |
| 08:00–08:30 | Recorder (0.5): a 10 s OBS capture at 1920×1080 with the Realtek mic → play it back | ☐ |
| 08:00–08:30 | Confirm every member is eligible and the team is registered on the YC event platform (§1.3) | ☐ |
| 08:30 | Optional re-run of 0.8 (6 pages, 200) and a glance at the changelog. Both passed at 01:15. | ☐ |
| Before leaving | Bring the charger and a phone hotspot (rate-limit or network fallback, §12). `C:\dev\proofroom-wheelhouse` makes S0 work offline. | ☐ |
| 09:30 | Ask the organizers Q1, Q2, Q5, Q6 (§16) → write the answers in the Day-check summary below | ☐ |
| 10:00 | Get the event key. Ask Crustdata Q3 and Q4. Choose the §14 role split. Run **Phase 1** (runbook start prompt, `PHASE 1`) using the event key by curl. | ☐ |

**Already done overnight (don't redo):**

- Phase 0 checks 0.1–0.4 and 0.7–0.9.
- §13.1 items 3–6 as prose in `proofroom\prep\`:
  - `Prep_01_Prompts_and_Schemas.md`: the three system prompts plus flat schemas (S6).
  - `Prep_02_Answer_Keys_and_Test_Groups.md`: P1–P3 keys with live graph values; T-api, T-identity, T-finance and T-safety cases (S9, S11).
  - `Prep_03_README_Selection_Video_Pitch.md`: README outline, the unseen-selection query, 2:00 narration, the 45 s pitch (S12–S16).
- Repo folder `C:\dev\proofroom` created outside OneDrive.

## S0 recipe (from 10:30; about 2 minutes, works offline)

```powershell
cd C:\dev\proofroom
git init
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links C:\dev\proofroom-wheelhouse -r C:\dev\proofroom-wheelhouse\requirements.lock.txt
Copy-Item C:\dev\proofroom-wheelhouse\requirements.lock.txt requirements.txt
.\.venv\Scripts\python.exe -c "import fastapi, anthropic, httpx, pydantic, bs4; print('ok')"
```

- Then add `.gitignore` (`.env`, `data/`, `cache/`, `.venv/`), `.env.example` (variable names only) and the `proofroom/` and `tests/` packages.
- The lock pins anthropic 2.3.0, httpx 0.28.1, httpx2 2.16.0, pydantic 2.14.2, fastapi 0.162.0, uvicorn 0.54.0, pytest 9.2.0 and others.
- **Optional** (needs a Decisions entry first): `python-dotenv` (to read `.env`) and `python-multipart` (only if FastAPI `Form()` is used). Both are in the wheelhouse; see `requirements.optional.txt`.

---

## Steps

| Step | Status | Owner | Started | Done | Commit | Verify result / note |
|---|---|---|---|---|---|---|
| S0 Setup | DONE | Neha | 10:44 | 10:47 | S0 | `ok 2.3.0 0.28.1 2.14.2` (anthropic, httpx, pydantic); pins from PyPI in `requirements.txt` |
| S1 T1 day-check Phase 2 | DONE (superseded) | Neha | 10:44 | 12:06 | — | Anthropic checks 2.1–2.2 superseded by D15/D20 (session model). 2.3–2.5 exercised by the Koah/Linear/Attio runs; 2.6 retrieval 6–11 s live |
| S2 Crustdata adapter | DONE | Neha | 10:47 | 10:50 | S2 | `33 passed`; `probe koahlabs.com` → `MATCHED id=3718859`. Error hierarchy, redacting logger, corrupt-cache = miss, PC-3 filter |
| S3 Models and run store | DONE | Neha | 10:50 | 10:51 | S3 | `9 passed`: write-once (`xb`), read-back hash, manifest only after verify; saf-4/saf-5; strict flat schemas |
| S4 Graph resolve | DONE | Neha | 10:51 | 10:54 | S4 | `28 passed` on recorded fixture `fixtures/koah`. 3 founders ✔ at 3718859; Herrick→Affirm 632082 ✔, Supermove 780882 ✔, **Qualified ? (see D14)**; seed $5M 2025-09-07. PC-2/3/6 applied |
| S5 Packet intake | DONE | Neha | 11:15 | 11:22 | S5 | `22 passed`. Koah picks: PR Newswire Series A 2026-02-24, TechCrunch $5M seed 2025-09-07, FinSMEs; 17 excluded with reasons. Attio published 2025-08-26 / updated 2026-08-04; "two months ago" → 2025-09. U2 injection meter in. 6 credits |
| S6 Model calls | DONE | Neha | 11:15 | 11:32 | S6 | `19 passed`. Session/API/fixture providers; strict local validation. PC-7: refusal = failed attempt (kept). Warmup N/A for session provider |
| S7 Vertical slice (CLI) | DONE | Neha | 11:20 | 11:29 | S7 | Koah Mode A run-1 DELIVERED (99 s incl. agent answering; pipeline ≈1 s on cache). `verify` → RECEIPT OK, 17/17 citations. FIXTURE demo `run --fixture koah` DELIVERED in 0.31 s with no keys |
| S8 Mode A end to end | DONE | Neha | 11:35 | 11:53 | S8 | Koah, Linear, Attio domain-only all DELIVERED + RECEIPT OK (fixture replays, no keys). Linear: tender = liquidity, total not capital, Karri ✔ (PC-3 union). Attio: GV matched only via source-stated alias |
| S9 T2 usefulness | DONE | Neha | 11:45 | 11:53 | S9 | Metrics below. P1 K1/K2 ✔; P2 L1 core ✔ (L1 qualifier sentence withheld by strict check), L2 no source in news[]; P3 A1/A2/A3 ✔. 0 false conflicts / false sums / wrong subjects / alias errors. T2 pass (≥3 reusable sentences, ≥1 ID join each) |
| S10 Web UI | DONE | Neha | 11:40 | 11:32 | S10 | `23 passed` (199 total). Playwright: index + demo run DELIVERED, drawer opens, 0 JS errors, mobile scrollWidth 390. U3/U4/U5/U7/U8 panels in. TODO polish: collapse long panels |
| S11 T3 tests and fixtures | DONE | Neha | 10:50 | 12:06 | 1196e58 | Strip script `proofroom/fixtures.py`; fixtures koah/linear/attio (Crustdata + model); T-api/T-identity/T-finance/T-safety cases across test files; `pytest -q` 204 green; FIXTURE in CLI and UI |
| S12 README and should-ship | DONE (README) | Neha | 12:00 | 12:03 | S12 | README: 5 deck sections, real results table (3/3 DELIVERED, 0 errors), 204 tests by group, 9 approaches tried. UI polish: run page 8826→1868 px, flag counts + readable desk. Clean-clone quickstart check moves to S13 |
| S13 Freeze checks | TODO | All | | | | Freeze 14:00; selection query in Prep_03 |
| S14 Unseen recording | TODO | D | | | | Narration in Prep_03 |
| S15 Submit | TODO | D | | | | By 15:20 |
| S16 Finals prep | TODO | All | | | | 45 s pitch + Q&A in Prep_03 |

**Status values:** TODO · IN PROGRESS · DONE · BLOCKED · CUT. A cut step needs a matching Decisions entry.

---

## Day-check summary

*Copy the verdict and any plan changes from `Day_Check_Report.md`.*

- **Verdict:** Phase 0 GO-WITH-CHANGES (01:25). Phase 1: ‹…› Phase 2: ‹…›
- **Event key:** balance ‹…›; required endpoints enabled ‹yes/no›; rate limits ‹…›
- **Plan changes applied:** PC-1 to PC-7 proposed (see Decisions). Apply them while coding S2/S4/S5/S6.
- **Organizer answers (Q1–Q6):** —

---

## Event deck facts (ContextCon 03 deck, read 11:25)

- **Judging /100:** end-to-end 25 · facts & verification 20 · robustness & edge cases 20 · customer value & idea 20 · demo & understanding 15.
- **Theme "Services, Replaced":** the agent does the whole service job; a person only for exceptions; every decision cites reasons.
- **Submit by 15:30:** public GitHub repo + 2-min Loom of a request never seen before → finished work. Commit history from 31 Oct.
- **README must have:** the service (who does it, who pays) · what it does now (and where a person is needed) · what next · how to run + how built (agents, models, tools, where Crustdata is called) · approaches tried (what worked / failed).
- Any model allowed. 15,000 Crustdata credits per builder (IITB email, code CONTEXTCON-IITB). Agents may contact only the team and the Crustdata/Techfest teams.

## Decisions

*Number every decision and cite the plan section it changes.*

| # | Time | Decision | Reason | Plan § |
|---|---|---|---|---|
| D1 | 01:20 | The venv uses Python 3.12.2; deps come from the offline wheelhouse with exact pins (anthropic 2.3.0) | Verified offline install; protects S0 against venue Wi-Fi | §8.1 |
| D2 | 01:25 | **PC-1:** SDK 2.x is httpx2-based and sends API version 2026-10-21. Never pass `httpx` objects to the Anthropic client; float timeouts only; never log headers (the key is in `Authorization: Bearer`); messages as dicts. | Verified in the installed SDK and the migration guide | §8.3 |
| D3 | 01:25 | **PC-2:** G4 type-matches milestones. `total_investment_usd` is never shown as capital when a `secondary_market` milestone exists. The subtraction question needs "no secondary". | Linear total 233.2M includes the $99M tender | §5.3, §7 |
| D4 | 01:25 | **PC-3:** S1 title filter = OR of `(.)` "founder" and `(.)` "cofounder", unioned with `people.founders`. No `experience.*` in `fields`. | It missed Linear CEO Karri Saarinen ("CEO, Cofounder"); experience fields cost 0.23/result | §6.2, §20.2 |
| D5 | 01:25 | **PC-4:** the ±7-day milestone rule is mandatory for S2 URL picks; `1970-01-01` = unknown date | Linear `news[]` has namesakes; Attio has sentinel and re-dated items | §20.2 |
| D6 | 01:25 | **PC-5/PC-6:** the gate compares amounts at the stated precision. Aliases (GV / Google Ventures, 01A / 01 Advisors) match only when a source states them. | Attio 52,020,932 vs "$52M"; real alias cases | §5.4, §7 |
| D8 | 01:28 | **S13 secret scan:** run the CLAUDE.md S13 regex with the pathspec `-- . ":!CLAUDE.md"`. A pass is exit code 1 (no match). | As written, the scan always self-matches CLAUDE.md line 128, where the regex itself appears | CLAUDE.md §5 S13 |
| D9 | 10:48 | Add `python-dotenv` (read `.env`) and `python-multipart` (FastAPI forms) | Optional deps listed in PROGRESS S0 recipe | §8.1 |
| D10 | 10:48 | Build runs in a Linux cloud container (Python 3.12.3, repo `/home/user/v2`), installing the lock's exact pins from PyPI instead of the Windows wheelhouse | Session is remote; PyPI reachable | §8.1 |
| D11 | 10:48 | Neha holds all four roles (A–D) in one session and works steps sequentially in plan order | Single-session build | §14 |
| D12 | 11:05 | No `Co-Authored-By` trailers on commits; checkpoint commit + push at every step and every 15 min | User instruction | CLAUDE.md §2 |
| D13 | 11:05 | Plan improvements are proposed to the user first and applied only after a go | User instruction | §15 |
| D14 | 11:12 | **APPROVED (user): labelled name-match fallback.** **Finding:** Identify("Qualified") returns 25 candidates, none is 632707 ("Qualified (Acquired by Salesforce)"), so the strict §7 prior-employer rule leaves Herrick→Qualified as `?`. Proposal to user: a labelled name-prefix fallback against the person's own past entries | Live probe 10:58 | §7 G2 |
| D15 | 11:12 | **Model provider = this Claude Code session (user).** No ANTHROPIC_API_KEY. A `session` provider writes each call's request (system, user, JSON schema) to the run's `model/` folder and waits for a response file written by an agent; code validates it with the same strict Pydantic schemas. Brief labels model source `session`. The SDK provider stays for when a key exists. | User decision; matches Day_Check_Report user correction | §8.3 |
| D16 | 11:12 | Build with parallel subagents on disjoint files; this session orchestrates, verifies (tests + review) and is the only committer | User instruction | CLAUDE.md §6 |
| D17 | 11:12 | Upgrades approved: U1 proof receipt (`verify` cmd), U2 injection meter, U3 origin map, U4 four-clocks timeline, U5 one-sentence check, U6 founder-meeting ask sheet (`questions.md`) | User go | §4.3, §15 |
| D18 | 11:12 | Pipeline runs independent stages concurrently (asyncio). New **FAST** profile: every stage runs, code gate kept in full, but effort low on all calls, ≤2 pages, ≤3 claims, no stage-4 extra retrieval; every output labelled FAST | User request | §8.2, §8.3 |
| D19 | 11:12 | Clock triggers relaxed for now at the user's request; freeze/submit times still noted | User instruction | CLAUDE.md §4 |
| D20 | 11:30 | Session provider only for the event; no API key will be added (user) | User decision | §8.3 |
| D21 | 11:30 | **U7 exception desk** approved: brief top section + UI badge "Needs a person: N" listing identity ties, conflicting claims, suppressed sentences and failed checks | Deck: "a person only for the exceptions" | §4.3 |
| D22 | 11:30 | **U8 founder email draft** approved as OPTIONAL, off by default: `PROOFROOM_FOUNDER_EMAIL=1` or `run --email` writes `founder_email.md` (draft only, never sent) | User decision; deck rule: agents contact only the team | §4.5 |
| D23 | 11:50 | **U9 diligence report** (user go: flags + considerations, NO verdict): fixed 3-page `report.md`/`report.html` per run — p1 snapshot + red/amber/green flags from 16 fixed rules citing evidence, p2 team/financing + considerations, p3 methodology + rule table | User idea; §4.5 keeps investment advice out of scope | §4.3 |
| D24 | 12:20 | **Equity-research PDF** (user request): page-1 rating INVEST/ACCUMULATE/HOLD/AVOID + suggested $ of the reader's check size (default $100k) scaled by confidence; flags re-levelled: **critical** = integrity/legal (identity, conflicts, record differs, founder no role, legal news, not active), **red** = business risks (headcount/traffic decline, crowded market, stale funding, lagging peers, thin team, revenue down, layoffs); all from fixed rules in `scoring.py`; Crustdata growth data (headcount/traffic/followers/revenue-estimate series, taxonomy, peers via Company Search); PDF via headless Chromium. Supersedes D23's no-verdict choice | User decision (overrides earlier advice) | §4.3, §4.5 |
| D25 | 12:38 | Crowding thresholds recalibrated to Crustdata's broad categories (pools of 1–2k): high ≥100 funded peers in 24 months, medium 30–99, low <30 (was 15/5, which saturated 'high' for every company). Added amber A5: capital raised (primary only) ≥20× the revenue-estimate upper bound | Data agent finding; all three dev companies were 'high' | D24 |
| D26 | 12:44 | **Economics model** (user request): payroll from headcount by location × role × salary benchmark, plus a switch-premium (1.20–1.25×) estimate from sampled employees' prior employers; revenue point estimate from a log-linear regression trained on Crustdata Company Search companies (cross-validated against their revenue bands) clamped to the company's band; customer profile from taxonomy, description, job titles and talent sources. Validated on 8 private companies against publicly reported ARR. New dev companies (Clay, Vercel, Retool, Ramp, Mercury) are excluded from the unseen pick. numpy 2.5.4 added | User request | D24 |
| D27 | 12:48 | TerraStack (terrastack.in, Crustdata 6421460, Mumbai geospatial) added as a development company at the user's request; excluded from the unseen pick. Signals fetched (8.36 credits): 7 people, 86% Mumbai, band $0–500K | User request | D26 |
| D28 | 13:01 | **Revenue model 2** kept separate from v1 (user): v1 features + Crustdata `social_posts` features (cadence, engagement, topic shares), trained on ~80 companies (≤450 credits; balance 15,110 after IITB promo), compared with v1 on the same CV folds. Prelim v1 CV (126 cos): within-2x 44% vs baseline 36%, median error 0.345 log10 (~2.2x) | User request | D26 |
| D29 | 13:16 | **Calibrated revenue ensemble**: weighted geometric mean of a leave-one-out reported-revenue-per-employee benchmark (60%), model v1 (25%) and model v2/social posts (15%, only if v2 beats v1 in CV); benchmark only for ≥50 staff and ≥$20M primary capital; namesake-flagged headcounts excluded from references; Crustdata band treated as stale when below the estimate. LOO on 6 reported companies: median error 31% (v1 57%, band 78%). Report work paused until models are final (user) | User go | D26 |
| D30 | 13:25 | **Revenue model 3** (user ideas), separate module: namesake-cleaned headcount, loaded payroll from location×role salary benchmarks (startup pay where company pay unknown), payroll-implied revenue, investor quality (top-tier backers), LinkedIn mentions by others, market width (peer pool), hiring intensity; ablations + LOO on reported revenue; diagnosis of Clay over / Ramp, Vercel under | User request | D29 |
| D31 | 14:35 | **Talent & pedigree** (user): founder schools tiered by home market (IIT/IISc/IIM/BITS for India; Ivy/Stanford/MIT/Berkeley/CMU/Oxbridge elsewhere), staff elite-alumni + ex-big-tech counts via Person Search total_count (limit 1, ~54 calls); Team pillar +0..14 and green flag G9; namesake founder filter (title + start ≤ founding+4y). Report gains Talent and Team-economics pages (salary vs PLFS/Payscale/BLS context). Model 3 ridge not adopted (worse than v1); bake-off pipeline stays | User request | D24, D30 |
| D7 | — | **PC-7 (open, S6 owner):** refusal fallback. The recommendation is to keep "refusal = failed attempt". | Fallback only re-runs cyber/frontier_llm declines on Sonnet 5.5 | §8.3 |

---

## Measurements (T2 and runs)

| Run | Mode | Company | LIVE/CACHED/FIXTURE | Seconds | Crustdata credits | Model tokens (in/out) | Sentences emitted/supported/suppressed | Team rows / ID joins | Issues |
|---|---|---|---|---|---|---|---|---|---|
| linear run-1 | A FULL | Linear | CACHED miss→LIVE, model=session agent | 200 (agent answering) | 5 | n/a | 5 sel / 3 supported / 2 withheld (excerpt cut 'blog post'; fixed) | 2 rows → 3 after PC-3 fix / 3 joins | Bugs found & fixed: calc line citation (receipt), excerpt width, deadline counted model wait, lead field, PC-3 union |
| attio run-1 | A FULL | Attio | LIVE, model=session agent | 81 (agent answering) | 5 | n/a | 5 / 5 supported / 0 withheld | 2 / 2 joins | GV = Google Ventures via source-stated alias only |
| koah run-1 | A FULL | Koah | CACHED, model=session | 99.5 (≈1 s pipeline + agent answering) | 0 (cached) | n/a (session) | 5 / 4 supported / 1 withheld (C4, call 3) | 3 / 3 role joins | Fixed after run: desk placement, excerpt boundary, PR Newswire = company statement, withheld-finding question kept if gated |

**Spend so far:**

- **Crustdata (event key, this session):** 3.39 credits: Koah Company Enrich 2, Linear founder search 0.39 (PC-3 confirmed: Karri found), Karri Person Enrich 1, packet agent fetch/search 6 (Koah 3, Attio 3). Linear+Attio agent runs 10, founder searches 0.65. Total ≈ 20. Identify is free.
- **Crustdata (earlier):** about 7.45 credits, all on the personal MCP account: about 2.4 at 00:10 plus 5.05 at 01:20 (balance 192.56). Nothing on the event key yet.
- **Anthropic:** $0.

---

## Unseen-run record (S13–S14)

- **Freeze time:** ‹HH:MM›
- **Selection query and time:** ‹…› (predeclared query in `proofroom\prep\Prep_03_README_Selection_Video_Pitch.md` §2)
- **Candidates (in order):** 1. ‹…› 2. ‹…› 3. ‹…›
- **Attempts:** ‹candidate, start time, result, raw file›
- **Video link / raw recording link:** ‹…›

---

## Session log

*Add one line per session start and end. Fold older entries into summaries when this file passes about 200 lines.*

- Session 0 · 30 Oct evening–31 Oct 00:10 · planning · plan v2, day-check runbook, build kit, §20 probe (personal MCP, ≈2.4 credits).
- Session P · 31 Oct 01:11–01:30 IST · pre-event prep (no code):
  - Phase 0 checks.
  - Offline wheelhouse plus lock.
  - SDK audit, which found anthropic 2.3.0 and httpx2.
  - P2/P3 graph probe (5.05 credits).
  - Prep_01 to Prep_03 written.
  - Repo folder created.
  - Ended at: the morning checklist.
- Session 1 started 10:44 IST (Linux cloud container), resuming at step S0. No ANTHROPIC_API_KEY in env; CRUSTDATA_API_KEY put in `.env`.
- 11:12 user answers: session-as-model (D15), parallel agents (D16), D14 fallback, U1–U6 (D17), FAST (D18).

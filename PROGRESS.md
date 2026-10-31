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

- **Updated:** 01:30 IST, 31 Oct, by the pre-event prep session (no product code written; rule 2).
- **Current step:** S0 (not started; it may start at 10:30 only). Phase 0 of the day check is done early: GO-WITH-CHANGES.
- **Works (verified):**
  - The offline wheelhouse installs and the S0 import check prints `ok` on Python 3.12.2 and 3.14.7.
  - anthropic 2.3.0 `messages.parse` supports `output_format`, `output_config` and `timeout`.
- **Half-done:** nothing. There is no code. The repo folder holds only CLAUDE.md and PROGRESS.md, with no `git init`.
- **Next action:** do the morning checklist below. At 10:30, run S1 (Phase 2) and S0 together, using the S0 recipe below.
- **Blockers / open decisions:** `ANTHROPIC_API_KEY` is not set (check 0.6). Recorder test 0.5 still to do. Plan changes PC-1 to PC-7 need to be applied (see Decisions).

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
| S0 Setup | DONE | Claude (A–D merged) | 10:44 | 10:47 | S0 | `ok 2.3.0 0.28.1 2.14.2` (anthropic, httpx, pydantic); pins from PyPI in `requirements.txt` |
| S1 T1 day-check Phase 2 | TODO | A + B | | | | Phase 0 done early (GO-WITH-CHANGES); Phase 1 at 10:00 |
| S2 Crustdata adapter | DONE | Claude | 10:47 | 10:50 | S2 | `33 passed`; `probe koahlabs.com` → `MATCHED id=3718859`. Error hierarchy, redacting logger, corrupt-cache = miss, PC-3 filter |
| S3 Models and run store | DONE | Claude | 10:50 | 10:51 | S3 | `9 passed`: write-once (`xb`), read-back hash, manifest only after verify; saf-4/saf-5; strict flat schemas |
| S4 Graph resolve | DONE | Claude | 10:51 | 10:54 | S4 | `28 passed` on recorded fixture `fixtures/koah`. 3 founders ✔ at 3718859; Herrick→Affirm 632082 ✔, Supermove 780882 ✔, **Qualified ? (see D14)**; seed $5M 2025-09-07. PC-2/3/6 applied |
| S5 Packet intake | TODO | C | | | | Apply PC-4 (±7-day rule mandatory; 1970-01-01 = unknown) |
| S6 Model calls | TODO | B | | | | Type in Prep_01; decide PC-7 |
| S7 Vertical slice (CLI) | TODO | B + C | | | | Deadline 11:35 |
| S8 Mode A end to end | TODO | A + B | | | | |
| S9 T2 usefulness | TODO | B + D | | | | Decision by 12:50; score against Prep_02 keys |
| S10 Web UI | TODO | D | | | | |
| S11 T3 tests and fixtures | TODO | C | | | | By 13:20; case tables in Prep_02 |
| S12 README and should-ship | TODO | D | | | | Outline in Prep_03 |
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
| D11 | 10:48 | One Claude session holds all four roles (A–D) and works steps sequentially in plan order | Single-session build | §14 |
| D12 | 11:05 | No `Co-Authored-By` trailers on commits; checkpoint commit + push at every step and every 15 min | User instruction | CLAUDE.md §2 |
| D13 | 11:05 | Plan improvements are proposed to the user first and applied only after a go | User instruction | §15 |
| D14 | open | **Finding:** Identify("Qualified") returns 25 candidates, none is 632707 ("Qualified (Acquired by Salesforce)"), so the strict §7 prior-employer rule leaves Herrick→Qualified as `?`. Proposal to user: a labelled name-prefix fallback against the person's own past entries | Live probe 10:58 | §7 G2 |
| D7 | — | **PC-7 (open, S6 owner):** refusal fallback. The recommendation is to keep "refusal = failed attempt". | Fallback only re-runs cyber/frontier_llm declines on Sonnet 5.5 | §8.3 |

---

## Measurements (T2 and runs)

| Run | Mode | Company | LIVE/CACHED/FIXTURE | Seconds | Crustdata credits | Model tokens (in/out) | Sentences emitted/supported/suppressed | Team rows / ID joins | Issues |
|---|---|---|---|---|---|---|---|---|---|

**Spend so far:**

- **Crustdata (event key, this session):** 3.39 credits: Koah Company Enrich 2, Linear founder search 0.39 (PC-3 confirmed: Karri found), Karri Person Enrich 1. Identify is free.
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

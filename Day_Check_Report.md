# Proofroom day-check report: 31 Oct 2026

**Latest verdict: GO-WITH-CHANGES / model workflow validation pending.** User confirms the switch to the hackathon promo-credit Crustdata account and chooses the currently running AI session (ChatGPT for now) for model work. Anthropic-specific checks are superseded for this workflow, not failed prerequisites. Recorder test remains undone. See the user correction below; earlier results are historical.

## User correction after the rerun

- **Crustdata:** user confirms they switched to the account with hackathon promo credits. Treat the configured account as the user-designated hackathon account. Last measured REST balance: 227.61 credits after 6.39 credits of probes. This is the last observation, not a new balance check; no additional grant amount is inferred.
- **Model workflow:** use whichever AI session the user is currently running; currently ChatGPT. No Anthropic key is required for session-driven work. Checks 0.6, 2.1 and 2.2 for Anthropic model access, SDK schema compilation and effort settings are superseded / not applicable to this chosen mode.
- **Remaining model validation:** extraction, assessment and sentence checking (2.3–2.5) still need to be exercised through the selected session against the real evidence. Measure actual workflow time (2.6); API token cost and cold/warm Anthropic compile measurements do not transfer to session operation. These tests have not been completed merely by changing providers.
- **Integration boundary:** selecting the active chat session does not by itself connect the standalone Proofroom app to a model. Session-driven operation can run here; any automatic app-to-model execution still needs an explicit supported integration and an end-to-end test. Do not promise an automatic domain-to-brief app until that path works.
- **Still open:** recorder test and organizer policy answers. The historical missing-Anthropic-key escalation below no longer governs the user's chosen session workflow.

| Item | Status |
|---|---|
| Phases 1 and 2 | Not run yet (they need the event key and the build window) |
| Crustdata event-key balance | ‹Phase 1› |
| Crustdata MCP account | **personal** (krunalgladiator12@gmail.com top-up). It held 197.61 credits before tonight's probes and **192.56** after. Expires 2026-11-13 18:33 UTC. |
| Anthropic model access | **not checked yet**: `ANTHROPIC_API_KEY` is still unset at the 09:02 re-run (0.6 BLOCKER) |
| Spend so far | Tonight: 5.05 Crustdata credits (personal account; the earlier 00:10 probe cost ≈2.4) · $0 Anthropic |

---

## Phase 0: Environment (run 01:11–01:25 IST)

| # | Check | Result | Evidence |
|---|---|---|---|
| 0.1 | Time and repo state | **PASS** | 01:11 IST, before code start. The repo folder `C:\dev\proofroom` (outside OneDrive) was created and holds **notes only** (CLAUDE.md, PROGRESS.md). No code, and no `git init`: S0 does that after 10:30, so every commit is timestamped after code start. |
| 0.2 | Python | **PASS** | `py -3.12` → 3.12.2 (`…\Programs\Python\Python312`); `python` → 3.14.7 (`C:\Python314`). **The venv uses 3.12.2.** 3.14.7 was also verified as a backup. |
| 0.3 | `pip` reaches PyPI | **PASS** | `pip index versions fastapi` → 0.162.0. Every dependency was pre-downloaded to `C:\dev\proofroom-wheelhouse` (39 wheels, 11 MB) and installed **offline** into throwaway 3.12 and 3.14 venvs. The S0 verify command prints `ok` on both. |
| 0.4 | Git and GitHub | **PASS (fallback known)** | git 2.51.0; `user.name`/`user.email` set; Git Credential Manager 2.6.1 holds a github.com account; `git ls-remote https://github.com/git/git` works. `gh` is **not installed**. It isn't needed: create the GitHub repo in the browser and push over HTTPS with GCM. |
| 0.5 | Screen recorder | **PENDING (user)** | Installed: OBS Studio, Snipping Tool, Game Bar, Clipchamp. Microphones: Realtek Microphone Array, Camo. Displays: 1920×1080 (primary), 2560×1440. **You still need to make a 10-second 1080p test capture with the microphone.** |
| 0.6 | Anthropic model access | **BLOCKED → morning** | `ANTHROPIC_API_KEY` is unset in the process, user and machine scopes. The `ant` CLI is not installed, so there's no profile fallback. Run the one-line check below after setting the key. |
| 0.7 | Crustdata MCP account | **PASS (info)** | `crustdata_credits_check_v2` shows the personal top-up: 200 granted on 2026-10-30, expiring 2026-11-13. Event-key checks must use REST/curl in Phase 1. |
| 0.8 | Dev pages live | **PASS** | All six return HTTP 200 with a browser user agent: Koah post (0.09 s), Theory post, both Linear posts, both Attio posts. |
| 0.9 | Doc changes | **PASS** | The changelog's newest entries are "October 2026" (month-level dates only; none dated 30–31 Oct). They add NAICS/SIC on company search, a `geo_polygon` filter, opt-in `research_profiles` (+2 credits, 403 without a grant; don't request it), and a free Usage API (`GET /account/usage/*`). **No breaking change to any endpoint Proofroom uses; still `x-api-version: 2025-11-01`.** |

### Phase 0 re-run (09:02–09:05 IST)

**Verdict: GO-WITH-CHANGES, with one open BLOCKER (0.6).** Nothing changed since 01:25. Spend: 0 credits, $0.

| # | Check | Result | Evidence |
|---|---|---|---|
| 0.1 | Time and repo state | **PASS** | 09:02:45 +05:30. `C:\dev\proofroom` still holds only CLAUDE.md (12,681 B) and PROGRESS.md (10,323 B). No code, no `.git`. |
| 0.2 | Python | **PASS** | `py -3.12` → 3.12.2; `python` → 3.14.7. The venv uses 3.12.2. |
| 0.3 | `pip` reaches PyPI | **PASS** | `pip index versions fastapi` → 0.162.0 (unchanged). `C:\dev\proofroom-wheelhouse\requirements.lock.txt` is present. |
| 0.4 | Git and GitHub | **PASS (fallback known)** | git 2.51.0.windows.2; `git ls-remote https://github.com/git/git HEAD` works. `gh` is still not installed (fallback: browser + GCM). |
| 0.5 | Screen recorder | **PENDING (user)** | Still needs your confirmation of a 10 s 1080p OBS capture with the Realtek mic. |
| 0.6 | Anthropic model access | **BLOCKED (BLOCKER)** | `ANTHROPIC_API_KEY` is still unset in the process and user scopes. Set it, then run the 0.6 one-liner below. It must print `claude-sonnet-5-5`. |
| 0.7 | Crustdata MCP account | **PASS (info)** | Personal account: 192.56 credits (top-up, 200 granted 2026-10-30, expires 2026-11-13 18:33 UTC). No spend since 01:20. `CRUSTDATA_API_KEY` is not set yet (expected before 10:00). |
| 0.8 | Dev pages live | **PASS** | All six return 200: Koah 0.44 s, Theory 0.61 s, Linear building-our-way 0.79 s, Linear sharing-growth 1.73 s, Attio Series B 0.73 s, Attio dev platform 0.50 s. |
| 0.9 | Doc changes | **PASS** | Changelog `lastModified` is 2026-10-16T21:39Z. It has the same four "October 2026" entries and no new ones. No change from v2 §20. |

### Extra checks run tonight (beyond the runbook)

| # | Check | Result | Evidence |
|---|---|---|---|
| X1 | Model settings (§8.3) vs the current Claude API reference | **PASS with changes** | `claude-sonnet-5-5` at $2 / $10 per MTok ✔. Adaptive thinking is the default ✔; `disabled` returns 400; `between_tools` means no extended thinking ✔ (never send it). Effort `low`/`medium`/`high` in `output_config` ✔; the default is `high`, so set it explicitly ✔. Prefill, forced `tool_choice` and citations with structured outputs each return 400 ✔. Blocks are read by type ✔. See PC-1 for the SDK changes. |
| X2 | Installed SDK surface | **PASS** | anthropic **2.3.0**: `messages.parse` accepts `output_format`, `output_config`, `thinking`, `timeout`, `system` and `max_tokens`, and has **no** `temperature`. The result has `parsed_output`, `stop_reason`, `stop_details` and `usage`. The effort literal includes low through max. `beta.messages.parse` exists. `max_retries` is supported. |
| X3 | P2/P3 graph shapes (personal MCP) | **PASS, with findings** | Company Enrich `basic_info, funding, news` on 633791 and 664000 cost 4 credits. Person Search S1 cost 0.92, and a name check 0.13. Values are in `prep/Prep_02_Answer_Keys_and_Test_Groups.md`. Findings → PC-2 to PC-6. |

---

## Blockers

- **None hard.**
- **Morning actions:** set `ANTHROPIC_API_KEY` and run 0.6; make the 0.5 recorder test.
- Make sure the Anthropic key has credit: the plan budgets about US$15.

**0.6 one-liner** (PowerShell, after `$env:ANTHROPIC_API_KEY = "…"`; it costs nothing and prints only the model id):

```powershell
(curl.exe -s https://api.anthropic.com/v1/models/claude-sonnet-5-5 -H "x-api-key: $env:ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" | ConvertFrom-Json).id
```

---

## Plan changes to apply before coding (cite v2 sections)

- **PC-1 (§8.1, §8.3, CLAUDE.md S0/S6): the SDK is `anthropic` 2.3.0, not 0.x/1.x.**
  - It sends API version `2026-10-21` (no sampling parameters; nothing in the plan breaks).
  - It is built on **`httpx2`**. Never hand `httpx` objects (Timeout, Client, transports) to the Anthropic client; pass float timeouts.
  - The Crustdata adapter may keep plain `httpx` 0.28.1, which is installed separately and pinned.
  - The API key now goes in `Authorization: Bearer`, so never log request headers.
  - Write messages as dicts; calling `MessageParam(...)` raises `TypeError`.
  - Pin exactly the lock file: `C:\dev\proofroom-wheelhouse\requirements.lock.txt`.
- **PC-2 (§7 G4, §5.3): Crustdata's `total_investment_usd` includes secondary sales.**
  - Linear: 233.2M = $99M tender + 82 + 35 + 13 + 4.2.
  - `last_round_*` can be a `secondary_market` entry.
  - G4 must type-match milestones (round ↔ `round_type`), and must never present the total as capital when any milestone is `secondary_market`.
  - The §5.3 "indexed total minus the announced round" question needs a third precondition: no `secondary_market` milestone, or subtract only primary milestones.
- **PC-3 (§6.2 S1, §20.2): the S1 title filter misses "Cofounder".**
  - Karri Saarinen (Linear CEO) has the title "CEO, Cofounder", and `(.)` "founder" does not match it.
  - Use `{"op": "or", "conditions": [title (.) "founder", title (.) "cofounder"]}` inside the AND, and union the result with `people.founders`.
  - Keep `fields` free of `experience.*`. Requesting those fields billed 0.23 per result tonight instead of 0.13.
- **PC-4 (§20.2 item 2, S2/S5): `news[]` is noisy and its dates are unreliable.**
  - Linear has 70 items, including namesakes ("Village Creek Linear Walking Trail" funding, "Index", Mercury).
  - Attio has a `1970-01-01` sentinel date and a 2026-dated page about a 2025 round.
  - So the ±7-day `milestones` proximity rule is **mandatory**, not a preference. Treat `1970-01-01` as unknown.
  - Company-owned posts (linear.app/now) are absent from `news[]`. Expect `independent_report` bases in Mode A.
- **PC-5 (§5.4 gate): record amounts can be FX-derived and non-round.** Attio's Series B is 52,020,932. Compare at the precision the sentence states ("$52M" matches).
- **PC-6 (§5.4, G4 investor match): real alias cases.** "GV" vs "Google Ventures" (Attio) and "01A" vs "01 Advisors" (Linear). Match only when a source states the alias; otherwise show "not matched (not a conflict)".
- **PC-7 (§8.3, optional, decide at S6).** Server-side refusal fallback (`fallbacks: "default"`) is recommended by the API reference, but for Sonnet 5.5 it only re-runs `cyber` and `frontier_llm` declines. **Recommendation:** keep the plan's "refusal = failed attempt" rule unless T1/T2 shows a refusal.

## Organizer answers (Q1–Q6)

- Not asked yet. Ask Q1, Q2, Q5 and Q6 at 09:30 and Q3, Q4 at 10:00 (plan v2 §16).

---

## Latest rerun: 31 October 2026, 10:12–10:15 IST

**Verdict: ESCALATE / incomplete.** Required Anthropic access is unverified because `ANTHROPIC_API_KEY` is absent from process, user and machine environments, including the actual user session outside the sandbox. No generation was attempted. Phase 2 has not passed.

The initial sandbox checks could not see the Windows user's Crustdata key and blocked outbound sockets. Repeating read-only checks outside the sandbox resolved those environment limitations. No keys were printed or saved. REST response bodies and response headers are saved outside the repository at `C:\Users\YASH\AppData\Local\Temp\proofroom-day-check-20261031`. Probe source is at `../.day-check/probe.ps1`; it reads the key at runtime.

**Accounts/spend:** connected MCP balance 200 credits, expires 2026-11-13 18:29:15 UTC; personal-account pattern, different from the historical 192.56 balance. Configured REST key: **234.00 before → 227.61 after**, **6.39 credits spent**; $0 Anthropic. REST grants: 200 credits granted today, expires 14 Nov; 34 credits granted today, expires 31 Oct 2027. This does not establish the expected event grant or event-account identity. Do not equate credit counts with dollar amounts.

| # | Check | Result | Current evidence |
|---|---|---|---|
| 0.1 | Time/repo | PASS | 10:12–10:15 IST, before 10:30. `C:\dev\proofroom` still has only CLAUDE.md and PROGRESS.md. The planning repo under OneDrive has a clean Git status before this report edit. No product code was created. |
| 0.2 | Python | PASS | Explicit Python312 executable reports 3.12.2; default Python reports 3.14.7. `py` is unavailable in the sandbox PATH; use the explicit 3.12 executable. |
| 0.3 | PyPI | PASS | Outside sandbox, `python -m pip index versions fastapi --retries 0` succeeds; latest listed 0.162.0. Offline requirements lock exists. |
| 0.4 | Git/GitHub | PASS with limitation | Git 2.51.0.windows.2; name/email configured; public `git ls-remote` succeeds. `gh` absent. Existing browser/GCM fallback from prior report remains; authenticated push was not tested. Git status succeeds with a command-local safe.directory override; no global config changed. |
| 0.5 | Recorder | BLOCKED | User confirms the 10-second 1080p microphone recording has **not** been done. Functional recording/audio cannot be marked PASS from installation evidence. |
| 0.6 | Anthropic model | BLOCKED — BLOCKER | Key absent in all three environment scopes in actual user session. Model access, billing and SDK/API compatibility are not verified by this run. |
| 0.7 | MCP account | PASS / informational | Free balance call: 200 credits, expiry 13 Nov 2026. Event REST checks used the configured user key, never the MCP account. |
| 0.8 | Six source pages | PASS | HTTP 200: Koah 0.22s, Theory 0.43s, Linear building 0.72s, Linear tender 0.61s, Attio Series B 0.15s, Attio platform 0.16s. |
| 0.9 | Changelog | PASS | Public changelog still shows the four October additions: NAICS/SIC, geo_polygon, research_profiles, Usage API; no breaking change identified for these calls. Month-level dates cannot establish an exact 30–31 Oct publication date. Source: https://docs.crustdata.com/openapi-specs/2025-11-01/changelog |
| 1.1 | Entitlements/rates | PASS | All six enabled: identify 30 rpm; company enrich 15; person search 30; person enrich 15; web search/fetch 10 each. Account token_limit_rpm is null; this does not prove absence of other shared limits. |
| 1.2 | Event grant | BLOCKED / balance read | `/account/credits` HTTP 200; 234 starting credits, grant details above. The API response does not label this an event account. Expected event allocation remains unconfirmed. |
| 1.3 | Field permissions | PASS | Both scoped endpoint queries HTTP 200. Company funding, people, news are not disabled; actual company response includes all three. Person assessment and profile urn_url are disabled. |
| 1.4 | Identify | PASS | HTTP 200, 1.04s, 0 credits. Koah 3718859, Linear 633791, Attio 664000; confidence 1.0 and exact primary domains. |
| 1.5 | Company shape | PASS | HTTP 200, 1.86s, 2 credits. Response wrapper `[].matches[].company_data`; milestones: series_a 20,500,000 / 2026-02-24 / Theory Ventures; seed 5,000,000 / 2025-09-07 / Forerunner; pre_seed amount null / 2024-01-01. Three founders, 20 news entries. Founder employment uses employer_company_id string arrays and employee_* names. |
| 1.6 | Founder search | PASS | HTTP 200, 1.01s, 0.39 credits. Mike Choi, Herrick Fang, Nic Baird with profile URLs. Applied PC-3 founder OR cofounder filter; fields exclude experience. |
| 1.7 | Person shape | PASS | HTTP 200, 1.05s, 1 credit. `[].matches[].person_data.experience.employment_details.current/past`; uses name, title, crustdata_company_id, start_date, end_date. Past company IDs include 820009, 632707, 780882, 632082. Confirms different employment schemas. |
| 1.8 | News search | PASS | HTTP 200, 5.64s, 1 credit. Seven results, including PR Newswire Series A and SiliconANGLE coverage. Results have source/title/url/snippet/position, no explicit publication-date field. Several URLs are Google redirect links; validate final fetched source identity. |
| 1.9 | REST fetch | PASS with finding | HTTP 200, 5.54s, 2 credits; both pages success=true. Raw HTML: Koah 121,934 chars; Linear 479,290 chars. Literal `For agents` absent in both responses. Keep HTML extraction; MCP's stripped-text behavior is not REST behavior. |
| 1.10 | Headers | PASS | Both company/fetch have X-Credits-Used=2 and X-RateLimit-Limit/Remaining/Reset. Company: 15/14/60; fetch: 10/9/60. Reset is the raw value 60; do not assume an epoch timestamp. |
| 1.11 | Errors | PASS | Both identifiers → HTTP 400, 0 credits, nested error object: type=invalid_request, message=Only one identifier type can be provided, metadata=[]. Invalid key → HTTP 401, flat message=Invalid API key in request. Bodies saved. |
| 1.12 | Organizer answers | BLOCKED / partial technical evidence | No organizer answers supplied. User requested independent checking. Q3 actual limits and Q4 permissions are measured above; whether limits are shared/raised remains unknown. Q1/Q2/Q5/Q6 are organizer policy decisions, not inferable from API results. No messages were sent to organizers. |
| 2.1 | Schema cold/warm compile | BLOCKED | Missing Anthropic key; no live schema calls. |
| 2.2 | Model settings | BLOCKED | Missing Anthropic key; no acceptance/stop_reason results. |
| 2.3 | Real-text extraction | BLOCKED | Missing Anthropic key. |
| 2.4 | Assessment effort | BLOCKED | Missing Anthropic key. |
| 2.5 | Sentence checker | BLOCKED | Missing Anthropic key. |
| 2.6 | Timed path | BLOCKED / partial | Measured enrich + fetch = 7.40s. End-to-end estimate cannot be completed without three model calls. |
| 2.7 | Spend | PASS for probes only | 6.39 REST credits by both response-header sum and balance delta; 0 MCP credits, $0 Anthropic this rerun. Full T1 budget remains untested. |

### Current blockers and required plan adjustments

- Make `ANTHROPIC_API_KEY` available to the actual execution session; then run 0.6 and all Phase 2 live checks during the build window. Earlier SDK/model assertions remain historical, not reconfirmed here.
- Confirm the configured REST key's event allocation with the organizers/dashboard; observed balance is 227.61 after probes, not an established event grant.
- Recorder functional test remains incomplete, as confirmed by the user. Organizer policy questions remain unanswered.
- v2 §6.2/§20: keep Company Enrich as the main graph call; normalize the array/matches wrapper and both employment shapes; use founder OR cofounder for fallback search.
- v2 §6.2/§20: retain HTML-to-text extraction for REST fetches and match fetched results by URL. Do not rely on an agent-specific note being present. Validate redirect destinations before source attribution.
- v2 §6.3: handle nested error objects and flat 401 messages; interpret rate-reset semantics explicitly before implementing retries. Retain the 10 rpm web limit and serialized evaluation/cache strategy.
- Previous PC-1 through PC-7 are preserved above; this rerun did not revalidate Anthropic-specific claims or repeat the Linear/Attio paid enrichment probes.

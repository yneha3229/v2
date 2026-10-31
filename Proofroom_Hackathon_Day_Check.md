# Proofroom: Hackathon-Day Pre-Build Check

*A runbook for Claude (Claude Code) on 31 October 2026. It confirms that everything the plan depends on actually works with the **event** setup before the team writes product code.*

---

## Start prompt

Paste this into Claude Code, run from the `C:\Users\YASH\OneDrive\Desktop\YC Hackathon` folder, and fill in the three `‹…›` values.

```text
You are running the Proofroom hackathon-day pre-build check.

Read these two files completely before doing anything:
  1. proofroom/Proofroom_Hackathon_Day_Check.md   (this runbook: follow it exactly)
  2. proofroom/Proofroom_Final_Project_Plan_v2.md (the plan of record, including §20 "Pre-event probe results")

Run PHASE ‹0 | 1 | 2› of the runbook now. Current time (IST): ‹HH:MM›. Team size: ‹1–4›.
The event Crustdata key is in the environment variable CRUSTDATA_API_KEY, and the Anthropic key is in ANTHROPIC_API_KEY. Never print, log, echo or write either key anywhere.

Hard rules:
- If the Crustdata MCP is connected, first check WHICH account it uses (crustdata_credits_check_v2).
  The personal account has about 200 credits expiring 13 Nov. Event-key checks must use the event key
  through the REST API (curl), not the personal MCP account.
- For each check, record PASS / FAIL / BLOCKED with evidence: field paths, values, HTTP status,
  timings, credits. If a check marked BLOCKER fails, stop and tell me immediately.
- Compare every result with v2 §20. Report any difference as a plan change.

When the phase is done, create or append to proofroom/Day_Check_Report.md, using the report template
at the end of the runbook. Then tell me in five lines or fewer: GO / GO-WITH-CHANGES / ESCALATE,
the blockers, and the exact plan changes to apply before coding.
```

---

## When to give this to Claude

| Phase | When | Needs | Duration | What it settles |
|---|---|---|---|---|
| **Phase 0: Environment** | 08:00–09:00, before kickoff, at home or on arrival | Your laptop and the Anthropic key. No event key. | About 15 min | Python, `pip`, Git/GitHub, the recorder, Anthropic model access, whether the packet pages are still live, and which account the Crustdata MCP uses |
| **Phase 1: Event key** | 10:00–10:30, right after the Crustdata walkthrough, once the key and team are in hand | The event Crustdata key in the environment | About 20 min | Entitlements, credits, field permissions, rate limits, error shapes, and whether tonight's response shapes hold on the event key |
| **Phase 2: Model and timing (T1)** | **10:30–10:50**, the first 20 minutes of official build time | Both keys; scratch scripts allowed | About 20 min | Structured-output schemas compile, effort and latency, a timed partial run, and a GO/NO-GO decision |

Send the start prompt three times: with `PHASE 0` at about 08:30, `PHASE 1` at about 10:05, and `PHASE 2` at 10:30. Each run appends to the same report.

If the organizers say that even manual API calls must wait until 10:30, run Phase 1 at 10:30 and Phase 2 right after it. The coding schedule then shifts by about 20 minutes.

**Key handling:** set the keys in the terminal with `$env:CRUSTDATA_API_KEY = "…"` (PowerShell), or in a `.env` file that is git-ignored. Never paste keys into the chat.

---

## What tonight's probe already settled

These were checked at 00:10 IST on 31 Oct with the **personal** Crustdata account. Phase 1 re-confirms them on the event key. Full details are in v2 §20.

| Question | Tonight's answer |
|---|---|
| Do the needed endpoints exist and are they enabled? | Yes on the personal account: identify, company enrich, person search, person enrich, web search, web fetch. Live and batch endpoints are disabled. |
| Does Identify resolve the development domains? | Koah → 3718859, Linear → 633791, Attio → 664000, each with confidence 1.0 and an exact `primary_domain` |
| Funding shape | `funding.milestones[]`, one entry per round with `round_type`, `date`, `amount_usd`, `lead_investors` and `investors_detailed` (Crunchbase links). There is **no `funding_rounds` key**. |
| Founders | `people.founders[]` returns full profiles, with `experience` and `updated_at` |
| Founder employment key names | `employer_name`, `employer_company_id` (a list of strings), `employee_title`, `employee_start_date`, `employee_end_date`. These differ from Person Enrich's documented keys. |
| News | `news[]` entries carry `article_url`, `article_title`, `article_publish_date`, `article_publisher_name` and `source` |
| Person Search with a `(.)` "founder" title filter | Found all 3 Koah co-founders, with profile URLs, for 0.39 credits |
| Company-level `updated_at` / `indexed_at` | `null` for Koah |

---

## Phase 0: Environment (no event key, no code)

| # | Check | How | Pass | Severity |
|---|---|---|---|---|
| 0.1 | Time and repository state | `Get-Date`. Confirm the repository folder is outside OneDrive (for example `C:\dev\proofroom`) and contains no product code. | Before 10:30, the folder is empty or holds only README notes | BLOCKER if code exists before 10:30 |
| 0.2 | Python | `py -3.12 --version` and `python --version` | 3.12.x or 3.14.x present. Record which one the venv will use. | BLOCKER if neither |
| 0.3 | `pip` can reach PyPI | `py -3.12 -m pip index versions fastapi` (read-only) | Versions are listed | High |
| 0.4 | Git and GitHub | `git --version`; `gh auth status` if `gh` is installed | Authenticated, or a fallback is known | High |
| 0.5 | Screen recorder | Ask the user to confirm a 10-second 1080p test capture with the microphone | The user confirms | High |
| 0.6 | Anthropic model access | `curl.exe -s https://api.anthropic.com/v1/models/claude-sonnet-5-5 -H "x-api-key: $env:ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01"` (no generation, so free) | Returns the model object | BLOCKER |
| 0.7 | Which account the Crustdata MCP uses | MCP `crustdata_credits_check_v2` | Record the balance and expiry. 200 credits expiring 13 Nov means the personal account. | Info |
| 0.8 | Development pages still live | `curl.exe -s -o NUL -w "%{http_code}"` on the 6 URLs in v2 §19 | All return 200 | Medium. Note any that fail. |
| 0.9 | Doc changes since 30 Oct | Fetch `https://docs.crustdata.com/openapi-specs/2025-11-01/changelog` and read entries dated 30–31 Oct | No breaking change to the endpoints used | Medium |

---

## Phase 1: Event key (manual calls only)

Every call below uses `-H "authorization: Bearer $env:CRUSTDATA_API_KEY" -H "x-api-version: 2025-11-01"` and adds `-H "content-type: application/json"` on POSTs. Use `curl.exe -s -D headers.txt` so the response headers are captured. Save all bodies to a scratch folder outside the repository.

| # | Check | Call | Pass | Severity |
|---|---|---|---|---|
| 1.1 | Endpoint entitlements and rate limits | `GET /account/endpoints` | `/company/identify`, `/company/enrich`, `/person/search`, `/person/enrich`, `/web/search/live` and `/web/enrich/live` are all `enabled`. Record `effective_rate_limit_rpm` for each. | **BLOCKER** if identify, enrich or person search is disabled → escalate to the Crustdata staff at the venue |
| 1.2 | Balance | `GET /account/credits` | Record `account.credits`. It should reflect the event grant ($1,500 per team per the brief). | High |
| 1.3 | Field permissions | `GET /account/endpoints?path=/company/enrich` (and `/person/search`) | `funding`, `people` and `news` are not in `fields.disabled` | **BLOCKER** for `funding` or `people` |
| 1.4 | Identify (free) | `POST /company/identify` with `{"domains":["koahlabs.com","linear.app","attio.com"]}` | The IDs match tonight's (3718859, 633791, 664000) | High |
| 1.5 | Company record shape (2 credits) | `POST /company/enrich` with `{"crustdata_company_ids":[3718859],"fields":["basic_info","funding","people","news"]}` | `funding.milestones[]` has 3 rounds (series_a $20.5M on 2026-02-24, led by Theory Ventures; seed $5M on 2025-09-07, led by Forerunner; pre_seed). `people.founders` has 3 entries with `employer_company_id`. `news[]` has `article_url`. Record any key differences. | **BLOCKER** if `milestones` and `founders` are both missing |
| 1.6 | Founder search (≈0.4 credits) | `POST /person/search`, using the S1 filter from v2 §6.2 (company_id 3718859 AND current.title `(.)` "founder"), fields `crustdata_person_id`, `basic_profile.name`, `basic_profile.current_title`, `social_handles.professional_network_identifier.profile_url`, limit 10 | 3 profiles, with `x-credits-used` ≈ 0.39 | Medium (fallback path) |
| 1.7 | Person Enrich key names (1 credit) | `POST /person/enrich` with `{"professional_network_profile_urls":["https://www.linkedin.com/in/herrickfang"],"fields":["basic_profile","experience","social_handles"]}` | Record the employment key names and whether past entries carry company IDs. Compare with 1.5. | Medium. It decides whether Person Enrich is needed at all. |
| 1.8 | News search (1 credit) | `POST /web/search/live` with `{"query":"Koah raises Series A","sources":["news"],"start_date":1704067200}` | Results include Koah's funding coverage. Note whether any result has a date field. | Medium |
| 1.9 | Fetch format and content negotiation (2 credits) | `POST /web/enrich/live` with `{"urls":["https://www.koahlabs.com/blog/theory-ventures-partnership","https://linear.app/now/sharing-growth-with-the-people-building-linear"]}` | Is `content` raw HTML or stripped text? Is Linear's "For agents" note present? How long did it take? | Medium. It decides the HTML-to-text step. |
| 1.10 | Rate-limit and credit headers | Read `headers.txt` from 1.5 and 1.9 | `x-credits-used` is present; `x-ratelimit-limit`, `-remaining` and `-reset` are present (record which ones) | Medium |
| 1.11 | Error shapes (free) | (a) `POST /company/identify` with both `domains` and `names` → expect 400. (b) Any call with the header `authorization: Bearer invalid` → expect 401. | Save both bodies. Is `error` an object or a string? Is there a flat `message`? These shapes drive the §6.3 normalizer. | Medium |
| 1.12 | Questions answered at 09:30 and 10:00 | Ask the user for the answers to v2 §16 questions Q1–Q6 | Answers recorded | High (Q1, Q2 and Q6 change the demo plan) |

---

## Phase 2: Model and timing (T1, from 10:30; scratch scripts allowed)

Create a venv with an explicit interpreter, install the v2 §8.1 libraries, and pin them in `requirements.txt` inside the repository. Probe scripts go in a scratch folder, not the repository.

| # | Check | How | Pass | Severity |
|---|---|---|---|---|
| 2.1 | Schema compile, cold and warm | For each of the three v2 §8.3 schemas, make one `client.messages.parse()` call on `claude-sonnet-5-5` with a tiny input. Record the cold time, then repeat to record the warm time. | All three succeed. Cold time is recorded (it can be long; the limit is 180 s). Warm call 1 ≤10 s. | **BLOCKER** if a schema is rejected as too complex: flatten it and retry |
| 2.2 | Settings accepted | The same calls with adaptive thinking (no `thinking` field), `output_config.effort` (`low`, then `medium`), and the system prompt ending "Think the problem through before you answer." No sampling parameters. | No 400 errors. `stop_reason` is `end_turn`. The parser reads blocks by type. | **BLOCKER** |
| 2.3 | Call 1 on real text | Extract claims from Koah's company post plus Theory's post (text from 1.9 or pasted) | Valid JSON. Claims include the $20.5M Series A, the Theory lead, the Forerunner seed lead, and the three founders who "overlapped at" Affirm, Supermove and Qualified. Time ≤15 s. | High |
| 2.4 | Call 2 effort choice | Run assessment on the claims from 2.3, with the evidence from 1.5 and 1.9, at `medium`, then at `high` | Record time and correctness for each. The expected outcome is in v2 §20.3. Choose the fastest setting that is correct. | High |
| 2.5 | Call 3 | Check the sentences produced by 2.4 | ≤10 s. The collective-employer sentence must not be marked entailed for each individual founder. | Medium |
| 2.6 | Timed path estimate | Add up: enrich time (1.5) + fetch time (1.9) + 2.3 + 2.4 + 2.5 | Total ≤75 s. If it's over, apply the v2 §15 cuts and record which ones. | High |
| 2.7 | Spend | Total the credits (`x-credits-used`) and Anthropic `usage` | ≤15 credits and ≤$1 | Info |

---

## Decisions this check can force

| Result | Plan change |
|---|---|
| 1.1 or 1.3 fails | Escalate at once to the Crustdata staff. Do not start a fallback product. |
| 1.5 matches tonight's shape | Use Company Enrich (`funding`, `people`, `news`) as the main graph call. Person Search becomes the fallback and Person Enrich becomes optional (v2 §20). |
| 1.5 has no `news` | S2 uses Web Search (v2 §6.2) |
| 1.5 has no `founders` | S1 uses Person Search (1.6) followed by Person Enrich |
| 1.7 keys differ from 1.5 | Write one employment normalizer that accepts both key sets |
| 1.9 returns stripped text, not HTML | Skip BeautifulSoup for fetched pages, but still read the page dates from the text |
| Web endpoints are below 10/min, or shared | Keep the development cache on and serialize evaluation runs |
| 2.1 cold compile over 60 s | Run the warm-up at server start and again before recording and the finals |
| 2.6 over 75 s | Cut to 4 claims → 2 people → skip stage-4 search → fewer fetched pages |

---

## Report template (`proofroom/Day_Check_Report.md`)

```markdown
# Proofroom day-check report: 31 Oct 2026
Verdict: GO | GO-WITH-CHANGES | ESCALATE      Updated: HH:MM IST
Accounts: Crustdata event key balance ‹…› · MCP account ‹personal/event› · Anthropic model access ‹ok›
Spend so far: ‹x› Crustdata credits · $‹y› Anthropic

| # | Check | Result | Evidence (paths, values, status, timing, credits) |
|---|---|---|---|

## Blockers
- …

## Plan changes to apply before coding (cite v2 sections)
- …

## Organizer answers (Q1–Q6)
- …
```

---

## Is this check necessary before coding?

Yes, for the parts the code is built on. Tonight's probe found that the real response shapes differ from the documentation:

- the funding data is under `milestones`, not `funding_rounds`;
- founder employment uses `employer_*` key names;
- the company-level refresh time is null.

Code written from the docs alone would have parsed the wrong fields.

Phase 1 now mainly confirms that the **event key** behaves like the personal account. Phase 2 confirms the model settings and the timing. Together they take about 40 minutes, 20 of them inside the build window. That is cheap insurance for a 5-hour build.

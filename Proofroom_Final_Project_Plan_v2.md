# Proofroom: Final Project Plan v2

*The final execution plan. It merges `Proofroom_Final_Project_Plan_v1.md` with Gemini's "Adversarial Audit of Proofroom Plan", after checking each audit claim against the sources.*

**Prepared:** 30 October 2026, late evening, IST
**Event:** ContextCon IIT Bombay, The Agentic Services Hackathon (Techfest 2026-27), 31 October 2026
**Status:** Final plan. Planning only: no product code has been written, and no authenticated Crustdata or Anthropic call has been made. Numbers marked **[T]** are targets, not measurements.
**How the audit was checked (30 Oct 2026):** every disputed claim was rechecked against:

- the official brief PDF;
- Crustdata's documentation, including the API-reference pages Gemini cited;
- Anthropic's Sonnet 5.5 prompting guide and its structured-outputs page;
- the raw HTML of all six development-packet pages;
- the Linear pages a second time, requested the way an AI agent requests them.

Gemini was right on most product and engineering points. It was wrong on some facts. So was v1. §17 records each verdict.
**Use:** Run the event from this file. v1 and all earlier plans are history.
**Update, 31 Oct 00:10 IST:** live Crustdata probes resolved several open questions and simplify the build. **§20 overrides earlier sections wherever they differ.** The hackathon-day check is in `Proofroom_Hackathon_Day_Check.md`.

---

## 0. What changed from v1

| # | Change | Why | Where |
|---|---|---|---|
| 1 | **A bare company domain is now a complete request.** Proofroom finds the funding announcement itself (Crustdata Web Search and Fetch) and finds the founders by company ID (Crustdata Person Search). Documents and profile URLs become optional. | Autonomy is what the End-to-End criterion and the live finals reward. A judge on stage will name a company, not hand over LinkedIn URLs. | §4.2, §6.2 |
| 2 | **The graph adds information on every run, including clean ones.** Each run produces a per-founder team table built from ID joins, splits collective claims into per-person rows, and cross-checks the financing and investors against Crustdata's record. | A brief that only restates a clean announcement doesn't show why the graph was needed. | §7 |
| 3 | **The build is smaller.** No SQLite version engine and no add/remove revision in must-ship. Each run becomes an immutable folder holding `case.json`, `brief.md` and a manifest. A re-run comparison drops to should-ship. | Revision appears in neither the video nor the stage demo, and cutting it saves about 2.5 team-hours. | §8.4, §15 |
| 4 | **Twelve fixtures become four composite test groups.** | The same coverage with less boilerplate. | §10.2 |
| 5 | **The model settings now follow Anthropic's Sonnet 5.5 guidance for JSON reasoning tasks.** That means adaptive thinking, the line "Think the problem through before you answer.", and no `between_tools`. Responses are read by block type. A `max_tokens` stop counts as a failure. A warm-up command runs at startup. | Verified against Anthropic's Sonnet 5.5 prompting guide. | §8.3 |
| 6 | **A polymorphic Crustdata error parser.** | The docs show three error shapes (§6.3). | §6.3 |
| 7 | **New timing rules.** No new retrieval after 55 s. No model repair call. `human_mode` only for pages that yield under 200 words. One idle minute on the web endpoints before any recorded or stage run. Target 75 s median, hard stop 110 s. | One fetch retry or repair breaks a 70-second target. | §8.2 |
| 8 | **The grounding gate is split.** Code checks money amounts, percentages, years, full dates and evidence IDs. The model checks names, titles, aliases and entailment. | A strict string gate suppresses valid sentences ("GV" vs "Google Ventures"). | §5.4 |
| 9 | **Development-packet facts are corrected in both directions.** Changes: the Koah byline and its "backed at inception" line; "overlapped at" instead of "worked together"; the Linear agent note, which is served only to AI agents; and the Attio update dates and relative dates. | Never tune prompts against a wrong answer key. | §10.1 |
| 10 | **A result-first video with a labeled ×4 time compression, and a "Load demo case (no keys)" button in the web UI.** | Judges should spend the 2 minutes looking at results. Judges who have no keys can still run the app. | §8.5, §11 |

---

## 1. Can Proofroom win?

No plan can guarantee a win in advance. The other teams, the judges' tastes and how the day goes are all unknown. What *can* be checked is fit against the brief and the risks.

### 1.1 Fit against the brief

| Factor | Evidence | Assessment |
|---|---|---|
| Theme | The brief's Investing theme names "analyzing startups, parsing data rooms" (p. 2) | Direct fit |
| Mandatory Crustdata integration | Uses 6 of the brief's listed endpoints: Company Identify, Company Enrich, Person Search, Person Enrich, Web Search, Web Fetch. Every brief is anchored on canonical IDs. | Strong, **if** the G1–G4 decisions visibly change the output (§7) |
| End-to-End Execution | Domain in → finished, exported brief out, with no human steps | Strong if Mode A (domain-only) passes T2 by 12:50 |
| Data Integrity & Verification | Claim-level citations to an exact passage or JSON path, ID joins, origin and four-clock rules, a grounding gate | Proofroom's strongest criterion. Most 5-hour entries will be summaries with links. |
| Robustness & Edge Cases | Error normalizer, four composite fault-test groups, and real-world mess: content-negotiated pages, update dates, relative dates, secondary sales | Adequate to strong |
| Demo Clarity | Result-first storyboard, plain labels, progressive UI | Depends entirely on rehearsal |
| Sponsor appeal | Shows Crustdata working as an identity graph (person → employer ID joins, investor resolution), not as a lookup table | High |

### 1.2 What decides the outcome

**Win conditions** (all are needed):

1. Mode A works end to end and passes T2 by 12:50.
2. Every run shows at least one fact that came from the graph and that a search-and-summarize agent would not produce. Examples: an ID-joined team table, a collective claim split into per-founder rows, or an investor and round cross-check.
3. The median run is ≤75 s, and the UI shows results progressively, so the live demo never sits silent.
4. The video is honest and clear, with one obvious "aha" moment inside two minutes.

**Most likely ways to lose:**

| Risk | Mitigation |
|---|---|
| The vertical slice is unfinished (the most common hackathon failure) | Build CLI-first, with the trigger "no verified export by 11:35" |
| The graph has thin coverage of the unseen company | Honest narrowing; a selection rule that prefers recently funded startups |
| The live run fails on stage (rate limit or network) | An idle minute before the run, a phone hotspot, and the recorded run as fallback |
| Judges prefer agents that take actions | Pitch the finished work: Proofroom does the associate's research, checking and writing end to end |
| The demo is full of jargon | Plain labels such as "Supported" and "company statement only" |

### 1.3 Verdict

**Proofroom has a realistic path to the podium, but it is not a favourite by default.**

- It fits the theme, the sponsor and all four criteria.
- Its verification core is hard to copy in five hours.
- After this revision, it can start from a bare domain, which is what a live stage demo needs.

This is a judgement, not a measurement:

- **If the must-ship list works by 14:00:** it is likely a finalist.
- **If it also delivers a clean demo and a stable live run:** the podium is plausible.
- **If it is unfinished:** it will not place, however good this plan is.

Rehearse with this in mind. Execution, not design, now decides the result.

**Preconditions to confirm tonight:** every team member is eligible (3rd- or 4th-year BTech, dual-degree, or MTech at IIT Bombay), and the team is registered on the official YC event platform (brief p. 3 and rule 1).

---

## 2. Plan at a glance

| | |
|---|---|
| **Pitch** | Type a startup's domain. Proofroom finds the funding announcement and the founders, checks every Team & Financing claim against Crustdata's identity graph and the original source, and returns a brief an investor can paste into a memo. Every sentence is cited, and every limit is stated. |
| **User** | An associate at a seed-to-Series-B fund preparing a partner's founder meeting. Demand is a hypothesis. |
| **Input** | Company domain (required). Optional: 1–3 documents (paste or URL), up to 3 people (names and/or profile URLs), a meeting date, a focus note. |
| **Output** | Case page plus `brief.md` and `case.json`, containing: source-backed sentences with status and basis; a team table from the graph; a financing table; 0–3 questions; a not-checked list; limitations; an evidence list; run statistics. |
| **The graph's job** | G1 subject ID · G2 team matrix (person → employer ID joins) · G3 founder roster · G4 financing and investor cross-check |
| **Model** | `claude-sonnet-5-5`, three structured-output calls, using the settings verified in §8.3 |
| **Run target** | ≤75 s median [T]; hard stop at 110 s |
| **Gates** | T1 10:50 · T2 12:50 · T3 13:20 · **freeze 14:00** · unseen recording 14:30–15:00 · submit by 15:20 · finals prep 15:30–17:30 |

---

## 3. What the brief requires and how each criterion is met

| Brief requirement (PDF) | How the plan meets it |
|---|---|
| Build on Crustdata's canonical people/company identity graph (p. 2; rule 3) | G1–G4 (§7). Tested by graph ablation (§10.5). |
| A functional repository, plus a 2-minute video of a never-seen request reaching finished work (p. 2; rule 5) | §8.5 run modes; §11 protocol |
| Five-hour sprint → video review (Phase 1) → live stage finals (Phase 2) (p. 3) | §11 video; §12 finals |
| `https://api.crustdata.com`, `authorization: Bearer …`, `x-api-version: 2025-11-01` (pp. 2–3) | §6.1 |
| Coding starts strictly at 10:30; ideas and architecture may be prepared earlier (rule 2) | §13.1 lists content and design work only |
| No interaction with external real people (rule 4) | Authorized APIs only. No outreach and no contact lookups. |
| Teams of up to 4, formed at 10:00 (p. 3) | §14 |

| Criterion (p. 3) | Feature | Proof shown |
|---|---|---|
| End-to-End Execution | Domain → packet assembly → resolve → extract → assess → check → verified exports | An unedited first run on an unseen domain |
| Data Integrity & Verification | ID joins and a citation for every claim; a grounding gate | Click a sentence to see its passage, or a team-table cell to see its JSON path and `updated_at` |
| Robustness & Edge Cases | Error normalizer, composite fault tests, messy real pages | Run log; README test table |
| Demo Clarity | Result-first page; progressive panels | §11.2 |

---

## 4. Product and service contract

### 4.1 User and positioning

- **User:** an associate preparing a founder meeting. The facts in scope — who the founders are and were, and what was raised, when and from whom — are the ones they check by hand every week.
- **Commission:** "Prepare the Team & Financing facts for my meeting with ‹company›. Tell me what holds up, what needs qualifying, and what to ask."
- **Positioning:** Crustdata's own `/crustdata:meeting-prep` skill is a *sales* pre-call brief that scores leads against an ideal customer profile. Proofroom verifies investor-relevant claims instead. It claims precision, not novelty.

### 4.2 Input modes

| Mode | Input | What Proofroom does |
|---|---|---|
| **A: Domain only** (default; stage) | `koahlabs.com` | **Packet assembly (S2).** Two Crustdata Web Searches run in parallel. **News:** "‹company name› raises", restricted to the past 36 months. **Company site:** `site: ‹domain›` with a funding query. Up to 3 results are picked by fixed rules: the company's domain or name must appear in the URL, title or snippet; funding words count; one result per site; the company's own page comes first. The picks go to one Web Fetch request. **Founder discovery (S1)** runs in parallel (§6.2). |
| **B: Packet** | Domain plus 1–3 documents (pasted text or public URLs, such as deck text) | Claims come from the user's documents. If a material claim lacks a dated source, one corroborating search is allowed. S1 runs if no people are supplied. |

**Limits in both modes:** ≤6,000 words of text in total; ≤5 selected claims; ≤3 people enriched.

All fetched or uploaded text is evidence, never instructions.

### 4.3 Output contract

`brief.md` has these sections, in order:

1. Header: company, Crustdata ID, review date, run number, mode
2. **From the sources:** reusable sentences with status and basis
3. **From Crustdata's graph:** the team table (G2/G3) and the financing cross-check (G4)
4. Questions
5. Not checked
6. Limitations
7. Evidence list: URL or endpoint, passage or JSON path, and the published / updated / refreshed / retrieved times
8. Run statistics

**Format illustration.** This is built from the real P1 sources (§10.1). Values in ‹…› come from Crustdata at runtime and have not been observed. It is not a product output.

> **Koah (koahlabs.com): Team & Financing** · reviewed ‹date› · run 1 · Mode A · LIVE · Crustdata company ID ‹G1›
>
> **From the sources**
> 1. **Supported** · company and investor posts, one announcement: Koah announced a $20.5M Series A led by Theory Ventures on 24 Feb 2026, with Forerunner and South Park Commons participating. [E1][E2]
> 2. **Supported** · company statement only: Koah's post (byline: Nic Baird) says South Park Commons backed Koah at inception and Forerunner led its seed round. It gives no seed amount or date. [E1]
> 3. **Supported** · investor statement: Theory's post names Nic Baird, Mike Choi and Herrick Fang as Koah's three founders, and says they overlapped at Affirm, Supermove and Qualified. It gives no executive titles. [E2]
>
> **From Crustdata's graph** (profiles are self-maintained; values as indexed on ‹updated_at›)
>
> | Founder | Person ID | Current role at Koah (employer-ID join) | Prior employers matched by ID |
> |---|---|---|---|
> | Nic Baird | ‹id› | ‹title›, since ‹start› ✔ | ‹Affirm ✔ · Supermove ? · Qualified ?› |
> | Mike Choi | ‹id› | ‹…› | ‹…› |
> | Herrick Fang | ‹id› | ‹…› | ‹…› |
>
> **Funding record:** ‹last round type, amount and date› → ‹consistent with the announcement / differs›. Theory Ventures is ‹listed / not listed› among the indexed investors.
>
> **Question:** ‹Only if the indexed total exceeds $20.5M:› What made up the ‹$X› raised before the Series A? Basis: a calculation from Crustdata's indexed total, whose provenance is undocumented.

### 4.4 Done definitions

- **Delivered:**
  - every selected claim has a disposition and rationale;
  - every emitted sentence passed the gate;
  - both files were written, read back and hashed into the manifest.
- **Useful:**
  - the T2 yield is met;
  - the brief contains graph-derived content (the team table or the financing cross-check), **or** states exactly why the graph returned nothing.
  - An all-unresolved brief can be *delivered* but is not *useful*.
- **"No material discrepancies within the checked scope"** may appear only after every selected claim finished a comparable check.

### 4.5 Not in scope

Investment advice, valuation, fraud scoring, legal-entity verification, private revenue or customer checks, headcount, authenticity scoring, OCR or scanned decks, outreach, CRM writes, Watchers, batch jobs, and an MCP server.

Large public companies get a narrowed brief that says it is outside the tool's private-startup focus.

---

## 5. Claims and evidence rules

### 5.1 Claim families and selection

| Family | Examples | What must be aligned |
|---|---|---|
| F1 Identity & source attribution | Which company a source concerns; who led a round | Subject ID, asserting party, origin group |
| F2 Dated roles | "Co-founder & CEO"; "ex-Affirm" | Person ID, employer ID, current vs past, dates and their precision |
| F3 Reported financing | Round amount, type and date; lead; total raised; secondary sale or tender | Event type, amount/currency/magnitude, announced vs closed, lead vs participant |

**Selection:**

- Select up to **5** material atomic claims, in the order of the focus note, then materiality.
- List the rest as Not checked, with a reason.
- Freeze the selection before assessment, and never pad it.

**Status labels** (disposition plus a basis chip, never a percentage):

- **Supported**
- **Supported, corrected** (with the reason: date, definition, attribution, title, entity or scope)
- **Conflicting**
- **Not established**
- **Not checked**

**Basis chips:**

- company statement
- investor statement
- independent report
- Crustdata indexed record
- calculation

### 5.2 Alignment rules

These are kept from v1.

**Subject:**

- A source counts for the subject only with an explicit match basis: the domain, a resolved ID, or specific company-and-person context.
- A publisher's domain normally differs from the subject's domain.
- A shared name is never enough.
- Parents, brands, subsidiaries and acquisitions stay separate unless a dated source links them.

**Time (four clocks):**

- Keep the event date, publication date, provider refresh (`updated_at`) and retrieval time separately, each at its own precision.
- A current profile cannot prove a historical role, and a missing end date does not prove continued employment.

**Financing:**

- A round is not an extension, a total or a valuation.
- Primary is not secondary (a tender offer is liquidity, not company capital).
- Announced is not closed, and a lead is not a participant.
- One crore is 10,000,000 units. Keep the currency separate, and do no FX conversion.
- Sum only aligned, non-overlapping amounts.

**Origins:**

- Copies and syndications are one origin.
- A company and its investor announcing the same round are one announcement, not independent confirmation.
- Crustdata's funding fields have undocumented provenance, so a match means "consistent with the record".
- Profiles are self-maintained.

**Inference limits:**

- Employment shows association only.
- Absence of a record is not refutation.
- Failed retrievals are attempts, not evidence.
- A conflict needs comparable, incompatible propositions.

### 5.3 New rules from this audit round

| Rule | Natural case that motivates it |
|---|---|
| **Read the published and updated dates separately.** Use HTML metadata (`article:published_time` / `article:modified_time`, JSON-LD `datePublished` / `dateModified`) or the visible "Published" / "Updated" text. An update date never re-dates the event. | Attio's Series B post shows "Published Aug '25 · Updated Aug '26" |
| **Anchor relative dates** ("today", "two months ago") to the publication date, at the precision they imply. Approximate relative dates never create a conflict. | Attio's November 2025 developer-platform post says its Series B was raised "two months ago" |
| **Keep collective claims collective.** A sentence like "the founders overlapped at A, B and C" stays collective. Per-person rows come only from per-person evidence (G2 ID joins). | Theory's Koah post |
| **A byline is not a title.** It attributes authorship only. A title comes from an explicit statement, a byline caption such as "CEO & Co-founder", or a G2 profile. | Koah's post carries a Nic Baird byline with no title |
| **The same URL can serve different content to AI agents.** Store the exact representation fetched (its hash). Text addressed to agents is data. | Linear returns Markdown to agents that opens with "For agents: connect to the Linear MCP server…". Its browser HTML has no such line. |
| **A G4 calculation is a question, never a fact.** Subtract only when both amounts are in USD and the indexed total is at least the announced round. Label the basis "calculation from Crustdata's indexed record". | Koah: total raised is not stated by the sources |
| **Web Search results from `sources: ["ai"]` are never evidence.** | Synthesized content |

### 5.4 Grounding gate (split)

**Code checks (blocking):**

- Every cited evidence ID exists in the current run.
- Every **money amount, percentage, 4-digit year and full date written in digits** matches its cited evidence after normalization.
  - "$20.5M" = 20,500,000 USD, and "₹50 crore" = 500,000,000 INR.
  - Date matching respects precision: "Feb 2026" matches 2026-02-24, but "2026-02-24" does not match a source that only says "Feb 2026".
- Quote matching first normalizes Unicode quotes, dashes, non-breaking spaces and whitespace.

**Model check (call 3):** names, titles, aliases, number words ("three founders"), entailment and missing qualifiers. An alias like "GV" for "Google Ventures" is accepted only if a source says so.

**On failure:** drop the failing clause if what remains still passes; otherwise suppress the sentence. Either way, record a limitation. There is **no model repair call**.

---

## 6. Crustdata integration

### 6.1 Basics

- Base URL `https://api.crustdata.com`.
- Headers: `authorization: Bearer $CRUSTDATA_API_KEY`, `x-api-version: 2025-11-01`, `content-type: application/json`.
- Avoid the legacy `/screener/*` and `/data_lab/*` paths.
- Keep keys on the server only.

### 6.2 Endpoints

| Purpose | Call | Request essentials | Fields used | Cost | Default limit |
|---|---|---|---|---|---|
| Preflight | `GET /account/endpoints` | — | Endpoint status, `fields.enabled/disabled`, effective rpm, prices | free | 300/min |
| Balance | `GET /account/credits` | — | `account.credits` | free | 300/min |
| **G1**, plus prior employers and lead investor | `POST /company/identify` | `{"domains": [d]}`, then a second call `{"names": [prior employers…, lead investor]}`. One identifier type per call; ≤25 values. | `matched_on`, `matches[].confidence_score`, `company_data.crustdata_company_id`, `basic_info.{name, primary_domain, all_domains}` | free | 30/min |
| **G3/G4** company record | `POST /company/enrich` | `{"crustdata_company_ids": [id], "fields": ["basic_info", "funding", "people"]}`, plus `"news"` if T1 shows article URLs there | `funding.{total_investment_usd, last_round_amount_usd, last_fundraise_date, last_round_type, investors, funding_rounds}`, `people.founders`, `updated_at` | 2 credits | 15/min |
| **S1** founder discovery | `POST /person/search` | `{"filters": {"op": "and", "conditions": [{"field": "experience.employment_details.current.company_id", "type": "=", "value": id}, {"field": "experience.employment_details.current.title", "type": "(.)", "value": "founder"}]}, "fields": ["crustdata_person_id", "basic_profile", "social_handles"], "limit": 10}`. Use names from the packet with `(.)` when they are known. | `crustdata_person_id`, name, `social_handles.professional_network_identifier.profile_url` | 0.03 + 0.10 per result (filtering on experience). Another +0.10 if experience is returned. **Always send `fields`**: omitting it returns experience and education at 0.23 per result. | 30/min |
| **G2** roles | `POST /person/enrich` | `{"professional_network_profile_urls": [≤3], "fields": ["basic_profile", "experience", "social_handles"]}` | `match_status`, `crustdata_person_id`, `updated_at`, `experience.employment_details.current[]/past[]` | 1 credit per match; redacted profiles are not billed | 15/min |
| **S2** and gap search | `POST /web/search/live` | `{"query": …, "sources": ["news"], "start_date": ‹unix s›}`, and `{"query": …, "sources": ["web"], "site": domain}` | `results[].{url, title, snippet}`, `metadata`; no publication dates and no entity IDs | 1 credit per query | 10/min |
| Passages | `POST /web/enrich/live` | `{"urls": [≤3]}` in one request. `human_mode: true` is used only for a page that yielded under 200 words. | `[{success, url, timestamp (s), title, content (raw HTML)}]`. Failures have null fields. Order is not guaranteed, so match by URL. | 1 credit per page | 10/min |

If T1 shows that Person Search can return past employment **with** company IDs, request `experience` from the search and skip Person Enrich. That costs +0.10 per result and saves one round trip.

### 6.3 Errors and usage

The docs show three error shapes:

- a nested `{"error": {"type", "message", "metadata"}}`, in the endpoint references;
- a string `{"error": "…", "description" | "reason": "…"}`, in the API introduction (`reason` is used by the Person API);
- a flat `{"message": "…"}`, for some 401 responses.

**Normalize every non-2xx response** into `{status, type, message, denied_fields}`:

1. If `error` is an object, read its `type`, `message` and `metadata`.
2. If `error` is a string, that string is the type, and the message is `description` or `reason`.
3. If there is only a top-level `message`, the type is `unauthorized`.
4. If the body is not JSON, the type is `http_<status>` and the message is the first 200 characters of the body.

| Status | Action |
|---|---|
| Identify: 200 with `matches: []`, or 404 | No match. The reference defines a 404 ("No data found") without saying when it fires, so handle both. Never conclude that the company doesn't exist. |
| 400 | Fix the request; no retry |
| 401 | Stop the run (FAILED) |
| 402 | Stop retrieval and deliver a narrowed brief |
| 403 | Optional field denied: drop it and retry once. Core endpoint denied: FAILED-core, and escalate to the organizers. |
| 429 | Wait `x-ratelimit-reset` (or `Retry-After`) plus jitter. At most 3 tries, all within the deadline. |
| 5xx | One retry if the deadline allows |

**Usage:**

- `x-credits-used` reports the exact decimal cost per response. It is absent on 429 and other pre-processing errors; show that case as "unknown".
- The balance deducts each call's fractional cost **rounded up to a whole credit**.

### 6.4 Rate limits and budget

**Rate-limit hygiene:**

- Run one process-wide limiter per endpoint (≤10 calls per rolling minute on each web endpoint).
- Use a development response cache.
- Make one person the designated evaluation runner.
- Before any recorded or stage run, leave the web endpoints idle for **60 s**.
- Keep the cache **off** for the unseen recording and the finals.

**Per run [T]:**

| Call | Count | Credits |
|---|---|---|
| Identify | ≤2 | 0 |
| Company Enrich | 1 | 2 |
| Person Search | 1 | ≤2 after rounding |
| Person Enrich | 1 | ≤3 |
| Web Search | ≤2 | 2 |
| Web Fetch | ≤2 requests, ≤5 pages | ≤5 |
| **Total** | | **≈14 worst case** |

Credits are not the binding constraint; rate limits are.

---

## 7. What the graph decides

| ID | Decision | Method | Shown as |
|---|---|---|---|
| **G1** Subject anchor | Which company everything is about | Identify by domain. Prefer the candidate whose `primary_domain` equals the input domain and has the highest `confidence_score`. Otherwise accept a **unique** candidate whose `all_domains` contains the input. Abstain only if two distinct IDs tie on both checks. | Identity panel: input → candidates → accepted ID and match basis; excluded namesakes |
| **G2** Team matrix | Each person's current role at *this* company and their prior employers | From S1 or supplied URLs, get person IDs. Person Enrich returns employment entries with `crustdata_company_id`. A current entry matching the G1 ID is the role join. Prior employers named in the sources are resolved with `Identify(names)`. Accept a prior-employer join only when **exactly one** candidate ID appears in that person's past entries. Collective claims are split into per-person rows here. | Team table with ✔ for an ID join and ? for no join; each cell opens its JSON path and `updated_at` |
| **G3** Founder roster | Whether the people named by the sources are the people the graph lists | `people.founders`, if T1 shows it is populated, combined with the S1 results | "Listed as founder by Crustdata", or "not listed (not a refutation)" |
| **G4** Financing and investor cross-check | Whether the announced round and lead match Crustdata's record | Compare the typed round with `funding.last_round_*` and `funding_rounds`. Look for the named lead in `funding.investors` (normalized name) and resolve it to an ID with `Identify(names)`. If the indexed total exceeds the announced round (both USD), raise a question with a calculation basis (§5.3). | "Consistent with Crustdata's record (updated ‹date›)", "record differs → question", or "lead found among indexed investors" |

**Materiality test:** a graph decision is material only if turning off the graph endpoints would change a subject mapping, a team row, or a sentence's status or wording. Displaying an ID is not material.

---

## 8. Architecture

### 8.1 Stack and environment

- **Python:** 3.12 or newer. This laptop runs 3.14.7 by default, and `py -3.12` gives 3.12.2. Create the venv with an explicit interpreter and pin `requirements.txt` at 10:30.
- **Libraries:** FastAPI and Uvicorn; a Jinja2 page with about 80 lines of vanilla-JS polling for progressive panels; Pydantic v2; HTTPX (async, explicit timeouts); BeautifulSoup4, removing `script`, `style`, `nav`, `footer` and `svg` before extracting text; the official `anthropic` SDK.
- **Storage:** files only. No database, ORM, React build, queue or agent framework.
- **Location:** keep the repo and `data/` **outside OneDrive** (for example `C:\dev\proofroom`).

### 8.2 Pipeline and time budget

| Stage | Mode A | Mode B | Budget [T] |
|---|---|---|---|
| 1 Packet | Two searches in parallel, choose ≤3 URLs, one fetch request | Fetch the user's URLs (one request) | ≤15 s |
| 2 Resolve (from t = 0, in parallel with stage 1) | Identify → Company Enrich ∥ Person Search → Person Enrich | Same | ≤12 s |
| 3 Extract and select | Call 1 | Call 1 | ≤15 s |
| 4 Gap resolution (no new retrieval after 55 s) | `Identify(names)` for prior employers and the lead investor; free and fast | Same, plus at most one search and one fetch | ≤10 s |
| 5 Assess | Call 2 | Call 2 | ≤22 s |
| 6 Check | Code checks, then call 3 | Same | ≤10 s |
| 7 Publish | Write, read back, hash into the manifest | Same | ≤2 s |

- **Critical path:** about 74 s. The target is a 75 s median [T] and the hard stop is 110 s. Every call's timeout is derived from the time left.
- **Progressive UI:** the page polls once a second. The Identity panel appears when stage 2 finishes (about 6–12 s), the claims when stage 3 finishes, and the brief at publication.

### 8.3 Model calls

The settings below were verified against Anthropic's Sonnet 5.5 prompting guide and its structured-outputs page on 30 Oct 2026.

**Model:** `claude-sonnet-5-5` ($2 / $10 per million input / output tokens).

- If T2 shows reasoning errors in call 2, try `claude-opus-5-5` at `low` effort for call 2 only, then re-time.
- No model changes after the 14:00 freeze.

**Thinking:** adaptive, which is the default.

- **Never send `between_tools`.** On a request without tools, it means the model answers with no thinking at all, and Anthropic reports lower accuracy on JSON reasoning tasks.
- **End every system prompt with "Think the problem through before you answer."** At `low` and `medium` effort the model often skips thinking on JSON tasks, and this line raises accuracy.

**Effort:**

- Call 1 (extract) at `low`; call 3 (check) at `low`.
- Call 2 (assess) at `medium`. T1 also times it at `high` with the line; keep the fastest setting that passes T2.

**Output:** structured outputs through `client.messages.parse()` with Pydantic models.

- Read responses by block **type**. A response can begin with an empty `thinking` block.
- A `stop_reason` of `max_tokens` is a failed attempt even if the JSON is valid. Retry it once if time allows.
- A `stop_reason` of `refusal` fails the stage. It is never a finding.
- Set `max_tokens` to about 12,000, leaving room for thinking plus the JSON.

**Never send:**

- `temperature`, `top_p` or `top_k`;
- a forced `tool_choice`;
- an assistant prefill;
- API citations, which are incompatible with structured outputs.

Never ask the model to write out its reasoning in the output; that invites `reasoning_extraction` refusals.

**Client:** create the SDK client with `max_retries=0` and pass a per-call `timeout` derived from the deadline.

**Schema rules (verified limits):**

- `additionalProperties: false` on every object.
- No recursion.
- `minItems` may only be 0 or 1.
- Across a request's strict schemas, at most 24 optional parameters and 16 union-type parameters. So make **every field required**, use `""` for "none" instead of nullable types, and keep the schemas flat.

**Warm-up:** `python -m proofroom warmup`.

- It sends each schema once, with a tiny input and a 180 s timeout. Compilation can take up to 180 s, and compiled grammars are cached for 24 h from last use.
- Run it at server start, before recording, and before the finals.
- Never warm up with an unseen request.

**Cost:** about $0.10–0.15 per run [T]. Record `usage` for every call.

**The three calls.** Design them tonight as prose; type them in after 10:30.

| Call | Input | Output (all fields required) |
|---|---|---|
| 1 Extract and select | Numbered documents, the focus note, scope rules | `claims[]: {id, doc_id, quote, family, predicate, subject, object, amount_text, currency_text, date_text, title_text, qualifiers, materiality, selected, exclusion_reason}` |
| 2 Assess | Frozen claims; an evidence table (ID, kind, source, subject mapping, excerpt or JSON path = value, clocks, origin); the team matrix; the rules | `findings[]: {claim_id, disposition, qualified, basis, sentence, evidence_ids, as_of, correction_reason, limitation, question}` |
| 3 Check | Each sentence with only its cited evidence | `checks[]: {claim_id, entailed, missing_qualifier, unsupported_fragment}` |

**Local validation:**

- `quote` must be a verbatim substring of its document after normalization; the app computes the spans itself.
- Evidence IDs must exist.
- No case-specific values go into the schemas.

### 8.4 Storage and runs

- **Run folder:** each run writes `data/cases/<case_id>/run-<n>/input.json`, `case.json` and `brief.md`. All three are written once.
- **Manifest:** the files are read back, and only then is `manifest.json` written, holding their SHA-256 hashes and `DELIVERED`. A missing or failed manifest means the run is not delivered.
- **Concurrency:** one active run per case, enforced by an in-process lock. An identical request within 10 minutes returns the existing run.
- **Should-ship:** "Re-run with documents added or removed" creates `run-<n+1>`, and a compare view diffs the findings by claim key.

### 8.5 Run modes and the repository

- **Modes:**
  - **LIVE** makes real calls.
  - **CACHED** uses development cache hits, labeled on each attempt.
  - **FIXTURE** replays recorded responses with no keys. It is available as `python -m proofroom run --fixture koah` **and** through a **"Load demo case (no keys)"** selector (Koah, Linear, Attio) on the web UI.
  - Every screen and export shows the mode.
- **Fixtures:** a strip script keeps only allowlisted fields (`crustdata_person_id`, name, title, `crustdata_company_id`, `start_date`, and the funding fields used). Fault fixtures use synthetic people.
- **`.gitignore`:** `.env`, `data/` and `cache/`. Scan for secrets before submitting.
- **README:**
  - the problem, with the video and raw-recording links;
  - a quickstart, with `.env.example` listing variable names only;
  - FIXTURE mode;
  - the architecture;
  - the Crustdata endpoints used, and why;
  - the evidence rules;
  - test and evaluation tables with denominators;
  - limitations;
  - the unseen-run protocol.

---

## 9. Failure handling

| Condition | Behavior | Result |
|---|---|---|
| Company has no match, or a genuine tie | Keep the candidates. Company-dependent claims become Not established, and an identity question is raised. | NARROWED |
| S2 finds no funding announcement | Report financing from Crustdata's record only, labeled as indexed, with the limitation "no public announcement found" | NARROWED |
| S1 finds no founders | Team table is empty, with the reason; role claims stay attributed to their sources | NARROWED |
| Namesake source | Exclude it, with the reason. Legitimate publishers stay. | — |
| Person `not_found` or `redacted` | `not_found`: attribute roles to the packet only. `redacted`: respect it, with no alternative lookups. | — |
| Optional field denied | Drop the field, retry once, record a limitation | — |
| Core graph endpoint denied | Produce a labeled recovery brief and escalate | FAILED (core) |
| 402, 429, 5xx, partial or thin fetch | As in §6.3. List failed URLs as requested minus succeeded. | — |
| 55 s reached | No new retrieval. Unfinished checks become "check incomplete", never "no discrepancies". | NARROWED |
| Model `max_tokens`, refusal, or invalid output | One retry for `max_tokens` if time allows; otherwise the stage fails | FAILED |
| Gate failure | Drop the clause or the sentence, and record a limitation | — |
| Export or read-back failure | No manifest is written, so the run is not delivered | FAILED |
| Instructions or agent notes in fetched text | Treated as data | — |

---

## 10. Evaluation

### 10.1 Development packets (seen, so never "unseen")

All facts below were rechecked against the live pages on 30 Oct 2026. They are public assertions, not audited facts.

| ID | Sources | Verified content | What it tests |
|---|---|---|---|
| **P1 Koah** (`koahlabs.com`) | The company post (byline Nic Baird, 24 Feb 2026) and Theory's post (24 Feb 2026) | **Company post:** a $20.5M Series A led by Theory Ventures, with Forerunner and South Park Commons participating. South Park Commons backed Koah at inception; Forerunner led the seed (no amount or date); AppLovin co-founder Andrew Karam wrote the first angel check. **Theory's post:** "Theory Ventures is leading". All three founders (Nic Baird, Mike Choi, Herrick Fang) were South Park Commons Founder Fellows and overlapped at Affirm, Supermove and Qualified. No executive titles are given. | One-origin rule; round vs total; byline ≠ title; a collective claim → G2 per-founder joins |
| **P2 Linear** (`linear.app`) | "Building our way" (10 Jun 2025) and "Sharing Linear's growth…" (26 Aug 2026) | An $82M Series C at $1.25B, including primary and secondary, led by Accel. Then a $99M tender at $2.5B, with no new primary capital; Accel and 01A participated, alongside new investors Salesforce Ventures and S32. The Markdown served to AI agents for both pages opens with a "For agents" note about Linear's MCP server; the browser HTML does not. | Primary vs secondary; valuation ≠ capital; no false sums; content negotiation; data is not instructions |
| **P3 Attio** (`attio.com`) | The Series B post and the developer-platform post | **Series B post:** published Aug 2025, updated Aug 2026; "Today we're announcing" a $52M Series B led by GV; "$116 million to date"; byline Nicolas Sharp, CEO & Co-founder. **Developer-platform post:** published Nov 2025, updated Jun 2026; byline Alexander Christie, CTO & Co-founder; "two months ago, we raised our Series B". | Published vs updated; relative dates; round vs total; titles from byline captions (company statements) |

Run each packet in **Mode A** (domain only) **and** in **Mode B** (the listed sources pasted in).

### 10.2 Composite test groups (labeled SYNTHETIC where faked)

| Group | Cases | Pass condition |
|---|---|---|
| **T-api** | All three error shapes plus a non-JSON body; a 403 denying an optional field (with `denied_fields`); a 429 with a reset header; a 402; a partial, reordered fetch with a null-URL failure | Normalized correctly; a field is dropped only when it is optional; the wait is respected; the brief is narrowed; URLs are matched by URL, never by position |
| **T-identity** | A namesake source; a redacted person; Identify with no match (both an empty 200 and a 404); a domain with two candidates | Exclusion with a reason; the redaction respected; a narrowed brief; the exact-domain candidate chosen |
| **T-finance** | Former, current and concurrent roles; a copied announcement; crore plus an unknown currency; a relative date; an update date | No false conflict; one origin; magnitude and currency kept separate; dates anchored to publication |
| **T-safety & delivery** | A private revenue claim; injected instructions; an export failure; the P2 agent note | Not checked; policy intact; not delivered; treated as data |

### 10.3 Gates

| Gate | When | Pass condition | If it fails |
|---|---|---|---|
| **T1** Access and shapes | 10:30–10:50 | Preflight and credits read. Identify and Enrich run on P1, checking whether `people.founders`, `funding_rounds` and `news` are populated. Person Search tests `(.)` on title and name. Person Enrich checks whether past entries carry `crustdata_company_id` and dates. Check whether web search supports `OR`, and which representation Web Fetch returns for `linear.app`. Time the schema warm-up and calls 1–3 at the chosen effort levels. | Core endpoint denied: escalate. No past IDs: G2 covers current roles only. No `people.founders`: S1 uses search only. |
| **T2** Usefulness | 12:15–12:50 | P1–P3 in both modes. At least 3 correct reusable sentences in at least 2 of the 3 packets. The team table is populated, with at least one ID join, in at least 2 of the 3. Zero wrong subjects, false conflicts or false sums. Median ≤75 s. | Reasoning errors: fix prompts and rules before UI work. Slow: cut to 4 claims and 2 people. Mode A failing: see the trigger in §15. |
| **T3** Robustness | by 13:20 | All four groups pass; FIXTURE mode works in both the CLI and the UI | Fix before the freeze |

### 10.4 Metrics

Always report denominators. These are not accuracy claims.

- sentences emitted, supported and suppressed;
- team rows and ID joins;
- wrong-entity acceptances;
- false conflicts and false sums;
- unnecessary abstentions;
- runtime;
- credits (exact, and rounded);
- tokens;
- the mode of each run.

### 10.5 Comparisons (should-ship)

- **Same-evidence baseline.** Give the same model the identical evidence bundle and a competent "cited Team & Financing brief" prompt. Count these error classes, and report wins, ties and losses:
  - wrong subject;
  - an announcement stated as fact without attribution;
  - round/total confusion;
  - copies counted as corroboration;
  - an update date treated as the event date.
- **Graph ablation.** Turn off Identify, Company Enrich, Person Search and Person Enrich; Crustdata Web Search and Fetch stay on. Count the team rows, ID joins and sentence statuses that are lost. This gives the pitch line "without the graph, X of Y joins disappear".

---

## 11. The two-minute video

### 11.1 Unseen-request protocol

Write this into the README before 14:00.

1. **Select after the freeze, by a fixed rule.** After 14:00, run a predeclared news search for startup funding announcements from the past 14 days. Take the first company that:
   - (a) was not touched during development;
   - (b) has a company domain;
   - (c) is a private startup.
2. **Line up three candidates.** Pick three this way, and use them in order.
3. **Keep the request minimal.** The request is the domain alone (plus a meeting date). That is Mode A.
4. **Show the proof on screen:** the selection result, an empty case list for that domain, and the wall clock.
5. **Record the first product run unedited,** and keep the raw file.
6. **Handle a failed run honestly.** A failed run stays in the record. The retake uses the next candidate and says so. Nothing for that company may come from the cache, a fixture or a prior run.

"Unseen" means never processed by Proofroom or used for tuning.

### 11.2 Storyboard (result-first)

| Time | On screen | Label |
|---|---|---|
| 0:00–0:12 | One sentence on the problem; type the unseen domain; click Prepare | UNSEEN REQUEST · selected after the 14:00 freeze · domain only |
| 0:12–0:30 | The Identity panel fills: G1 ID, then the founders found by company ID. Then compress the remaining wait, showing the wall clock. | LIVE · ⏩ ×4 · actual X s |
| 0:30–1:05 | The team table: open a founder's row to show the employer-ID join, title and start date, and the JSON path with `updated_at`. Show a collective claim split into per-person rows. | GRAPH JOIN |
| 1:05–1:35 | Financing: the announced-round sentence with its passage highlighted; publication vs update dates; company and investor posts grouped as one origin; the Crustdata record cross-check or question | VERIFIED CITATION |
| 1:35–2:00 | Exports, run statistics (time, exact credits, tokens, LIVE), and the evaluation card (P1–P3, the four test groups, the ablation result if done) | VERIFIED ARTIFACTS · PREVIOUSLY RECORDED EVALUATION |

If the unseen run produces no ID joins, say so plainly and show the honest narrowing.

### 11.3 Honesty rules

- Never call cached, fixture or replayed output live.
- Never plant claims.
- Never hide human steering.
- Always show the actual wall time when time is compressed.
- Link the raw recording.
- Keep every attempt.

Ask at 09:30 whether labeled time compression is allowed. If it isn't, record with 3 claims and 2 people to shorten the run.

---

## 12. Live finals

Code freezes at 15:30, so the finals run the submitted build. Ask about the format and duration at 09:30.

| Time | Action |
|---|---|
| 15:30–16:30 | Build the stage kit: two fresh eligible domains selected by the §11.1 rule (not yet run); the recorded unseen run; an exported brief open in a tab; `.env` loaded; laptop charger and phone hotspot; the display tested at 125–150% zoom |
| 16:30–17:00 | Rehearse three times with a timer, using **development packets in CACHED mode**. Never rehearse on the stage domains. Run order: a 45-second pitch → start the live run in the first 15 seconds → narrate the Identity panel as it fills → open one team-table cell and one cited sentence → a 15-second close with the evaluation numbers and limits. |
| 17:10 | Switch to LIVE, run the warm-up, then leave the web endpoints idle from 17:15 |
| 17:30 | Finals. If a judge names a company, type its domain (Mode A). |

**If the network or an API fails on stage:** say so. Switch to the recorded run and show a FIXTURE replay, labeled as such.

**Q&A preparation:**

- *"How do you know it's right?"* The gate, the test groups and the stated limits.
- *"What does Crustdata add?"* G1–G4 and the ablation count.
- *"Isn't this just a chatbot with search?"* The baseline result, typed financing, ID joins and the exports.
- *"Who pays?"* Fund associates and platform teams. Say plainly that demand is a hypothesis.

---

## 13. Schedule

### 13.1 Tonight (30 Oct): content and design only

1. Confirm eligibility and registration (§1.3).
2. Assign provisional roles.
3. Write the three system prompts and schemas as prose (§8.3). Each prompt ends with the "think" line.
4. Write the expected answer keys for P1–P3 from §10.1.
5. Write the four test groups as tables.
6. Draft the README outline, the §11.1 selection rule, the video narration and a 45-second pitch.
7. Check every laptop: Python, a working `pip`, a 1080p screen recorder with the microphone, and GitHub access.
8. Check the Anthropic key with a one-line call. That is environment setup, not product code.
9. Create an empty repository folder outside OneDrive.

### 13.2 Event day (31 Oct, IST)

| Time | Work | Exit condition |
|---|---|---|
| 09:00–10:00 | Kickoff and briefing: ask the §16 questions | Answers noted |
| 10:00–10:30 | Walkthrough and team formation: choose the §14 split, get the key, ask the Crustdata questions | Team and key |
| 10:30–10:50 | **T1.** A: Crustdata probes, including S1 and S2. B: model calls and warm-up timing. C: repo, models, error normalizer, run folders. D: page skeleton with progressive panels. | T1 recorded |
| 10:50–11:35 | Vertical slice through the CLI: Mode B on P1 → verified `case.json` and `brief.md` | First DELIVERED run |
| 11:35–12:15 | A: S1 and S2. B: alignment rules, split gate, G2/G4 reasoning. C: run log, modes, fixture capture and strip script. D: brief, team table, evidence drawer. | Mode A runs end to end |
| 12:15–12:50 | **T2** on P1–P3 in both modes; fix reasoning before any UI work | T2 decision |
| 12:50–13:20 | **T3**: the four test groups; FIXTURE mode in the CLI and UI | T3 pass |
| 13:20–14:00 | Fixes; README results. At the 13:30 mentor checkpoint, show a Mode A live run. Build the should-ship items only if green. | Ready to freeze |
| **14:00** | **Feature freeze.** Correctness fixes only, each followed by the affected tests. | — |
| 14:00–14:30 | Clean-clone test (FIXTURE without keys, then LIVE); secrets scan; warm-up; select three unseen candidates; rehearse on a non-candidate | Clean clone works |
| 14:30–15:00 | Web endpoints idle for 60 s → record the unseen run → edit it with labels → upload, with the raw file linked | Video link |
| 15:00–15:20 | Final README, commit hash, repository access check, submit | Receipt |
| 15:20–15:30 | Buffer | Deadline 15:30 |
| 15:30–17:30 | Finals preparation (§12) | Stage kit ready |

The 12:30 lightning talks are optional. Don't let them stall the critical path.

---

## 14. Team roles (decide at 10:00)

| Team size | Split |
|---|---|
| 4 | **A Data:** Crustdata adapter, limiter and cache, S1, S2, G1–G4 retrieval, T1 · **B Reasoning:** prompts and schemas, assessment, gate, G2 and G4 reasoning · **C State:** run folders and manifest, error normalizer, exports, fixtures and strip script, test groups · **D Product:** page and progressive UI, fixture selector, README, video, submission, pitch |
| 3 | A Data · B Reasoning + State · C Product + Tests |
| 2 | A Data + State · B Reasoning + Product |
| 1 | CLI and `brief.md` plus a minimal page; Mode A plus pasted text; 4 claims; 2 people; T-api and T-identity only; the same gates and honesty rules |

---

## 15. Scope tiers, cut order and triggers

**Must-ship:**

- Mode A (S2 packet assembly) and Mode B (paste and URL);
- S1 founder discovery;
- G1, G2 and G4, plus G3 when T1 shows data;
- extraction and selection;
- the evidence rules;
- assessment;
- the split gate;
- verified exports with a manifest;
- the error normalizer;
- the run log and run modes;
- FIXTURE mode in the CLI and the UI;
- the four test groups;
- the README;
- the unseen recording.

**Should-ship:** re-run compare, the same-evidence baseline, the graph ablation, and an identity pin.

**Stretch:** text-PDF upload.

**Never:** OCR, headcount, authenticity scoring, valuation, revenue or customer verification, outreach, CRM, Watchers, an MCP server.

**Cut order:**

1. PDF upload
2. Identity pin
3. Baseline
4. Re-run compare
5. Ablation (keep it if at all possible: it is the pitch's graph number)
6. Mode B URL fetch (keep paste)
7. The third person
8. Page polish (fall back to rendered Markdown)

**Never cut:** G1/G2, the evidence rules, the gate, verified exports, honest labels, the unseen first run, and the README's setup and results.

| Trigger | Decision |
|---|---|
| No verified export by 11:35 | Stop UI work; finish the CLI-to-export path |
| Mode A not passing at 12:50 | Video and stage use Mode B with one announcement URL; the stage script asks the judge for a link. Keep S1, since founders found by company ID are still the graph showcase. |
| T2 fails on reasoning | Fix rules and prompts before UI work |
| Median over 75 s | Cut to 4 claims → 2 people → skip stage-4 search → fewer fetched pages. Never drop the checks. |
| Core endpoint denied | Escalate at once. A packet-only summary does not meet the brief. |
| Behind at 13:20 | Drop the should-ship items and freeze at 14:00 regardless |

---

## 16. Unknowns, T1 probes and questions for the organizers

| ID | Unknown | How it gets resolved | Fallback |
|---|---|---|---|
| U1 | Key entitlements, including field permissions for `people` and `funding` | T1: `/account/endpoints`; ask at 10:00 | Escalate; drop optional fields |
| U2 | Whether past entries carry `crustdata_company_id` and dates. The reference documents only `company_status` for past roles, and no `end_date`. | T1 on two profiles | G2 covers current roles only |
| U3 | `people.founders`, `funding_rounds`, `investors` and `news` sub-fields | T1 | S1 by search; G4 on totals and last round |
| U4 | Person Search `(.)` behavior on title and name fields | T1 | `=` on the full name taken from the packet |
| U5 | Web Search boolean `OR`, and the quality of the `site` filter | T1 | Plain queries |
| U6 | Which representation Web Fetch returns (HTML or agent Markdown) | T1 on `linear.app` | Record the hash; rules unchanged |
| U7 | Rate limits per key or per account; team contention | Ask at 10:00; read the headers | Limiter, cache, idle minute |
| U8 | Latency with the "think" line at the chosen effort levels | T1 timings | Lower effort for calls 1 and 3; 4 claims |
| U9 | Graph coverage of very new startups | T2 and the selection rule | Honest narrowing |
| U10 | Usefulness on natural packets and graph materiality | T2 and ablation | Narrow the claim families |

**Ask at 09:30 (organizers):**

- (Q1) How long is each finals slot, and do judges supply the company?
- (Q2) Is a labeled time compression allowed in the video if the raw recording is linked?
- (Q5) Will repository reviewers run the code without keys?
- (Q6) How is "never seen" checked? Will there be an official test request?

**Ask at 10:00 (Crustdata):**

- (Q3) Are the web live endpoints enabled on our key, and is the 10/min limit shared or raised for the event?
- (Q4) Which field permissions does our key have for `people`, `funding`, `urn_url` and `assessment`?

---

## 17. Gemini audit: what held up

### 17.1 Findings

| ID | Gemini's finding | Check result | Decision | v2 |
|---|---|---|---|---|
| F-01 | The graph is passive without supplied URLs; promote S1 and S2 | Facts correct. "Manual search violates End-to-End" is overstated, since preparing a request is not steering a run, but the stage-optics argument stands. | **Accepted** | §4.2, §6.2, §7 |
| F-02 | Schedule overload; cut SQLite and revision; consolidate the tests | Judgement; agreed (revision is not shown in the video or on stage) | **Accepted**; re-run compare kept as should-ship | §8.4, §10.2, §15 |
| F-03 | Sonnet 5.5 thinking and effort misconfigured | **Verified** in Anthropic's Sonnet 5.5 prompting guide: `between_tools` means no thinking on tool-less requests; add the "think" line; read by block type; `max_tokens` = failed | **Accepted** | §8.3 |
| F-04 | The error parser would crash on string errors | **Verified**: three shapes appear across the docs | **Accepted** | §6.3 |
| F-05 | The 70 s target and the 40 s cutoff break under one retry | Modelled estimates, not measurements, but plausible | **Accepted in direction**: 55 s cutoff, no repair call, conditional `human_mode`, idle minute, 75 s / 110 s | §6.4, §8.2 |
| F-06 | The deterministic gate causes false abstentions | Judgement; agreed | **Accepted**, with a digits-only rule | §5.4 |
| F-07 | Packet facts wrong | **Mixed.** Correct: the Koah byline and the inception and angel lines. **Wrong:** Theory does not call the founders "Co-founders" (it says "All three founders… were Founder Fellows"). **Wrong:** "Linear has no agent-directed text". The Markdown Linear serves to agents opens with a "For agents" MCP note; only the browser HTML lacks it. | **Corrected both ways** | §5.3, §10.1 |
| F-08 | Attio's update date and collective claims are traps | **Verified** (Published Aug '25, Updated Aug '26, "Today we're announcing") | **Accepted**; added the relative-date rule | §5.3, §7 |
| F-09 | S1 credits understated about 2×, and no name filter | **Partly.** v1's 0.13 per result was right when `fields` excludes experience. 0.23 applies if experience is returned or `fields` is omitted. Per-call rounding up is verified. | **Accepted**: explicit `fields`, `limit` 10, title and name filters | §6.2 |
| F-10 | The storyboard wastes 45 s on progress | Judgement; agreed | **Accepted** with honest labels | §11.2 |
| F-11 | No UI fixture loader; cache privacy | Agreed | **Accepted** | §8.5 |
| F-12 | Cold schema compile can time out | **Verified**: 180 s compile timeout and a 24 h cache | **Accepted** | §8.3 |

### 17.2 Gemini's fact ledger and disagreements

| Gemini claim | Check result |
|---|---|
| `/account/credits` is rate limited at 300/min; its 401 body is `{"message": …}` | Correct |
| `x-credits-used` is decimal; the balance rounds up per call; the header is absent on 429 | Correct |
| Identify never returns 404 for an unmatched company | **Not supported.** The reference still defines 404 ("No data found") without a trigger, so v2 handles both. |
| Past-role shape is fully documented | **Overstated.** The reference lists only `company_status` for past roles, and no `end_date`. Stays a T1 test. |
| `urn_url` is documented, with a permission gate | Correct (v1 was wrong) |
| API version `2026-10-21` requires `Authorization: Bearer` instead of `x-api-key` | **Not found** in the migration reference. Its summary lists sampling parameters, citation and document blocks, Admin API fields and SDK changes. Moot anyway, since the SDK handles headers. |
| Attio developer post: Nov 2025, Alexander Christie, CTO & Co-founder | Correct (also "Updated Jun '26") |
| Eligibility is limited to 3rd/4th-year BTech, dual-degree and MTech students at IIT Bombay | Correct; added to the preconditions |
| Disagreements 1–4 and 6 (`between_tools`, information gain, priority inversion, gate, Identify ties) | Accepted |
| Disagreement 5 (Linear has no agent text) | **Rejected.** See F-07. |

---

## 18. Verification ledger (this round, 30 Oct 2026)

| Claim | Status | Source |
|---|---|---|
| Error bodies appear as a nested object, a string with `description`/`reason`, or a flat `message` | Verified | Crustdata Identify API reference; API introduction (2025-11-01); Credits page |
| Identify: an unmatched domain gives 200 with `[]`; a 404 is defined with no trigger; `fields` limited to `crustdata_company_id`, `basic_info`, `social_profiles` | Verified | Identify API reference |
| Credits: exact decimal header; rounding up per call; no header on 429; `/account/credits` at 300/min | Verified | Credits page |
| Person Search: `(.)` = every word in any order; title filter allowed; profile URL field; omitting `fields` costs 0.23 per result | Verified | Person Search introduction |
| Person Enrich: past entries document only `company_status`; no `end_date`; `urn_url` needs a permission | Verified | Person Enrich reference |
| Sonnet 5.5: no thinking under `between_tools` on tool-less calls; the "think" line; read by block type; `max_tokens` = failed | Verified | Anthropic, Prompting Claude Sonnet 5.5 |
| Structured outputs: 180 s compile timeout; 24 h cache; `minItems` 0/1; 24 optional and 16 union-type parameter limits | Verified | Anthropic, Structured outputs |
| API `2026-10-21`: no auth-header change listed | Verified (absent) | Anthropic API version migration reference |
| Koah post: Nic Baird byline; inception backing; seed lead; angel check | Verified | koahlabs.com raw HTML |
| Theory post: "All three founders"; "Founder Fellows"; "overlapped at" Affirm, Supermove and Qualified; no "co-founder" title | Verified | tomtunguz.com raw HTML |
| Linear: the Markdown served to agents opens with a "For agents" MCP note; browser HTML has none | Verified | Requests with `Accept: text/markdown` vs a browser user agent |
| Attio: Published Aug '25 / Updated Aug '26 / "$116 million to date"; developer post Nov '25 / Jun '26 by Alexander Christie, with "two months ago" | Verified | attio.com raw HTML |
| Gemini's per-stage timings (61.5 / 81 / 114 s) | Estimates, not measurements | Gemini audit §5; to be measured at T1/T2 |

All v1 ledger items not listed here stand as v1 recorded them (v1 §16), except V20 (`urn_url`), which is now corrected.

---

## 19. Sources

- **Official brief:** [ContextCon PS - CrustData (1).pdf](<../ContextCon PS - CrustData (1).pdf>)
- **Gemini audit:** "Adversarial Audit of Proofroom Plan.docx" (archived in the old `IMP Projects\Y Combinator Hackathon\proofroom` folder; §17 summarizes it)
- **Previous plan:** [Proofroom_Final_Project_Plan_v1.md](Proofroom_Final_Project_Plan_v1.md)

**Crustdata:**

- [API introduction (2025-11-01)](https://docs.crustdata.com/openapi-specs/2025-11-01/introduction)
- [Identify API reference](https://docs.crustdata.com/api-reference/company-apis/identify-a-company-from-name-domain-id-or-profile-url)
- [Company Enrich reference](https://docs.crustdata.com/company-docs/enrichment/reference)
- [Person Enrich reference](https://docs.crustdata.com/person-docs/enrichment/reference)
- [Person Search introduction](https://docs.crustdata.com/person-docs/search/introduction)
- [Web Search](https://docs.crustdata.com/web-docs/search/introduction)
- [Web Fetch](https://docs.crustdata.com/web-docs/fetch/introduction)
- [Credits](https://docs.crustdata.com/general/credits)
- [Pricing](https://docs.crustdata.com/general/pricing)
- [Rate limits](https://docs.crustdata.com/general/rate-limits)
- [Permissions](https://docs.crustdata.com/general/permissions)
- [Error best practices](https://docs.crustdata.com/openapi-specs/2025-11-01/best-practices)

**Anthropic:**

- [Prompting Claude Sonnet 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5)
- [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [API version 2026-10-21 migration](https://platform.claude.com/docs/en/api/migration-2026-10-21)
- The Claude API reference bundled with Claude Code (model table cached 6 Oct 2026)

**Packets:**

- [Koah company post](https://www.koahlabs.com/blog/theory-ventures-partnership)
- [Theory Ventures post](https://tomtunguz.com/koah-theory/)
- [Linear Series C](https://linear.app/now/building-our-way)
- [Linear tender](https://linear.app/now/sharing-growth-with-the-people-building-linear)
- [Attio Series B](https://attio.com/blog/attio-raises-52m-series-b)
- [Attio developer platform](https://attio.com/blog/meet-the-attio-developer-platform)

These are public assertions by their authors.

---

## 20. Pre-event probe results (31 Oct 2026, 00:10 IST): these override earlier sections

These were run through the Crustdata MCP connected to the **personal** account (krunalgladiator12@gmail.com: 200 credits, expiring 13 Nov), not the event key. They cost about 2.4 credits. They used only the development companies. Phase 1 of the day check re-confirms them on the event key.

### 20.1 What was observed

| Probe | Result |
|---|---|
| Endpoint access | Enabled: `/company/identify` (30/min), `/company/enrich` (15/min), `/company/search`, `/person/search` (30/min), `/person/enrich` (15/min), `/web/search/live` (10/min), `/web/enrich/live` (10/min), `/job/search`, `/social_post/search` and `/agent/query` (2 credits). Disabled: all live person/company endpoints, all batch endpoints, and contact enrich. |
| Identify | Koah → **3718859**, Linear → **633791**, Attio → **664000**. Each had a single candidate with confidence 1.0, an exact `primary_domain` and `all_domains` = [domain]. |
| Company Enrich (Koah; `basic_info`, `funding`, `people`, `news`; 2 credits) | **`funding`:** `total_investment_usd` 25,500,000; `last_round_amount_usd` 20,500,000; `last_round_type` `series_a`; `last_fundraise_date` 2026-02-24; `num_funding_rounds` 3; `investors` = [Andrew Karam, Forerunner, South Park Commons, Theory Ventures]. **There is no `funding_rounds` key.** Per-round data is in **`milestones[]`**: `{round_type, date, funding_date, amount_usd, investors, lead_investors, investors_detailed[]}`. The rounds are: series_a, 2026-02-24, $20.5M, lead Theory Ventures; seed, 2025-09-07, $5M, lead Forerunner; pre_seed, "2024-01-01", amount null, South Park Commons. `investors_detailed` carries Crunchbase profile URLs. |
| Company-level clocks | `updated_at` and `indexed_at` are **null** for Koah, so the company record's refresh time is "unknown". Each founder record has its own `updated_at` (2026-10-23). |
| `people.founders` | 3 full profiles (Mike Choi, Nic Baird, Herrick Fang), each with `experience`, `education` and `updated_at`. The employment keys are **`employer_name`, `employer_company_id` (a list of strings, e.g. `["3718859"]`), `employee_title`, `employee_start_date`, `employee_end_date`**. These differ from Person Enrich's documented `name`, `title`, `crustdata_company_id`, `start_date`. |
| `news[]` | 20 items, each `{article_url, article_title, article_publish_date, article_publisher_name, publisher_domain, source: "crunchbase", confidence_score}`. They include the funding coverage, such as Morningstar/PR Newswire (2026-02-24), Techmeme (2026-02-25) and VC News Daily (2026-03-03). |
| Person Search, S1 (company_id = 3718859 AND current.title `(.)` "founder") | Exactly the 3 co-founders, with `current_title` "Co-Founder" and profile URLs. Cost: 0.39 credits (3 × 0.13). `(.)` matches "Co-Founder". |
| MCP Web Fetch | Returns **stripped visible text capped at 30,000 characters**, while the raw API is documented to return raw HTML. MCP tool behavior is not the same as the REST API's. |
| MCP skills | None granted on this account |

### 20.2 Plan changes

1. **Company Enrich becomes the main graph call.** Request `fields: ["basic_info", "funding", "people", "news"]` for 2 credits. That single call supplies G3 (founders), G2 (founders' current and past employers with company IDs), G4 (`milestones`, `investors`) and S2 candidate URLs (`news`).
   - Person Search (S1) is the fallback when `founders` is empty.
   - Person Enrich is needed only for people who are not founders, or who were supplied as profile URLs.
   - Web Search is the fallback when `news` has no funding article.
   - Expected run cost: about 5–7 credits. Fewer sequential calls also shortens stage 2.
2. **S2 packet assembly** picks ≤3 URLs from `news[]`. Prefer titles containing funding words, a press release or the company's own page, and an `article_publish_date` within 7 days of a `milestones` date. Fetch them with Web Fetch. Note that `news` URLs are linked to the company by Crustdata (provider-asserted subject mapping), but each source's subject still passes the §5.2 checks.
3. **One employment normalizer** maps both key sets into `{employer_name, employer_id (int), title, start, end, start_precision}`. It also handles `employer_company_id` being a list of strings.
4. **Date precision.** Treat `YYYY-01-01` as year-level precision and `YYYY-MM-01` as month-level precision, unless a source states the exact day. Example: Koah's pre-seed "2024-01-01" means "2024". Never compute tenures or "same-day" overlaps from padded dates.
5. **G4 basis label:** "Crustdata funding record (Crunchbase-derived)". The `investors_detailed` links and the `news.source` field point to Crunchbase. That makes the record derived from public announcements, so **it is still not independent corroboration** of an announcement. It can fill gaps the sources leave, but only as a labeled indexed fact.
6. **Clocks:** show "record refresh: unknown" when the company-level `updated_at` is null. Founder rows use each founder's own `updated_at`.
7. **REST API, not MCP, inside Proofroom.** The product calls the REST API directly. That gives typed responses, `x-credits-used` and rate-limit headers, and documented fetch output. The Crustdata MCP is for *developer* probing in Claude Code (as here). If time is ever spent on the MCP wrapper's behavior, note the differences listed in 20.1.
8. **U2, U3, U4 and U6** are resolved for the personal account (past roles carry company IDs; funding sub-fields and the `(.)` behavior are known). **U1** (event-key entitlements) remains open until Phase 1.

### 20.3 A real, unplanted finding on development packet P1

This finding is the expected result for check 2.4 in the day-check file, and an example for the README and pitch. **It is not the unseen demo.**

| Source statement | Graph evidence (founder records, indexed 23 Oct 2026) | Correct output |
|---|---|---|
| Theory: all three founders "overlapped at three companies: Affirm, Supermove, & Qualified" | Only **Herrick Fang** lists Affirm (ID 632082, 2019–2020), Supermove (780882, 2020–2021) and "Qualified (Acquired by Salesforce)" (632707, 2021–2023). Mike Choi lists Google, Apple, Twitter, X, South Park Commons and others. Nic Baird lists Halo Neuroscience, MarkSetBot, Thync, Thinktiv and South Park Commons. | **Supported, corrected (scope):** "Theory's post says the founders overlapped at Affirm, Supermove and Qualified. Crustdata's indexed profiles show those three employers only for Herrick Fang." Question: "Which founders worked at Affirm, Supermove and Qualified?" Profiles are self-maintained, so this is a qualification, **not** a refutation. |
| Koah's post: "Forerunner led our seed round" (no amount or date) | `milestones`: seed, 2025-09-07, $5M, lead Forerunner | Sentence 2 stays **Supported** (company statement). The graph adds: "Crustdata's funding record lists a $5M seed dated 7 Sep 2025, led by Forerunner (indexed, Crunchbase-derived)." |
| Theory: all three were South Park Commons "Founder Fellows" | Mike Choi: "Founder Fellow", 2023–2024. Nic Baird: "Founder Fellow" (current), plus earlier "Investor" and "Member". Herrick Fang: "Member", 2023–2025. | Qualified: Herrick Fang's indexed title is "Member", not "Founder Fellow" |
| Total raised (not stated by the sources) | `total_investment_usd` 25.5M = 20.5M + 5M | Graph-added: "$25.5M across 3 rounds per Crustdata's record". The prior-round question is answered, so none is raised. |
| Current roles | Each founder's current entry is Koah (ID 3718859) as "Co-Founder". Nic Baird also has a concurrent current South Park Commons entry. | G2 ✔ for all three. Concurrent roles are allowed. |

Every row above came from a live call on 31 Oct 00:10 IST. The `‹…›` placeholders in the §4.3 illustration can now be read as these values for development use.

**Final product promise:** type a domain and get a Team & Financing brief in which every sentence is tied to a Crustdata identity and an exact source, every limit is stated, and every number can be checked.

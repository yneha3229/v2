# Proofroom: Final Project Plan v1

*A verified, audited and improved version of `Proofroom_Final_Project_Plan.md`.*

**Prepared:** 30 October 2026, IST
**Event:** ContextCon IIT Bombay, The Agentic Services Hackathon (Techfest 2026-27), 31 October 2026
**Status:** Planning only. No product code has been written. No authenticated Crustdata or Anthropic call was made for this audit. Nothing here is a measured result. Numbers marked **[T]** are targets.
**Use:** Run the event from this file. The other five files in `proofroom/` are history: the original plan audited here, and the later four-stage chain (`Proofroom_Plan_v1_Product.md` → `Proofroom_Plan_v2_Evidence.md` → `Proofroom_Plan_v3_Execution.md` → `Proofroom_Final_Winning_Plan.md`). I read that chain in full. Its sound decisions are folded in here, and its errors are corrected (§17).

**How this was verified (30 Oct 2026):**

- The official brief, `ContextCon PS - CrustData (1).pdf`: the full text extraction, plus the page images of pp. 3–4.
- Crustdata's current documentation for every endpoint the plan uses.
- The Anthropic API reference bundled with Claude Code (its model table was cached on 6 Oct 2026).
- The five public pages used as development packets.
- This laptop's toolchain.

Reading documentation is not the same as testing at runtime. Every runtime unknown has a named test in §15.

---

## 0. Audit verdict

**Keep Proofroom.** The original plan's product logic and evidence rules are sound. They fit the brief's *Investing* theme and its *Data Integrity & Verification* criterion. Its event facts are correct. As written, though, it would not win reliably, for the reasons below. This version fixes all of them.

| # | Severity | Finding | Evidence | Fix |
|---|---|---|---|---|
| A1 | **Critical** | **The live on-stage finals are not planned.** The plan prepares only the video. Shortlisted teams demonstrate live at 5:30 PM. Code freezes at 3:30, so anything the stage needs must ship before then. | PDF p. 3 (Phase 2); p. 4 (5:00 finalists, 5:30 finals) | §11 finals plan; URL intake moves into core; stage kit |
| A2 | High | **The demo storyboard does not allow time for the run.** §9 targets a 90-second run, but the §13 storyboard opens results about 25 seconds after the run starts. | Original §9, §13 | §10: storyboard built on a 70 s [T] run, live progress and a labeled time-skip |
| A3 | High | **Crustdata looks like enrichment, not graph use.** No ID-level join is defined, so the graph can look decorative under the criterion about leveraging "Crustdata's canonical graph". | PDF p. 3; original §6, §9 | §6.3: four graph decisions (G1–G4), visible in an Identity panel and in citations |
| A4 | High | **The scope is more than five hours of work.** It includes a React plus FastAPI two-app stack, six claims, PDF parsing, a dependency-invalidation engine with Dependency and Memo-sentence records, and eleven tests plus a baseline. | Original §3, §8, §12 | One FastAPI app with a server-rendered page and a CLI; ≤5 claims; text/URL intake; whole-case rerun for revisions; tiered tests |
| A5 | Medium | **The API contract is under-specified.** It is missing the base URL, the default field sections, the per-endpoint rate limits (the web endpoints allow only 10 per minute), the 10-URL fetch batch, the `x-credits-used` header, the error envelope, and which errors to retry. | Crustdata docs (§16) | §6 verified contract |
| A6 | Medium | **No model is chosen.** Current models reject sampling parameters and forced tool choice. Structured outputs cannot be combined with API citations. New schemas add latency the first time they are used. | Anthropic API reference | §7.3 model, settings, three fixed schemas, warm-up rule |
| A7 | Medium | **"Unseen request" is not operationalized.** There is no selection rule, no proof on screen and no retake policy. | PDF p. 2: "a request it has never seen" | §10.1 protocol |
| A8 | Medium | **The repository ignores judges who have no API keys.** There is no CLI and no keyless run mode, and no clean-clone test is planned. | PDF rule 5 | §7.6 FIXTURE replay mode, CLI, README; clean-clone test at 14:00 |
| A9 | Medium | **The headline depends on luck.** "Reasoned correction" needs a correction event, and a natural unseen packet may not contain one. | Original §1, §13 | Headline: graph-anchored, cited claim checks. Corrections appear when evidence demands them; revisions are proven in tests |
| A10 | Medium | **The later chain over-corrected.** It drops URL intake, which the stage needs. Its graph ablation "removes Crustdata but keeps the web budget", yet web search and fetch *are* Crustdata endpoints. It caps model output at 900/1,800/600 tokens including thinking, which risks truncation. It adds idempotency machinery that a single-process app does not need. And it is too dense to execute under time pressure. | V3 §10; Winning Plan §7–§9 | Keep its evidence rules and whole-case rerun; correct the rest (§17) |
| A11 | Low | **The team forms at 10:00 on the day.** The plan has 4/2/1-person splits but no 3-person split and no decision point. | PDF p. 3 timeline | §13 |
| A12 | Low | **Environment traps on this laptop.** The project folder is inside OneDrive, whose sync can lock files and corrupt SQLite. `python` is 3.14.7 and a 3.12.2 install also exists. The "bundled Python 3.12.14" the later plans call verified is not present here. | Local check | §7.1: repo outside OneDrive; explicit venv interpreter |
| A13 | Low | **Fixtures could republish personal data and provider data.** | Original §11 (intent only) | §7.6: minimal fields; synthetic people for fault fixtures |

**What the original got right, and this version keeps:**

- the event date, coding window, the four criteria and the no-contact rule;
- the Crustdata headers and endpoint paths;
- limited default enrichment sections;
- the authenticity field path and its permission gate;
- Web Fetch per-item failures and reordering;
- the permissions endpoint;
- the evidence principles: round ≠ total, current ≠ former, namesakes, and "copies are one assertion".

Details are in §16.

---

## 1. Plan at a glance

| | |
|---|---|
| **Pitch** | Proofroom turns a founder-meeting packet into Team & Financing facts an investor can paste into a memo. Each sentence is tied to a Crustdata identity and an exact source. Overstatements are corrected, with the reason shown. |
| **User** | An associate at a seed-to-Series-B fund preparing a partner's founder meeting. Demand is a hypothesis. |
| **Input** | Company domain; 1–3 documents as pasted text or public URLs (≤6,000 words in total); up to 2 people (name, plus an optional profile URL); optional meeting date and focus note |
| **Output** | Case page, `brief.md` and `case.json`, containing: reusable sentences with status and basis, a claim ledger, financing and role tables, 0–3 questions, a not-checked list, limitations, run statistics and version history |
| **Crustdata's job** | G1 subject ID · G2 person → employer ID joins · G3 founder roster check · G4 indexed funding comparison · Web Search/Fetch for source passages |
| **Model** | `claude-sonnet-5-5`, with three fixed structured-output calls: extract, assess and check |
| **Run target** | ≤70 s from click to delivery [T]; hard stop at 100 s |
| **Demo moment** | A sentence opens to its exact passage and the Crustdata ID join behind it. No planted error, ever. |
| **Gates** | T1 10:50 · T2 12:10 · T3 13:20 · **freeze 14:00** · unseen recording 14:30–15:00 · submit by 15:20 · finals prep 15:30–17:30 |

---

## 2. What the brief requires, and how the plan meets it

| Requirement (official PDF) | Plan response |
|---|---|
| Autonomous agents for professional services (p. 1). The Investing theme covers "analyzing startups, parsing data rooms" (p. 2). | A bounded diligence service for one recurring investor task |
| Must build on Crustdata's canonical identity graph for people and companies (p. 2; rule 3) | G1–G4 ID decisions are core, visible and tested by ablation (§6.3, §9.5) |
| A functional repository, plus a 2-minute video of a never-seen request reaching finished work (p. 2; rule 5) | §7.6 run modes; §10 protocol; §12 submission steps |
| Modes: one agent, a system of agents, an MCP server or a CLI (p. 2) | One orchestrated agent with a web page and a CLI; no MCP server |
| API at `https://api.crustdata.com` with `authorization: Bearer …` and `x-api-version: 2025-11-01` (pp. 2–3) | §6.1 |
| Ideas and architecture may be prepared in advance; coding starts strictly at 10:30 (rule 2) | The §12.1 pre-event list is content and design only |
| Agents must not interact with external real people (rule 4) | Authorized APIs only: no outreach, email or contact lookups |
| A 5-hour sprint, then Phase 1 (video and repository review) and Phase 2 (live finals) (p. 3) | §10 video; §11 finals |
| Teams of up to 4, formed at 10:00 (p. 3) | §13 |
| $1,500 in Crustdata credits per team (p. 5) | §6.5. The credit-to-dollar rate is not published, so read `account.credits` at 10:30. |

---

## 3. Rubric → feature → proof

The brief lists four criteria with no weights.

| Criterion | What the brief asks | Feature | Proof shown to judges |
|---|---|---|---|
| End-to-End Execution | Request to finished work without human intervention | One click runs intake → resolve → extract → retrieve → assess → check → publish. A case is DELIVERED only after its exports are written and read back. | An unedited first run with an elapsed clock; the downloads opened |
| Data Integrity & Verification | Use of "Crustdata's canonical graph" and "verifiable citations for every claim" | ID joins (G1–G4). Every sentence cites a passage or a JSON path. The grounding gate suppresses unsupported sentences. | Click a sentence to see the passage, URL and dates, or the endpoint, JSON path and `updated_at`; the Identity panel with IDs |
| Robustness & Edge Cases | Messy data, unformatted inputs, unexpected tool responses | Messy-text intake; typed financing (round, total, secondary); namesake exclusion; handling for 402, 403, 429, partial fetches, redaction and model refusal | A run log of real attempts; the README fixture table |
| Demo Clarity | The video or live presentation shows the workflow's results | A result-first page with plain labels | §10 storyboard; §11 stage script |

---

## 4. Product and service contract

### 4.1 User, commission and positioning

**User:** an associate or analyst at a seed-to-Series-B fund, preparing a partner's first or second founder meeting. They do this weekly. The packet is short and mostly public. The facts in scope — who the founders are and were, and what was raised, when and from whom — are exactly what they check by hand, and errors in them spread into memos and the CRM. Willingness to pay is a hypothesis.

**Commission:** "Prepare the Team & Financing facts for my meeting with ‹Company› from these materials. Tell me what I can reuse as written, what needs correcting or qualifying, and what to ask."

**Positioning:** Crustdata's own Claude plugin ships `/crustdata:meeting-prep`. That skill is a *sales* pre-call brief: it scores leads against an ideal customer profile. Proofroom does something different: it verifies a supplied packet claim by claim, with typed financing and canonical-ID joins, and exports the evidence and versions. It does not claim novelty. It claims precision.

### 4.2 Input contract

| Field | Rule |
|---|---|
| Company domain | Required |
| Documents | 1–3 items, each pasted text or a public `http(s)` URL fetched through Crustdata Web Fetch. ≤6,000 words in total after extraction [T]. Messy text is expected. |
| People | ≤2. A name is required; a profile URL is optional (without one, see S1 in §14). |
| Meeting date | Optional. It is context only and never proves that a fact holds on that date. |
| Focus note | Optional. Priority claims are honored within scope. |

Uploaded or fetched text is evidence, never instructions.

### 4.3 Output contract

`brief.md` has these sections:

1. Header: company, Crustdata ID, review date, version, run mode
2. Reusable sentences
3. Financing events
4. Roles
5. Questions
6. Not checked
7. Limitations
8. Evidence list (URL or endpoint, passage or JSON path, publication/refresh/retrieval dates)
9. Run statistics

`case.json` holds the full case record (§7.4). The case page shows the same version.

**Format illustration.** This is built from the real P1 sources (§9.1). Values in ‹…› come from Crustdata at runtime and have not been observed. It is not a product output.

> **Koah (koahlabs.com): Team & Financing** · reviewed ‹date› · v1 · LIVE · Crustdata company ID ‹G1›
>
> 1. **Supported** · company and investor statements, one announcement, not independent: Koah announced a $20.5M Series A led by Theory Ventures on 24 Feb 2026. [E1][E2] · Crustdata funding record: ‹G4›
> 2. **Supported** · company statement only: Koah's post says Forerunner led its seed round. Neither source gives the seed amount or date. [E1]
> 3. **Supported** · investor statement: Theory's 24 Feb 2026 post names Nic Baird, Mike Choi and Herrick Fang as Koah's three founders. It gives no titles. [E2] · Crustdata founder list: ‹G3› · current roles: ‹G2›
> 4. **Supported** · investor statement: Theory's post says the three founders previously worked together at Affirm, Supermove and Qualified. It does not say who held which role. [E2] · Past-employer ID joins per founder: ‹G2›
>
> | Announced | Event | Amount | Lead | Sources |
> |---|---|---|---|---|
> | not stated | Seed | not stated | Forerunner (company statement) | E1 |
> | 2026-02-24 | Series A | $20.5M | Theory Ventures | E1, E2 (one origin) |
>
> **Question:** What is the total raised to date, including the seed? The sources state only the Series A.
> **Not checked:** customer quotes and product claims.
> **Run:** ‹seconds› s · Crustdata ‹credits from `x-credits-used`› · model ‹tokens› · LIVE

### 4.4 Two definitions of done

- **Delivered (technical).** Every selected claim has a disposition and a rationale. Every emitted sentence passed the grounding gate. Both exports were written, re-read and hash-checked. The version is saved.
- **Useful (product).** The brief contains correct reusable sentences beyond a copy of the input (the T2 gate in §9.3). An all-unresolved brief can be *delivered* but fails *useful*.
- The line "No material discrepancies within the checked scope" may appear only when every selected claim finished a comparable check.

### 4.5 Not in scope

Investment advice, valuation, fraud scoring, legal-entity verification, private revenue or customer checks, headcount and workforce analysis, authenticity scoring, OCR or scanned decks, outreach, CRM writes, monitoring and Watchers, batch jobs, and an MCP server.

---

## 5. Claims and evidence rules

### 5.1 Claim families

| Family | Examples | What must be aligned |
|---|---|---|
| F1 Identity & source attribution | Which company a source concerns; who led a round | Subject ID; asserting party; origin group |
| F2 Dated roles | "Co-founder & CEO"; "ex-Affirm" | Person ID; employer ID; current vs past; dates and their precision |
| F3 Reported financing | Round amount, type and date; lead; total raised; secondary or tender | Event type; amount, currency and magnitude; announced vs closed; lead vs participant |

Selection rules:

- Select up to **5** material atomic claims [T]. Drop to 4 if the T2 timing gate fails.
- Honor the focus note.
- List every other extracted claim as *Not checked*, with a reason.
- Freeze the selection before assessment, and never swap a hard claim for an easier one.
- Fewer eligible claims means a narrower scope. Never pad with trivia.

### 5.2 Status, basis and correction

The ledger stores four things separately:

- **(a)** the original claim's **disposition**: `SUPPORTED`, `CONFLICTING_EVIDENCE`, `INSUFFICIENT_EVIDENCE` or `OUTSIDE_SCOPE`, plus a `qualified` flag;
- **(b)** the **reusable sentence**, which may be narrower than the claim;
- **(c)** its **basis**: `ISSUER_STATEMENT`, `COUNTERPARTY_STATEMENT`, `INDEPENDENT_REPORT`, `INDEXED_RECORD` (Crustdata) or `CALCULATION`;
- **(d)** a **correction reason**, if any: `DATE`, `DEFINITION`, `ATTRIBUTION`, `TITLE`, `ENTITY` or `SCOPE`.

| UI label | Meaning |
|---|---|
| **Supported** | The claim holds as stated, at the basis shown |
| **Supported, corrected** | The original overstated, misdated or misattributed something. The rewritten sentence is supported, and the reason is shown. |
| **Conflicting** | Comparable sources disagree. Both are shown, the claim is not reusable, and a question is raised. |
| **Not established** | Evidence is missing, ambiguous or inaccessible. No factual sentence is written; a limitation is recorded, plus a question if the claim is material. |
| **Not checked** | Outside scope, or not selected |

The basis chip always appears next to the label (for example, "company statement only"). Never show confidence percentages. A company's own page supports "X announced Y". It does not prove audited receipt or give independent confirmation.

### 5.3 Alignment rules, applied before any comparison

**Subject**

- A source supports a claim about the subject only with an explicit match basis: the subject's domain (in `primary_domain` or `all_domains`), a resolved person ID, or specific company-and-person context. Record that basis.
- A publisher's domain normally differs from the subject's domain. That alone is not a mismatch.
- A shared name is never enough. Parents, subsidiaries, brands, acquisitions and rebrands stay separate unless a dated source links them. Never merge financing by name similarity.
- `all_domains` is a provider association, not a legal alias list.

**Time: four clocks**

- Store four times separately: the event or effective date, the publication date, the provider refresh time (`updated_at`), and the retrieval time.
- Unknown stays unknown, and a month-level date stays month-level.
- Web Search results carry no publication date. Take it from the page, or mark it unknown.
- A current profile cannot prove a historical role. A missing end date does not prove continued employment. Concurrent roles and title changes are normal.

**Financing definitions**

- A round is not an extension, a total raised, or a valuation.
- Primary is not secondary: a tender offer is shareholder liquidity, not company capital.
- Announced is not closed, and a lead is not a participant.
- Store the amount text, magnitude and currency separately. One crore is 10,000,000 units. No FX conversion. An unqualified "$" stays as written unless the context fixes the currency.
- Sum only aligned, non-overlapping amounts. An incomplete itemization is not a total. A missing breakdown is "not disclosed", not zero.

**Origins**

- Copies, syndications and aggregator rewrites of one announcement count as one origin.
- A company and its investor announcing the same round are two parties to one announcement, not independent confirmation.
- A company's own page shows what the company claims, nothing more.
- Crustdata's funding fields have undocumented provenance. Matching values mean "consistent with Crustdata's record", never independent corroboration.
- Profiles are largely self-maintained. A founder's bio and profile agreeing are not independent sources.

**Inference limits**

- Employment shows association only. It does not show payroll, exclusivity, authority, contribution, investor representation, layoffs or work location.
- A missing public record never refutes a private fact.
- An empty search, a redaction, a denied field or a failed fetch is an attempt, not evidence.
- A conflict needs two comparable, incompatible propositions about the same subject, event or interval, under the same definition and currency.

**Data is never instructions**

- Text from documents, pages and API responses cannot change policy, tools, credentials or export targets. Both Linear pages (P2) contain text addressed to AI agents, which makes them a natural test.
- Web Search snippets are leads. Results from `sources: ["ai"]` are synthesized and are never evidence.

### 5.4 Grounding gate

1. **Deterministic checks:**
   - Every cited evidence ID exists in the current version.
   - Every number, amount, date, name and title in a sentence matches a value in its cited evidence after normalization. For example, "$20.5M" = 20,500,000 USD, "₹50 crore" = 500,000,000 INR, and dates keep their precision.
   - `INDEXED_RECORD` is never labeled independent.
   - `CONFLICTING_EVIDENCE` needs at least two comparable items from different origins.
2. **Model check:** call 3 checks each sentence for entailment and missing qualifiers.
3. **On failure:** suppress the sentence and record a limitation. Allow one repair attempt if time remains. Neither check proves truth.

---

## 6. Crustdata integration: the verified contract

### 6.1 Request basics

- **Base URL:** `https://api.crustdata.com`.
- **Headers:** `authorization: Bearer $CRUSTDATA_API_KEY`, `x-api-version: 2025-11-01` and `content-type: application/json`. Pin the version.
- **Avoid legacy paths:** the docs list `/screener/*` and `/data_lab/*` as legacy endpoints.
- Keep keys on the server only.

### 6.2 Endpoints used

| Purpose | Call | Request essentials | Response fields used | Cost | Default limit |
|---|---|---|---|---|---|
| Preflight | `GET /account/endpoints` | — | `endpoints[].path/status/effective_rate_limit_rpm`, `fields.enabled/disabled`, `base_credits`, `premium_fields` | free | 300/min |
| Balance | `GET /account/credits` | — | `account.credits` | free | — |
| **G1** subject | `POST /company/identify` | `{"domains": ["koahlabs.com"]}`. One identifier type per request, ≤25 values. Optional `exact_match`. | Top-level array: `matched_on`, `match_type`, `matches[].confidence_score`, `matches[].company_data.crustdata_company_id`, `…basic_info.{name, primary_domain, all_domains, website}` | free | 30/min |
| **G3/G4** company record | `POST /company/enrich` | `{"crustdata_company_ids": [id], "fields": ["basic_info", "funding", "people"]}`. The default is `basic_info` only. | `funding.{total_investment_usd, last_round_amount_usd, last_fundraise_date, last_round_type, investors, funding_rounds}`; `people.{founders, cxos}`; `updated_at`, `indexed_at` | 2 credits per company | 15/min |
| **G2** roles | `POST /person/enrich` | `{"professional_network_profile_urls": [≤25], "fields": ["basic_profile", "experience", "social_handles"]}`. This is the only accepted identifier. The default is `basic_profile` plus `social_handles`, so request `experience`. | `match_status` (matched / not_found / redacted); `crustdata_person_id`; `updated_at`; `experience.employment_details.current[]` and `past[]` (documented keys: `name`, `title`, `crustdata_company_id`, `start_date`); `social_handles.professional_network_identifier.profile_url` | 1 credit per matched profile; experience is included; redacted profiles are not billed | 15/min |
| S1 person without a URL | `POST /person/search` | `{"filters": {"field": "experience.employment_details.current.company_id", "type": "=", "value": id}, "fields": [...], "limit": 50}` | `profiles[]`, `next_cursor`, `total_count` | 0.03 per result, plus 0.1 per result for filtering on experience | 30/min |
| Gap discovery | `POST /web/search/live` | `{"query": "…", "sources": ["news"], "start_date": ‹unix s›, "end_date": ‹unix s›}`; optional `site` | `success`; `results[].{url, title, snippet, source, position}`; `metadata.{failed_pages, empty_pages}`; `timestamp` in ms. No publication date and no entity IDs. | 1 credit per query | 10/min |
| Source passages | `POST /web/enrich/live` | `{"urls": [≤10]}`; optional `human_mode` | An array of `{success, url, timestamp (s), title, content (raw HTML)}`. A failure has `success: false` with every other field null. Order is not guaranteed. | 1 credit per page | 10/min |

**Not used in core:** the authenticity assessment (it needs a field grant and is not material here), Watchers, batch verify, contact enrichment, Job Search, Company Search, and the plan-gated live person and company endpoints.

### 6.3 What the graph decides, and how judges see it

| ID | Decision | Method | Shown as | If missing |
|---|---|---|---|---|
| **G1** Subject anchor | Which company every claim and source is about | Identify by domain. Accept a candidate only if its `primary_domain` or `all_domains` contains the input domain. Keep ties as ambiguous. | Identity panel: input → candidates → accepted ID and match basis; excluded namesakes with reasons | No match or a tie: company-dependent claims become Not established, and the brief is narrowed |
| **G2** Role join | Whether a role is at *this* company (current) or at a named former employer | Person Enrich returns employment entries with `crustdata_company_id`. Compare current entries with the G1 ID. For a former employer named in the packet, resolve its candidates with Identify (by domain, or else by name). Accept the join only if exactly one candidate ID appears in the person's past entries. | "Nic Baird → employer ID ‹x› = subject ID ✔ · title ‹…› · since ‹start_date›" | Profile missing, redacted or without an ID: the role sentence is attributed to the packet only |
| **G3** Founder roster | Whether the founders named in the packet appear in Crustdata's founder list | Company Enrich `people.founders` (shape checked at T1) | "Listed as founder by Crustdata ✔", or "not listed (not a refutation)" | Field empty: no G3 statement |
| **G4** Indexed funding comparison | Whether the packet's round matches Crustdata's funding record | `funding.last_round_*` and `funding_rounds` against the typed packet event | "Consistent with Crustdata's record (updated ‹date›)", or "record differs → question" | Never labeled independent; provenance is undocumented |

A graph decision is **material** only if turning off the graph endpoints would change a subject mapping, or a sentence's status or wording. Displaying an ID is not material.

### 6.4 Errors, retries and usage

| Response | Meaning | Action |
|---|---|---|
| Identify: 200 with `matches: []`, or 404 | No match | Record the attempt. Never conclude that the company doesn't exist. |
| 400 | Bad request: mixed identifier types, more than 25 values, or a URL without a scheme | Fix it; no retry |
| 401 | Missing or invalid key | Stop. The run FAILS. |
| 402 `insufficient_credits` | Terminal | Stop retrieval and deliver a narrowed brief with a limitation |
| 403 `permission_error` | An endpoint or field is denied. Field denials list `metadata.denied_fields` and `permitted_fields`. | Optional field: drop it and retry once. Core endpoint: integration is blocked (FAILED-core). |
| 429 `rate_limit_error` | Over the limit | Wait `x-ratelimit-reset` seconds plus jitter. At most 3 tries within the run deadline. |
| 5xx or timeout | Provider error (the docs give no guidance) | One retry if the deadline allows; otherwise record a limitation |

- **Usage:** record `x-credits-used` from every response (it reports the exact credits deducted) and show the total for each run. If the header is missing, show "unknown", never 0.
- **Error body:** `{"error": {"type", "message", "metadata"}}`. Parse it defensively.

### 6.5 Per-run budget and rate-limit plan

**Per run [T]:**

- Identify: ≤2 calls (the subject, then former employers)
- Company Enrich: 1 call
- Person Enrich: 1 call (≤2 URLs)
- Web Search: ≤2 queries
- Web Fetch: ≤2 requests (≤3 packet URLs and ≤3 gap pages), plus one `human_mode` retry

The worst case is about **13 credits** (S1 adds about 6.5). Credits are not the constraint. The per-endpoint rate limits are: web search and fetch allow 10 requests per minute, probably shared by the whole team's key (U7).

**Rules:**

- Keep one shared on-disk response cache for development, keyed by (endpoint, request-body hash, API version).
- Put all fetch URLs in a single request.
- Run a limiter for each endpoint.
- Make one person the designated evaluation runner.
- Turn the cache **off** for the recorded unseen run and for the finals.

---

## 7. Architecture

### 7.1 Stack and environment

- **Python:** 3.12 or newer, decided per laptop at 10:30. On this laptop, `python` is 3.14.7 and `py -3.12` is 3.12.2. Create the venv with an explicit interpreter. Prefer 3.12 for wheel availability; 3.14 is fine if `pip install` succeeds.
- **Libraries:** FastAPI and Uvicorn; a Jinja2 server-rendered page with about 50 lines of vanilla-JS polling; Pydantic v2; HTTPX (async, with explicit timeouts); BeautifulSoup4 for HTML → text; the standard library's SQLite and `Decimal`; the official `anthropic` Python SDK.
- **Not used:** a React build, an ORM, a queue, a graph database or an agent framework.
- **Location:** put the repo and `data/` **outside OneDrive** (for example `C:\dev\proofroom`). OneDrive sync can lock or roll back files mid-write, and SQLite in synced folders is a known corruption risk.
- **Pinning:** pin dependency versions in `requirements.txt` at 10:30.

### 7.2 Pipeline

```
request ─► 1 Intake ────────────► 3 Extract & select ─► 4 Gap retrieval ─► 5 Assess ─► 6 Check ─► 7 Publish
  │        paste or Web Fetch       model call 1          Identify former     model     rules +    brief.md,
  │                                                       employers; Web      call 2    call 3     case.json, vN
  └──────► 2 Resolve: Identify → Company Enrich ∥ Person Enrich ──┘  Search and Fetch
```

| # | Stage | Calls | Budget [T] |
|---|---|---|---|
| 1 | Intake: validate input, fetch URL documents, convert HTML to text, hash | Web Fetch ×1 (≤3 URLs) | ≤10 s |
| 2 | Resolve: starts at t = 0, in parallel with stage 1 | Identify, then Company Enrich and Person Enrich in parallel | ≤8 s |
| 3 | Extract and select: starts when the text is ready | Model call 1 | ≤15 s |
| 4 | Gap retrieval: material gaps only, with no new retrieval after 40 s | Identify former employers; Web Search ≤2; Web Fetch ×1 | ≤12 s |
| 5 | Assess | Model call 2 | ≤20 s |
| 6 | Check: deterministic gate, then model call 3; one repair if time allows | Model call 3 | ≤10 s |
| 7 | Render, write, read back, publish | — | ≤3 s |

The critical path adds up to about 70 s. Every call's timeout comes from the time left before the 100-second hard stop.

### 7.3 Model calls (settings verified against the API reference)

**Model choice.** Use `claude-sonnet-5-5` ($2 / $10 per million input / output tokens; 1M context; supports structured outputs). It is chosen for speed inside a ≤70 s pipeline; T2 verifies that its quality is adequate.

- **Escalation:** if T2 shows reasoning errors, run call 2 alone on `claude-opus-5-5` ($4 / $20) at `low` effort, then re-time. On Opus 5.5, thinking cannot be disabled and the default effort is `medium`, so set it explicitly.
- Do not switch models after the 14:00 freeze.

**Settings:**

- **Structured JSON** through `output_config.format`, or the SDK's `messages.parse` with Pydantic models.
  - Every object needs `additionalProperties: false`.
  - No recursive schemas.
  - No min/max or length constraints; the SDK strips them and validates on the client.
- **Effort** (`output_config.effort`): start at `low` for calls 1 and 3 and `medium` for call 2. Measure latency at T1 and quality at T2, adjust once, then freeze.
- **Thinking:** leave the adaptive default.
  - `{"type": "between_tools"}` turns thinking off on Sonnet 5.5.
  - It is valid only at effort ≤ `high`, and with no other thinking fields.
  - Use it only if T1 latency requires it.
- **Never send:**
  - `temperature`, `top_p` or `top_k`. Non-default values return a 400 on Sonnet 5.5, and API version `2026-10-21` removes them entirely.
  - A forced `tool_choice` (400).
  - An assistant prefill (400).
  - API citations. They are incompatible with structured outputs (400); the app renders its own evidence links.
- **`max_tokens`:** set it generously (about 8,000). Truncation is a failure; latency is controlled by effort and timeouts. Check `stop_reason` for `max_tokens` and `refusal` before parsing. A refusal is a failed stage, never a finding.
- **Timeouts:** create the SDK client with `max_retries=0` (or 1) and pass a per-call `timeout` derived from the deadline. The SDK default retries twice, and retried timeouts can blow the deadline.
- **Schema warm-up:** a new schema compiles on first use and is then cached for 24 hours.
  - Run each of the three fixed schemas once on a development packet after each restart.
  - Disclose this in the README.
  - Never warm up with an unseen packet.
- **Cost:** about 25k input and 4k output tokens per run, which is roughly $0.10 [T]. Record `usage` for every call.

**The three calls.** Design them tonight as prose; type them in after 10:30.

| Call | Input | Output schema (essential fields) |
|---|---|---|
| 1 Extract and select | Numbered documents, the focus note, scope rules | `claims[]: {id, doc_id, quote, family, predicate, subject, object, amount_text, currency_text, date_text, title_text, qualifiers[], materiality, selected, exclusion_reason}` |
| 2 Assess | Frozen claims; an evidence table (ID, kind, source, subject mapping, excerpt or JSON path = value, four clocks, origin group); the rules | `findings[]: {claim_id, disposition, qualified, basis, sentence, evidence_ids[], as_of, correction_reason, limitation, question}` |
| 3 Check | Each emitted sentence with only its cited evidence | `checks[]: {claim_id, entailed, missing_qualifier, unsupported_fragment}` |

**Local validation:**

- `quote` must be a verbatim substring of its document, and the app computes the span offsets itself. Never ask the model for offsets.
- Every evidence ID must exist in the current snapshot.
- Fields use enums only.
- Case-specific IDs never go into schema enums, because changing the schema forces a recompile.

### 7.4 Records

| Record | Essential content |
|---|---|
| Case | ID, request, domain, meeting date, current version |
| Document | ID, version, source (paste or URL), text, hash, active or withdrawn |
| Entity | Input identifier, candidates, accepted Crustdata ID, match basis |
| Claim | ID, document span, quote, typed fields, selected or excluded (with reason) |
| Evidence | ID; kind (passage or API field); URL, or endpoint plus JSON path; value; subject mapping; four clocks; origin group |
| Attempt | Endpoint or model, request hash, status or error type, latency, `x-credits-used` or token usage, mode (LIVE / CACHED / FIXTURE) |
| Finding | Claim ID, disposition, `qualified`, basis, sentence, evidence IDs, correction reason, limitation, question |
| Version | Case ID, number, parent, active documents and identity pins, findings snapshot, diff from the parent, status |
| Artifact | Version, path, SHA-256, read-back result |

### 7.5 Versions, revisions and publication

- **Revision is a whole-case rerun** on the changed packet. Must-ship: add or remove a document. Should-ship: identity pin, refresh.
  - The selected claims stay frozen.
  - If a document is withdrawn, its claims remain as audit stubs.
  - Removed URLs are excluded from later retrieval.
- **Diff:** for each claim, the old and new status and sentence, plus the cause.
- **Publish:**
  1. Write `brief.md` and `case.json` into `data/cases/<id>/v<n>/`.
  2. Re-read both files, parse them, and check the IDs and SHA-256 hashes.
  3. In one SQLite transaction, insert the version row and move the case's current pointer.
  4. If any step fails, the previous version stays current and a FAILED attempt is recorded.
  5. Old versions are never edited.
- **Idempotency:** allow one active run per case (enforced by a SQLite unique constraint). An identical resubmission returns the existing version, matched by request hash. That is enough for a single-process app.

### 7.6 Run modes and the repository

- **Modes:**
  - **LIVE** makes real calls.
  - **CACHED** uses development cache hits, labeled on each attempt.
  - **FIXTURE** replays recorded responses and needs no keys, so judges can run `python -m proofroom run --fixture koah`.
  - Every screen and export shows the mode.
- **Fixtures** keep only the fields the app reads: names, titles, employer IDs and dates. No locations, summaries or contact data. Fault fixtures use synthetic people.
- **README:**
  - the problem and the video link;
  - a quickstart, with `.env.example` listing variable names only;
  - FIXTURE mode;
  - the architecture;
  - the Crustdata endpoints used, and why;
  - the evidence rules;
  - an evaluation table with denominators;
  - limitations;
  - the unseen-run protocol, with a link to the raw capture.
- **Secrets:** `.env` is git-ignored, and the repository is scanned for keys before submission.

---

## 8. Failure handling

| Condition | Behavior | Result |
|---|---|---|
| Company: no match or a tie | Keep the candidates. Company-dependent claims become Not established, and an identity question is raised. | DELIVERED · NARROWED |
| Namesake source | Exclude it, with the reason. Legitimate third-party publishers stay. | — |
| Person `not_found` | Role claims are attributed to the packet only | DELIVERED |
| Person `redacted` | Respect it: no alternative lookups. Those claims become Not checked. | DELIVERED |
| Optional field denied | Drop the field, retry once, record a limitation | DELIVERED |
| Core graph endpoint denied or unavailable | Produce a packet-only recovery brief, clearly labeled, and escalate to the organizers | FAILED (core) |
| 402, out of credits | Stop retrieval and list what was left unchecked | NARROWED |
| 429 | Wait for the reset plus jitter; at most 3 tries within the deadline | — |
| Partial or thin fetch | Continue. List failed URLs (requested minus succeeded). One `human_mode` retry. | — |
| 100 s deadline | Retrieval stops at 40 s. Unfinished claims are "check incomplete", never "no discrepancies". | NARROWED |
| Model refusal, `max_tokens` or invalid JSON | One repair attempt if time allows; otherwise the stage fails | FAILED |
| Grounding failure | Suppress the sentence and record a limitation | — |
| Export or read-back failure | The previous version stays current | FAILED |
| Instructions inside documents | Treated as data only | — |
| Non-`http(s)` URL | Rejected at intake | — |

---

## 9. Evaluation, sized for five hours

### 9.1 Development packets (already seen, so never "unseen")

These were checked against the live pages on 30 Oct 2026. They are public assertions, not audited facts.

| ID | Sources | Verified content | What it tests |
|---|---|---|---|
| **P1 Koah** | Koah's Theory Ventures partnership post; tomtunguz.com/koah-theory | Both are dated 24 Feb 2026: a $20.5M Series A led by Theory Ventures, with Forerunner and South Park Commons participating. The company post says Forerunner led the seed (no amount or date) and names no founders. The investor post names three founders (Nic Baird, Mike Choi, Herrick Fang) without titles, and says they previously worked together at Affirm, Supermove and Qualified. | Origin dependence (company plus investor = one announcement); round vs total (the total is not stated); G2 former-employer joins; a compound, collective claim |
| **P2 Linear** | linear.app "Building our way" (10 Jun 2025); "Sharing growth with the people building Linear" (26 Aug 2026) | An $82M Series C at a $1.25B valuation, including primary and secondary, led by Accel. Later, a $99M employee tender at $2.5B, with no new primary capital. | Primary vs secondary; valuation ≠ capital; no false sums; agent-directed text on both pages |
| **P3 Attio** | attio.com Series B post (plus its developer-platform post) | Published Aug 2025, updated Aug 2026: a $52M Series B led by GV; total raised $116M; Nicolas Sharp, CEO & co-founder | Round vs total; the page-update clock; title at a date |

At T1, add one founder profile URL for each packet. That URL is human-supplied input.

### 9.2 Logic and fault fixtures (labeled SYNTHETIC)

| # | Fixture | Expected outcome |
|---|---|---|
| F1 | Namesake source | Excluded, with reason |
| F2 | Former, current and concurrent roles | Temporal qualification, not a conflict |
| F3 | Copied announcement | One origin |
| F4 | Private revenue claim | Not checked |
| F5 | 403 on an optional field, with `denied_fields` | Field dropped and limitation recorded |
| F6 | 429 with a reset header | Waits, then succeeds |
| F7 | Partial, reordered fetch with a null-URL failure | Correct URL association and the failed URL listed |
| F8 | Redacted person | Respected, with no workaround |
| F9 | Injected instructions | Policy unchanged |
| F10 | Export failure | Never shown as delivered |
| F11 | ₹ crore plus an unknown currency | Magnitude normalized, currency kept separate |
| F12 | Identify returns no match (empty 200, and 404) | Narrowed brief, never "doesn't exist" |

### 9.3 Gates

| Gate | When | Pass condition | If it fails |
|---|---|---|---|
| **T1** Access and shapes | 10:30–10:50 | Permissions and credits read. Identify and Enrich run on P1. Person Enrich on one profile answers whether past entries carry `crustdata_company_id` and dates. One fetch and one call per schema succeed. Timings are recorded. | Core endpoint denied: escalate. No past IDs: G2 covers current roles only. Thin fetch: paste text first. |
| **T2** Usefulness | by 12:10 | P1–P3 run through the vertical slice. At least 3 correct reusable sentences in at least 2 of the 3 packets. Zero wrong subjects. Zero false conflicts or sums. At least one material graph decision across the set. Runtime ≤100 s. | Missing data: narrow the families. Bad reasoning: fix rules and prompts before UI work. Too slow: 4 claims, then 1 person, then fewer fetches. |
| **T3** Robustness and revision | by 13:20 | F1–F12 produce their expected outcomes. Add/remove revisions change only the affected claims, and no stale line remains in any export. | Revision failing: ship add-only, or cut revision. Fixtures failing: fix them before the freeze. |

### 9.4 Metrics

Always report denominators. These are not accuracy claims.

- sentences emitted, supported and suppressed;
- wrong-entity acceptances;
- false conflicts and false sums;
- unnecessary abstentions on positive controls;
- revision consistency;
- runtime;
- Crustdata credits;
- model tokens;
- the mode of each run.

### 9.5 Comparisons (should-ship)

- **Same-evidence baseline.** Give `claude-sonnet-5-5` the identical evidence bundle and a competent prompt asking for a cited Team & Financing brief. Count these error classes:
  - wrong subject;
  - an announcement stated as fact without attribution;
  - round/total confusion;
  - copies counted as corroboration;
  - stale tense.

  Report wins, ties and losses honestly. A tie removes any superiority claim.
- **Graph ablation.** Run Proofroom with Identify, Company Enrich, Person Enrich and Person Search turned off; Crustdata Web Search and Fetch stay on. Count the changed subject mappings and sentence statuses. If nothing changes, do not claim the graph is essential; narrow the claims to where it matters.

---

## 10. The two-minute video

### 10.1 Unseen-request protocol

Write this into the README before 14:00.

1. **Select after the freeze, by a fixed rule.** After the 14:00 freeze, the recorder runs a predeclared public news search for funding announcements from the past 14 days. Take the first result that:
   - (a) is not P1–P3 or any company touched during development;
   - (b) has a company domain;
   - (c) names at least one founder whose public profile URL can be found;
   - (d) has a second public source, such as an investor post or a news article.
2. **Line up three candidates.** Pick three candidates this way, and use them in order.
3. **Show the proof on screen.** Show the selection, an empty case list for that domain, and the wall clock. Record the first product run unedited, and keep the raw file.
4. **Handle a failed run honestly.** A failed run stays in the record. The retake uses the next candidate and says so on screen. Nothing for that company may come from the cache, a fixture or a prior run.

"Unseen" means never processed by Proofroom or used for tuning. It does not mean unknown to model training.

### 10.2 Storyboard

| Time | On screen | Label |
|---|---|---|
| 0:00–0:10 | The problem in one sentence, then the request form with the packet and profile; click Prepare | FIRST RUN · selected after freeze at ‹time› |
| 0:10–0:30 | Live progress: domain → Crustdata company ID; founder → person ID → employer join; claims selected and not checked | LIVE · real clock |
| 0:30–0:55 | Retrieval and assessment progress, while narrating one rule (round ≠ total, or one announcement ≠ two sources). If the run passes about 45 s, cut, with "⏩ wait shortened, actual X s" on screen. | LIVE |
| 0:55–1:25 | The brief: sentences with labels. Open one: the passage highlighted, with URL and dates. Open a G2 join: the JSON path and `updated_at`. | RESULT |
| 1:25–1:45 | One correction or qualification, if the run produced one. Otherwise, "No material discrepancies within the checked scope" and the not-checked list. | RESULT · nothing planted |
| 1:45–2:00 | The downloads (`brief.md`, `case.json`), run statistics (time, credits, tokens, LIVE) and the evaluation card (fixtures passed; development metrics with denominators) | VERIFIED ARTIFACTS · PREVIOUSLY RECORDED EVALUATION |

Revision is not shown live in the video. It appears in the evaluation card and the README, and stays available for the finals.

### 10.3 Honesty rules

- Never call cached, fixture or replayed output live.
- Never plant claims about real companies.
- Never hide human steering.
- When time is compressed, show the actual wall time.
- Keep every attempt.

---

## 11. Live finals plan (new)

The brief gives no format or duration for the finals. Ask at the 09:30 briefing. Code freezes at 15:30, so the finals use exactly the submitted build.

| Time | Action |
|---|---|
| 15:30–16:30 | Build the stage kit: two fresh eligible packets selected by the §10.1 rule (not yet run); the recorded unseen run; an exported brief open in a tab; `.env` loaded; cache off; schemas warmed on a development packet; laptop charger and phone hotspot; the display tested at 125–150% zoom |
| 16:30–17:00 | Rehearse three times against a timer: a 45-second pitch → a live run on a stage packet (narrate the Identity panel while it runs) → open one cited sentence → a 15-second close (evaluation numbers and limits) |
| 17:00 | Finalists announced |
| 17:30 | Finals |

**If a judge names a company:** accept a domain plus one public link through URL intake. The founder profile URL is optional if S1 shipped. If no link is available and S2 did not ship, find the announcement by hand on stage. That is preparing the request, not steering the run.

**If the network or an API fails on stage:** say so. Switch to the recorded run and show the FIXTURE replay, labeled as such.

**Q&A preparation:**

- *"How do you know it's right?"* The grounding gate, the fixture results and the stated limits.
- *"What does Crustdata add?"* G1–G4 and the ablation result.
- *"Isn't this just a chatbot with search?"* The same-evidence baseline result, typed financing, ID joins and versioned exports.
- *"Who pays?"* Fund associates and platform teams. Say plainly that demand is a hypothesis.

---

## 12. Schedule

### 12.1 Tonight (30 Oct): content and design only

1. Confirm the team's registration on the official Y Combinator event platform (rule 1).
2. Assign provisional roles; they become final at 10:00.
3. Write the prompt text and the three schema designs (§7.3) as prose in a notes file. No code.
4. Copy the P1–P3 source texts and URLs into a notes file. Write the expected ledger for each, meaning what a correct run should say.
5. Write the fixtures F1–F12 as tables.
6. Draft the README outline, the unseen-selection rule, the video narration and a 45-second pitch.
7. Check every laptop: Python version, a working `pip`, a screen recorder that captures 1080p with the microphone, and GitHub access.
8. Check that the Anthropic API key is active and has credit. A one-line access check is environment setup, not product code.
9. Create an empty repository folder outside OneDrive.

### 12.2 Event day (31 Oct, IST)

| Time | Work | Exit condition |
|---|---|---|
| 09:00–10:00 | Doors, kickoff, theme briefing. Ask about the finals format, the unseen protocol, the submission form and repository visibility. | Answers noted |
| 10:00–10:30 | API walkthrough and team formation. Choose the §13 role plan and get the key. Ask whether the key is per team, whether the web endpoints are enabled, and about rate limits and credits. | Team and key |
| 10:30–10:50 | **T1** (A and B). C: repository, venv, records, export writer. D: input page and progress view. | T1 result recorded |
| 10:50–11:35 | Vertical slice through the CLI: P1 → resolve → extract → assess → verified `brief.md` and `case.json` | First DELIVERED case |
| 11:35–12:10 | Alignment rules, gap retrieval, grounding gate; **T2** on P1–P3 | T2 decision |
| 12:10–12:50 | Case page (brief, evidence drawer, Identity panel, run log); add/remove revision with diff | Page usable; revision works on P1 |
| 12:50–13:20 | **T3**: fixtures F1–F12, FIXTURE mode, revision checks | T3 pass |
| 13:20–14:00 | Fix defects; fill in README results. At the 13:30 mentor checkpoint, show a live run. Run the baseline and ablation if green. | Ready to freeze |
| **14:00** | **Feature freeze.** Correctness fixes only, and each fix reruns the affected tests. | — |
| 14:00–14:30 | Clean-clone setup test (FIXTURE without keys, and LIVE); secrets scan; a rehearsal on a non-candidate packet; select three unseen candidates | The clean clone runs |
| 14:30–15:00 | Record the unseen run; edit it to 2:00 with labels; upload | Video link |
| 15:00–15:20 | Last call: final README, commit hash, repository access check, submit | Submission receipt |
| 15:20–15:30 | Buffer | Official deadline 15:30 |
| 15:30–17:30 | Finals preparation (§11) | Stage kit ready |

The 12:30 lightning talks are optional. Don't let them stall the critical path.

---

## 13. Team roles (decide at 10:00)

| Team size | Split |
|---|---|
| 4 | **A Data:** adapter, limiter and cache, G1–G4, T1 · **B Reasoning:** prompts and schemas, assessment, grounding · **C State:** records, versions, exports, revision, FIXTURE mode · **D Product:** page, evaluation harness, README, video, submission, pitch |
| 3 | A Data + State · B Reasoning · C Product + Evaluation |
| 2 | A Data + State · B Reasoning + Product |
| 1 | CLI, `brief.md`/`case.json` and a minimal page; 4 claims; 1 person; paste or URL; add-document revision; P1–P2 plus fixtures F5–F8 and F10; the same gates and honesty rules |

---

## 14. Scope tiers, cut order and triggers

**Must-ship:**

- intake (paste and URL);
- G1 and G2, plus the G4 display;
- extraction and selection;
- the alignment rules;
- assessment;
- the grounding gate;
- exports with read-back;
- versioned add/remove revision;
- the §8 failure handling;
- the run log and run modes;
- FIXTURE mode;
- a README with results;
- the unseen recording.

**Should-ship:**

- **S1** person lookup without a profile URL;
- **S3** the same-evidence baseline;
- **S4** the graph ablation;
- **S5** identity-pin revision;
- **G3** the founder roster, if T1 shows the data.

**Stretch** (only if T2 passed by 12:10 and the team is on time at 13:20):

- **S2** domain-only packet assembly. Use Company Enrich `news` if T1 shows article URLs; otherwise one news search plus the top two fetches.
- Text-PDF upload.

**Never:** OCR, headcount or workforce, authenticity scoring, valuation, revenue or customer verification, outreach, CRM, Watchers, an MCP server.

**Cut order:**

1. S2
2. PDF upload
3. S5
4. S4
5. S3
6. S1
7. The second person
8. Page polish (fall back to rendered Markdown)
9. The remove path of revision (keep add)

**Never cut:** the G1/G2 joins, the evidence rules, the grounding gate, verified exports, honest labels, the unseen first-run capture, and the README's setup and results.

| Trigger | Decision |
|---|---|
| No verified export by 11:35 | Stop UI work; finish the CLI-to-export path |
| T2 fails on data | Narrow to financing plus current roles that have data |
| T2 fails on reasoning | Fix the rules and prompts before any UI work |
| Run longer than 100 s | Cut to 4 claims, then 1 person, then skip gap search, then fewer fetches. Never drop the checks. |
| Core endpoint denied | Escalate at once. A packet-only summary does not meet the brief. |
| Behind at 13:20 | Drop the should-ship items and freeze at 14:00 regardless |

---

## 15. Unknowns and decisive tests

| ID | Unknown | Why it matters | Test | Fallback |
|---|---|---|---|---|
| U1 | Event-key entitlements and per-key restrictions | Core path | T1: `/account/endpoints` | Escalate |
| U2 | Whether past entries carry `crustdata_company_id`, title and dates (the docs example shows `past: []`) | G2 for former employers | T1, on two profiles | G2 for current roles only |
| U3 | `funding_rounds` and `investors` sub-fields, and their provenance | G4 | T1 | Show only the totals and last round, as "consistent with record" |
| U4 | The shape of `people.founders` | G3 | T1 | Skip G3 |
| U5 | Graph coverage of small or new startups | Quality of the unseen run | T2 and the selection rule | An honest narrowed brief |
| U6 | Web Fetch quality on the target sites (raw HTML; JavaScript-heavy pages) | Source passages | T1 on P1–P3 | `human_mode` retry; paste the text |
| U7 | Whether rate limits apply per key or per account, and team contention | Development speed | Ask at 10:00; read the response headers | Shared cache and limiter |
| U8 | Model latency at the chosen effort | The 70 s target | T1 timings | Lower effort, `between_tools`, fewer claims |
| U9 | Usefulness on natural packets | Product value | T2 | Narrow the families |
| U10 | Whether the graph is material | Fit with the criterion | T2 and the S4 ablation | Narrow claims to where IDs matter |
| U11 | The finals format, and whether judges supply input | Stage plan | Ask at 09:30 | A stage kit for both cases |
| U12 | Details of the unseen protocol | Validity of the submission | Ask at 09:30 | The §10.1 default |

---

## 16. Verification ledger

**Status key:**

- **Verified:** the source says what the plan says.
- **Added:** the source says it, and the original plan omitted it.
- **Corrected:** the plan was wrong or unclear.
- **Open:** it needs a runtime test.
- **Not reproduced:** a claim that this audit's checks contradicted.

**Event (official PDF):**

| # | Claim | Status | Basis |
|---|---|---|---|
| V1 | Coding runs 31 Oct 2026, 10:30–15:30, IST | Verified | pp. 3–4. No timezone is printed; IST is inferred from IIT Bombay. |
| V2 | Crustdata identity-graph integration is mandatory | Verified | p. 2; rule 3 |
| V3 | A repository plus a 2-minute video of a never-seen request reaching finished work | Verified | p. 2; rule 5 |
| V4 | Four criteria, unweighted | Verified | p. 3; no weights are given |
| V5 | No interaction with external real people | Verified | Rule 4 |
| V6 | Preparation is allowed; coding starts at 10:30 | Verified | Rule 2 |
| V7 | Optional mentor checkpoint at 13:30 | Verified | p. 4 |
| V8 | Video review 15:45, finalists 17:00, live finals 17:30 | Added | pp. 3–4; missing from the original |
| V9 | API walkthrough and team formation at 10:00; teams of up to 4 | Added | p. 3 |
| V10 | Base URL `https://api.crustdata.com`; CLI and MCP modes allowed | Added | pp. 2–3 |
| V11 | $1,500 in Crustdata credits per team | Added | p. 5 |

**Crustdata (documentation checked on 30 Oct 2026):**

| # | Claim | Status | Basis |
|---|---|---|---|
| V12 | `authorization: Bearer` and `x-api-version: 2025-11-01` | Verified | PDF p. 3; API introduction |
| V13 | `GET /account/endpoints` shows enabled endpoints and fields | Verified | Free; 300/min; `fields.enabled/disabled`; effective rpm |
| V14 | `GET /account/credits` | Verified | Free; `account.credits` |
| V15 | `POST /company/identify` resolves a domain or name | Verified | Free; 30/min; ≤25 values; one identifier type per request; no match returns 200 with empty `matches`, or 404 |
| V16 | Company Enrich returns limited sections by default | Verified | The default is `basic_info`; 2 credits per company; 15/min; funding keys as in §6.2; `funding_rounds` sub-fields undocumented (Open, U3) |
| V17 | Person Enrich by profile URL | Verified | `professional_network_profile_urls` is the only identifier (≤25); the defaults are `basic_profile` and `social_handles`; `experience` must be requested; 1 credit per match; 15/min; redacted profiles are not billed |
| V18 | The shape of past roles | Open | The docs example shows `past: []`. The documented current keys are `name`, `title`, `crustdata_company_id` and `start_date`. |
| V19 | Authenticity sits at `person_data.assessment.authenticity` and needs a permission | Verified | It holds `verdict` and `tier`; without the grant, a 403 says "Access denied to fields: assessment" |
| V20 | `urn_url` | Corrected (removed) | Not found in the current docs. URN-form profile URLs are accepted as input, and the core does not need the field. |
| V21 | `POST /person/search` | Verified | Filter syntax as in §6.2; 0.03 per result plus premium groups; 30/min; no `contains`; `=` matches the whole value |
| V22 | `POST /web/search/live` | Verified and Added | 1 credit per query; 10/min; no publication date or entity IDs. Added: `start_date`, `end_date` and `site` filters. |
| V23 | Web Fetch per-item failures and reordering | Verified | ≤10 URLs per request; raw HTML; a failure has `success: false` with null fields; 1 credit per page; 10/min |
| V24 | The permissions response governs fields | Verified | A 403 `permission_error` lists `denied_fields` and `permitted_fields` |
| V25 | Error semantics | Added | The envelope `{error: {type, message, metadata}}`; 402 and 403 are terminal; retry only 429, after `x-ratelimit-reset` |
| V26 | Credits used per call | Added | The `x-credits-used` response header |
| V27 | Data freshness | Verified | Profiles are refreshed at least every 30 days; `updated_at` is the last refresh; funding provenance is undocumented |
| V28 | "Live endpoints are enterprise-only" (API introduction) | Corrected (clarified) | Web search and fetch are available on self-serve and enterprise plans. The person and company live endpoints are plan-gated, and Proofroom does not use them. |
| V29 | The credit-to-dollar conversion | Open | Not published. Read the balance at 10:30. |
| V30 | Crustdata ships a meeting-prep skill (later chain) | Verified, with a caveat | It is a sales pre-call brief that scores leads against an ICP, not investor claim verification |

**Anthropic (bundled API reference):**

| # | Claim | Status | Basis |
|---|---|---|---|
| V31 | `claude-sonnet-5-5` is valid (later chain) | Verified | $2 / $10 per million tokens; 1M context; 128K output |
| V32 | API version `2026-10-21` (later chain) | Verified | Under it, `temperature`, `top_p` and `top_k` return a 400 on every model |
| V33 | Structured outputs through `output_config.format` | Verified | `additionalProperties: false`; no recursion; no numeric or length constraints |
| V34 | API citations conflict with structured outputs | Verified | The combination returns a 400 |
| V35 | Schemas add first-use latency | Verified | A one-time compile per new schema, then a 24-hour cache |
| V36 | `between_tools` turns thinking off on Sonnet 5.5 | Verified | Valid only at effort ≤ `high`, with no other thinking fields |
| V37 | Forced `tool_choice` and prefill are rejected | Verified | Both return a 400 |
| V38 | Output caps of 900/1,800/600 tokens including thinking (later chain) | Corrected | Truncation risk. Use a generous `max_tokens`, effort and deadlines instead. |

**Packets and environment:**

| # | Claim | Status | Basis |
|---|---|---|---|
| V39 | Koah facts | Verified | Both posts are dated 24 Feb 2026: a $20.5M Series A led by Theory Ventures; Forerunner led the seed (no amount or date); the company post names no founders; the investor post names three, with no titles |
| V40 | Linear facts | Verified | 10 Jun 2025: an $82M Series C at $1.25B, primary plus secondary, led by Accel. 26 Aug 2026: a $99M tender at $2.5B with no new primary capital. |
| V41 | Attio facts | Verified | Published Aug 2025, updated Aug 2026: a $52M Series B led by GV; $116M total; Nicolas Sharp, CEO & co-founder |
| V42 | Natural pages contain agent-directed instructions | Added | The fetch tool reported such text on both Linear pages |
| V43 | "Locally verified bundled Python 3.12.14" (later chain) | Not reproduced | On this laptop, `python` is 3.14.7 and `py -3.12` is 3.12.2 |
| V44 | The ablation "removes only Crustdata and keeps the web budget" (later chain) | Corrected | Web Search and Fetch are Crustdata endpoints. Disable only the graph endpoints. |

---

## 17. What changed

### 17.1 Against the original `Proofroom_Final_Project_Plan.md`

| Original section | v1 decision | Why |
|---|---|---|
| §1 Product: a meeting memo, with "reasoned correction" as the distinctive behavior | A Team & Financing brief of reusable, cited sentences. Corrections appear when the evidence requires them, and revision is proven in tests. | The criteria weight graph use and citations. A clean natural packet still yields value, and the unseen packet may contain no correction. |
| §2 Contract: memo, ledger, manifest, questions, history | The same artifacts, led by reusable sentences; 0–3 questions; "delivered" kept separate from "useful" | Reuse value; no padding |
| §3 Scope: ≤6 claims, ≤3 documents, text PDFs, 12,000 words | ≤5 claims (4 if slow); 1–3 documents as text or URLs; ≤6,000 words; PDFs as stretch | The five-hour build, the 70 s run, and URL input for the stage |
| §4 Claim families | F1 identity & source attribution, F2 dated roles, F3 reported financing, now with secondary/tender typing and valuation kept separate | "Company context" is not a checkable claim. Linear-style packets need primary/secondary typing. |
| §5 A six-area workspace | One case page (brief, evidence drawer, Identity panel, run log, versions, downloads), plus a CLI | Build time. The CLI serves evaluation and judges. |
| §6 An eleven-step workflow | Seven timed stages (§7.2) | Runtime control |
| §7 Evidence rules | Kept. Added: four clocks, financing typing, the company-plus-investor origin rule, the AI-search exclusion and deterministic grounding | Edge cases verified in P1–P3 |
| §8 React/TypeScript plus FastAPI; a dependency-invalidation engine; Dependency and Memo-sentence records | One FastAPI app (Jinja2) plus a CLI; whole-case rerun; nine records | Less to build, and no class of stale-state bugs |
| §8 No model named | `claude-sonnet-5-5` with three structured calls and verified settings | Avoids 400 errors and latency surprises |
| §9 An endpoint list | A verified contract: defaults, limits, costs, errors and the credits header; G1–G4 decisions | Correctness and fit with the criterion |
| §10 Delivery and failure table | Kept, and mapped to the verified HTTP semantics | The Robustness criterion |
| §11 Deliverables | Kept. Added: FIXTURE mode, the CLI, the raw capture and a clean-clone test | Judges without keys |
| §12 Evaluation | Development packets P1–P3 (verified), fixtures F1–F12, gates T1–T3, a same-evidence baseline and a corrected ablation | Feasible in five hours |
| §13 Demo | A storyboard that fits the runtime, plus the unseen protocol | A2, A7 |
| §14 Schedule, with a freeze at 14:15 | Freeze at 14:00; submit by 15:20; finals preparation 15:30–17:30; a tonight checklist | A1 and buffer |
| §15 Decisions at limits | Kept. Added triggers for the finals, team size and rate limits | — |
| §16 Definition of a strong submission | Mapped to the four criteria (§3) | Judges score against the criteria |

### 17.2 Against the later chain (V1 → V2 → V3 → Final Winning Plan)

| Later-chain decision | In v1 | Reason |
|---|---|---|
| Team & Financing focus; reusable attributed wording; disposition separate from basis | Adopted | Sound |
| Four clocks; financing typing; origin groups | Adopted | Verified on P1–P3 |
| Whole-case rerun; immutable versions; read-back before publishing | Adopted, simplified | Sound |
| Server-rendered Python stack | Adopted | Build time |
| `claude-sonnet-5-5`; API `2026-10-21`; no sampling parameters or forced tools | Adopted | Verified |
| 70 s target and 100 s hard stop; T1/T2/T3; a 14:00 freeze; post-freeze unseen selection; honest labels | Adopted | Sound |
| A four-claim cap | Changed to five (four if slow) | One financing paragraph plus two people needs about five atomic claims |
| Pasted text only (V3 §10 calls URL intake "already excluded") | Reversed: URLs are core | The live finals, and Fetch is a Crustdata endpoint anyway |
| Graph ablation that "removes only Crustdata and keeps the web budget" | Corrected | Web Search and Fetch are Crustdata endpoints |
| Output caps of 900/1,800/600 tokens including thinking | Replaced | Truncation risk |
| Idempotency fingerprints, retrieval epochs, late-worker generation guards | Simplified | A single process with one active run per case |
| A 40/35/15/10 credit split | Dropped | About 13 credits per run; rate limits bind, not credits |
| "Locally verified bundled Python 3.12.14" | Corrected | This laptop: 3.14.7 by default, with 3.12.2 present |
| No finals plan and no 3-person split | Added | A1, A11 |
| D/A/R/S/H/X evidence-class labels throughout | Replaced with Verified / Open / Target | Readability under time pressure |

---

## 18. Sources

**Official brief:** [ContextCon PS - CrustData (1).pdf](<../ContextCon PS - CrustData (1).pdf>), all five pages.

**Crustdata documentation, checked 30 Oct 2026:**

- [API introduction](https://docs.crustdata.com/general/introduction)
- [Permissions](https://docs.crustdata.com/general/permissions)
- [Credits](https://docs.crustdata.com/general/credits)
- [Pricing](https://docs.crustdata.com/general/pricing)
- [Rate limits](https://docs.crustdata.com/general/rate-limits)
- [Data updates](https://docs.crustdata.com/general/data-updates)
- [Error best practices](https://docs.crustdata.com/openapi-specs/2025-11-01/best-practices)
- [Company Identify](https://docs.crustdata.com/company-docs/identify/introduction)
- [Company Enrich reference](https://docs.crustdata.com/company-docs/enrichment/reference)
- [Company Enrich examples](https://docs.crustdata.com/company-docs/enrichment/examples)
- [Person Enrich introduction](https://docs.crustdata.com/person-docs/enrichment/introduction)
- [Person Enrich reference](https://docs.crustdata.com/person-docs/enrichment/reference)
- [Person Search reference](https://docs.crustdata.com/person-docs/search/reference)
- [Web Search](https://docs.crustdata.com/web-docs/search/introduction)
- [Web Fetch](https://docs.crustdata.com/web-docs/fetch/introduction)
- [Claude plugin](https://docs.crustdata.com/integrations/claude-plugin)

**Anthropic:** the Claude API reference bundled with Claude Code (model table cached 6 Oct 2026), covering models and pricing, structured outputs, thinking and effort, and the [API version 2026-10-21 migration guide](https://platform.claude.com/docs/en/api/migration-2026-10-21).

**Development packets, checked 30 Oct 2026:**

- [Koah company post](https://www.koahlabs.com/blog/theory-ventures-partnership?source=theory)
- [Theory Ventures post](https://tomtunguz.com/koah-theory/)
- [Linear Series C](https://linear.app/now/building-our-way)
- [Linear tender](https://linear.app/now/sharing-growth-with-the-people-building-linear)
- [Attio Series B](https://attio.com/blog/attio-raises-52m-series-b)

These are public assertions by their authors, not audited facts.

**Local check (30 Oct 2026):** `python` is 3.14.7 (SQLite 3.50.4); `py -3.12` is 3.12.2 (SQLite 3.43.1); Node is v24.19.0; Git is 2.51.0. The planning folder is inside OneDrive and is not a git repository.

**Final product promise:** a Team & Financing brief in which every sentence is tied to a Crustdata identity and an exact source, every limit is stated, and every change has a reason.

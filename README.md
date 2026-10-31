# Proofroom

**Type a startup's domain. Get a Team & Financing diligence report in which every sentence is tied to a Crustdata identity and an exact source, every number is re-checked by code, and everything the evidence cannot settle is handed to a person.**

ContextCon 03 · IIT Bombay · 31 Oct 2026 · Theme: **Investing** · *Services, Replaced*

- 2-minute video (an unseen company, first run): ‹link added at submission›
- Raw unedited recording: ‹link›

![Diligence report, page 1, for Koah](docs/screenshots/koah-report-page1.png)

---

## 1. The service

**The job.** Before every founder meeting, an analyst or associate at a fund checks the same basic facts by hand:

- Who are the founders, and did they really work where the deck says?
- How much was raised, when, and who led the round?

It takes about an hour of open tabs per company: the company blog, the lead investor's post, news coverage, professional profiles, and a funding database.

**Who does it today, and who pays.** VC analysts and associates, diligence firms, angel-syndicate leads and corporate-development teams. Funds pay for it in associate time, in diligence-vendor fees, and in database seats that still need a person to reconcile what they show.

**Why it is hard, and why a summarizing chatbot gets it wrong:**

- A funding announcement is the company's own statement. The lead investor's post about the same round is **not** a second, independent confirmation.
- News sites copy each other, re-date old stories, and report one round in several currencies.
- Profiles are self-maintained, and "the founders worked at A, B and C" is often true for only one of them.
- A round, a total, a valuation and a sale of existing shares (a tender) are easy to mix up. Crustdata's own `total_investment_usd` for Linear (**$233.2M**) includes a **$99M tender**, which is liquidity for shareholders, not capital for the company.

A chatbot that searches and summarizes will repeat the press release, which is exactly what the investor is trying to check.

## 2. What it does now (end to end)

Input: a domain (Mode A). Optionally: pasted text or URLs (Mode B), one sentence to check, or a focus note.

| Stage | What happens | Where Crustdata is used |
|---|---|---|
| 1 Identity | The domain resolves to **one** company ID. Exact primary domain wins; a tie abstains and goes to a person | `POST /company/identify` |
| 2 Graph | **In parallel:** the company record (founders with employment IDs, funding milestones, news index) and a founder search (title `founder` OR `cofounder`), merged. People found only by the search are enriched | `/company/enrich` ∥ `/person/search`, then `/person/enrich` |
| 3 Packet | The funding announcement and coverage are picked from Crustdata's news index, using a ±7-day rule around recorded round dates and one source per publisher, then fetched in one request. Text addressed to AI agents is counted and ignored | `/web/enrich/live` (`/web/search/live` as fallback) |
| 4 Claims | Up to 5 material Team & Financing claims, each **quoted verbatim**; code checks every quote against the page | — |
| 5 Joins | Lead investors and named prior employers resolved by name; prior employers joined to each person **by employer ID** (✔), by a **labelled name match** (≈), or not at all (?) | `/company/identify` (names, free) |
| 6 Assess | Each claim gets a status (Supported / Supported, corrected / Conflicting / Not established) and a basis (company statement, investor statement, independent report, indexed record, calculation) | — |
| 7 Gate | **Code** checks every amount, percentage, year and date against the evidence the sentence cites. A **separate check** confirms each sentence is entailed by *only* its cited evidence. A failure drops the clause or withholds the sentence. There is no "repair" call | — |
| 8 Deliver | `brief.md`, `case.json`, `questions.md`, `report.md` and `report.html` are written once, read back, and SHA-256-hashed into `manifest.json` | — |

**Outputs:**

- **Diligence report** (3 pages, the same format for every company):
  1. a snapshot plus 🔴 red flags, 🟡 open points and 🟢 green flags, produced by **16 fixed rules**, each flag citing its evidence;
  2. team, financing, and "considerations for the investment decision", which are facts for the reader's decision and **never a buy/pass verdict**;
  3. the methodology, including this run's numbers and the rule table.
- **Cited brief:** every sentence carries [E#] (source passage) or [G#] (Crustdata JSON path) citations, plus the founder table, the funding cross-check, "Not checked", "Limitations" and the evidence list with four clocks: published, updated, provider refresh, retrieved.
- **"Needs a person: N"** at the top of every brief: identity ties, conflicting sources, withheld sentences, failed sources. This is the only part of the job that still needs a human.
- **Founder-meeting ask sheet** (`questions.md`), ranked, each question with its evidence lines.
- **Proof receipt:** `python -m proofroom verify <run folder>` re-hashes the files and re-checks every number against the stored evidence, offline and with no keys.
- Optional **founder email draft** (`--email`): a draft only, never sent.

**Where a person is still needed:**

- a genuine identity tie;
- sources that disagree;
- the questions only the founder can answer.

The model calls are also answered by an agent session; see §5.

## 3. Results on the development companies

These are development cases, seen during the build. The unseen company is in the video.

| Company | Status | Sentences emitted / withheld | Founders ID-joined | Key findings | Errors |
|---|---|---|---|---|---|
| **Koah** (koahlabs.com) | DELIVERED · RECEIPT OK | 4 / 1 | 3 of 3 | $20.5M Series A led by Theory ✔ record; Forerunner seed ✔ (TechCrunch + record); CEO title rests on the company's word only; the release's "more than $26 million" exceeds the indexed $25.5M, so it asks how big the 2024 pre-seed was | 0 |
| **Linear** (linear.app) | DELIVERED · RECEIPT OK | 3 / 2 | 3 of 3 (incl. the CEO, found only by the founder search) | $82M Series C ✔ record; **$99M tender shown as liquidity, not capital**; the $233.2M total is flagged "not capital raised"; the non-secondary rounds sum to $134.2M (labelled calculation), matching Tracxn's "$134M over 4 rounds" | 0 |
| **Attio** (attio.com) | DELIVERED · RECEIPT OK | 5 / 0 | 2 of 2 | $52M Series B led by GV ✔ (GV = Google Ventures **only because the release says so**); "$116 million to date" consistent with the record | 0 |

"Errors" counts false conflicts, false sums, wrong subjects, totals presented as capital, and alias errors.

Usefulness bar from the plan, at least 3 reusable sentences and at least 1 ID join per company: **3 of 3 pass.**

A real, unplanted finding: Theory Ventures' post says Koah's founders "overlapped at Affirm, Supermove and Qualified". In Crustdata's profiles only **Herrick Fang** lists those employers: Affirm 632082 ✔, Supermove 780882 ✔, Qualified ≈ 632707. Qualified is only a name match, because Identify("Qualified") returns 25 namesakes and none of them is this company. Proofroom keeps the collective claim collective and reports it as a scope correction, not a refutation.

**Timing:**

- Live retrieval (identity + graph + packet) takes 6–11 s.
- A replayed demo case runs end to end in about 0.3 s.
- In the recorded development runs, most of the wall-clock time was the agent session answering the three model calls (81–200 s).

**Cost:** about 5 Crustdata credits per company.

**Tests:** `pytest -q` passes **204 tests**:

| Group | File | Tests |
|---|---|---|
| T-api: error shapes, retries, cache, fixture mode | `test_errors.py` | 33 |
| T-identity / T-finance: G1–G4 on the recorded Koah fixture | `test_graph_koah.py` | 31 |
| Gate: amounts, currencies, precision, dates, clause drop | `test_gate.py` | 36 |
| Packet: dates, relative anchoring, picks, injection meter | `test_packet.py` | 23 |
| Model layer: providers, local validation, refusal and max_tokens | `test_llm.py` | 19 |
| Render + receipt, report, exception desk | `test_render.py`, `test_report.py`, `test_exceptions.py` | 25 |
| Store: write-once, read-back, tamper detection | `test_store.py` | 10 |
| Web UI | `test_web.py` | 23 |
| Pipeline helpers | `test_pipeline_helpers.py` | 4 |

## 4. How to run it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # set CRUSTDATA_API_KEY
```

**No keys? Replay a demo case** (Koah, Linear or Attio). The output is labelled FIXTURE everywhere:

```bash
.venv/bin/python -m proofroom run --fixture koah
```

**A real run:**

```bash
.venv/bin/python -m proofroom run --domain koahlabs.com --mode LIVE                 # Mode A, domain only
.venv/bin/python -m proofroom run --domain koahlabs.com --fast                      # FAST profile
.venv/bin/python -m proofroom run --domain koahlabs.com --sentence "Koah raised a \$20.5M Series A led by Theory Ventures"
.venv/bin/python -m proofroom verify data/cases/koahlabs-com/run-1                   # proof receipt
```

**The web UI** opens at <http://127.0.0.1:8000>. It has a form, the "Load demo case (no keys)" selector, live progress, an evidence drawer behind every citation, and the report:

```bash
.venv/bin/uvicorn proofroom.web:app
```

**Model provider.** With `ANTHROPIC_API_KEY` set, the three calls go to `claude-sonnet-5-5` through the official SDK. Without it, the default for this event, each call is written to `data/cases/<case>/run-<n>/model/<call>.request.json` (system prompt, user message, JSON schema). An agent session answers it in `<call>.response.json`, and code validates the answer against the same strict schema.

**Labels.** Every run is labelled LIVE, CACHED or FIXTURE, with its model source and its profile.

## 5. How it is built

- **Python 3.12**, async `httpx`, Pydantic v2, FastAPI + Jinja2 + about 200 lines of vanilla JS, BeautifulSoup. Files only: no database, queue or agent framework.
- **`proofroom/crustdata.py`:** the REST adapter. It has a per-endpoint rolling rate limiter, a development cache keyed by (endpoint, body hash, API version), a normalizer for all three documented error shapes plus non-JSON bodies, and retry rules (429 waits for the reset, max 3 tries; one retry on 5xx and network errors; never on 4xx). It records `x-credits-used` on every attempt, and failed attempts are kept.
- **`graph.py`:** G1 tie rule, an employment normalizer for both of Crustdata's key sets, the team matrix, ID joins plus the labelled name-match fallback, and G4 type-matched round checks with precision-aware amounts. It never treats a secondary sale as capital.
- **`packet.py`:** news picking, HTML-to-text, published vs. updated dates, relative-date anchoring, press-release detection, and the injection meter.
- **`llm.py` / `prompts.py`:** three strict, flat schemas; the SDK, session and fixture providers; local validation (verbatim quotes, evidence IDs exist, selection cap).
- **`gate.py`:** the deterministic gate. **`render.py`** renders the brief and questions; **`report.py`** builds the 3-page report from the fixed flag rules; **`exceptions.py`** builds "Needs a person"; **`verify.py`** is the proof receipt.
- **`pipeline.py`:** the orchestrator. Independent stages run concurrently; FULL and FAST profiles; deadlines derived from a hard stop.
- **`store.py`:** write-once files, read-back, SHA-256 manifest. No manifest means the run was not delivered.

**Crustdata endpoints and why:**

| Endpoint | Why |
|---|---|
| `POST /company/identify` (domain) | The subject anchor: everything is about one company ID |
| `POST /company/identify` (names) | Lead investors and prior employers, resolved to IDs for joins (free) |
| `POST /company/enrich` `basic_info, funding, people, news` | One 2-credit call that gives founders with employer IDs, funding milestones, investors and candidate article URLs |
| `POST /person/search` | Founder discovery, merged with the record. It found Linear's CEO, whom the record omits |
| `POST /person/enrich` | Employment history for people the record does not list |
| `POST /web/enrich/live` | The source pages themselves (raw HTML, matched by URL) |
| `POST /web/search/live` | Fallback when the news index has no funding article |

## 6. Approaches tried: what worked and what did not

| Approach | Outcome |
|---|---|
| Person Search, then Person Enrich, as the main graph path | **Replaced.** One Company Enrich call returns founders *with* employer IDs plus funding and news for 2 credits. The search now runs *in parallel* and is merged |
| Founder search only when the record lists no founders | **Failed on Linear.** It missed the CEO ("CEO, Cofounder"), so the search always runs, with a `founder OR cofounder` title filter |
| Strict ID-only prior-employer joins | **Too strict.** Identify("Qualified") returns 25 namesakes and none is the right company. We added a clearly labelled name-match fallback (≈) that is never counted as an ID join |
| Using Crustdata's `total_investment_usd` as "total raised" | **Wrong for Linear.** It includes a $99M tender. Rounds are now type-matched, and the total is shown as capital only when no secondary sale exists |
| Trusting `news[]` order and dates | **Noisy.** It had namesakes, a `1970-01-01` sentinel date, and re-dated pages. The ±7-day rule around recorded rounds plus one source per publisher fixed it |
| Short (220-character) evidence excerpts | **Caused false withholds.** Attributions such as "said in a blog post" were cut off. Excerpts are now sentence-complete |
| Asking the model to fix sentences that fail checks | **Rejected by design.** It is the "summarize and hope" failure mode. Failing clauses are dropped or the sentence is withheld, with a reason |
| A model-written invest/pass verdict | **Rejected.** It cannot be sourced from team and financing facts. Flags come from fixed rules; considerations are facts for the reader |
| The Crustdata MCP inside the product | **Used for development probing only.** The product calls REST for typed responses, credit headers and documented fetch output |

## 7. What it could do next

- **Watchers:** re-run when a founder changes role or a new round is indexed, and diff against the last report. We held this back because run-to-run comparison needs the evidence rules to be stable first.
- **Deck upload (PDF)** as Mode B input, and **a third person** (early employees, board) in the team table.
- **More claim families:** board composition, acquisitions, headcount trajectory. Each needs its own evidence rules before it can be checked rather than summarized.

## 8. Limitations

- Coverage of very new startups in Crustdata's graph can be thin; absence of a record is reported as "not found", never as a refutation.
- Profiles are self-maintained, and funding records are Crunchbase-derived, so they are labelled "indexed record", never "independent".
- In this build the model calls are answered by an agent session through request files. The Anthropic SDK provider (`claude-sonnet-5-5`) is implemented and unit-tested against a fake client, but it was not exercised against the live API during the event.
- Out of scope: revenue, valuation advice, market assessment, OCR, outreach.

## 9. The unseen-run protocol (for the video)

After the feature freeze, one predeclared Crustdata news search is run for recent seed and Series A announcements. The first three results that meet all three criteria become candidates, in returned order:

- the company was never touched during development;
- it has its own domain;
- it is a private startup.

The first candidate is run once, live, with the cache off, and recorded uncut. Failed attempts are kept and shown.

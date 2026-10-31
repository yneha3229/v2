# Prep 03: README outline, unseen-selection rule, video narration, 45-second pitch (plan v2 §8.5, §11, §12, §13.1 item 6)

*Written 31 Oct 2026, ~01:25 IST. Content only. Fill in the ‹…› values on the day, from measured runs only.*

---

## 1. README outline (S12, write it into the repo after 10:30)

1. **Proofroom**: one line. "Type a startup's domain. Get a Team & Financing brief where every sentence is tied to a Crustdata identity and an exact source."
   - Links: the 2-minute video ‹link› · the raw unedited recording ‹link›
2. **The problem.** An associate checks founders and rounds by hand before every meeting. Announcements are company statements, profiles are self-maintained, and aggregators copy each other. A summary with links doesn't say which claims hold.
3. **What it does** (Mode A, domain only):
   - G1: identify the company
   - G3: founders from the graph
   - G2: employer-ID joins
   - packet assembly from Crustdata news and Web Fetch
   - extract → assess → gate → verified exports
4. **Quickstart**
   - Python 3.12; `py -3.12 -m venv .venv`; `pip install -r requirements.txt`
   - Copy `.env.example` to `.env`; set `CRUSTDATA_API_KEY` and `ANTHROPIC_API_KEY`
   - `python -m proofroom warmup`
   - `python -m proofroom run --domain koahlabs.com`
   - `uvicorn proofroom.web:app` → open http://127.0.0.1:8000
5. **No keys? FIXTURE mode.** `python -m proofroom run --fixture koah`, or "Load demo case (no keys)" in the UI (Koah, Linear, Attio). FIXTURE output is labeled FIXTURE everywhere.
6. **Architecture.** The 7-stage pipeline table (§8.2) with measured timings ‹median s›; three model calls; files-only storage; run folder + manifest.
7. **Crustdata endpoints used and why.** Identify (G1, prior employers, investors), Company Enrich `basic_info, funding, people, news` (G2–G4 + candidate URLs), Person Search (S1 fallback), Person Enrich (non-founders / supplied URLs), Web Search (fallback), Web Fetch (passages). Headers and the per-run credit cost ‹measured›.
8. **Evidence rules.** Four clocks; one origin; collective claims; byline ≠ title; secondary ≠ capital; indexed record ≠ independent; the split gate (code checks digits, the model checks entailment); no repair call.
9. **Evaluation (with denominators).**
   - The T2 table for P1–P3 × Mode A/B: sentences emitted / supported / suppressed; team rows / ID joins; false conflicts / false sums; seconds; credits; tokens.
   - The four test groups: pass counts.
   - Ablation: "without the graph, ‹X› of ‹Y› joins disappear" (if done).
10. **A real finding on a development packet** (§20.3): "overlapped at Affirm, Supermove and Qualified" holds only for Herrick Fang in the graph. Labeled development packet, not unseen.
11. **Limitations.**
    - Graph coverage of very new startups.
    - Profiles are self-maintained.
    - Funding record provenance is Crunchbase-derived.
    - Crustdata's `total_investment_usd` can include secondary sales.
    - No OCR, revenue, valuation advice or outreach.
12. **The unseen-run protocol** (below) and the honesty rules (LIVE / CACHED / FIXTURE labels, kept failed attempts).

---

## 2. Unseen-request selection rule (write into the README before 14:00; run after the freeze)

**Predeclared query** (Crustdata Web Search, run once at ‹time after 14:00›, results saved verbatim):

```json
{"query": "startup raises seed OR \"Series A\" funding round", "sources": ["news"], "start_date": <unix seconds for freeze time minus 14 days>}
```

If T1 shows that Web Search doesn't support `OR`, use the fallback query `startup raises Series A funding` with the same filters.

**Take results in returned order. Accept the first three that meet all of these:**

- (a) the company was never touched during development. That excludes Koah, Linear and Attio, and anything in `cache/` or `data/`.
- (b) the article names a company domain, or the company has an obvious own domain.
- (c) the company is a private startup (not listed, not a subsidiary of a listed group).

**Before recording:**

- Record the three candidates in PROGRESS.md (Unseen-run record) **before** any Proofroom call touches them.
- Never warm up, probe or rehearse on them.
- Show on screen the selection result, an empty case list for the domain, and the wall clock.

---

## 3. Video narration (2:00, result-first; matches the §11.2 storyboard)

| Time | Say (≈ words) | On screen / label |
|---|---|---|
| 0:00–0:12 | "Before a founder meeting, an associate checks who the founders are and what was raised. Proofroom does that check end to end. Here's a company it has never seen: domain only." (28) | Type the domain, click Prepare · **UNSEEN REQUEST · selected after the 14:00 freeze · domain only** |
| 0:12–0:30 | "First it pins the company to one Crustdata ID, then finds the founders by that ID, not by name search. The rest of the wait is sped up; the real time is in the corner." (34) | Identity panel fills · **LIVE · ⏩ ×4 · actual ‹X› s** |
| 0:30–1:05 | "This is the team table. Each check mark is an ID join: the founder's employer record points at this exact company ID. Open one: title, start date, the JSON path and when the profile was last refreshed. When a source says 'the founders' did something, Proofroom splits it per person and shows whom the graph actually supports." (60) | Open a founder row; JSON path + `updated_at` · **GRAPH JOIN** |
| 1:05–1:35 | "Financing: the announcement sentence with its exact passage. Published and updated dates are kept apart. The company's post and its investor's post count as one announcement, not two confirmations. Then the cross-check against Crustdata's funding record, labeled as an indexed record." (49) | Highlighted passage; origin grouping; G4 line · **VERIFIED CITATION** |
| 1:35–2:00 | "It exports a cited brief and a JSON case file, hashed and read back. ‹X› seconds, ‹Y› credits, live. On our development packets, ‹N› of ‹M› sentences passed the gate, with zero false sums. The code and the raw recording are linked below." (45) | brief.md, case.json, run stats, evaluation card · **VERIFIED ARTIFACTS · PREVIOUSLY RECORDED EVALUATION** |

If the unseen run produces no ID joins, replace 0:30–1:05 with: "The graph had no employer join for this company, and Proofroom says so instead of guessing: the team table is empty with its reason."

---

## 4. The 45-second stage pitch

> "Every week, a fund associate checks the same facts before a founder meeting: who the founders really are, and what was really raised. Today that's an hour of tabs. A chatbot will summarize the press release, which is exactly the thing you're trying to check.
>
> Proofroom takes a bare domain. It pins the company to Crustdata's identity graph, finds the founders by company ID, joins their employer records, and checks every Team & Financing claim against the original source and the graph. Every sentence is cited, every number is checked by code, and every limit is stated.
>
> On our development set it caught that 'the founders overlapped at Affirm, Supermove and Qualified' is true for one founder, not three. Let's run a company you pick."

(≈120 words ≈ 45 s. Start the live run within the first 15 s, per §12.)

**Q&A one-liners (§12):**

- *How do you know it's right?* The split gate, four test groups, and stated limits. Denominators are in the README.
- *What does Crustdata add?* G1–G4: the ID-joined team table and the funding cross-check. Plus the ablation number.
- *Isn't this a chatbot with search?* No. It works on typed financing, a separate check per claim, and ID joins, with verified exports. Without the graph, ‹X› of ‹Y› joins disappear.
- *Who pays?* Fund associates and platform teams. Demand is a hypothesis.

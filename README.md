# Proofroom

**Type a startup's domain. Get a Team & Financing brief where every sentence is tied to a Crustdata identity and an exact source.**

ContextCon 03, IIT Bombay (31 Oct 2026) · Theme: **Investing** · *Services, Replaced*

- 2-minute video: ‹link, added at submission›
- Raw unedited recording of the unseen run: ‹link›

> Draft README, written during the build. Sections marked ‹…› are filled only from measured runs.

---

## 1. The service

**The job:** before every founder meeting, an analyst or associate at a fund checks the basic facts by hand. Who are the founders, and did they really work where the deck says? How much was raised, when, and who led the round?

**Who does it today:** VC analysts and associates, diligence firms, and angel syndicate leads. It means an hour of open tabs per company: the company blog, the investor's post, news coverage, professional profiles and funding databases.

**Who pays:** funds pay for it in associate time, through diligence vendors, and through database seats that still need a human to reconcile them.

**Why it is hard:**

- A funding announcement is the company's own statement. The lead investor's post about the same round is not a second, independent confirmation.
- News sites copy each other, re-date old stories, and report the same round in different currencies.
- Profiles are self-maintained, and "the founders worked at A, B and C" is often true for only one of them.
- A round, a total, a valuation and a sale of existing shares (a tender) are easy to mix up.

A chatbot that searches and summarizes will happily repeat the press release, which is exactly what the investor is trying to check.

## 2. What it does now

Proofroom does the associate's research, checking and first draft end to end:

1. **Identity (G1):** resolves the domain to one Crustdata company ID. Namesakes are excluded, with reasons.
2. **Team (G2/G3):** finds the founders in Crustdata's graph. It joins each person's current role to the company **by employer ID**, and prior employers named by the sources by ID (✔), by a labelled name match (≈), or not at all (?).
3. **Packet:** picks the funding announcement and coverage from Crustdata's `news[]`, using a ±7-day rule around the funding record's milestone dates, and fetches the pages.
4. **Claims:** extracts up to 5 material Team & Financing claims, each quoted verbatim from a source.
5. **Assessment:** compares each claim with the evidence table (source passages plus graph JSON paths) under fixed evidence rules.
6. **Gate:** code checks every amount, percentage, year and date in each sentence against the evidence it cites, and a separate check confirms entailment. A failing clause is dropped or the sentence is suppressed. There is no repair call.
7. **Delivery:** `brief.md`, `case.json` and `questions.md` (a ranked founder-meeting ask sheet) are written once, read back, and SHA-256-hashed into `manifest.json`.

**Where a person is still needed (the exceptions):**

- a genuine identity tie;
- conflicting sources;
- the questions in `questions.md`, which only the founder can answer.

## 3. What it could do next

‹filled at S12›

## 4. How to run it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # set CRUSTDATA_API_KEY (and ANTHROPIC_API_KEY if you use the API provider)
.venv/bin/python -m proofroom run --domain koahlabs.com            # Mode A, domain only
.venv/bin/python -m proofroom run --domain koahlabs.com --fast     # FAST profile: every step, lighter checks
.venv/bin/python -m proofroom run --domain koahlabs.com --sentence "Koah raised a \$20.5M Series A led by Theory Ventures"
.venv/bin/python -m proofroom verify data/cases/koahlabs-com/run-1  # proof receipt, offline
```

**No keys? FIXTURE mode:** `python -m proofroom run --fixture koah` replays recorded responses. Its output is labelled FIXTURE everywhere.

**Labels:** every run is labelled LIVE, CACHED or FIXTURE, with its model source and its profile (FULL or FAST).

## 5. How it is built

‹architecture table with measured timings, at S12›

### Crustdata endpoints, and why

| Endpoint | Used for |
|---|---|
| `POST /company/identify` (domain) | G1: the subject anchor, with the tie rule |
| `POST /company/identify` (names) | Prior employers and lead investors, resolved to IDs for joins |
| `POST /company/enrich` `basic_info, funding, people, news` | Founders with employment IDs (G2/G3), funding milestones (G4), candidate article URLs (2 credits) |
| `POST /person/search` | Fallback founder discovery (title `founder` OR `cofounder`) |
| `POST /person/enrich` | Employment history for people the record doesn't list |
| `POST /web/search/live` | Fallback when `news[]` has no funding article |
| `POST /web/enrich/live` | The source pages themselves (raw HTML; matched by URL) |

## 6. Approaches tried

‹filled from PROGRESS.md decisions at S12›

## 7. A real finding on a development packet

Theory Ventures' post says Koah's three founders "overlapped at three companies: Affirm, Supermove, & Qualified". In Crustdata's indexed profiles, only **Herrick Fang** lists those employers:

- Affirm 632082 ✔
- Supermove 780882 ✔
- Qualified ≈ 632707

Qualified is shown as a name match because Identify("Qualified") returns 25 namesakes, none of them this company. Proofroom therefore reports the claim as **Supported, corrected (scope)**. It is not a refutation, since profiles are self-maintained. This is a development packet, not the unseen run.

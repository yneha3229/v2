# Attio: Diligence report (Team & Financing)

*FIXTURE · model: recorded model responses (FIXTURE) · profile FULL · run 3 · reviewed 2026-10-31*

> Facts for your decision, not a recommendation. Proofroom checks team and financing claims; it does not assess the market, the product or the price.

## Page 1 · Snapshot and flags

| | |
|---|---|
| Company | Attio (attio.com) |
| Crustdata ID | 664000 |
| Founders (graph) | Alexander Christie, Nicolas Sharp |
| Latest indexed round | Indexed series b: 2025-08-26, $52,020,932, Google Ventures (indexed record, Crunchbase-derived). |
| Indexed total | Total raised per Crustdata's record: $116,220,932 across 5 rounds; it equals the sum of the recorded round amounts (indexed record, Crunchbase-derived). |
| Sources checked | 2 documents, 14 evidence rows |
| Claims | 5 checked, 5 sentences emitted, 0 withheld |

### 🔴 Red flags (0)

- None found by the rules.

### 🟡 Open points (5)

- **C1: holds with a qualification**: The release is the company's own statement; Crustdata's record is not independent confirmation. [E1][G4] `A2 qualified`
- **C2: holds with a qualification**: The lead is the company's own statement; no investor post is in the packet. [E2][G4] `A2 qualified`
- **C3: holds with a qualification**: The graph title comes from a self-maintained profile; it shows association, not proof. [E3][G3] `A2 qualified`
- **C4: holds with a qualification**: The graph title comes from a self-maintained profile; it shows association, not proof. [E4][G2] `A2 qualified`
- **C5: holds with a qualification**: A total raised to date is not a round; the figure is the company's own and is as of the release date. [E5][G9] `A2 qualified`

### 🟢 Green flags (3)

- **Round matches the indexed record**: C1 (series b): consistent with Crustdata's record. [G4] `G1 round-confirmed`
- **2 of 2 founders ID-joined to the company**: Alexander Christie, Nicolas Sharp [G2][G3] `G3 founders-joined`
- **Indexed total adds up**: Total raised per Crustdata's record: $116,220,932 across 5 rounds; it equals the sum of the recorded round amounts (indexed record, Crunchbase-derived). [G9] `G5 total-explained`

## Page 2 · Team, financing and considerations

### Team (Crustdata graph)

| Founder | Current role (ID join) | Prior employers named by sources |
|---|---|---|
| Alexander Christie | Co-Founder & CTO since 2019-11 ✔ | none named |
| Nicolas Sharp | Co-Founder and CEO since 2019-11 ✔ | none named |

### Financing

- C1 (series b): consistent with Crustdata's record. [G4]
- Indexed series b: 2025-08-26, $52,020,932, Google Ventures (indexed record, Crunchbase-derived). [G4]
- Indexed undisclosed: 2024-08-28, $33,000,000, Redpoint, Point Nine, Balderton Capital, 01 Advisors (indexed record, Crunchbase-derived). [G5]
- Indexed series a: 2023-03, $23,500,000, Redpoint (indexed record, Crunchbase-derived). [G6]
- Indexed seed: 2021-11-24, $7,700,000, Point Nine (indexed record, Crunchbase-derived). [G7]
- Indexed pre seed: 2018-10, no amount recorded, lead not recorded (indexed record, Crunchbase-derived). [G8]
- Total raised per Crustdata's record: $116,220,932 across 5 rounds; it equals the sum of the recorded round amounts (indexed record, Crunchbase-derived). [G9]

### Considerations for the investment decision

*Facts for your decision, not a recommendation. Proofroom checks team and financing claims; it does not assess the market, the product or the price.*

**What supports the case**

- The announced rounds match Crustdata's indexed record, so they can be cited in a memo together with their sources.
- The founding team in Crustdata's graph matches the company's current roster; reference checks can start from these profiles.
- The indexed funding history adds up: the total equals its rounds.

**What weakens the case until resolved**

- Some facts rest on one party's word; confirm them in the meeting.

## Page 3 · Methodology

1. Identity: the domain is resolved to one Crustdata company ID (exact primary domain first; a tie abstains).
2. Sources: the funding announcement and coverage are picked from Crustdata's news index within ±7 days of a recorded round date, one per publisher, then fetched; text addressed to AI agents is treated as data and ignored.
3. Claims: up to 5 material Team & Financing claims are quoted verbatim from the sources.
4. Graph: founders' current roles and named prior employers are joined by employer ID; funding rounds are type-matched against the indexed record (Crunchbase-derived, never treated as independent).
5. Assessment: each claim gets a status and basis under fixed rules (four clocks, one origin per announcement, secondary sales are not capital, aliases only when a source states them).
6. Gate: code checks every amount, percentage, year and date against the cited evidence; a separate check confirms each sentence is entailed by only its cited evidence. A failure drops the clause or withholds the sentence; there is no repair.
7. Delivery: files are written once, read back and SHA-256-hashed into a manifest; `python -m proofroom verify <run folder>` re-checks every number offline.

### This run

- Sources used: 2 (excluded during selection: 45)
  - D1: https://www.prnewswire.com/news-releases/attio-raises-52m-series-b-to-scale-the-first-ai-native-crm-for-go-to-market-builders-302538357.html · origin company (press release) · published 2025-08-26
  - D2: https://www.thesaasnews.com/news/attio-raises-33-million-in-funding · origin unknown · published 2024-08-30
- Crustdata calls: /company/enrich ×1, /company/identify ×2, /person/search ×1, /web/enrich/live ×1 · credits 0.0
- Model calls: 3 · failed attempts kept: 0
- Agent-directed instructions found in sources and ignored: 0
- Claims not checked (listed in the brief): 7
- Run time: 0.26 s

### Flag rules (identical for every company)

| Rule | Level | Fires when |
|---|---|---|
| `R1 identity` | Red flag | The domain did not resolve to exactly one Crustdata company |
| `R2 conflict` | Red flag | A selected claim is Conflicting between comparable sources |
| `R3 record-differs` | Red flag | An announced round differs from Crustdata's indexed record |
| `R4 founder-no-join` | Red flag | A founder listed by Crustdata has no current role at the company |
| `A1 withheld` | Open point | A sentence could not be verified as written and was withheld |
| `A2 qualified` | Open point | A claim holds only with a qualification or rests on one party's word |
| `A3 corrected` | Open point | A claim is true only with a correction (date, scope, title...) |
| `A4 not-established` | Open point | Evidence neither supports nor contradicts a selected claim |
| `A5 secondary` | Open point | The indexed total includes secondary sales (liquidity, not capital) |
| `A6 retrieval` | Open point | A data source failed, so a check is incomplete |
| `A7 no-sources` | Open point | No public source documents were found |
| `G1 round-confirmed` | Green flag | An announced round matches Crustdata's indexed record |
| `G2 independent` | Green flag | A financing claim is supported by an independent report |
| `G3 founders-joined` | Green flag | Every founder Crustdata lists holds a current role at the company (employer-ID join) |
| `G4 prior-employer` | Green flag | A prior employer named by a source joins to the person by ID |
| `G5 total-explained` | Green flag | The indexed total equals the sum of the recorded rounds |

Evidence IDs refer to the evidence list in `brief.md` (E = source passage, G = Crustdata graph value).

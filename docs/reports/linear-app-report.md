# Linear: Diligence report (Team & Financing)

*FIXTURE · model: recorded model responses (FIXTURE) · profile FULL · run 3 · reviewed 2026-10-31*

> Facts for your decision, not a recommendation. Proofroom checks team and financing claims; it does not assess the market, the product or the price.

## Page 1 · Snapshot and flags

| | |
|---|---|
| Company | Linear (linear.app) |
| Crustdata ID | 633791 |
| Founders (graph) | Tuomas Artman, Jori Lallo, Karri Saarinen |
| Latest indexed round | Indexed secondary sale (liquidity, not company capital): 2026-08-26, $99,000,000, Accel (indexed record, Crunchbase-derived). |
| Indexed total | Crustdata's indexed total $233,200,000 includes secondary sales, so it is not capital raised. |
| Sources checked | 3 documents, 16 evidence rows |
| Claims | 5 checked, 3 sentences emitted, 2 withheld |

### 🔴 Red flags (0)

- None found by the rules.

### 🟡 Open points (6)

- **C1: holds with a qualification**: The packet holds a press report, not Linear's own post; the report is not independent of the company's announcement, and Crustdata's record is not independent confirmation. [E1][G6] `A2 qualified`
- **C4: holds with a qualification**: Karri Saarinen is not among the founders in Crustdata's people record for this run, so his title has no graph join here; the title comes from the press report only. [E1][E3][E4] `A2 qualified`
- **C5: holds with a qualification**: The Series C itself includes secondary funding (per the CEO's quoted post), so neither total is a measure of primary capital; Tracxn is an aggregator, not a primary source. [E5][G6][G7][G8][G9][G10][G4] `A2 qualified`
- **Indexed total includes secondary sales**: Crustdata's indexed total $233,200,000 includes secondary sales, so it is not capital raised. [G10] `A5 secondary`
- **A sentence was withheld**: C2 could not be verified as written from its cited evidence; the unsupported part was "blog post".  `A1 withheld`
- **A sentence was withheld**: C3 could not be verified as written from its cited evidence; the unsupported part was "blog post".  `A1 withheld`

### 🟢 Green flags (4)

- **Round matches the indexed record**: C1 (series c): consistent with Crustdata's record. [G6] `G1 round-confirmed`
- **C1: independently reported**: TechStartups reported on 2025-06-10 that Linear has raised an $82 million Series C, as the company said. This is consistent with Crustdata's indexed record (Crunchbase-derived), which lists a Series C of $82,000,000 on… [E1][G6] `G2 independent`
- **C5: independently reported**: Tracxn's page (updated 2026-10-13) says Linear has raised a total of $134M over 4 funding rounds, which lines up with the seed, Series A, Series B and Series C entries in Crustdata's indexed record (Crunchbase-derived).… [E5][G6][G7][G8][G9][G10][G4] `G2 independent`
- **2 of 2 founders ID-joined to the company**: Tuomas Artman, Jori Lallo [G2][G3][G11] `G3 founders-joined`

## Page 2 · Team, financing and considerations

### Team (Crustdata graph)

| Founder | Current role (ID join) | Prior employers named by sources |
|---|---|---|
| Tuomas Artman | Co-Founder since 2019-04 ✔ | none named |
| Jori Lallo | Co-Founder, CPO since 2019-04 ✔ | none named |
| Karri Saarinen | CEO, Cofounder since 2019-04 ✔ | none named |

### Financing

- C1 (series c): consistent with Crustdata's record. [G6]
- Indexed secondary sale (liquidity, not company capital): 2026-08-26, $99,000,000, Accel (indexed record, Crunchbase-derived). [G4]
- Indexed secondary sale (liquidity, not company capital): 2025-06-10, no amount recorded, lead not recorded (indexed record, Crunchbase-derived). [G5]
- Indexed series c: 2025-06-10, $82,000,000, Accel (indexed record, Crunchbase-derived). [G6]
- Indexed series b: 2023-09-14, $35,000,000, Accel (indexed record, Crunchbase-derived). [G7]
- Indexed series a: 2020-12-08, $13,000,000, Sequoia Capital (indexed record, Crunchbase-derived). [G8]
- Indexed seed: 2019-11-22, $4,200,000, Sequoia Capital (indexed record, Crunchbase-derived). [G9]
- Crustdata's indexed total $233,200,000 includes secondary sales, so it is not capital raised. [G10]
- The recorded rounds not marked as secondary sales sum to $134,200,000 (calculation from the indexed record; a round can still include some secondary shares). [G6][G7][G8][G9]

### Considerations for the investment decision

*Facts for your decision, not a recommendation. Proofroom checks team and financing claims; it does not assess the market, the product or the price.*

**What supports the case**

- The announced rounds match Crustdata's indexed record, so they can be cited in a memo together with their sources.
- At least one financing fact is reported by a publisher other than the company or its investors.
- The founding team in Crustdata's graph matches the company's current roster; reference checks can start from these profiles.

**What weakens the case until resolved**

- Some facts rest on one party's word; confirm them in the meeting.
- Do not read the indexed total as capital in the company; part of it is secondary liquidity.
- A stated figure could not be verified as written; ask for the supporting document (for example a cap-table summary).

**Ask the founders**

- How much of the $82M Series C was new primary capital to Linear, and how much was secondary sales by existing holders?

## Page 3 · Methodology

1. Identity: the domain is resolved to one Crustdata company ID (exact primary domain first; a tie abstains).
2. Sources: the funding announcement and coverage are picked from Crustdata's news index within ±7 days of a recorded round date, one per publisher, then fetched; text addressed to AI agents is treated as data and ignored.
3. Claims: up to 5 material Team & Financing claims are quoted verbatim from the sources.
4. Graph: founders' current roles and named prior employers are joined by employer ID; funding rounds are type-matched against the indexed record (Crunchbase-derived, never treated as independent).
5. Assessment: each claim gets a status and basis under fixed rules (four clocks, one origin per announcement, secondary sales are not capital, aliases only when a source states them).
6. Gate: code checks every amount, percentage, year and date against the cited evidence; a separate check confirms each sentence is entailed by only its cited evidence. A failure drops the clause or withholds the sentence; there is no repair.
7. Delivery: files are written once, read back and SHA-256-hashed into a manifest; `python -m proofroom verify <run folder>` re-checks every number offline.

### This run

- Sources used: 3 (excluded during selection: 67)
  - D1: https://tracxn.com/d/companies/linear/__xC97n-jdX7VZjDBpNyRfVH-H_Elzu354nD5Yz5FaUVI/funding-and-investors · origin unknown · published 2021-08-17
  - D2: http://www.techmeme.com/250610/p18#a250610p18 · origin unknown · published unknown
  - D3: https://techstartups.com/2025/06/10/linear-raises-82m-in-series-c-funding-at-1-25b-valuation-to-challenge-atlassian/ · origin unknown · published 2025-06-10
- Crustdata calls: /company/enrich ×1, /company/identify ×2, /person/enrich ×1, /person/search ×1, /web/enrich/live ×1 · credits 0.0
- Model calls: 3 · failed attempts kept: 0
- Agent-directed instructions found in sources and ignored: 0
- Claims not checked (listed in the brief): 13
- Run time: 0.25 s

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

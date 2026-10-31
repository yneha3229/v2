# Koah: Diligence report (Team & Financing)

*FIXTURE · model: recorded model responses (FIXTURE) · profile FULL · run 9 · reviewed 2026-10-31*

> Facts for your decision, not a recommendation. Proofroom checks team and financing claims; it does not assess the market, the product or the price.

## Page 1 · Snapshot and flags

| | |
|---|---|
| Company | Koah (koahlabs.com) |
| Crustdata ID | 3718859 |
| Founders (graph) | Mike Choi, Nic Baird, Herrick Fang |
| Latest indexed round | Indexed series a: 2026-02-24, $20,500,000, Theory Ventures (indexed record, Crunchbase-derived). |
| Indexed total | Total raised per Crustdata's record: $25,500,000 across 3 rounds; it equals the sum of the recorded round amounts (indexed record, Crunchbase-derived). |
| Sources checked | 3 documents, 13 evidence rows |
| Claims | 5 checked, 4 sentences emitted, 1 withheld |

### 🔴 Red flags (0)

- None found by the rules.

### 🟡 Open points (2)

- **C2: holds with a qualification**: The CEO title rests on the company's statement; the indexed profile shows only Co-Founder. [E2][G3] `A2 qualified`
- **A sentence was withheld**: C4 could not be verified as written from its cited evidence; the unsupported part was "the Series A brings its total funding".  `A1 withheld`

### 🟢 Green flags (6)

- **Round matches the indexed record**: C1 (series a): consistent with Crustdata's record. [G5] `G1 round-confirmed`
- **Round matches the indexed record**: C3 (seed): consistent with Crustdata's record. Lead Forerunner is among the record's investors. [G6] `G1 round-confirmed`
- **C3: independently reported**: TechCrunch reported that Forerunner led Koah's seed round with South Park Commons and Andrew Karam participating, and Crustdata's indexed record lists a $5M seed dated 7 Sep 2025 led by Forerunner. [E3][G6] `G2 independent`
- **C5: independently reported**: TechCrunch reported on 7 Sep 2025 that Koah had recently raised $5 million in seed funding. [E5][G6] `G2 independent`
- **3 of 3 founders ID-joined to the company**: Mike Choi, Nic Baird, Herrick Fang [G2][G3][G4] `G3 founders-joined`
- **Indexed total adds up**: Total raised per Crustdata's record: $25,500,000 across 3 rounds; it equals the sum of the recorded round amounts (indexed record, Crunchbase-derived). [G8] `G5 total-explained`

## Page 2 · Team, financing and considerations

### Team (Crustdata graph)

| Founder | Current role (ID join) | Prior employers named by sources |
|---|---|---|
| Mike Choi | Co-Founder since 2024-08 ✔ | none named |
| Nic Baird | Co-Founder since 2024 ✔ | none named |
| Herrick Fang | Co-Founder since 2024 ✔ | none named |

### Financing

- C1 (series a): consistent with Crustdata's record. [G5]
- C3 (seed): consistent with Crustdata's record. Lead Forerunner is among the record's investors. [G6]
- C5 (seed): consistent with Crustdata's record. [G6]
- Indexed series a: 2026-02-24, $20,500,000, Theory Ventures (indexed record, Crunchbase-derived). [G5]
- Indexed seed: 2025-09-07, $5,000,000, Forerunner (indexed record, Crunchbase-derived). [G6]
- Indexed pre seed: 2024, no amount recorded, lead not recorded (indexed record, Crunchbase-derived). [G7]
- Total raised per Crustdata's record: $25,500,000 across 3 rounds; it equals the sum of the recorded round amounts (indexed record, Crunchbase-derived). [G8]

### Considerations for the investment decision

*Facts for your decision, not a recommendation. Proofroom checks team and financing claims; it does not assess the market, the product or the price.*

**What supports the case**

- The announced rounds match Crustdata's indexed record, so they can be cited in a memo together with their sources.
- At least one financing fact is reported by a publisher other than the company or its investors.
- The founding team in Crustdata's graph matches the company's current roster; reference checks can start from these profiles.
- The indexed funding history adds up: the total equals its rounds.

**What weakens the case until resolved**

- Some facts rest on one party's word; confirm them in the meeting.
- A stated figure could not be verified as written; ask for the supporting document (for example a cap-table summary).

**Ask the founders**

- How much was the 2024 pre-seed? The release's total of more than $26 million exceeds the $25.5M in recorded rounds.

## Page 3 · Methodology

1. Identity: the domain is resolved to one Crustdata company ID (exact primary domain first; a tie abstains).
2. Sources: the funding announcement and coverage are picked from Crustdata's news index within ±7 days of a recorded round date, one per publisher, then fetched; text addressed to AI agents is treated as data and ignored.
3. Claims: up to 5 material Team & Financing claims are quoted verbatim from the sources.
4. Graph: founders' current roles and named prior employers are joined by employer ID; funding rounds are type-matched against the indexed record (Crunchbase-derived, never treated as independent).
5. Assessment: each claim gets a status and basis under fixed rules (four clocks, one origin per announcement, secondary sales are not capital, aliases only when a source states them).
6. Gate: code checks every amount, percentage, year and date against the cited evidence; a separate check confirms each sentence is entailed by only its cited evidence. A failure drops the clause or withholds the sentence; there is no repair.
7. Delivery: files are written once, read back and SHA-256-hashed into a manifest; `python -m proofroom verify <run folder>` re-checks every number offline.

### This run

- Sources used: 3 (excluded during selection: 17)
  - D1: https://www.prnewswire.com/news-releases/koah-raises-20-5m-series-a-led-by-theory-ventures-to-scale-ai-native-monetization-302695002.html · origin company (press release) · published 2026-02-24
  - D2: https://techcrunch.com/2025/09/07/koah-raises-5m-to-bring-ads-into-ai-apps/ · origin unknown · published 2025-09-07
  - D3: https://www.finsmes.com/2026/02/koah-raises-20-5m-in-series-a-funding.html · origin unknown · published 2026-02-24
- Crustdata calls: /company/enrich ×1, /company/identify ×2, /person/search ×1, /web/enrich/live ×1 · credits 0.0
- Model calls: 3 · failed attempts kept: 0
- Agent-directed instructions found in sources and ignored: 0
- Claims not checked (listed in the brief): 5
- Run time: 0.31 s

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

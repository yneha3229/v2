# Signal dashboard (offline replay, as of 2026-10-31)

Growth and market signals from Crustdata; revenue = calibrated estimate (bake-off pipeline, LOO-validated median error 14% on 6 reported companies); signal = fixed scoring rules (`proofroom/scoring.py`). **Rules-based signal, not financial advice.** Companies marked *unverified* have no claims check yet (Verification pillar neutral).

## Growth signals

| Company | Staff | Staff YoY | Web visitors | Visitors YoY | Followers YoY | Last round | Crowding (funded peers 24m) |
|---|---|---|---|---|---|---|---|
| Koah | 24 | +167% | 17,228/mo | +29% | +734% | 8 mo ago | unknown (–) |
| Linear | 303 | +71% | 9,387,120/mo | +115% | +47% | 17 mo ago | unknown (–) |
| Attio | 206 | +55% | 1,724,793/mo | +128% | +63% | 14 mo ago | unknown (–) |
| Clay | 1,572 | +46% | 1,303,154/mo | +10% | +68% | 2 mo ago | unknown (–) |
| Vercel | 1,027 | +26% | 30,173,255/mo | +154% | +52% | 13 mo ago | unknown (–) |
| Retool | 413 | -10% | 1,259,990/mo | – | +23% | 51 mo ago | unknown (–) |
| Ramp | 3,757 | -49% | 7,188,513/mo | +110% | +56% | 1 mo ago | unknown (–) |
| Mercury | 1,782 | +31% | 3,709,846/mo | +48% | +47% | 5 mo ago | unknown (–) |
| Terrastack | 7 | +0% | 7,657/mo | – | +64% | 2 mo ago | unknown (–) |

## Money signals

| Company | Est. revenue (range) | Revenue / employee | Avg salary | Loaded payroll | Primary capital |
|---|---|---|---|---|---|
| Koah | $509K ($438K–$591K) | $21K | $130K | $4.1M | $25.5M |
| Linear | $81.4M ($70.1M–$94.5M) | $269K | $98K | $38.7M | $134.2M |
| Attio | $45.9M ($39.5M–$53.3M) | $223K | $86K | $23.1M | $116.2M |
| Clay | $300.0M ($258.4M–$348.3M) | $191K | $90K | $184.4M | $317.0M |
| Vercel | $451.0M ($388.5M–$523.5M) | $439K | $128K | $170.3M | $863.0M |
| Retool | $129.1M ($111.2M–$149.9M) | $313K | $133K | $71.4M | $141.0M |
| Ramp | $1.82B ($1.57B–$2.12B) | $486K | $57K | $277.6M | $5.42B |
| Mercury | $684.8M ($589.9M–$795.0M) | $384K | $108K | $251.0M | $657.1M |
| Terrastack | $423K ($364K–$491K) | $60K | $8K | $71K | $0K |

## Invest signal

| Company | Signal | Score | Confidence | Suggested (of $100K) | 🛑/🔴/🟡/🟢 | Strongest / weakest pillar | Key red flag |
|---|---|---|---|---|---|---|---|
| Koah | **INVEST** | 83 | high | $100K | 0/0/3/7 | Traction 97 / Market 50 | none |
| Linear | **INVEST** | 78 | high | $100K | 0/0/6/5 | Team 95 / Market 50 | none |
| Attio | **INVEST** | 75 | high | $100K | 0/0/5/6 | Team 85 / Market 50 | none |
| Clay *(unverified)* | **INVEST** | 73 | medium | $75K | 0/0/0/5 | Team 95 / Market 50 | none |
| Vercel *(unverified)* | **ACCUMULATE** | 58 | low | $25K | 0/0/0/2 | Financing 76 / Team 45 | none |
| Retool *(unverified)* | **AVOID** | 45 | medium | $0 | 0/2/0/1 | Team 70 / Financing 20 | Team is shrinking |
| Ramp *(unverified)* | **HOLD** | 56 | medium | $0 | 0/1/0/5 | Financing 89 / Traction 20 | Team is shrinking |
| Mercury *(unverified)* | **ACCUMULATE** | 70 | medium | $40K | 0/0/0/5 | Team 85 / Market 50 | none |
| Terrastack *(unverified)* | **ACCUMULATE** | 59 | medium | $40K | 0/1/0/4 | Financing 83 / Traction 43 | Team is shrinking |

## Why each revenue estimate is where it is

- **Koah**: band is stale (listed 2-10, actual 24); early-stage: no reported-revenue correction; model and band only; fast headcount growth (+167% yoy) suggests revenue ahead of the band.
- **Linear**: band is stale (listed 51-200, actual 303); estimate is 4.1x the Crustdata band top; fast headcount growth (+71% yoy) suggests revenue ahead of the band.
- **Attio**: band is stale (listed 51-200, actual 206); estimate is 9.2x the Crustdata band top.
- **Clay**: headcount 1,572 is inflated by namesake profiles, so per-employee figures are distorted; band is stale (listed 501-1000, actual 1,572); estimate is 60.0x the Crustdata band top; guardrail fired: capped at 15x band top x4.0 stale-bucket scale = $300,000,000.
- **Vercel**: band is stale (listed 501-1000, actual 1,027); estimate is 4.5x the Crustdata band top.
- **Retool**: estimate is 2.6x the Crustdata band top; shrinking headcount (-10% yoy).
- **Ramp**: headcount 3,757 is inflated by namesake profiles, so per-employee figures are distorted; estimate is 1.8x the Crustdata band top.
- **Mercury**: headcount 1,782 is inflated by namesake profiles, so per-employee figures are distorted.
- **Terrastack**: band is stale (listed 11-50, actual 7); early-stage: no reported-revenue correction; model and band only.

# Revenue model evaluation (D29)

Scored against publicly reported revenue/ARR (`proofroom/data/revenue_ground_truth.json`, cited). **Leave-one-out:** a company's own reported figure is never in the benchmark that estimates it. Offline replay of recorded Crustdata data.

Ensemble weights: benchmark 60%, v1 25%, v2 (social posts) 15% — v2 used: **no** (not available or did not beat v1 in cross-validation).

## Accuracy against reported revenue

| Estimator | n | Median error | Within 30% | Within 2x | Median estimate/reported |
|---|---|---|---|---|---|
| Crustdata band midpoint | 6 | 78% | 17% | 17% | 0.22 |
| Model v1 (band-trained regression) | 6 | 57% | 33% | 33% | 0.43 |
| Reported-revenue benchmark (LOO) | 6 | 42% | 17% | 83% | 1.12 |
| **Calibrated ensemble** | 6 | 31% | 50% | 67% | 0.83 |

Same, excluding companies whose headcount is flagged as inflated by namesake profiles:

| Estimator | n | Median error | Within 30% | Within 2x | Median estimate/reported |
|---|---|---|---|---|---|
| Crustdata band midpoint | 3 | 85% | 0% | 0% | 0.15 |
| Model v1 (band-trained regression) | 3 | 64% | 0% | 0% | 0.36 |
| Reported-revenue benchmark (LOO) | 3 | 47% | 0% | 100% | 1.33 |
| **Calibrated ensemble** | 3 | 20% | 67% | 67% | 0.80 |

## Per company

| Company | Staff | Crustdata band | v1 | Benchmark (LOO) | Ensemble (range) | Reported | Ensemble error | v1 error |
|---|---|---|---|---|---|---|---|---|
| Koah | 24 | $0K–$500K | $540K | – | $540K | – | – | – |
| Linear | 303 | $10.0M–$20.0M | $24.2M | $132.5M | $80.4M ($19.4M–$165.7M) | $100.0M | -20% | -76% |
| Attio | 206 | $2.5M–$5.0M | $11.1M | $68.0M | $39.9M ($8.9M–$85.0M) | – | – | – |
| Clay | 1,572 ⚠️ | $2.5M–$5.0M | $249.2M | $518.8M | $418.2M ($199.4M–$648.5M) | $200.0M | +109% | +25% |
| Vercel | 1,027 | $50.0M–$100.0M | $218.0M | $318.7M | $285.0M ($174.4M–$398.3M) | $600.0M | -52% | -64% |
| Retool | 413 | $20.0M–$50.0M | $44.1M | $188.8M | $123.1M ($35.3M–$236.0M) | $120.0M | +3% | -63% |
| Ramp | 3,757 ⚠️ | $500.0M–$1.00B | $983.2M | $1.24B | $1.16B ($786.6M–$1.55B) | $2.00B | -42% | -51% |
| Mercury | 1,782 ⚠️ | $500.0M–$1.00B | $500.0M | $588.1M | $560.7M ($400.0M–$735.1M) | $650.0M | -14% | -23% |
| Terrastack | 7 | $0K–$500K | $457K | – | $457K | – | – | – |

⚠️ headcount flagged as inflated by namesake profiles (excluded from the benchmark's reference set; their estimates are less reliable).

## Notes per company

- **Koah**: early-stage company (<50 staff or <$20M primary capital): the scaleup revenue-per-employee benchmark does not apply; v1 kept
- **Linear**: estimate is above Crustdata's band ($20.0M top): the band is treated as stale (it tracks a self-reported size bucket); benchmark: 2 reference companies, median reported revenue per employee $437K (leave-one-out)
- **Attio**: estimate is above Crustdata's band ($5.0M top): the band is treated as stale (it tracks a self-reported size bucket); benchmark: 3 reference companies, median reported revenue per employee $330K (leave-one-out)
- **Clay**: estimate is above Crustdata's band ($5.0M top): the band is treated as stale (it tracks a self-reported size bucket); benchmark: 3 reference companies, median reported revenue per employee $330K (leave-one-out)
- **Vercel**: estimate is above Crustdata's band ($100.0M top): the band is treated as stale (it tracks a self-reported size bucket); benchmark: 2 reference companies, median reported revenue per employee $310K (leave-one-out)
- **Retool**: estimate is above Crustdata's band ($50.0M top): the band is treated as stale (it tracks a self-reported size bucket); benchmark: 2 reference companies, median reported revenue per employee $457K (leave-one-out)
- **Ramp**: estimate is above Crustdata's band ($1,000.0M top): the band is treated as stale (it tracks a self-reported size bucket); benchmark: 3 reference companies, median reported revenue per employee $330K (leave-one-out)
- **Mercury**: benchmark: 3 reference companies, median reported revenue per employee $330K (leave-one-out)
- **Terrastack**: early-stage company (<50 staff or <$20M primary capital): the scaleup revenue-per-employee benchmark does not apply; v1 kept

## Caveats

- Only 6 companies have a reported figure (5 company/press, 1 third-party estimate); results are indicative, not statistically strong.
- Reported figures mix ARR, run-rate and 'passed $X' lower bounds, at different dates.
- The benchmark is built from well-known venture-backed scaleups; it does not apply to early-stage companies (Koah, TerraStack keep model v1).

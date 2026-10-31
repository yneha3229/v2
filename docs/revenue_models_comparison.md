# Revenue model bake-off (alternative model families)

Offline: `scripts/compare_revenue_models.py` (0 credits). Code: `proofroom/revenue_models_alt.py`. Chosen parameters: `proofroom/data/revenue_models_alt.json`. Every number below is an ESTIMATE quality measure; no model output is reported revenue.

## 1. Cross-validation on Crustdata bands (126 rows)

Same protocol as v1: 5 folds, seed 7, training on the listed size bucket, held-out rows scored with the headcount-implied bucket. Hyperparameters by inner 4-fold CV on each training fold (never on the test fold); `v1 ridge` keeps v1's lambda 30, which v1 chose on these same folds (mildly optimistic). Error is |log10(pred / band midpoint)|.

| Model | Median abs log10 err | Within 2x | Band hit | Worst over | Worst under | Tuned |
|---|---|---|---|---|---|---|
| (0) baseline: headcount x median rev/employee | 0.441 | 36% | 17% | 247x | 29x | – |
| (a) v1 ridge, lambda 30 (reproduced) | 0.345 | 44% | 24% | 85x | 98x | – |
| (a') ridge, lambda by inner CV | 0.363 | 44% | 22% | 133x | 158x | {"lam": 10.0}, {"lam": 3.0}, {"lam": 30.0} |
| (b) Huber IRLS | 0.372 | 43% | 28% | 138x | 145x | {"lam": 10.0}, {"lam": 3.0}, {"lam": 30.0} |
| (c) interval-censored Tobit (EM) | 0.335 | 43% | 24% | 120x | 171x | {"lam": 1.0}, {"lam": 10.0}, {"lam": 30.0} |
| (d) kNN on rev/employee | 0.433 | 37% | 18% | 169x | 106x | {"k": 20}, {"k": 30}, {"k": 3}, {"k": 8} |
| (e) boosted depth-2 trees | 0.332 | 48% | 33% | 126x | 620x | {"n_trees": 25}, {"n_trees": 50} |
| (f) segment rev/employee | 0.399 | 36% | 18% | 261x | 45x | – |
| (g) equal-weight stack of b-f + ridge | 0.362 | 45% | 28% | 150x | 122x | – |

Differences of 0.01–0.03 in median error are within fold noise at n=126. All models are trained on bands that are biased low for fast-growing companies, so band accuracy is not the deciding metric (section 2).

## 2. Accuracy on publicly reported revenue (6 companies)

Band-trained models are scored straight (they never see reported figures). The bias factor (median reported / model over the OTHER unflagged reported companies) and the revenue-per-employee benchmark are leave-one-out. Ratio = estimate / reported.

**All 6 reported**

| Estimator | n | Median abs % err | Within 30% | Within 2x | Median ratio | Max over | Max under |
|---|---|---|---|---|---|---|---|
| Crustdata band midpoint | 6 | 78% | 17% | 17% | 0.22 | 1.15x | 53.33x |
| v1 point (band-clamped, in production) | 6 | 57% | 33% | 33% | 0.43 | 1.25x | 4.13x |
| Benchmark rev/employee (LOO) | 6 | 42% | 17% | 83% | 1.12 | 2.59x | 1.88x |
| Current calibrated ensemble (D29, LOO) | 6 | 31% | 50% | 67% | 0.83 | 2.09x | 2.11x |
| ridge_v1 raw | 6 | 59% | 17% | 17% | 0.41 | 1.25x | 4.13x |
| ridge raw | 6 | 59% | 17% | 17% | 0.41 | 1.25x | 4.13x |
| huber raw | 6 | 48% | 17% | 67% | 0.60 | 1.55x | 4.96x |
| tobit raw | 6 | 62% | 17% | 17% | 0.38 | 1.15x | 4.49x |
| knn raw | 6 | 60% | 33% | 33% | 0.40 | 1.06x | 6.94x |
| gbm raw | 6 | 51% | 17% | 50% | 0.49 | 0.75x | 5.88x |
| segment raw | 6 | 48% | 17% | 67% | 0.73 | 1.47x | 3.57x |
| stack raw | 6 | 52% | 17% | 50% | 0.48 | 1.14x | 4.70x |
| tobit raw + guardrails | 6 | 62% | 17% | 17% | 0.38 | 1.15x | 4.49x |
| gbm raw + guardrails | 6 | 51% | 17% | 50% | 0.49 | 0.75x | 5.88x |
| ridge_v1 x LOO bias factor | 6 | 30% | 50% | 83% | 1.26 | 3.43x | 1.51x |
| tobit x LOO bias factor | 6 | 31% | 50% | 83% | 1.26 | 3.41x | 1.52x |
| gbm x LOO bias factor | 6 | 73% | 17% | 33% | 0.81 | 2.79x | 3.99x |
| stack x LOO bias factor | 6 | 46% | 33% | 83% | 1.36 | 2.80x | 1.99x |
| ridge_v1 bias-corrected 50/50 benchmark (LOO) | 6 | 14% | 67% | 83% | 1.00 | 2.98x | 1.23x |
| tobit bias-corrected 50/50 benchmark (LOO) | 6 | 14% | 67% | 83% | 0.99 | 2.97x | 1.23x |
| gbm bias-corrected 50/50 benchmark (LOO) | 6 | 46% | 17% | 83% | 0.85 | 2.09x | 1.97x |
| stack bias-corrected 50/50 benchmark (LOO) | 6 | 14% | 67% | 83% | 1.00 | 2.70x | 1.23x |
| tobit bias-corrected 50/50 benchmark + guardrails (LOO) | 6 | 14% | 67% | 100% | 0.99 | 1.50x | 1.23x |
| gbm bias-corrected 50/50 benchmark + guardrails (LOO) | 6 | 46% | 17% | 83% | 0.85 | 2.09x | 1.97x |

**Without namesake-flagged headcounts (Linear, Vercel, Retool)**

| Estimator | n | Median abs % err | Within 30% | Within 2x | Median ratio | Max over | Max under |
|---|---|---|---|---|---|---|---|
| Crustdata band midpoint | 3 | 85% | 0% | 0% | 0.15 | 0.29x | 8.00x |
| v1 point (band-clamped, in production) | 3 | 64% | 0% | 0% | 0.36 | 0.37x | 4.13x |
| Benchmark rev/employee (LOO) | 3 | 47% | 0% | 100% | 1.33 | 1.57x | 1.88x |
| Current calibrated ensemble (D29, LOO) | 3 | 20% | 67% | 67% | 0.80 | 1.03x | 2.11x |
| ridge_v1 raw | 3 | 64% | 0% | 0% | 0.36 | 0.37x | 4.13x |
| ridge raw | 3 | 64% | 0% | 0% | 0.36 | 0.37x | 4.13x |
| huber raw | 3 | 57% | 0% | 33% | 0.43 | 0.59x | 4.96x |
| tobit raw | 3 | 66% | 0% | 0% | 0.34 | 0.34x | 4.49x |
| knn raw | 3 | 68% | 0% | 0% | 0.32 | 0.41x | 6.94x |
| gbm raw | 3 | 38% | 33% | 67% | 0.62 | 0.75x | 5.88x |
| segment raw | 3 | 65% | 0% | 33% | 0.35 | 0.52x | 3.57x |
| stack raw | 3 | 59% | 0% | 0% | 0.41 | 0.44x | 4.70x |
| tobit raw + guardrails | 3 | 66% | 0% | 0% | 0.34 | 0.34x | 4.49x |
| gbm raw + guardrails | 3 | 38% | 33% | 67% | 0.62 | 0.75x | 5.88x |
| ridge_v1 x LOO bias factor | 3 | 27% | 67% | 100% | 1.24 | 1.27x | 1.51x |
| tobit x LOO bias factor | 3 | 28% | 67% | 100% | 1.25 | 1.28x | 1.52x |
| gbm x LOO bias factor | 3 | 125% | 0% | 0% | 2.25 | 2.79x | 3.99x |
| stack x LOO bias factor | 3 | 50% | 0% | 100% | 1.42 | 1.58x | 1.99x |
| ridge_v1 bias-corrected 50/50 benchmark (LOO) | 3 | 19% | 67% | 100% | 0.94 | 1.41x | 1.23x |
| tobit bias-corrected 50/50 benchmark (LOO) | 3 | 19% | 67% | 100% | 0.93 | 1.42x | 1.23x |
| gbm bias-corrected 50/50 benchmark (LOO) | 3 | 42% | 33% | 67% | 1.09 | 2.09x | 1.74x |
| stack bias-corrected 50/50 benchmark (LOO) | 3 | 18% | 67% | 100% | 0.92 | 1.50x | 1.23x |
| tobit bias-corrected 50/50 benchmark + guardrails (LOO) | 3 | 19% | 67% | 100% | 0.93 | 1.42x | 1.23x |
| gbm bias-corrected 50/50 benchmark + guardrails (LOO) | 3 | 42% | 33% | 67% | 1.09 | 2.09x | 1.74x |

Per company (estimate / reported):

| Company | v1 point | Ensemble D29 | tobit raw | gbm raw | tobit chosen (LOO) | gbm chosen (LOO) |
|---|---|---|---|---|---|---|
| Linear | 0.24 | 0.80 | 0.22 | 0.17 | 0.93 | 0.58 |
| Clay ⚠️ | 1.25 | 2.09 | 1.15 | 0.65 | 1.50 | 1.50 |
| Vercel | 0.36 | 0.48 | 0.34 | 0.62 | 0.81 | 1.09 |
| Retool | 0.37 | 1.03 | 0.34 | 0.75 | 1.42 | 2.09 |
| Ramp ⚠️ | 0.49 | 0.58 | 0.45 | 0.36 | 0.91 | 0.60 |
| Mercury ⚠️ | 0.77 | 0.86 | 0.41 | 0.18 | 1.05 | 0.51 |

⚠️ headcount flagged as inflated by namesake profiles.

## 3. Guardrails

`apply_guardrails`: revenue per employee clipped to $20K–$1.5M (public SaaS/fintech leaders sit around $300K–$1M per employee; $20K is below any functioning software business, $1.5M above all but a few outliers); never below the band floor when the band is trusted (listed size bucket = bucket implied by headcount, no namesake flag); never above 15x the band top, with that cap scaled up by (implied / listed bucket midpoint) when the listed bucket is stale. Every clip is flagged in the output. The per-employee floor is skipped for namesake-inflated headcounts.

On the 126 band rows (held-out CV predictions; ratios vs band midpoint):

| Model | Fired | Band floor | Band cap | Rev/emp cap | Rev/emp floor | Worst over before → after | Worst under before → after | Median err before → after | Within 2x before → after | Worst over / under after, plausible bands only |
|---|---|---|---|---|---|---|---|---|---|---|
| ridge_v1 | 25% | 29 | 1 | 1 | 1 | 85x → 83x | 98x → 35x | 0.345 → 0.228 | 44% → 60% | 10x / 5x |
| tobit | 25% | 29 | 1 | 1 | 2 | 120x → 93x | 171x → 59x | 0.335 → 0.229 | 43% → 58% | 22x / 7x |
| gbm | 25% | 27 | 1 | 1 | 5 | 126x → 98x | 620x → 47x | 0.332 → 0.176 | 48% → 63% | 16x / 7x |
| stack | 24% | 29 | 1 | 1 | 0 | 150x → 106x | 122x → 46x | 0.362 → 0.189 | 45% → 59% | 11x / 5x |

19 of 126 band labels themselves imply revenue per employee outside $20K–$1.5M (e.g. Telegram listed 11-50 with 3,530 staff and a $5–10M band; Unison Risk Advisors 73 staff with a $100–500M band). The remaining large 'errors' are against those labels; guardrailed outputs can never leave the per-employee range, so against any plausible truth the worst case is bounded by construction (1.5M / 20K = 75x at the extreme, far less in practice).

On the 9 study companies, raw model outputs clipped: baseline 0/9, ridge_v1 0/9, ridge 0/9, huber 2/9, tobit 0/9, knn 1/9, gbm 0/9, segment 0/9, stack 0/9. Chosen pipeline (tobit, bias-corrected + benchmark): 1/9 clipped.

- Clay: capped at 15x band top x4.0 stale-bucket scale = $300,000,000 (was $594,464,446)

Worst ratios on reported revenue after guardrails (chosen pipeline, LOO): max over 1.50x, max under 1.23x.

## 4. Why over or under? (per company)

Drivers: contribution of each standardized feature to the tobit linear model (coef x standardized value, log10 units; x10^v as a factor). Contributions + intercept reproduce the raw prediction exactly (max check error 8.9e-16). Estimate = chosen pipeline (LOO for reported companies).

Intercept: 7.523 (= $33.4M for an average training row).

| Company | Staff | Listed → implied bucket | Band | Estimate | Reported | Est/rep | Implied rev/emp | Benchmark rev/emp | HC yoy | Web yoy | Primary capital / staff | Top 4 drivers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Koah | 24 | 2-10 → 11-50 | $0K–$500K | $509K | – | – | $21K | $330K | +167% | +29% | $1.1M | log_size_bucket -0.64; hc_growth_log -0.41; log_headcount -0.32; age_years -0.32 |
| Linear | 303 | 51-200 → 201-500 | $10.0M–$20.0M | $93.2M | $100.0M | 0.93 | $308K | $437K | +71% | +115% | $443K | hc_growth_log -0.18; age_years -0.09; cat_ai +0.05; log_size_bucket +0.04 |
| Attio | 206 | 51-200 → 201-500 | $2.5M–$5.0M | $45.9M | – | – | $223K | $330K | +55% | +128% | $564K | largest_country_high_cost -0.20; hc_growth_log -0.13; cat_ai -0.12; age_years -0.09 |
| Clay ⚠️ | 1,572 | 501-1000 → 1001-5000 | $2.5M–$5.0M | $300.0M | $200.0M | 1.50 | $191K | $330K | +46% | +10% | $202K | log_size_bucket +0.64; log_headcount +0.23; hc_growth_log -0.10; cat_ai +0.05 |
| Vercel | 1,027 | 501-1000 → 1001-5000 | $50.0M–$100.0M | $487.9M | $600.0M | 0.81 | $475K | $310K | +26% | +154% | $840K | log_size_bucket +0.64; log_headcount +0.18; cat_ai -0.12; age_years +0.10 |
| Retool | 413 | 201-500 → 201-500 | $20.0M–$50.0M | $170.2M | $120.0M | 1.42 | $412K | $457K | -10% | – | $341K | hc_growth_log +0.15; cat_ai -0.12; log_headcount +0.06; log_size_bucket +0.04 |
| Ramp ⚠️ | 3,757 | 1001-5000 → 1001-5000 | $500.0M–$1.00B | $1.82B | $2.00B | 0.91 | $486K | $330K | -49% | +110% | $1.4M | log_size_bucket +0.64; hc_growth_log +0.44; log_headcount +0.35; age_years -0.09 |
| Mercury ⚠️ | 1,782 | 1001-5000 → 1001-5000 | $500.0M–$1.00B | $684.8M | $650.0M | 1.05 | $384K | $330K | +31% | +48% | $369K | log_size_bucket +0.64; log_headcount +0.25; cat_ai +0.05; hc_growth_log -0.04 |
| Terrastack | 7 | 11-50 → 2-10 | $0K–$500K | $423K | – | – | $60K | $330K | +0% | – | $0K | log_size_bucket -1.09; log_headcount -0.49; age_years -0.32; log_funding -0.18 |

Plain-English reasons:

- **Koah**: No reported revenue to compare: band is stale (listed 2-10, actual 24); early-stage: no reported-revenue correction; model and band only; fast headcount growth (+167% yoy) suggests revenue ahead of the band.
- **Linear**: Close (0.93x reported): low revenue per employee ($330K reported vs $437K benchmark); band is stale (listed 51-200, actual 303); estimate is 4.7x the Crustdata band top; fast headcount growth (+71% yoy) suggests revenue ahead of the band.
- **Attio**: No reported revenue to compare: band is stale (listed 51-200, actual 206); estimate is 9.2x the Crustdata band top.
- **Clay**: Overestimated (1.50x reported): headcount 1,572 is inflated by namesake profiles, so per-employee figures are distorted; band is stale (listed 501-1000, actual 1,572); estimate is 60.0x the Crustdata band top; guardrail fired: capped at 15x band top x4.0 stale-bucket scale = $300,000,000.
- **Vercel**: Close (0.81x reported): high revenue per employee ($584K reported vs $310K benchmark), unusually efficient; band is stale (listed 501-1000, actual 1,027); estimate is 4.9x the Crustdata band top.
- **Retool**: Overestimated (1.42x reported): low revenue per employee ($291K reported vs $457K benchmark); estimate is 3.4x the Crustdata band top; shrinking headcount (-10% yoy).
- **Ramp**: Close (0.91x reported): headcount 3,757 is inflated by namesake profiles, so per-employee figures are distorted; estimate is 1.8x the Crustdata band top.
- **Mercury**: Close (1.05x reported): headcount 1,782 is inflated by namesake profiles, so per-employee figures are distorted.
- **Terrastack**: No reported revenue to compare: band is stale (listed 11-50, actual 7); early-stage: no reported-revenue correction; model and band only.

## 5. Recommendation

RECOMMENDATION_PLACEHOLDER

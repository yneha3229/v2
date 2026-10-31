# Revenue model v3: results

Everything here is an **ESTIMATE** from indexed Crustdata data, not reported revenue.
Code: `proofroom/revenue_model_3.py`. Training and evaluation: `scripts/train_revenue_model_3.py`
(`fetch`, then `train`). Parameters: `proofroom/data/revenue_model_3.json`. Stripped inputs:
`proofroom/data/model3_features.json`. Tests: `tests/test_revenue_model_3.py`. Study-company
results replay offline from `fixtures/<name>/crustdata/` (the new mention and market-count records were added there, and no existing file was overwritten).

**Bottom line:** the ridge v3 (v1 plus the new features) is **worse** than v1, both in cross-validation and on reported revenue. Do not ship it as a replacement. The one useful new estimator is **payroll-implied revenue**: k × loaded payroll on clean headcount, with k fitted on *band* data only. On the 6 reported companies it scores 34% median error and 83% within 2x. Without the namesake-flagged companies it scores 26% median error and 100% within 2x. That matches the current D29 ensemble (36% / 83%) while using no reported figures at all. Clean headcount helps as a diagnostic, but it does not fix Clay. It makes Ramp worse.

## Method

- **Training data:** a stratified 80 of the 126 `training_set.json` rows: 16 per size stratum, ordered by `sha256('rev3:<id>')`. Each row has one Company Enrich call (headcount, taxonomy, hiring, funding, locations), free mention counts and two market-width counts. The target is the same as v1: log10 of the Crustdata revenue band midpoint. The band is third-party, not reported revenue.
- **CV protocol:** the same as v1. 5 folds with seed 7. Held-out rows are scored with the headcount-implied size bucket, and the metric is |log10 error| against the band midpoint. **v1's method and lambda (midpoint ridge, λ = 30) are reused unchanged for every variant**, so nothing is tuned on these folds. The comparisons use v1 refit on the same 80 rows. A paired sign test is run against that v1.
- **Reported revenue:** the 6 companies in `revenue_ground_truth.json`. Leave-one-out (LOO) is used wherever a reported figure feeds an estimator. The v1 and v3 points are clamped into the effective Crustdata band, as in production.

## New features and their sources

| Group | Features | Source |
|---|---|---|
| clean_headcount | log clean headcount, clean/raw share | Company Enrich `headcount.by_region_absolute`, `by_role_absolute`, `locations.all_office_addresses`. Kept countries: the HQ country, any country with an office, and `TECH_HUBS` countries no larger than the HQ country. Functions dropped unless the description names the domain: Education, Community and Social Services, Military and Protective Services, Healthcare Services, Real Estate. clean = headcount × min(region share, function share). The kept share rescales inflated region sums to headcount. |
| loaded_payroll | log loaded payroll, log payroll per head | `salary_benchmarks.json` cells (BLS OEWS May 2025, ONS ASHE 2025, Payscale) through `economics.dedupe_regions`, `role_people` and `Benchmarks.get`, applied to the clean counts, × 1.3. Startup pay: tech roles outside India get the file's employer tier, either `scaleup` 1.21 (BLS NAICS 513200 / all industries; software or fintech with ≥ $100M funding) or `startup` 1.01 (Carta H1 2025, https://carta.com/data/startup-compensation-h1-2025/). **No levels.fyi or Glassdoor lookups were made**, because the file's tiers covered the adjustment. |
| investor_quality | count of top-tier investors (capped at 8), top-tier lead on the last round | `funding.investors` and `funding.milestones[].investors/lead_investors`, matched against the 22-firm `TOP_TIER_INVESTORS` list (Sequoia … Y Combinator, with aliases). Secondary rounds are ignored for the lead. |
| mentions | log posts by persons mentioning the company (all time and 12 months), log of those posts with partnership phrases | `POST /social_post/search` with `mentions.company_id in [id]` and `actor.actor_type = person`, `limit 0`, which returns total_count for 0 credits (https://docs.crustdata.com/social-post-docs/indexed-search/reference.md). The partnership count adds `text [.]` "sponsored", "partnered with", "powered by" or "in partnership". |
| market_width | log pool size, log funded peers in 24 months | `POST /company/search` with `taxonomy.categories =` the first specific category (`signals.candidate_categories`), limit 1 (~0.13 credits), and the same with `funding.last_fundraise_date ≥` as_of − 24 months |
| hiring_intensity | openings / clean headcount | Company Enrich `hiring.openings_count`. Headcount growth is already in v1. |

## Cross-validation on band data (n = 80) and ablation

| Variant | Median abs log10 error | Within 2x | Band hit | Mean abs log10 error | Rows better / worse than v1 (sign-test p) |
|---|---|---|---|---|---|
| v1 (16 features, refit on these 80) | 0.360 | 38% | 20% | 0.478 | – |
| v1 + clean_headcount | 0.363 | 42% | 20% | 0.481 | 40 / 40 (1.00) |
| v1 + loaded_payroll | 0.372 | 40% | 20% | 0.484 | 40 / 40 (1.00) |
| v1 + investor_quality | 0.354 | 39% | 20% | 0.485 | 35 / 45 (0.31) |
| v1 + mentions | 0.388 | 38% | 19% | 0.479 | 35 / 45 (0.31) |
| v1 + market_width | 0.355 | 39% | 21% | 0.481 | 34 / 46 (0.22) |
| v1 + hiring_intensity | **0.347** | 40% | 17% | **0.469** | 46 / 34 (0.22) |
| **v3 = v1 + all new** (saved) | 0.405 | 41% | 25% | 0.482 | 38 / 42 (0.74) |
| Baseline: raw headcount × median revenue per employee | 0.415 | 31% | 14% | 0.532 | 33 / 47 (0.15) |
| Baseline: clean headcount × median revenue per clean employee | 0.469 | 33% | 16% | 0.579 | 31 / 49 (0.06) |
| Payroll-implied, k by stage | 0.585 | 33% | 17% | 0.686 | 30 / 50 (0.03) |
| Payroll-implied, single k | 0.621 | 25% | 10% | 0.761 | 25 / 55 (0.001) |

For reference, published v1 on all 126 rows scores 0.345 median and 44% within 2x.

Reading:

- No new group improves on v1 significantly. Hiring intensity gives the only small gain (0.347 vs 0.360, p = 0.22). Investor quality and market width are neutral. Clean headcount and payroll add nothing beyond `log_headcount`. Mentions hurt slightly. All features together over-fit 80 rows with 28 features (0.405).
- Payroll-implied and clean-headcount baselines are much worse **against the band**. That is expected: Crustdata's band tracks the listed size bucket, so raw headcount is what generated it. The band is the wrong yardstick for any estimator that corrects headcount.
- Clean headcount changed 43 of 80 training rows. The median clean share was 0.977, so most corrections are small.
- Band-fitted k: early stage (< $100M funding) 9.64, late stage 1.89. The early k is unusable in practice: band midpoints for small or bootstrapped companies are high relative to payroll.

## Reported revenue (6 companies)

Columns:

- **v1** and **v3**: band-clamped points.
- **Payroll (band k)**: late-stage k = 1.89 from band data. No reported figure is used.
- **Payroll (LOO)**: k = median reported/payroll ratio of the other 5 companies.
- **Clean benchmark (LOO)**: clean headcount × median reported revenue per clean employee of the other 5.
- **Ensemble**: geometric mean of v3, payroll (LOO) and clean benchmark (LOO). This was pre-registered.
- **Ens. v1**: the same with v1 in place of v3. This variant was chosen after seeing the results.

| Estimator | n | Median abs % error | Within 30% | Within 2x | Median estimate/reported | Worst over | Worst under |
|---|---|---|---|---|---|---|---|
| v1 | 6 | 57% | 33% | 33% | 0.43 | Clay 1.25x | Linear 0.24x |
| v3 | 6 | 79% | 17% | 17% | 0.25 | Clay 2.05x | Linear 0.15x |
| **Payroll (band k)** | 6 | **34%** | 50% | **83%** | 0.77 | Clay 1.76x | Ramp 0.13x |
| Payroll (LOO) | 6 | 44% | 50% | 67% | 1.00 | Clay 2.28x | Ramp 0.16x |
| Clean benchmark (LOO) | 6 | 36% | 50% | 67% | 1.01 | Clay 2.57x | Ramp 0.16x |
| Ensemble (pre-registered) | 6 | 49% | 33% | 50% | 0.63 | Clay 2.29x | Ramp 0.19x |
| Ens. v1 (post hoc) | 6 | 41% | 33% | 83% | 0.77 | Clay 1.94x | Ramp 0.24x |

The same estimators without the namesake-flagged companies (Clay, Ramp and Mercury are flagged), leaving Linear, Vercel and Retool:

| Estimator | n | Median abs % error | Within 30% | Within 2x | Median estimate/reported | Worst over | Worst under |
|---|---|---|---|---|---|---|---|
| v1 | 3 | 64% | 0% | 0% | 0.36 | Retool 0.37x | Linear 0.24x |
| v3 | 3 | 83% | 0% | 0% | 0.17 | Vercel 0.25x | Linear 0.15x |
| **Payroll (band k)** | 3 | **26%** | 67% | **100%** | 0.77 | Retool 1.25x | Vercel 0.58x |
| Payroll (LOO) | 3 | 26% | 67% | 100% | 1.00 | Retool 1.63x | Vercel 0.75x |
| Clean benchmark (LOO) | 3 | 29% | 67% | 100% | 1.13 | Retool 1.29x | Vercel 0.56x |
| Ensemble (pre-registered) | 3 | 45% | 33% | 67% | 0.55 | Retool 0.70x | Vercel 0.47x |
| Ens. v1 (post hoc) | 3 | 35% | 33% | 100% | 0.65 | Retool 0.92x | Vercel 0.53x |

The current D29 ensemble (`docs/revenue_evaluation.md`) scores 36% median error and 83% within 2x on all 6, and 28% and 67% on the 3 unflagged. This is only 6 companies, three of them flagged, so no difference here is statistically meaningful.

### Clay, Ramp and Vercel: did the errors shrink?

- **Clay overprediction did not shrink. It grew** for v3 (2.05x, against 1.25x for v1) and stays at about 2x for the payroll and benchmark estimators. Clean headcount removes only 196 of 1,572 indexed staff: 93 Education, 38 Community and Social Services, and 64 in Pakistan. Clay's namesakes (pottery, Clay County schools and offices) sit mostly **in the US**, which is Clay's own HQ country, and in ordinary functions. A country and function filter cannot see them. Clay's revenue per clean employee is about $145K, against $290K–$585K for the other five, which says the 1,376 clean staff are still roughly 2x inflated. v3 makes it worse: Clay's mentions (23,911 person posts, the most of the 9) push the prediction up.
- **Ramp's underprediction got worse.** Clean headcount is 985 (Brazil 6,877 and Italy 411 removed; the kept 2,591 is rescaled from 9,879 located to 3,757 headcount). Every staff-based estimator then lands at 0.13x–0.24x of $2B. The reason is the business model: Ramp earns card interchange, which scales with customer card spend, not staff. Its revenue per clean employee is about $2.0M. No payroll or headcount multiple from software companies can reach that.
- **Vercel's underprediction shrank** from 0.36x (v1) to 0.75x (payroll LOO), 0.58x (payroll, band k) and 0.56x (clean benchmark). Vercel has no namesake problem: clean equals raw at 1,027. Its gap comes from revenue per employee of about $584K. Usage-billed hosting passes cloud cost through to revenue, so revenue per head runs above SaaS norms. Payroll per head ($177K loaded, the highest of the study set, with a SF-heavy mix) captures part of that.

## Per company (9)

| Company | Raw → clean staff | Removed | Loaded payroll (per head) | Top-tier investors / last lead | Person mentions (12 m) | v1 | v3 | Payroll (band k) | Reported |
|---|---|---|---|---|---|---|---|---|---|
| Koah | 24 → 24 | – | $3.9M ($164K) | 0 / Theory Ventures | 68 (54) | $540K | $1.20M | ($37.9M, early k: not usable) | – |
| Linear | 303 → 303 | – | $40.6M ($134K) | 3 / Accel (top) | 3,219 (1,863) | $24.2M | $14.7M | $77.0M | $100M |
| Attio | 206 → 206 | – | $25.6M ($124K) | 2 / GV (top) | 3,423 (2,410) | $11.1M | $7.3M | $48.4M | – |
| Clay ⚠️ | 1,572 → 1,376 | Education 93, Community 38, PAK 64 | $185M ($135K) | 3 / Wellington | 23,911 (13,198) | $249M | $411M | $351M | $200M |
| Vercel | 1,027 → 1,027 | – | $182M ($177K) | 6 / Accel, GIC (top) | 14,322 (7,516) | $218M | $151M | $345M | $600M |
| Retool | 413 → 413 | – | $79.5M ($192K) | 2 / Sequoia (top) | 1,956 (541) | $44.1M | $20.0M | $151M | $120M |
| Ramp ⚠️ | 3,757 → 985 | BRA 6,877, ITA 411 (rescaled) | $134M ($136K) | 13 / Founders Fund, Thrive (top) | 9,976 (5,234) | $983M | $500M | $255M | $2.0B |
| Mercury ⚠️ | 1,782 → 1,737 | Military and Protective Services 39 | $265M ($152K) | 3 / TCV | 3,680 (1,635) | $500M | $500M | $502M | $650M |
| TerraStack | 7 → 5.8 | Education 2 (of 12 with a function) | $59K ($10K, India) | 0 / Google DeepMind (as indexed) | 13 (12) | $457K | $500K (raw $519K, band cap) | $571K | – |

The TerraStack v3 point is $500K: the raw model gave $519K, clamped to the $0–$500K band.

One line per company:

- **Koah:** no namesake issue. At Series A, payroll-implied revenue is meaningless (band k for early-stage companies is 9.6), so v1's ~$0.5M stands.
- **Linear:** clean staff 303. Revenue per employee is about $330K, and payroll-implied ($77M with band k, $100M LOO) is far closer to the reported $100M+ than v1 or v3 (0.15–0.24x), which follow a stale $10–20M band.
- **Attio:** clean 206. Payroll-implied gives $48M (band k) to $63M (reported k), against v1 at $11M. There is no reported figure; the company has said it is on track to 4x ARR, so treat this as an upper-side estimate.
- **Clay:** clean staff 1,376 (only 12% removed). US-based namesakes survive the country filter. Revenue per clean employee of about $145K implies the true team is roughly half that, so every staff-based method overpredicts by about 2x.
- **Vercel:** clean equals raw (1,027). Revenue per employee is about $584K because usage-billed infrastructure passes cloud cost through to revenue. Payroll-implied halves v1's error.
- **Retool:** clean 413. Revenue per employee is about $290K. Payroll-implied gives $151M (band k) to $196M (LOO) against the reported $120M estimate; v1 and v3 follow a stale $20–50M band.
- **Ramp:** clean headcount 985 (Brazil namesakes removed, rescaled from 9,879 located). Revenue per clean employee is about $2.0M because interchange revenue scales with card spend, not staff. All staff-based methods underpredict 4–8x.
- **Mercury:** small clean-up (39 Military and Protective Services profiles; Mercury Systems is a namesake). Payroll-implied gives $502M (band k) and $652M (LOO) against the reported $650M. This is the best case.
- **TerraStack:** 7 → 5.8 staff, India-priced payroll of $59K loaded. All methods agree at about $0.45–0.57M, inside the $0–500K band, so there is no evidence against the band.

## Recommendation

1. **Do not replace v1 with ridge v3.** It is worse in CV (0.405 vs 0.360) and on reported revenue (79% vs 57%). The saved `revenue_model_3.json` is the pre-registered full v3, kept only for transparency.
2. **Add payroll-implied revenue (late-stage, band-fitted k = 1.89) as an ensemble member** for companies with ≥ $100M funding. It is the only estimator here that uses no reported figure and still reaches 34% median error and 83% within 2x (26% and 100% unflagged). The reported-company k (2.46) is close to it, which is a useful cross-check. Do not use it for early-stage companies.
3. **Keep clean_headcount as a data-quality diagnostic and as the headcount for payroll.** It does not belong in the regression. It catches foreign namesakes (Ramp, Mercury) and cannot catch same-country namesakes (Clay). For Clay-like cases, a person-level check would be needed, such as the share of sampled profiles whose title mentions the product.
4. **Hiring intensity** is the only regression feature worth re-testing on all 126 rows, at an extra ~92 credits for 46 enrich calls. Investor quality, mentions and market width add nothing beyond v1's funding and headcount features.
5. **Fintech (Ramp) needs a business-model term**, such as interchange or payments volume. No staff-based multiple reaches $2M per employee.

`predict_v3()` returns all of these estimators. `ensemble_usd` is the pre-registered combination. `ensemble_recommended_usd` uses the v1 point, payroll (reported k) and clean benchmark; it was chosen after seeing these 6 companies and is not independently validated.

## Cost

| | Credits |
|---|---|
| Company Enrich, 80 companies plus 1 probe of 2 | 164 |
| Market-width counts (training and study) | ~22.5 |
| Mention counts | 0 (`limit 0`) |
| **Own spend** | **~186** (budget ≤ 300) |

The `/account/credits` balance went from 14,669.35 at the start to 14,481.76 at the end, a drop of 187.6. That balance is shared with concurrent agents.

## Caveats

- Only 6 companies have reported figures, three of them namesake-flagged. Reported figures mix ARR, run-rate and "passed $X" lower bounds.
- The band target rewards raw headcount, so the CV systematically penalizes any headcount correction.
- 80 of the 126 training rows were used to fit the budget. Lambda was reused from v1, which picked it by CV on all 126 rows including these 80, so v1's mild optimism carries over.
- Salary cells are medians for all employers. The employer-tier multipliers are industry proxies, not company figures.

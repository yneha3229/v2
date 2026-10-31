# Revenue model 2 (rev-2): social-post features. Results

Every figure here is an **ESTIMATE**. The training target is Crustdata's third-party revenue band, not reported revenue. Rev-2 is separate from rev-1: the code is in `proofroom/revenue_model_2.py` and `scripts/train_revenue_model_2.py`, and the model is in `proofroom/data/revenue_model_2.json`. It imports rev-1's feature code, target, ridge/interval-EM fit, CV folds and band clamp from `proofroom/revenue_model.py`, and uses them read-only.

## Data source and permission check

- **Company Enrich `social_posts` was not available.** On koahlabs.com (3718859), `fields: ["basic_info","social_posts"]` returned **403 `permission_error`**: "Access denied to fields: social_posts". `/account/endpoints` also lists `social_posts` as disabled for `/company/enrich`.
- **Social Post Search (`POST /social_post/search`) is enabled.** It costs 0.5 credits per post returned, and `limit: 0` count queries are free. Rev-2 uses it with these settings:
  - filter `actor.crustdata_entity_id` = Crustdata company id and `actor.actor_type` = company;
  - newest first;
  - `limit` 10, the same "10 most recent posts" window the Enrich add-on documents.
- **Shape check (Koah).** Koah returned 7 posts for 3.5 credits. Each post has these keys: `share_url`, `text`, `date_posted` (ISO timestamp), `post_type` (`original`, `repost_quote`, `repost_without_thoughts`), `has_video`, `content_types`, `hashtags`, and `engagement` {`total_reactions`, `total_comments`, `num_shares`, `reactions_by_type`}.
- **Plain reshares.** This endpoint also returns plain reshares (`repost_without_thoughts`), which the Enrich add-on excludes. Rev-2 keeps them, and their engagement is the original post's engagement.
- **Credits.** The account balance was 15,086.58 at task start and 14,669.35 at the end. Rev-2's own spend, summed from `x-credits-used`, was **401.5**:
  - Koah probe: 3.5;
  - 80-company pull: 362;
  - 9 study companies: 36.

  The balance is shared with agents running at the same time, which accounts for the rest of the drop. It also lagged right after the pull.

## Features

The model uses rev-1's 16 features unchanged, plus 14 social features computed as of 2026-10-31. A company with no posts gets 0 for every social feature, which `has_posts` = 0 marks.

| Feature | Definition |
|---|---|
| `has_posts` | 1 if at least one post is returned |
| `log_total_posts` | log10(1 + `total_count`): all company posts indexed (free count) |
| `posts_per_30d` | n / max(newest − oldest post date, 30 days) × 30, capped at 30 |
| `days_since_last_post` | as-of date − newest post date, capped at 730 |
| `log_median_engagement`, `log_mean_engagement` | log10(1 + median or mean of reactions + comments + shares per post). The raw median and mean are stored but not modelled. |
| `video_share` | share of posts with `has_video` (or a video content type) |
| `original_share` | share of posts with `post_type` `original` |
| `topic_customers` | share of posts whose text matches customer, case study, client, partnered with, trusted by, powering or use case |
| `topic_launches` | launch, introducing, new feature, now available, release or beta |
| `topic_hiring` | hiring, join our team, we're hiring or open role |
| `topic_funding` | raised, funding, series A–H, seed or investors |
| `topic_partnerships` | partnership, partner or integration |
| `topic_events` | webinar, conference or summit |

## Training subset

The subset comes from `proofroom/data/training_set.json`, the same 126 private companies rev-1 uses, each with a Crustdata revenue band.

- **Selection.** Inside each of the 5 size strata, rows are ordered by sha256("rev2:<id>") and the first 16 are taken, giving **80 companies**. The selection is deterministic and unrelated to size or revenue.
- **Posts.** 76 of the 80 companies have posts, and 68 hit the 10-post window.
- **Stored data.** The derived features, plus at most 200 characters of the 3 newest posts per company, are in `proofroom/data/social_posts_training.json`.

## Cross-validation on the same 80 companies

All models use the same rows and the same rev-1 folds (5-fold, seed 7). Each model's fit method and lambda are tuned by that CV, using rev-1's rule, which makes the scores mildly optimistic. Held-out rows are scored with the headcount-implied size bucket, as at inference.

| Model | Fit (λ) | Within 2x | Median abs log10 err | Mean abs log10 err | Band hit |
|---|---|---|---|---|---|
| Baseline: headcount × median revenue/employee | — | 34% | 0.494 | 0.596 | 20% |
| v1 refit on the subset (16 features) | interval EM (10) | 36% | 0.376 | 0.497 | **28%** |
| **v2** (16 + 14 social) | interval EM (10) | **45%** | **0.357** | **0.492** | 21% |
| Ablation: v1 + `has_posts`, `log_total_posts` | interval EM (10) | 35% | 0.394 | 0.506 | 24% |
| Ablation: v1 + volume + activity | midpoint (30) | 39% | 0.424 | 0.501 | 20% |
| Ablation: v1 + `has_posts` + topics | interval EM (30) | 36% | 0.397 | 0.512 | 24% |

For reference, rev-1 on all 126 companies scores 44% within 2x, 0.345 median error and 24% band hit; its baseline scores 36%, 0.441 and 17%.

**Paired comparison (held-out |log10 error|, v2 against v1):**

- v2 is closer on **34 of 80** companies, and v1 is closer on 46.
- The mean difference is 0.004 in v2's favour; the median difference is −0.025.
- A two-sided sign test gives p = 0.22.

Against the baseline, v2 is closer on 42 of 80.

**Verdict: social posts do not reliably help.**

- **Mixed headline metrics.** v2 is better on within-2x and median error but worse on band hit and on the 80th-percentile error (0.788 against 0.739).
- **Paired comparison.** v1 is closer for more companies, and the difference is not significant.
- **Ablations.** Every subset of the social features scores worse than v1 alone. The full-set gain therefore looks like noise from n = 80 with 30 features.
- **Role in the product.** v2 should be treated at most as a low-weight secondary signal, not a replacement for v1.

## Largest standardized social coefficients (final v2 fit, 80 companies)

| Feature | Coef | Feature | Coef |
|---|---|---|---|
| `log_total_posts` | +0.154 | `topic_funding` | −0.076 |
| `original_share` | +0.118 | `posts_per_30d` | −0.074 |
| `video_share` | +0.107 | `topic_partnerships` | +0.073 |
| `log_mean_engagement` | −0.094 | `topic_customers` | +0.054 |
| `topic_events` | −0.087 | `days_since_last_post` | −0.038 |

The size features carry most of the weight, as in rev-1. Total indexed post volume is the strongest social term, and it is largely a proxy for company age and size.

## Nine study companies

These rows come from a FIXTURE replay: `scripts/train_revenue_model_2.py apply --offline` reproduces them exactly. In the table:

- **v1** is `revenue_model.estimate_revenue`, the shipped rev-1 model (126 rows).
- **v2** is `estimate_revenue_v2`, its point estimate after the clamp into the band, with rev-1's stale-band rule.
- **Reported** is `best_estimate_usd` from `proofroom/data/revenue_ground_truth.json`.
- **Range** is v2's point ×/÷ 10^0.357 (the CV median error), intersected with the band.

| Company | id | Band | Posts (window/total) | v1 point | v2 raw | v2 point (range) | Reported | v1 err | v2 err |
|---|---|---|---|---|---|---|---|---|---|
| Koah | 3718859 | $0–0.5M* | 7/7 | $0.54M | $0.16M | $0.16M (0.07–0.37) | n/a | — | — |
| Linear | 633791 | $10–20M* | 10/207 | $24.2M | $36.9M | $36.9M (16–84) | $100M | −76% | −63% |
| Attio | 664000 | $2.5–5M* | 10/253 | $11.1M | $4.7M | $4.7M (2.5–10.7) | n/a | — | — |
| Clay | 1010356 | $2.5–5M* | 10/490 | $249M | $310M | $310M (136–704) | $200M | +25% | +55% |
| Vercel | 631347 | $50–100M* | 10/590 | $218M | $206M | $206M (91–468) | $600M | −64% | −66% |
| Retool | 633593 | $20–50M | 10/433 | $44.1M | $78.3M | $50.0M (22–50) | $120M | −63% | −58% |
| Ramp | 689494 | $500M–1B | 10/1128 | $983M | $1.71B | $1.00B (0.5–1.0) | $2.0B | −51% | −50% |
| Mercury | 631990 | $500M–1B | 10/435 | $500M | $239M | $500M (0.5–1.0) | $650M | −23% | −23% |
| TerraStack | 6421460 | $0–0.5M† | 2/2 | $0.46M | $0.03M | $0.03M (0.01–0.06) | n/a | — | — |

\* The listed size bucket is below the bucket the headcount implies, so the band is used as a floor only.

† The listed bucket (11-50) is above the bucket that 7 staff imply, so the band is used as a cap only.

**v2 against v1 on the 6 companies with a reported figure:**

- v2 is closer on 3: Linear, Retool and Ramp.
- v1 is closer on 2: Clay and Vercel.
- Mercury is a tie, because both estimates are clamped to the band floor.
- The median |% error| is about 57% for both (56.6% for v2, 57.0% for v1).

**What the comparison shows:**

- **Both models underestimate well-known companies.** The band they are trained on sits below reported ARR for these companies.
- **The band clamp can hurt v2.** For Retool and Ramp, v2's unclamped raw value is closer to the reported figure than its clamped point.
- **The smallest companies diverge most.** For Koah and TerraStack, v2 is far below v1. Few posts and low engagement pull v2 down, while v1 sits near the band's top.

## Caveats

- **Short window.** At most the 10 most recent posts are used, so cadence and topics describe only weeks to months of activity for active companies.
- **Rough topic rules.** The topic shares are keyword rules. For example, "partner" also matches investor-partner posts, and "seed" can match unrelated text.
- **Small sample.** n = 80 with 30 features. Lambda and method are tuned by the same CV that is reported. The paired gain is not significant.
- **Posts are a chosen channel.** Companies choose what they publish, and the posts reflect marketing habits as much as business scale. Plain reshares are included.
- **Not reported revenue.** The target is still Crustdata's band, so rev-2 learns the band rather than reported revenue.
- **Different source from the Enrich add-on.** The source is Social Post Search, not the Enrich `social_posts` add-on, which is 403 on this key. If the add-on is enabled later, `posts_from_response` accepts its shape.

## Reproduce

```
.venv/bin/python scripts/train_revenue_model_2.py fit              # offline
.venv/bin/python scripts/train_revenue_model_2.py apply --offline  # 9-company table from fixtures
.venv/bin/python -m pytest tests/test_revenue_model_2.py -q
```

The fixtures are `fixtures/<name>/crustdata/social_post_search-*.json` for koah, linear, attio, clay, vercel, retool, ramp, mercury and terrastack. Rev-2 adds only those files; the enrich and identify fixtures belong to the economics work.

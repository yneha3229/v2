"""Revenue model 2 ("rev-2"): revenue model 1's features plus company social-post features.

Kept separate from `revenue_model.py` (rev-1). The rev-1 feature code, target, ridge fit,
CV folds, metrics, band clamp and stale-band rule are IMPORTED from `revenue_model` and
used read-only, so rev-2 = rev-1 features + the social features below, fitted the same way.

Data source. The Company Enrich `social_posts` field group returns 403 permission_error on
the event key (checked 31 Oct 2026 on koahlabs.com). The same company-authored posts come
from Social Post Search (`POST /social_post/search`, enabled, 0.5 credits per post
returned, `limit: 0` count queries free), filtered by `actor.crustdata_entity_id` = the
Crustdata company id and `actor.actor_type` = company, newest first, `limit` 10: the same
"10 most recent posts" window the enrich add-on documents. Unlike the add-on it also returns
plain reshares (`repost_without_thoughts`); they are kept (their engagement is the original
post's). `extract_social_features` accepts posts from either source.

Social features (as of a fixed date; all 0 plus `has_posts` = 0 when there are no posts):
- has_posts            1 if at least one post is returned.
- log_total_posts      log10(1 + total_count), total company posts indexed (free count).
- posts_per_30d        n / max(span, 30 days) x 30, span = newest - oldest post date in the
                       window (capped at 30).
- days_since_last_post as_of - newest post date, in days (capped at 730).
- median_engagement,   per post: total_reactions + total_comments + num_shares
  mean_engagement      (informational; heavy-tailed, so the model uses the logs below).
- log_median_engagement, log_mean_engagement: log10(1 + the value).
- video_share          share of posts with has_video (or "video" in content_types).
- original_share       share of posts whose post_type is "original".
- topic_<name>         share of posts whose text matches the keyword rule (TOPIC_RULES).
"""
from __future__ import annotations

import json
import math
import re
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from proofroom import revenue_model as rm
from proofroom.errors import CrustError
from proofroom.research_models import Signals

MODEL_PATH = rm.DATA_DIR / "revenue_model_2.json"
SOCIAL_TRAINING_PATH = rm.DATA_DIR / "social_posts_training.json"
MODEL_VERSION = "rev-2"
AS_OF = date(2026, 10, 31)           # training pull date (same as rev-1's training set)

POSTS_ENDPOINT = "/social_post/search"
POST_LIMIT = 10
POST_FIELDS = ("share_url", "text", "date_posted", "post_type", "has_video", "hashtags",
               "engagement", "content_types", "actor.name", "actor.crustdata_entity_id",
               "actor.actor_type")
DAYS_CAP = 730.0
CADENCE_CAP = 30.0

TOPIC_RULES: dict[str, re.Pattern] = {
    "topic_customers": re.compile(r"\bcustomers?\b|case stud(?:y|ies)|\bclients?\b|"
                                  r"partnered with|trusted by|\bpowering\b|use cases?", re.I),
    "topic_launches": re.compile(r"\blaunch(?:es|ed|ing)?\b|\bintroducing\b|new features?|"
                                 r"now available|\breleas(?:e|es|ed|ing)\b|\bbeta\b", re.I),
    "topic_hiring": re.compile(r"\bhiring\b|join our team|we['’]re hiring|open roles?", re.I),
    "topic_funding": re.compile(r"\braised\b|\bfunding\b|\bseries [a-h]\b|\bseed\b|"
                                r"\binvestors?\b", re.I),
    "topic_partnerships": re.compile(r"\bpartnerships?\b|\bpartners?\b|\bintegrations?\b",
                                     re.I),
    "topic_events": re.compile(r"\bwebinars?\b|\bconferences?\b|\bsummits?\b", re.I),
}
TOPICS = tuple(TOPIC_RULES)

# Features the regression uses (raw engagement is reported but not modelled).
SOCIAL_FEATURES: tuple[str, ...] = (
    "has_posts", "log_total_posts", "posts_per_30d", "days_since_last_post",
    "log_median_engagement", "log_mean_engagement", "video_share", "original_share") + TOPICS
FEATURES: tuple[str, ...] = tuple(rm.FEATURES) + SOCIAL_FEATURES
INFO_FEATURES = ("n_posts", "median_engagement", "mean_engagement")


# ---- social feature extraction ---------------------------------------------------------

def posts_body(company_id: int, limit: int = POST_LIMIT) -> dict:
    """Fixed request body (stable dev-cache key): the company's own posts, newest first."""
    return {"filters": {"op": "and", "conditions": [
        {"field": "actor.crustdata_entity_id", "type": "=", "value": int(company_id)},
        {"field": "actor.actor_type", "type": "=", "value": "company"}]},
        "sorts": [{"field": "date_posted", "order": "desc"}],
        "fields": list(POST_FIELDS), "limit": int(limit)}


def _post_date(raw: Any) -> date | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None


def _num(v: Any) -> float:
    if isinstance(v, bool) or v is None:
        return 0.0
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return x if math.isfinite(x) else 0.0


def post_engagement(post: dict) -> float:
    """total_reactions + total_comments + num_shares (reactions summed by type when the
    total is missing)."""
    e = post.get("engagement") or {}
    if not isinstance(e, dict):
        return 0.0
    reactions = e.get("total_reactions")
    if reactions is None:
        reactions = sum(_num(v) for v in (e.get("reactions_by_type") or {}).values())
    return _num(reactions) + _num(e.get("total_comments")) + _num(e.get("num_shares"))


def _is_video(post: dict) -> bool:
    types = post.get("content_types") or []
    return bool(post.get("has_video")) or any("video" in str(t).lower() for t in types)


def empty_social_features(total_posts: float | None = None) -> dict[str, float]:
    feats = {k: 0.0 for k in SOCIAL_FEATURES + INFO_FEATURES}
    if total_posts:
        feats["log_total_posts"] = math.log10(1.0 + max(float(total_posts), 0.0))
    return feats


def extract_social_features(posts: list[dict] | None, as_of: date,
                            total_posts: float | None = None) -> dict[str, float]:
    """Social features from up to the 10 most recent company posts (module doc)."""
    seen, clean = set(), []
    for p in posts or []:
        if not isinstance(p, dict):
            continue
        key = p.get("share_url") or (p.get("date_posted"), (p.get("text") or "")[:80])
        if key in seen:
            continue
        seen.add(key)
        clean.append(p)
    if not clean:
        return empty_social_features(total_posts)
    n = len(clean)
    total = max(float(total_posts or 0), float(n))
    dates = [d for d in (_post_date(p.get("date_posted")) for p in clean) if d]
    if dates:
        span = (max(dates) - min(dates)).days
        cadence = min(n / max(span, 30) * 30.0, CADENCE_CAP)
        since = float(min(max((as_of - max(dates)).days, 0), DAYS_CAP))
    else:
        cadence, since = 0.0, DAYS_CAP
    eng = [post_engagement(p) for p in clean]
    med, mean = float(statistics.median(eng)), float(sum(eng) / n)
    feats = {
        "has_posts": 1.0,
        "log_total_posts": math.log10(1.0 + total),
        "posts_per_30d": round(cadence, 6),
        "days_since_last_post": since,
        "log_median_engagement": math.log10(1.0 + med),
        "log_mean_engagement": math.log10(1.0 + mean),
        "video_share": sum(_is_video(p) for p in clean) / n,
        "original_share": sum(str(p.get("post_type") or "") == "original" for p in clean) / n,
        "n_posts": float(n), "median_engagement": med, "mean_engagement": mean,
    }
    for name, pat in TOPIC_RULES.items():
        feats[name] = sum(1 for p in clean if pat.search(str(p.get("text") or ""))) / n
    return feats


def posts_from_response(resp: Any) -> tuple[list[dict], float | None]:
    """(posts, total_count) from a Social Post Search response, or from a Company Enrich
    response / record carrying the `social_posts` group."""
    if isinstance(resp, dict) and "posts" in resp:
        posts = resp.get("posts") or []
        return [p for p in posts if isinstance(p, dict)], _num(resp.get("total_count")) or None
    from proofroom.graph import company_record
    rec = resp if isinstance(resp, dict) and "social_posts" in resp else company_record(resp)
    posts = (rec.get("social_posts") or []) if isinstance(rec, dict) else []
    return [p for p in posts if isinstance(p, dict)], None


def audit_snippets(posts: list[dict], k: int = 3, chars: int = 200) -> list[dict]:
    return [{"date_posted": str(p.get("date_posted") or "")[:10],
             "post_type": str(p.get("post_type") or ""),
             "engagement": post_engagement(p),
             "text": str(p.get("text") or "")[:chars]} for p in posts[:k]]


async def social_features_for(client: Any, company_id: int, as_of: date | None = None
                              ) -> dict:
    """Fetch the company's 10 most recent posts and return
    {"features", "n_posts", "total_count", "snippets", "mode", "credits_used", "error"}.
    A failed call returns zero features with has_posts 0 and the error type."""
    as_of = as_of or date.today()
    out: dict[str, Any] = {"company_id": int(company_id), "as_of": as_of.isoformat(),
                           "source": f"POST {POSTS_ENDPOINT} limit {POST_LIMIT}", "error": ""}
    try:
        resp = await client.request("POST", POSTS_ENDPOINT, posts_body(company_id))
    except CrustError as e:
        out.update(features=empty_social_features(), n_posts=0, total_count=None,
                   snippets=[], error=e.type, mode=getattr(client, "mode", ""),
                   credits_used="0")
        return out
    a = client.attempts[-1] if getattr(client, "attempts", None) else None
    posts, total = posts_from_response(resp)
    out.update(features=extract_social_features(posts, as_of, total), n_posts=len(posts),
               total_count=total, snippets=audit_snippets(posts),
               mode=a.mode if a else "", credits_used=a.credits_used if a else "unknown")
    return out


# ---- fitting and evaluation (rev-1's method, imported) --------------------------------

def design(feats: list[dict[str, float]], names: tuple[str, ...] = FEATURES) -> np.ndarray:
    return np.array([[f[k] for k in names] for f in feats], float)


def cv_predictions(X: np.ndarray, X_eval: np.ndarray, y_mid: np.ndarray, y_lo: np.ndarray,
                   y_hi: np.ndarray, lam: float, method: str) -> np.ndarray:
    """Held-out log10 predictions with rev-1's folds (5, seed 7) and fit."""
    pred = np.zeros_like(y_mid)
    for test in rm._folds(len(y_mid)):
        train = np.setdiff1d(np.arange(len(y_mid)), test)
        params = rm.fit(X[train], y_mid[train], y_lo[train], y_hi[train], lam, method)
        pred[test] = rm._predict(params, X_eval[test])
    return pred


def baseline_predictions(y_mid: np.ndarray, headcount: np.ndarray) -> np.ndarray:
    base = np.zeros_like(y_mid)
    for test in rm._folds(len(y_mid)):
        train = np.setdiff1d(np.arange(len(y_mid)), test)
        rpe = np.median(10 ** y_mid[train] / headcount[train])
        base[test] = np.log10(headcount[test] * rpe)
    return base


def tune(X: np.ndarray, X_eval: np.ndarray, y_mid: np.ndarray, y_lo: np.ndarray,
         y_hi: np.ndarray) -> dict:
    """rev-1's selection rule: method x lambda by held-out median |log10 error|, ties by
    band hit rate."""
    best = None
    for method in ("midpoint", "interval_em"):
        for lam in rm.LAMBDAS:
            pred = cv_predictions(X, X_eval, y_mid, y_lo, y_hi, lam, method)
            m = rm._metrics(pred, y_mid, y_lo, y_hi)
            key = (m["median_abs_log10_error"], -m["band_hit_rate"])
            if best is None or key < best["key"]:
                best = {"key": key, "method": method, "lambda": lam, "metrics": m,
                        "pred": pred}
    best.pop("key")
    return best


def training_matrix(rows: list[dict], social: dict[int, dict], as_of: date = AS_OF
                    ) -> dict:
    """Rows with rev-1 features and social features (training: listed bucket; eval:
    headcount-implied bucket, as rev-1's CV)."""
    usable, f_train, f_eval = [], [], []
    for r in rows:
        s = social.get(int(r["crustdata_company_id"]))
        f = rm.features_from_row(r, as_of)
        if f is None or s is None:
            continue
        fe = rm.features_from_row(r, as_of, listed_bucket=False)
        sf = {k: s["features"][k] for k in SOCIAL_FEATURES}
        usable.append(r)
        f_train.append({**f, **sf})
        f_eval.append({**fe, **sf})
    y_mid, y_lo, y_hi = rm.targets(usable)
    return {"rows": usable, "f_train": f_train, "f_eval": f_eval, "y_mid": y_mid,
            "y_lo": y_lo, "y_hi": y_hi,
            "headcount": np.array([r["headcount"] for r in usable], float)}


def evaluate(mat: dict, feature_sets: dict[str, tuple[str, ...]]) -> dict:
    """Tuned CV metrics per feature set on the same rows and folds, plus the baseline."""
    y_mid, y_lo, y_hi = mat["y_mid"], mat["y_lo"], mat["y_hi"]
    out: dict[str, Any] = {}
    for name, cols in feature_sets.items():
        X = design(mat["f_train"], cols)
        Xe = design(mat["f_eval"], cols)
        out[name] = tune(X, Xe, y_mid, y_lo, y_hi)
    base = baseline_predictions(y_mid, mat["headcount"])
    out["baseline"] = {"method": "headcount x median revenue/employee", "lambda": None,
                       "metrics": rm._metrics(base, y_mid, y_lo, y_hi), "pred": base}
    return out


def paired(pred_a: np.ndarray, pred_b: np.ndarray, y_mid: np.ndarray, tol: float = 1e-9
           ) -> dict:
    """On how many rows b is closer to the band midpoint than a."""
    ea, eb = np.abs(pred_a - y_mid), np.abs(pred_b - y_mid)
    d = ea - eb
    return {"n": int(len(y_mid)), "b_closer": int((d > tol).sum()),
            "a_closer": int((d < -tol).sum()), "ties": int((np.abs(d) <= tol).sum()),
            "mean_abs_err_diff_a_minus_b": round(float(d.mean()), 4),
            "median_abs_err_diff_a_minus_b": round(float(np.median(d)), 4)}


def fit_document(mat: dict, chosen: dict, cv: dict, extra: dict) -> dict:
    X = design(mat["f_train"], FEATURES)
    w, b, mu, sd = rm.fit(X, mat["y_mid"], mat["y_lo"], mat["y_hi"], chosen["lambda"],
                          chosen["method"])
    return {
        "version": MODEL_VERSION, "trained_on": AS_OF.isoformat(), "n_rows": len(mat["rows"]),
        "target": "log10(Crustdata revenue band midpoint) (rev-1 target)",
        "method": chosen["method"], "lambda": chosen["lambda"], "features": list(FEATURES),
        "v1_features": list(rm.FEATURES), "social_features": list(SOCIAL_FEATURES),
        "coef_standardized": [round(float(x), 6) for x in w], "intercept": round(b, 6),
        "feature_means": [round(float(x), 6) for x in mu],
        "feature_stds": [round(float(x), 6) for x in sd],
        "cv": {"folds": rm.CV_FOLDS, "seed": rm.CV_SEED, "model": chosen["metrics"], **cv},
        **extra,
    }


# ---- inference ------------------------------------------------------------------------

class RevenueModel2:
    def __init__(self, doc: dict):
        self.doc = doc
        self.features = list(doc["features"])
        self.w = np.array(doc["coef_standardized"], float)
        self.b = float(doc["intercept"])
        self.mu = np.array(doc["feature_means"], float)
        self.sd = np.array(doc["feature_stds"], float)
        self.sd[self.sd == 0] = 1.0
        self.cv = doc.get("cv", {}).get("model", {})
        self.q50 = float(self.cv.get("median_abs_log10_error", 0.35))
        self.q80 = float(self.cv.get("q80_abs_log10_error", 0.8))

    @classmethod
    def load(cls, path: Path | None = None) -> "RevenueModel2 | None":
        try:
            return cls(json.loads((path or MODEL_PATH).read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError):
            return None

    def predict_log10(self, feats: dict[str, float]) -> float:
        x = np.array([feats[k] for k in self.features], float)
        return float(((x - self.mu) / self.sd) @ self.w + self.b)


def estimate_revenue_v2(signals: Signals, social_features: dict[str, float] | None, *,
                        model: RevenueModel2 | None = None, as_of: date | None = None,
                        largest_country: str = "", listed_bucket: str = "") -> dict:
    """rev-2 ESTIMATE (not reported revenue): raw model -> clamp into the company's
    Crustdata band (rev-1's stale-band rule) -> point; low/high = point x/÷ 10^(CV median
    |log10 error|) (about a 50% interval), intersected with the band."""
    model = model or RevenueModel2.load()
    band = signals.revenue_band_usd
    if band is not None:
        band = (max(float(band[0]), 0.0), float(band[1]))
        band = band if band[1] > 0 else None
    out: dict[str, Any] = {"model_version": MODEL_VERSION, "point_usd": None,
                           "low_usd": None, "high_usd": None, "model_raw_usd": None,
                           "crustdata_band_usd": band, "clamped": False, "features": {},
                           "cv": dict(model.cv) if model else {}, "label": "ESTIMATE",
                           "notes": []}
    v1 = rm.features_from_signals(signals, as_of or AS_OF, largest_country)
    if model is None or v1 is None:
        out["notes"].append("No rev-2 model or no headcount: no model estimate.")
        if band:
            out["point_usd"] = (band[0] + band[1]) / 2
            out["low_usd"], out["high_usd"] = band
            out["notes"].append("Fell back to the Crustdata band midpoint.")
        return out
    social = {k: float((social_features or {}).get(k, 0.0)) for k in SOCIAL_FEATURES}
    if not social_features:
        out["notes"].append("No social features: posts treated as absent (has_posts 0).")
    feats = {**v1, **social}
    out["features"] = {k: round(v, 4) for k, v in feats.items()}
    raw = 10 ** model.predict_log10(feats)
    out["model_raw_usd"] = round(raw, 0)
    clamp_band, stale = rm.effective_band(band, listed_bucket, signals.headcount_total)
    point, clamped = rm.clamp_to_band(raw, clamp_band)
    spread = 10 ** model.q50
    low, high = point / spread, point * spread
    if clamp_band:
        low, high = max(low, clamp_band[0]), min(high, clamp_band[1])
    out.update(point_usd=round(point, 0), low_usd=round(low, 0), high_usd=round(high, 0),
               clamped=clamped)
    if stale:
        out["notes"].append(stale)
    out["notes"].append(f"Range = point x/÷ {spread:.2f} (CV median |log10 error|), "
                        + ("intersected with the band." if clamp_band else "no band."))
    return out

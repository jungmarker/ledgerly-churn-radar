"""Forward churn risk from completed usage weeks. No latent health feature."""

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from reporting import render
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = [
    "adoption_28d",
    "adoption_change",
    "integrations",
    "usage_weeks",
    "tenure_days",
]


def heldout(account):
    return int(hashlib.sha256(account.encode()).hexdigest()[:8], 16) % 5 == 0


def features(usage, subs, asof):
    t = pd.Timestamp(asof)
    u = usage.copy()
    s = subs.copy()
    u["week_start"] = pd.to_datetime(u.week_start)
    s["start_date"] = pd.to_datetime(s.start_date)
    s["end_date"] = pd.to_datetime(s.end_date)
    s = s[(s.start_date <= t) & (s.end_date.isna() | (s.end_date >= t))].copy()
    # A week is available only once all seven days have elapsed.
    u["available_at"] = u.week_start + pd.Timedelta(days=7)
    u = u[u.available_at <= t]
    u["adoption"] = u.weekly_active_users / u.licensed_seats.clip(lower=1)
    recent = (
        u[u.available_at > t - pd.Timedelta(days=28)]
        .groupby("account_id")
        .agg(
            adoption_28d=("adoption", "mean"),
            integrations=("integrations_connected", "max"),
            usage_weeks=("week_start", "count"),
        )
    )
    prev = (
        u[
            (u.available_at <= t - pd.Timedelta(days=28))
            & (u.available_at > t - pd.Timedelta(days=56))
        ]
        .groupby("account_id")
        .adoption.mean()
        .rename("prior_adoption")
    )
    x = (
        s[["account_id", "start_date"]]
        .merge(recent, on="account_id", how="left")
        .merge(prev, on="account_id", how="left")
    )
    x["adoption_change"] = x.adoption_28d - x.prior_adoption
    x["tenure_days"] = (t - x.start_date).dt.days
    x["asof"] = t
    return x


def label(rows, events):
    e = events.copy()
    e["churn_date"] = pd.to_datetime(e.churn_date)
    z = rows.merge(
        e[["account_id", "churn_date"]],
        on="account_id",
        how="left",
        validate="many_to_one",
    )
    z["churn_90d"] = (
        (z.churn_date > z["asof"]) & (z.churn_date <= z["asof"] + pd.Timedelta(days=90))
    ).astype(int)
    return z


def evaluate(frame, k=20):
    y = frame.churn_90d
    p = frame.risk
    top = frame.nlargest(min(k, len(frame)), "risk")
    positives = int(y.sum())
    return {
        "accounts": len(frame),
        "churns": positives,
        "prevalence": float(y.mean()),
        "average_precision": average_precision_score(y, p),
        "auc": roc_auc_score(y, p) if y.nunique() > 1 else None,
        "brier": brier_score_loss(y, p),
        "precision_at_20": float(top.churn_90d.mean()),
        "recall_at_20": float(top.churn_90d.sum() / positives) if positives else 0.0,
    }


def main(data, out):
    u = pd.read_csv(data / "raw/product_usage_weekly.csv")
    s = pd.read_csv(data / "raw/subscriptions.csv")
    events = pd.read_csv(data / "truth/churn_events.csv")
    dates = pd.date_range("2023-06-30", "2025-09-30", freq="QE")
    # Truth provides forward labels only; feature construction has no access to it.
    train = pd.concat(
        [label(features(u, s, d), events) for d in dates], ignore_index=True
    )
    train = train[~train.account_id.map(heldout)]
    model = make_pipeline(
        SimpleImputer(add_indicator=True),
        StandardScaler(),
        LogisticRegression(max_iter=2000, C=0.5),
    ).fit(train[FEATURES], train.churn_90d)
    tests = []
    scores = []
    for date in ["2026-03-31", "2026-06-30"]:
        test = label(features(u, s, date), events)
        test = test[test.account_id.map(heldout)].copy()
        assert not set(test.account_id) & set(train.account_id)
        test["risk"] = model.predict_proba(test[FEATURES])[:, 1]
        metrics = evaluate(test)
        metrics["asof"] = date
        metrics["constant_baseline_brier"] = brier_score_loss(
            test.churn_90d, np.full(len(test), train.churn_90d.mean())
        )
        scores.append(metrics)
        tests.append(test)
    current = features(u, s, "2026-09-30")
    current["risk"] = model.predict_proba(current[FEATURES])[:, 1]
    current["review_reason"] = np.where(
        current.adoption_28d.isna(),
        "Insufficient usage history",
        np.where(
            current.adoption_change < -0.1,
            "Adoption declined",
            "Review adoption and integrations",
        ),
    )
    queue = current.nlargest(20, "risk")[
        ["account_id", "risk"] + FEATURES + ["review_reason"]
    ]
    scoreframe = pd.DataFrame(scores)
    summary = {
        "training_rows": len(train),
        "heldout_account_periods": sum(x["accounts"] for x in scores),
        "mean_average_precision": round(scoreframe.average_precision.mean(), 4),
        "mean_prevalence": round(scoreframe.prevalence.mean(), 4),
        "mean_precision_at_20": round(scoreframe.precision_at_20.mean(), 4),
        "outreach_capacity": 20,
    }
    render(
        out,
        "Customer churn radar",
        summary,
        {
            "evaluation": scoreframe,
            "outreach_queue": queue,
            "heldout_predictions": pd.concat(tests)[
                ["account_id", "asof", "churn_90d", "risk"] + FEATURES
            ],
        },
        "Churn within 90 days, evaluated on future periods AND accounts excluded from training. Usage requires a completed week. Latest September predictions are unscored because 90-day outcomes are censored. The outreach queue allocates review capacity; it does not estimate causal intervention benefit. No real customer data is used.",
        (
            scoreframe["asof"].tolist(),
            scoreframe.precision_at_20.tolist(),
            "Precision among top 20 risk accounts",
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("data"))
    p.add_argument("--out", type=Path, default=Path("reports"))
    a = p.parse_args()
    main(a.data, a.out)

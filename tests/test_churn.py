import pandas as pd
from run import FEATURES, features, label


def test_incomplete_weeks_and_future_usage_cannot_affect_features():
    s = pd.DataFrame(
        [("a", "2023-01-01", None)], columns=["account_id", "start_date", "end_date"]
    )
    u = pd.DataFrame(
        [
            ("a", "2024-01-01", 10, 5, 1),
            ("a", "2024-01-29", 10, 10, 9),
            ("a", "2024-02-05", 10, 10, 9),
        ],
        columns=[
            "account_id",
            "week_start",
            "licensed_seats",
            "weekly_active_users",
            "integrations_connected",
        ],
    )
    x = features(u, s, "2024-01-31")
    assert x.adoption_28d.iloc[0] == 0.5 and x.integrations.iloc[0] == 1
    pd.testing.assert_frame_equal(x, features(u.iloc[:1], s, "2024-01-31"))
    e = pd.DataFrame([("a", "2024-02-15")], columns=["account_id", "churn_date"])
    assert label(x, e).churn_90d.iloc[0] == 1
    assert not {"health", "end_date", "status", "churn_date", "cancel_reason"} & set(
        FEATURES
    )


def test_cancelled_accounts_and_censored_labels_are_not_features():
    s = pd.DataFrame(
        [("a", "2023-01-01", "2024-01-15"), ("b", "2024-02-01", None)],
        columns=["account_id", "start_date", "end_date"],
    )
    u = pd.DataFrame(
        columns=[
            "account_id",
            "week_start",
            "licensed_seats",
            "weekly_active_users",
            "integrations_connected",
        ]
    )
    assert features(u, s, "2024-01-31").empty


def test_ranking_metrics_reflect_fixed_contact_capacity():
    from run import evaluate

    frame = pd.DataFrame({"churn_90d": [1, 0, 1, 0], "risk": [0.9, 0.8, 0.2, 0.1]})
    metrics = evaluate(frame, k=2)
    assert metrics["precision_at_20"] == 0.5 and metrics["recall_at_20"] == 0.5

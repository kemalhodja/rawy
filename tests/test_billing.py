from datetime import datetime, timedelta, timezone

from app.services.billing import effective_plan, plans_catalog


def test_effective_plan_trial():
    class U:
        plan = "starter"
        trial_ends_at = datetime.now(timezone.utc) + timedelta(days=3)

    assert effective_plan(U()) == "pro"


def test_effective_plan_starter_expired():
    class U:
        plan = "starter"
        trial_ends_at = datetime.now(timezone.utc) - timedelta(days=1)

    assert effective_plan(U()) == "starter"


def test_plans_catalog():
    c = plans_catalog()
    assert c["trial_days"] == 14
    assert len(c["plans"]) == 3
    ids = {p["id"] for p in c["plans"]}
    assert ids == {"starter", "pro", "team"}

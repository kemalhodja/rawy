"""
Todoist-benzeri sade akış: Bugün (max 3) + Yakında, derin/yüzeysel, akıllı yoklama.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Task, User

VALID_DEPTH = frozenset({"deep", "shallow"})
TODAY_MAX = 3
SOON_DAYS = 7
SOON_MAX = 15
NUDGE_COOLDOWN_HOURS = 4


def _bounds_today(user_tz: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(user_tz or "UTC")
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _active_filter(q, now_aware: datetime):
    return q.filter(
        (Task.snooze_until.is_(None)) | (Task.snooze_until <= now_aware),
    )


def flow_buckets(db: Session, user: User) -> dict:
    """Bugün (en fazla 3) + Yakında (önümüzdeki günler, limitli)."""
    tz = user.timezone or "UTC"
    start, end = _bounds_today(tz)
    now = datetime.now(ZoneInfo(tz))

    base = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.done.is_(False))
        .order_by(Task.created_at.asc())
    )
    base = _active_filter(base, now)
    incomplete = base.all()

    def depth_rank(t: Task) -> int:
        d = getattr(t, "depth", None) or "shallow"
        return 0 if d == "deep" else 1

    def sort_today_key(t: Task) -> tuple:
        due = t.due_at
        if due is not None:
            due_l = due.astimezone(ZoneInfo(tz)) if due.tzinfo else due.replace(tzinfo=ZoneInfo(tz))
        else:
            due_l = None

        if due_l is not None and due_l < start:
            tier = 0  # gecikmiş
        elif due_l is not None and start <= due_l < end:
            tier = 1  # bugün
        elif due_l is None:
            tier = 2  # tarihsiz
        else:
            tier = 9  # ileri tarih — Bugün listesine girmez

        return (tier, depth_rank(t), due_l or datetime.max.replace(tzinfo=ZoneInfo(tz)), t.id)

    today_pool = [t for t in incomplete if sort_today_key(t)[0] < 9]
    today_pool.sort(key=sort_today_key)
    today = today_pool[:TODAY_MAX]
    today_ids = {t.id for t in today}

    soon_start = end
    soon_end = soon_start + timedelta(days=SOON_DAYS)
    soon_list: list[Task] = []
    for t in incomplete:
        if t.id in today_ids:
            continue
        due = t.due_at
        if due is None:
            continue
        due_l = due.astimezone(ZoneInfo(tz)) if due.tzinfo else due.replace(tzinfo=ZoneInfo(tz))
        if soon_start <= due_l < soon_end:
            soon_list.append(t)

    soon_list.sort(
        key=lambda x: (
            x.due_at or datetime.min.replace(tzinfo=ZoneInfo("UTC")),
            depth_rank(x),
            x.id,
        )
    )
    soon: list[Task] = []
    for t in soon_list:
        if len(soon) >= SOON_MAX:
            break
        soon.append(t)

    # Tarihsiz kalanlar (Bugün'e sığmayanlar) → Yakında
    for t in incomplete:
        if t.id in today_ids:
            continue
        if t.due_at is not None:
            continue
        if len(soon) >= SOON_MAX:
            break
        soon.append(t)

    return {
        "today": today,
        "soon": soon,
        "meta": {
            "today_max": TODAY_MAX,
            "soon_days": SOON_DAYS,
            "soon_max": SOON_MAX,
            "depths": {"deep": "Derin", "shallow": "Yüzeysel"},
        },
    }


def nudge_cooldown_active(user: User) -> bool:
    if not getattr(user, "last_task_nudge_at", None):
        return False
    last = user.last_task_nudge_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last < timedelta(hours=NUDGE_COOLDOWN_HOURS)


def nudge_cooldown_until(user: User) -> datetime | None:
    if not getattr(user, "last_task_nudge_at", None):
        return None
    last = user.last_task_nudge_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return last + timedelta(hours=NUDGE_COOLDOWN_HOURS)


def select_nudge_candidate(db: Session, user: User) -> Task | None:
    """Tek yoklama adayı: gecikmiş / bugün / derin önce (cooldown kontrolü yok)."""
    tz = user.timezone or "UTC"
    start, end = _bounds_today(tz)
    now = datetime.now(ZoneInfo(tz))

    q = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.done.is_(False))
    )
    q = _active_filter(q, now)
    candidates = q.all()
    if not candidates:
        return None

    def score(t: Task) -> tuple:
        due = t.due_at
        if due is not None:
            due_l = due.astimezone(ZoneInfo(tz)) if due.tzinfo else due.replace(tzinfo=ZoneInfo(tz))
        else:
            due_l = None
        if due_l is not None and due_l < start:
            tier = 0
        elif due_l is not None and start <= due_l < end:
            tier = 1
        elif due_l is None:
            tier = 3
        else:
            tier = 5
        deep = 0 if (getattr(t, "depth", None) or "shallow") == "deep" else 1
        return (tier, deep, t.id)

    candidates.sort(key=score)
    return candidates[0]


def pick_nudge_task(db: Session, user: User) -> Task | None:
    """Eski API uyumu: cooldown aktifse None."""
    if nudge_cooldown_active(user):
        return None
    return select_nudge_candidate(db, user)

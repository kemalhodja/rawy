from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Task, User
from app.services.task_flow import (
    flow_buckets,
    nudge_cooldown_active,
    nudge_cooldown_until,
    select_nudge_candidate,
)

router = APIRouter()


class TaskOut(BaseModel):
    id: int
    title: str
    done: bool
    due_at: str | None
    depth: str
    snooze_until: str | None
    source_voice_note_id: int | None

    model_config = {"from_attributes": True}


def _task_out(t: Task) -> TaskOut:
    return TaskOut(
        id=t.id,
        title=t.title,
        done=bool(t.done),
        due_at=t.due_at.isoformat() if t.due_at else None,
        depth=getattr(t, "depth", None) or "shallow",
        snooze_until=t.snooze_until.isoformat()
        if getattr(t, "snooze_until", None)
        else None,
        source_voice_note_id=t.source_voice_note_id,
    )


class TaskPatch(BaseModel):
    done: bool | None = None
    depth: str | None = None
    snooze_hours: int | None = Field(None, ge=1, le=168)

    @field_validator("depth")
    @classmethod
    def depth_ok(cls, v: str | None) -> str | None:
        if v is not None and v not in ("deep", "shallow"):
            raise ValueError("depth: deep veya shallow olmalı")
        return v


@router.get("/flow")
def tasks_flow(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sade görünüm: Bugün (en fazla 3) + Yakında.
    Derin / yüzeysel: `depth` alanı.
    """
    buckets = flow_buckets(db, current_user)
    return {
        "today": [_task_out(t) for t in buckets["today"]],
        "soon": [_task_out(t) for t in buckets["soon"]],
        "view": {
            "style": "todoist_simple",
            "today_max": buckets["meta"]["today_max"],
            "soon_window_days": buckets["meta"]["soon_days"],
            "depth_labels": buckets["meta"]["depths"],
            "voice_action_items": "Toplantı transkriptindeki aksiyonlar doğrudan görev olarak oluşturulur",
        },
    }


@router.get("/nudge")
def task_nudge(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Akıllı yoklama: en fazla 4 saatte bir aday gösterir (hatırlatma bombardımanı yok).
    """
    if nudge_cooldown_active(current_user):
        cu = nudge_cooldown_until(current_user)
        return {
            "nudge": None,
            "cooldown_active": True,
            "cooldown_until": cu.isoformat() if cu else None,
        }

    u = db.query(User).filter(User.id == current_user.id).first()
    if u and getattr(u, "active_focus_block_id", None):
        return {
            "nudge": None,
            "cooldown_active": False,
            "cooldown_until": None,
            "suppressed_reason": "active_focus",
        }

    task = select_nudge_candidate(db, current_user)
    if not task:
        return {"nudge": None, "cooldown_active": False, "cooldown_until": None}

    current_user.last_task_nudge_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "nudge": _task_out(task),
        "cooldown_active": False,
        "cooldown_until": None,
    }


@router.get("/", response_model=list[TaskOut])
def list_tasks(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Task)
        .filter(Task.user_id == current_user.id)
        .order_by(Task.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_task_out(t) for t in rows]


@router.patch("/{task_id}", response_model=TaskOut)
def patch_task(
    task_id: int,
    body: TaskPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.user_id == current_user.id)
        .first()
    )
    if not task:
        raise HTTPException(404, "Görev bulunamadı")

    if body.done is not None:
        task.done = body.done
        if body.done:
            task.snooze_until = None
    if body.depth is not None:
        task.depth = body.depth
    if body.snooze_hours is not None:
        task.snooze_until = datetime.now(timezone.utc) + timedelta(hours=body.snooze_hours)

    if body.done is None and body.depth is None and body.snooze_hours is None:
        raise HTTPException(400, "En az bir alan gönderin: done, depth, snooze_hours")

    db.commit()
    db.refresh(task)
    return _task_out(task)

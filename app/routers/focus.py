"""Aktif odak: bildirim politikası (istemci), şu anki blok, odak ses türleri."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import FocusBlock, FocusSession, User
from app.schemas import FocusBlockOut
from app.services.focus_mode import (
    enter_focus_session,
    exit_focus_session,
    focus_session_phase,
    get_current_block,
    now_in_tz,
    user_in_declared_focus,
)

router = APIRouter()


def _to_out(b: FocusBlock) -> FocusBlockOut:
    return FocusBlockOut(
        id=b.id,
        title=b.title,
        start_at=b.start_at,
        end_at=b.end_at,
        is_focus=b.is_focus,
        source=b.source,
    )


class FocusEnterBody(BaseModel):
    block_id: int = Field(..., ge=1)


class FocusCompanionStartBody(BaseModel):
    mode: str = Field(default="solo")
    partner_user_id: int | None = Field(default=None, ge=1)


@router.get("/context")
def focus_context(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    İstemci: bildirimleri kapat (Freedom tarzı), ajanda yalnız şu anki blok,
    odak ses kayıtları için `recording_type` değerleri.
    """
    u = db.query(User).filter(User.id == current_user.id).first()
    if not u:
        raise HTTPException(401)

    current = get_current_block(db, u)
    declared = user_in_declared_focus(db, u)
    phase = focus_session_phase(db, u)

    notif_active = bool(getattr(u, "active_focus_block_id", None))

    return {
        "notifications": {
            "policy": "all_off_while_focus_session",
            "silence_active": notif_active,
            "freedom_style": True,
            "hint_tr": "Aktif odak oturumundayken tüm bildirimler kapalı (istemci uygular).",
        },
        "calendar": {
            "view": "current_block_only",
            "current_block": _to_out(current) if current else None,
        },
        "voice": {
            "idea_capture": {
                "recording_type": "focus_idea",
                "works_in_deep_focus": True,
                "hint_tr": "Anlık fikir kaydı; derin odak modunda bile kullanılabilir.",
            },
            "session_end_log": {
                "recording_type": "focus_debrief",
                "prompt_tr": "Nasıl geçti? Kısa bir ses kaydı yapın.",
                "suggest_when": "Blok bitişinden sonra veya odak oturumunu kapattığınızda",
            },
        },
        "session": {
            "phase": phase,
            "declared_focus_block_id": getattr(u, "active_focus_block_id", None),
            "suggest_focus_debrief": phase == "after",
        },
    }


@router.post("/enter")
def focus_enter(
    body: FocusEnterBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Odak oturumu başlat (süresi dolmamış blok)."""
    blk = (
        db.query(FocusBlock)
        .filter(FocusBlock.id == body.block_id, FocusBlock.user_id == current_user.id)
        .first()
    )
    if not blk:
        raise HTTPException(404, "Blok bulunamadı")
    now = now_in_tz(current_user)
    if now >= blk.end_at:
        raise HTTPException(400, "Blok süresi dolmuş; yeni bir blok seçin")

    enter_focus_session(db, current_user, body.block_id)
    db.refresh(current_user)
    return {"ok": True, "active_focus_block_id": current_user.active_focus_block_id}


@router.post("/exit")
def focus_exit(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Odak oturumunu bitir; istemci ardından focus_debrief kaydı tetikleyebilir."""
    exit_focus_session(db, current_user)
    return {"ok": True, "hint_tr": "İsterseniz recording_type=focus_debrief ile kısa bir 'nasıl geçti?' kaydı alın."}


@router.get("/session-phase")
def focus_phase(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """during | after | none — bitiş yansıtması zamanlaması için."""
    return {"phase": focus_session_phase(db, current_user)}


@router.post("/companion/start")
def start_focus_companion(
    body: FocusCompanionStartBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mode = (body.mode or "solo").strip().lower()
    if mode not in {"solo", "random"}:
        raise HTTPException(400, "mode: solo|random olmalı")

    partner_id = body.partner_user_id
    if mode == "random" and partner_id is None:
        partner = (
            db.query(User)
            .filter(User.id != current_user.id, User.is_active.is_(True))
            .order_by(func.random())
            .first()
        )
        partner_id = partner.id if partner else None

    session = FocusSession(
        host_user_id=current_user.id,
        partner_user_id=partner_id,
        mode=mode,
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "id": session.id,
        "mode": session.mode,
        "status": session.status,
        "partner_user_id": session.partner_user_id,
        "started_at": session.started_at,
    }


@router.post("/companion/{session_id}/checkin")
def focus_companion_checkin(
    session_id: int,
    note: str | None = None,
    complete: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = (
        db.query(FocusSession)
        .filter(FocusSession.id == session_id, FocusSession.host_user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(404, "Session bulunamadı")
    if note and note.strip():
        session.checkin_note = note.strip()[:1000]
    if complete:
        session.status = "completed"
        session.ended_at = now_in_tz(current_user)
    db.commit()
    db.refresh(session)
    return {
        "id": session.id,
        "status": session.status,
        "mode": session.mode,
        "checkin_note": session.checkin_note,
        "ended_at": session.ended_at,
    }

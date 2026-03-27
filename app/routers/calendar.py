from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import CalendarEvent, FocusBlock, User, VoiceNote
from app.schemas import (
    AvailabilityMapOut,
    FocusBlockCreate,
    FocusBlockOut,
    UserAvailabilitySlice,
    VoicePlanBody,
    VoicePlanResult,
)
from app.services.calendar_logic import (
    apply_buffer_before_start,
    focus_duration_hours,
    parse_event_from_voice,
    validate_focus_duration,
)
from app.services.focus_mode import get_current_block
from app.services.google_calendar_service import google_calendar_service
from app.services.voice_planning import parse_voice_planning

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


@router.post("/from-voice/{note_id}")
def create_event_from_voice(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == note_id, VoiceNote.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(404, "Not bulunamadı")
    if not note.transcript:
        raise HTTPException(422, "Notta transkript yok")

    tz = current_user.timezone or "UTC"
    try:
        start, end, title, is_focus = parse_event_from_voice(note.transcript, tz)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    event = CalendarEvent(
        user_id=current_user.id,
        title=title,
        start_time=start,
        end_time=end,
        source_note_id=note.id,
        is_focus_block=is_focus,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    sync_result = google_calendar_service.push_event(
        title=event.title,
        start_time=event.start_time,
        end_time=event.end_time,
        user_id=current_user.id,
    )
    if sync_result.get("synced"):
        event.external_event_id = sync_result.get("external_event_id")
        db.commit()
        db.refresh(event)

    return {
        "id": event.id,
        "title": event.title,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "source_note_id": event.source_note_id,
        "is_focus_block": event.is_focus_block,
        "google_sync": sync_result,
    }


@router.get("/")
def weekly_calendar_view(
    week_start: date | None = Query(None, description="Hafta başlangıcı YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tz_name = current_user.timezone or "UTC"
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()
    ws = week_start or (today - timedelta(days=today.weekday()))
    start = datetime.combine(ws, time.min, tzinfo=tz)
    end = start + timedelta(days=7)

    events = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == current_user.id,
            CalendarEvent.start_time < end,
            CalendarEvent.end_time > start,
        )
        .order_by(CalendarEvent.start_time.asc())
        .all()
    )

    blocks = (
        db.query(FocusBlock)
        .filter(
            FocusBlock.user_id == current_user.id,
            FocusBlock.start_at < end,
            FocusBlock.end_at > start,
        )
        .order_by(FocusBlock.start_at.asc())
        .all()
    )

    return {
        "week_start": ws.isoformat(),
        "week_end": (ws + timedelta(days=6)).isoformat(),
        "events": [
            {
                "id": e.id,
                "title": e.title,
                "start_time": e.start_time,
                "end_time": e.end_time,
                "source_note_id": e.source_note_id,
                "is_focus_block": e.is_focus_block,
                "external_event_id": e.external_event_id,
            }
            for e in events
        ],
        "focus_blocks": [
            {
                "id": b.id,
                "title": b.title,
                "start_at": b.start_at,
                "end_at": b.end_at,
                "source": b.source,
            }
            for b in blocks
        ],
    }


@router.post("/blocks", response_model=FocusBlockOut)
def create_block(
    data: FocusBlockCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    start = data.start_at
    end = data.end_at
    if end <= start:
        raise HTTPException(400, "Bitiş başlangıçtan sonra olmalı")

    buf_start, buf_end, adjusted = apply_buffer_before_start(
        db, current_user.id, start, end
    )
    hours = focus_duration_hours(buf_start, buf_end)
    if data.is_focus:
        try:
            validate_focus_duration(hours)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    overlap = (
        db.query(FocusBlock)
        .filter(
            FocusBlock.user_id == current_user.id,
            FocusBlock.start_at < buf_end,
            FocusBlock.end_at > buf_start,
        )
        .first()
    )
    if overlap:
        raise HTTPException(
            409,
            f"Bu aralıkta zaten bir blok var (id={overlap.id})",
        )

    source = "anti_busywork" if adjusted else (data.source or "manual")

    block = FocusBlock(
        user_id=current_user.id,
        title=data.title,
        start_at=buf_start,
        end_at=buf_end,
        is_focus=data.is_focus,
        source=source,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return _to_out(block)


@router.post("/plan-from-voice", response_model=VoicePlanResult)
def plan_from_voice(
    body: VoicePlanBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tz = current_user.timezone or "UTC"
    try:
        ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        raise HTTPException(400, f"Geçersiz saat dilimi: {tz}") from None

    try:
        start, end, title = parse_voice_planning(body.text, tz)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    buf_start, buf_end, adjusted = apply_buffer_before_start(
        db, current_user.id, start, end
    )
    hours = focus_duration_hours(buf_start, buf_end)
    is_focus = True
    if body.allow_shallow and (
        hours < settings.FOCUS_BLOCK_MIN_HOURS or hours > settings.FOCUS_BLOCK_MAX_HOURS
    ):
        is_focus = False
    elif not body.allow_shallow:
        try:
            validate_focus_duration(hours)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    overlap = (
        db.query(FocusBlock)
        .filter(
            FocusBlock.user_id == current_user.id,
            FocusBlock.start_at < buf_end,
            FocusBlock.end_at > buf_start,
        )
        .first()
    )
    if overlap:
        raise HTTPException(
            409,
            f"Bu aralıkta zaten bir blok var (id={overlap.id})",
        )

    source = "voice+anti_busywork" if adjusted else "voice"

    block = FocusBlock(
        user_id=current_user.id,
        title=title[:500],
        start_at=buf_start,
        end_at=buf_end,
        is_focus=is_focus,
        source=source,
    )
    db.add(block)
    db.commit()
    db.refresh(block)

    return VoicePlanResult(
        block=_to_out(block),
        parsed_title=title,
        adjusted_for_buffer=adjusted,
        duration_hours=round(focus_duration_hours(buf_start, buf_end), 2),
    )


@router.get("/blocks/current", response_model=FocusBlockOut | None)
def get_current_block_only(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aktif odak ajandası: yalnızca şu anki blok (yoksa null)."""
    b = get_current_block(db, current_user)
    return _to_out(b) if b else None


@router.get("/blocks", response_model=list[FocusBlockOut])
def list_blocks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    time_from: datetime = Query(..., alias="from"),
    time_to: datetime = Query(..., alias="to"),
):
    if time_to <= time_from:
        raise HTTPException(400, "'to' 'from'dan sonra olmalı")
    rows = (
        db.query(FocusBlock)
        .filter(
            FocusBlock.user_id == current_user.id,
            FocusBlock.start_at < time_to,
            FocusBlock.end_at > time_from,
        )
        .order_by(FocusBlock.start_at.asc())
        .all()
    )
    return [_to_out(r) for r in rows]


@router.get("/availability-map", response_model=AvailabilityMapOut)
def availability_map(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    day: date = Query(..., description="Takvim günü (kullanıcı saat diliminde), YYYY-MM-DD"),
):
    """
    MVP: yalnızca oturum açmış kullanıcı + blokları.
    Takım genişlemesi için `user_ids` ileride eklenecek.
    """
    tz_name = current_user.timezone or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")

    day_start = datetime.combine(day, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    blocks = (
        db.query(FocusBlock)
        .filter(
            FocusBlock.user_id == current_user.id,
            FocusBlock.start_at < day_end,
            FocusBlock.end_at > day_start,
        )
        .order_by(FocusBlock.start_at.asc())
        .all()
    )

    return AvailabilityMapOut(
        date=day_start.date().isoformat(),
        default_timezone=tz_name,
        team=[
            UserAvailabilitySlice(
                user_id=current_user.id,
                email=current_user.email,
                timezone=tz_name,
                blocks=[_to_out(b) for b in blocks],
            )
        ],
        note="Takım uygunluk haritası — şimdilik tek kullanıcı; çoklu hesap sonra.",
    )

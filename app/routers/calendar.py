from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import FocusBlock, User
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
    validate_focus_duration,
)
from app.services.focus_mode import get_current_block
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

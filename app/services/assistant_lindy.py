"""
Lindy tarzı ama sade asistan: LLM yok; transkript + ajanda + görevlerden türetim.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import FocusBlock, Task, User, VoiceNote


def _utc_bounds_from_local_start_end(
    start_local: datetime, end_local: datetime
) -> tuple[datetime, datetime]:
    """DB ile karşılaştırma için UTC sınırları."""
    su = start_local.astimezone(timezone.utc)
    eu = end_local.astimezone(timezone.utc)
    return su, eu


def iso_week_range_local(user: User) -> tuple[datetime, datetime, int, int]:
    """Bu ISO haftası [start, end) kullanıcı TZ'de; yıl, hafta no."""
    tz = ZoneInfo(user.timezone or "UTC")
    now = datetime.now(tz)
    y, w, _ = now.isocalendar()
    d0 = date.fromisocalendar(y, w, 1)
    start = datetime.combine(d0, time.min, tzinfo=tz)
    end = start + timedelta(days=7)
    return start, end, y, w


def weekly_what_did_i_do(db: Session, user: User) -> dict[str, Any]:
    """Bu hafta ne yaptım? — özet + alıntılar."""
    start, end, y, w = iso_week_range_local(user)
    su, eu = _utc_bounds_from_local_start_end(start, end)

    notes = (
        db.query(VoiceNote)
        .filter(
            VoiceNote.user_id == user.id,
            VoiceNote.created_at >= su,
            VoiceNote.created_at < eu,
            VoiceNote.is_processed.is_(True),
        )
        .order_by(VoiceNote.created_at.asc())
        .all()
    )

    by_type: dict[str, int] = {}
    for n in notes:
        rt = n.recording_type or "quick_note"
        by_type[rt] = by_type.get(rt, 0) + 1

    parts: list[str] = []
    if not notes:
        parts.append("Bu hafta henüz işlenmiş ses notu yok.")
    else:
        parts.append(
            f"Bu hafta (ISO {y}-W{w:02d}) {len(notes)} ses notu kaydettiğin görünüyor."
        )
        if by_type:
            breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(by_type.items()))
            parts.append(f"Tür dağılımı: {breakdown}.")

    quotes: list[dict[str, Any]] = []
    for n in notes[:8]:
        tr = (n.transcript or "").strip()
        if not tr:
            continue
        excerpt = tr.replace("\n", " ")
        if len(excerpt) > 220:
            excerpt = excerpt[:217] + "..."
        quotes.append(
            {
                "note_id": n.id,
                "title": n.title or f"Not #{n.id}",
                "excerpt": excerpt,
                "recording_type": n.recording_type or "quick_note",
            }
        )

    summary_tr = " ".join(parts)

    return {
        "intent": "weekly_summary",
        "iso_year": y,
        "iso_week": w,
        "note_count": len(notes),
        "by_recording_type": by_type,
        "summary_tr": summary_tr,
        "quotes": quotes[:6],
    }


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_ideas_transcripts(
    db: Session, user: User, query: str, limit: int = 20
) -> dict[str, Any]:
    """Transkript ve başlıkta bağlantılı arama (ILIKE)."""
    q = (query or "").strip()
    if len(q) < 2:
        return {"intent": "search", "matches": [], "hint_tr": "En az 2 karakter girin."}

    if any(c in q for c in ("%", "_", "\\")):
        safe = _escape_like(q)
        pattern = f"%{safe}%"
        like_kw = {"escape": "\\"}
    else:
        pattern = f"%{q}%"
        like_kw = {}

    rows = (
        db.query(VoiceNote)
        .filter(
            VoiceNote.user_id == user.id,
            VoiceNote.transcript.isnot(None),
            or_(
                VoiceNote.transcript.ilike(pattern, **like_kw),
                VoiceNote.title.ilike(pattern, **like_kw),
            ),
        )
        .order_by(VoiceNote.created_at.desc())
        .limit(limit)
        .all()
    )

    matches: list[dict[str, Any]] = []
    low = q.lower()
    for n in rows:
        tr = n.transcript or ""
        snippet = tr.replace("\n", " ")
        idx = snippet.lower().find(low)
        if idx == -1:
            idx = 0
        start = max(0, idx - 60)
        end = min(len(snippet), idx + len(q) + 80)
        cut = ("…" if start > 0 else "") + snippet[start:end] + ("…" if end < len(snippet) else "")
        rel = list(n.related_note_ids) if n.related_note_ids else []
        matches.append(
            {
                "note_id": n.id,
                "title": n.title or f"Not #{n.id}",
                "snippet_tr": cut,
                "related_note_ids": rel[:12],
                "wikilink_style": "[[başlık]] ile çapraz bağ kurmak için transkriptte köprü kullan",
            }
        )

    return {
        "intent": "search",
        "query": q,
        "match_count": len(matches),
        "matches": matches,
        "summary_tr": f"'{q}' için {len(matches)} not bulundu.",
    }


def suggest_tomorrow_plan(db: Session, user: User) -> dict[str, Any]:
    """Yarın için basit ajanda + görev önerisi (kural tabanlı)."""
    tz = ZoneInfo(user.timezone or "UTC")
    now = datetime.now(tz)
    tomorrow = (now.date() + timedelta(days=1))
    day_start = datetime.combine(tomorrow, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    su, eu = _utc_bounds_from_local_start_end(day_start, day_end)

    blocks = (
        db.query(FocusBlock)
        .filter(
            FocusBlock.user_id == user.id,
            FocusBlock.start_at < eu,
            FocusBlock.end_at > su,
        )
        .order_by(FocusBlock.start_at.asc())
        .all()
    )

    tasks_tomorrow = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.done.is_(False),
            Task.due_at.isnot(None),
            Task.due_at >= su,
            Task.due_at < eu,
        )
        .order_by(Task.due_at.asc())
        .all()
    )

    deep_pending = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.done.is_(False),
            Task.depth == "deep",
        )
        .order_by(Task.created_at.asc())
        .limit(5)
        .all()
    )

    suggestions: list[dict[str, Any]] = []

    if not blocks:
        suggestions.append(
            {
                "kind": "focus_block",
                "title": "Önerilen derin odak",
                "start_local": day_start.replace(hour=9, minute=0).isoformat(),
                "end_local": day_start.replace(hour=12, minute=0).isoformat(),
                "reason_tr": "Yarın takvimde blok yok; sabah 3 saatlik derin çalışma önerilir.",
            }
        )
    else:
        suggestions.append(
            {
                "kind": "calendar_note",
                "reason_tr": f"Yarın {len(blocks)} takvim bloğu zaten var; yeni blok eklemeden mevcut aralıklara uy.",
                "existing_blocks": [
                    {
                        "id": b.id,
                        "title": b.title,
                        "start_at": b.start_at.isoformat() if b.start_at else None,
                        "end_at": b.end_at.isoformat() if b.end_at else None,
                    }
                    for b in blocks[:6]
                ],
            }
        )

    if deep_pending and not tasks_tomorrow:
        suggestions.append(
            {
                "kind": "task_hint",
                "reason_tr": "Derin işaretli görevler var; yarın odak bloğuna bu başlıklardan birini bağlamayı düşün.",
                "task_titles": [t.title[:120] for t in deep_pending[:3]],
            }
        )

    hint = (
        f"Yarın ({tomorrow.isoformat()}) için {len(blocks)} blok, "
        f"{len(tasks_tomorrow)} görev (son tarih yarın)."
    )

    return {
        "intent": "tomorrow_plan",
        "date": tomorrow.isoformat(),
        "timezone": user.timezone or "UTC",
        "tasks_due_tomorrow": [
            {"id": t.id, "title": t.title, "due_at": t.due_at.isoformat() if t.due_at else None}
            for t in tasks_tomorrow
        ],
        "suggestions": suggestions,
        "summary_tr": hint,
    }


def interpret_user_message(text: str) -> dict[str, Any]:
    """
    Serbest metni sınırlı kalıplarla yönlendirir (LLM yok).
    """
    raw = (text or "").strip()
    low = raw.lower()
    if not low:
        return {"intent": "unknown", "query": None}

    if re.search(
        r"bu hafta|ne yaptım|haftalık|hafta özet|this week|weekly summary",
        low,
        re.I,
    ):
        return {"intent": "weekly_summary", "query": None}

    if re.search(
        r"yarın.*plan|plan öner|yarın için|yarınki|tomorrow.*plan",
        low,
        re.I,
    ):
        return {"intent": "tomorrow_plan", "query": None}

    if re.search(r"bul|ara|geçen|içeren|search|find", low, re.I):
        qm = re.search(r"['\"]([^'\"]{2,120})['\"]", raw)
        if qm:
            return {"intent": "search", "query": qm.group(1).strip()}
        m = re.search(
            r"([\wçğıöşüÇĞİÖŞ]+)\s*(?:geçen|içeren|diye)",
            raw,
            re.I,
        )
        if m:
            return {"intent": "search", "query": m.group(1).strip()}
        if "geçen" in low:
            before = low.split("geçen", 1)[0].strip()
            tokens = re.findall(r"[\wçğıöşü]+", before)
            if tokens:
                return {"intent": "search", "query": tokens[-1]}

    return {"intent": "unknown", "query": None}


def dispatch_message(db: Session, user: User, text: str) -> dict[str, Any]:
    """interpret + uygun fonksiyon."""
    r = interpret_user_message(text)
    intent = r["intent"]
    q = r.get("query")

    if intent == "weekly_summary":
        out = weekly_what_did_i_do(db, user)
        out["routed_from"] = text[:200]
        return out
    if intent == "tomorrow_plan":
        out = suggest_tomorrow_plan(db, user)
        out["routed_from"] = text[:200]
        return out
    if intent == "search" and q:
        out = search_ideas_transcripts(db, user, q)
        out["routed_from"] = text[:200]
        return out

    return {
        "intent": "unknown",
        "hint_tr": "Örnek: «Bu hafta ne yaptım?», «Fikirlerimde ürün geçenleri bul», «Yarın için plan öner»",
        "interpreted": r,
    }

"""Toplantı transkripti: özet + aksiyon maddeleri → görevler."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import Task, VoiceNote


def extract_meeting_summary(text: str, max_len: int = 900) -> str:
    t = text.strip()
    if not t:
        return ""
    parts = re.split(r"\n\s*\n+", t)
    first = parts[0] if parts else t
    if len(first) > max_len:
        return first[: max_len - 3] + "..."
    return first


def extract_action_items(text: str) -> list[dict[str, str | None]]:
    """Basit satır tabanlı aksiyon çıkarımı; assignee opsiyonel."""
    items: list[dict[str, str | None]] = []
    seen: set[str] = set()

    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue

        m_assignee = re.match(
            r"^([A-Za-zÇĞİÖŞÜçğıöşü][a-zçğıöşüA-Za-zÇĞİÖŞÜ]*)\s*:\s*(.+)$",
            raw,
        )
        assignee: str | None = None
        body = raw
        if m_assignee:
            assignee = m_assignee.group(1)
            body = m_assignee.group(2).strip()

        if re.match(r"^[-*•]\s+", body):
            body = re.sub(r"^[-*•]\s+", "", body)
        elif re.match(r"^\d+[\.)]\s+", body):
            body = re.sub(r"^\d+[\.)]\s+", "", body)
        elif re.match(r"(?i)^(action|aksiyon|yapılacak|yapilacak|todo)\s*:\s*", body):
            body = re.split(r":", body, 1)[-1].strip()
        else:
            continue

        if len(body) < 2:
            continue
        key = body[:200].lower()
        if key in seen:
            continue
        seen.add(key)
        items.append({"text": body[:500], "assignee": assignee})

    return items[:25]


def process_meeting_note(db: Session, note: VoiceNote) -> dict:
    text = (note.transcript or "").strip()
    if not text:
        return {"meeting": "empty"}

    summary = extract_meeting_summary(text)
    actions = extract_action_items(text)
    note.meeting_summary = summary
    note.meeting_action_items = actions

    created_task_ids: list[int] = []
    for item in actions:
        title = item["text"]
        if item.get("assignee"):
            title = f"[{item['assignee']}] {title}"
        task = Task(
            user_id=note.user_id,
            title=title[:500],
            done=False,
            depth="shallow",
            source_voice_note_id=note.id,
        )
        db.add(task)
        db.flush()
        created_task_ids.append(task.id)

    if created_task_ids and note.linked_task_id is None:
        note.linked_task_id = created_task_ids[0]
    if created_task_ids:
        note.task_converted = True

    note.ai_category = "meeting"
    tags = list(note.tags) if note.tags else []
    if "toplantı" not in tags:
        tags.append("toplantı")
    note.tags = tags

    db.commit()
    return {
        "meeting_summary_len": len(summary),
        "action_items_count": len(actions),
        "task_ids": created_task_ids,
    }

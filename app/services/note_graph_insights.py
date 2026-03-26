"""
Obsidian tarzı [[wikilink]] + iki not arasında ortak tema özeti (kural tabanlı, LLM yok).
Örnek: Not A → [[Proje X]] → Not B; çıktı: "Bu iki not arasında 3 ortak tema var: ..."
"""

from __future__ import annotations

import re
from sqlalchemy.orm import Session

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

_TR_STOP = frozenset(
    """
    ve veya ile için gibi daha çok az en çok bir bu şu o da de ki mi mı mu mü
    ben sen biz siz onlar şey bir iki üç böyle şöyle böyleyse
    bugün yarın dün şimdi sonra önce burada orada
    the a an is are was were to of in on at it be
    """.split()
)


def extract_wikilinks(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for m in WIKILINK_RE.finditer(text):
        s = m.group(1).strip()
        if s:
            out.append(s)
    return out


def _significant_tokens(text: str) -> set[str]:
    words = re.findall(r"[\wçğıöşüÇĞİÖŞ]+", (text or "").lower())
    return {
        w
        for w in words
        if len(w) >= 3
        and w not in _TR_STOP
        and not w.isdigit()
    }


def pair_theme_analysis(
    a_transcript: str | None,
    b_transcript: str | None,
    *,
    max_terms: int = 12,
) -> dict:
    """
    Ortak anlamlı kelimeler + ortak [[wikilink]] birlikte sayılır.
    """
    ta = _significant_tokens(a_transcript or "")
    tb = _significant_tokens(b_transcript or "")
    shared_words = sorted(ta & tb)[:max_terms]

    wa = set(extract_wikilinks(a_transcript or ""))
    wb = set(extract_wikilinks(b_transcript or ""))
    shared_links = sorted(wa & wb)

    common_count = len(shared_words) + len(shared_links)
    labels = shared_links + shared_words

    if common_count == 0:
        msg = "Bu iki not arasında belirgin ortak tema veya ortak köprü bulunamadı."
    else:
        msg = _message_tr(common_count, labels[:10])

    return {
        "common_theme_count": common_count,
        "theme_terms": shared_words,
        "shared_wikilinks": shared_links,
        "message_tr": msg,
    }


def _message_tr(count: int, labels: list[str]) -> str:
    labels = [x for x in labels if x][:8]
    preview = ", ".join(labels)
    if count == 1:
        return f"Bu iki not arasında 1 ortak tema var: {preview}."
    return f"Bu iki not arasında {count} ortak tema var: {preview}."


def find_notes_by_anchor_title(
    db: Session, user_id: int, anchor_title: str, limit: int = 50
) -> list:
    """Transkriptte [[başlık]] geçen notlar."""
    from app.models import VoiceNote

    t = (anchor_title or "").strip()
    if not t:
        return []
    needle = f"%[[{t}]]%"
    return (
        db.query(VoiceNote)
        .filter(
            VoiceNote.user_id == user_id,
            VoiceNote.transcript.isnot(None),
            VoiceNote.transcript.ilike(needle),
        )
        .order_by(VoiceNote.created_at.desc())
        .limit(limit)
        .all()
    )

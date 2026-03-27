"""
Knowledge Graph servisi - Notlar arası bağlantıları yönetir
Obsidian tarzı [[wikilink]] + AI similarity önerileri
"""

from __future__ import annotations

import re
from typing import List, Optional

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from app.models import NoteEdge, VoiceNote

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
    """Transkriptten [[wikilink]] çıkarır"""
    if not text:
        return []
    return [m.group(1).strip() for m in WIKILINK_RE.finditer(text) if m.group(1).strip()]


def _significant_tokens(text: str) -> set[str]:
    """Anlamlı kelimeleri çıkarır (stop words hariç)"""
    words = re.findall(r"[\wçğıöşüÇĞİÖŞ]+", (text or "").lower())
    return {
        w for w in words
        if len(w) >= 3
        and w not in _TR_STOP
        and not w.isdigit()
    }


def calculate_similarity(note_a: VoiceNote, note_b: VoiceNote) -> float:
    """
    İki not arasındaki benzerliği hesaplar (0-1 arası)
    Metin benzerliği + wikilink overlap
    """
    if not note_a.transcript or not note_b.transcript:
        return 0.0
    
    # Metin benzerliği
    tokens_a = _significant_tokens(note_a.transcript)
    tokens_b = _significant_tokens(note_b.transcript)
    
    if not tokens_a or not tokens_b:
        text_sim = 0.0
    else:
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        text_sim = intersection / union if union > 0 else 0.0
    
    # Wikilink overlap
    wiki_a = set(extract_wikilinks(note_a.transcript))
    wiki_b = set(extract_wikilinks(note_b.transcript))
    
    wiki_sim = 0.0
    if wiki_a and wiki_b:
        wiki_intersection = len(wiki_a & wiki_b)
        wiki_union = len(wiki_a | wiki_b)
        wiki_sim = wiki_intersection / wiki_union if wiki_union > 0 else 0.0
    
    # Ağırlıklı ortalama
    return (text_sim * 0.6) + (wiki_sim * 0.4)


def create_wikilink_edges(db: Session, note: VoiceNote) -> list[NoteEdge]:
    """
    Bir nottaki [[wikilink]]'leri bulup edge'ler oluşturur
    """
    wikilinks = extract_wikilinks(note.transcript or "")
    if not wikilinks:
        return []
    
    created_edges = []
    
    for link_title in wikilinks:
        # Hedef notu bul (başlık eşleşmesi veya transkript içinde geçme)
        target = (
            db.query(VoiceNote)
            .filter(
                VoiceNote.user_id == note.user_id,
                VoiceNote.id != note.id,
                or_(
                    VoiceNote.title.ilike(f"%{link_title}%"),
                    VoiceNote.transcript.ilike(f"%{link_title}%")
                )
            )
            .first()
        )
        
        if target:
            # Edge zaten var mı kontrol et
            existing = (
                db.query(NoteEdge)
                .filter(
                    NoteEdge.source_note_id == note.id,
                    NoteEdge.target_note_id == target.id,
                    NoteEdge.edge_type == "wiki"
                )
                .first()
            )
            
            if not existing:
                edge = NoteEdge(
                    user_id=note.user_id,
                    source_note_id=note.id,
                    target_note_id=target.id,
                    edge_type="wiki",
                    strength=1.0
                )
                db.add(edge)
                created_edges.append(edge)
    
    if created_edges:
        db.commit()
    
    return created_edges


def suggest_similar_notes(
    db: Session, 
    note_id: int, 
    user_id: int,
    limit: int = 5,
    min_similarity: float = 0.15
) -> list[dict]:
    """
    Bir nota benzer diğer notları önerir
    """
    source = db.query(VoiceNote).filter(
        VoiceNote.id == note_id,
        VoiceNote.user_id == user_id
    ).first()
    
    if not source or not source.transcript:
        return []
    
    # Tüm kullanıcı notlarını al
    other_notes = (
        db.query(VoiceNote)
        .filter(
            VoiceNote.user_id == user_id,
            VoiceNote.id != note_id,
            VoiceNote.transcript.isnot(None)
        )
        .all()
    )
    
    # Benzerlik skorlarını hesapla
    scored = []
    for note in other_notes:
        sim = calculate_similarity(source, note)
        if sim >= min_similarity:
            scored.append((note, sim))
    
    # Sırala ve sınırla
    scored.sort(key=lambda x: x[1], reverse=True)
    
    return [
        {
            "note_id": note.id,
            "title": note.title or "Isimsiz Not",
            "preview": (note.transcript or "")[:100] + "..." if note.transcript else "",
            "similarity": round(sim, 3),
            "created_at": note.created_at.isoformat() if note.created_at else None
        }
        for note, sim in scored[:limit]
    ]


def get_note_graph(
    db: Session,
    user_id: int,
    center_note_id: Optional[int] = None,
    hops: int = 2,
    limit: int = 50
) -> dict:
    """
    Not graph'ini döner (nodes + edges)
    Obsidian graph view için
    """
    # Notları al
    query = db.query(VoiceNote).filter(
        VoiceNote.user_id == user_id,
        VoiceNote.transcript.isnot(None)
    )
    
    if center_note_id:
        # Merkez not ve bağlı notları al
        center = db.query(VoiceNote).filter(
            VoiceNote.id == center_note_id,
            VoiceNote.user_id == user_id
        ).first()
        
        if not center:
            return {"nodes": [], "edges": []}
        
        # Bağlı not ID'lerini topla
        related_ids = {center_note_id}
        current_ids = {center_note_id}
        
        for _ in range(hops):
            edges = db.query(NoteEdge).filter(
                NoteEdge.user_id == user_id,
                or_(
                    NoteEdge.source_note_id.in_(current_ids),
                    NoteEdge.target_note_id.in_(current_ids)
                )
            ).all()
            
            new_ids = set()
            for edge in edges:
                new_ids.add(edge.source_note_id)
                new_ids.add(edge.target_note_id)
            
            related_ids.update(new_ids)
            current_ids = new_ids - related_ids
            if not current_ids:
                break
        
        notes = db.query(VoiceNote).filter(VoiceNote.id.in_(related_ids)).limit(limit).all()
    else:
        # Tüm notları al
        notes = query.limit(limit).all()
    
    note_ids = {n.id for n in notes}
    
    # Edge'leri al
    edges = db.query(NoteEdge).filter(
        NoteEdge.user_id == user_id,
        NoteEdge.source_note_id.in_(note_ids),
        NoteEdge.target_note_id.in_(note_ids)
    ).all()
    
    return {
        "nodes": [
            {
                "id": n.id,
                "title": n.title or f"Not #{n.id}",
                "preview": (n.transcript or "")[:80] + "..." if n.transcript else "",
                "created_at": n.created_at.isoformat() if n.created_at else None
            }
            for n in notes
        ],
        "edges": [
            {
                "source": e.source_note_id,
                "target": e.target_note_id,
                "type": e.edge_type,
                "strength": e.strength
            }
            for e in edges
        ]
    }


def get_backlinks(db: Session, note_id: int, user_id: int) -> list[dict]:
    """
    Bir nota işaret eden (incoming) edge'leri döner
    """
    edges = (
        db.query(NoteEdge)
        .join(VoiceNote, NoteEdge.source_note_id == VoiceNote.id)
        .filter(
            NoteEdge.target_note_id == note_id,
            NoteEdge.user_id == user_id
        )
        .all()
    )
    
    return [
        {
            "note_id": e.source_note_id,
            "title": e.source_note.title or f"Not #{e.source_note_id}",
            "edge_type": e.edge_type,
            "strength": e.strength
        }
        for e in edges
    ]


def auto_link_notes(db: Session, user_id: int, min_similarity: float = 0.3) -> int:
    """
    Benzer notları otomatik olarak bağlar (admin/batch işlemi için)
    """
    notes = (
        db.query(VoiceNote)
        .filter(
            VoiceNote.user_id == user_id,
            VoiceNote.transcript.isnot(None)
        )
        .all()
    )
    
    created_count = 0
    
    for i, note_a in enumerate(notes):
        for note_b in notes[i+1:]:
            sim = calculate_similarity(note_a, note_b)
            
            if sim >= min_similarity:
                # Edge zaten var mı kontrol et
                existing = (
                    db.query(NoteEdge)
                    .filter(
                        NoteEdge.user_id == user_id,
                        or_(
                            and_(
                                NoteEdge.source_note_id == note_a.id,
                                NoteEdge.target_note_id == note_b.id
                            ),
                            and_(
                                NoteEdge.source_note_id == note_b.id,
                                NoteEdge.target_note_id == note_a.id
                            )
                        )
                    )
                    .first()
                )
                
                if not existing:
                    edge = NoteEdge(
                        user_id=user_id,
                        source_note_id=note_a.id,
                        target_note_id=note_b.id,
                        edge_type="similar",
                        strength=sim
                    )
                    db.add(edge)
                    created_count += 1
    
    if created_count > 0:
        db.commit()
    
    return created_count

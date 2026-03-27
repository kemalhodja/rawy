"""
Knowledge Graph API - Obsidian tarzı not bağlantıları
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, VoiceNote
from app.services.knowledge_graph import (
    create_wikilink_edges,
    get_backlinks,
    get_note_graph,
    suggest_similar_notes,
    auto_link_notes,
)

router = APIRouter(prefix="/graph", tags=["knowledge-graph"])


@router.get("")
def get_graph(
    center_note_id: int = None,
    hops: int = 2,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Not graph'ini getir (nodes + edges)
    - center_note_id: Merkez not (opsiyonel)
    - hops: Kaç adım öteye git (1-3)
    """
    hops = max(1, min(hops, 3))  # Sınırla
    return get_note_graph(db, current_user.id, center_note_id, hops)


@router.get("/suggest/{note_id}")
def suggest_links(
    note_id: int,
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bir nota benzer diğer notları öner
    """
    note = db.query(VoiceNote).filter(
        VoiceNote.id == note_id,
        VoiceNote.user_id == current_user.id
    ).first()
    
    if not note:
        raise HTTPException(404, "Not bulunamadi")
    
    return suggest_similar_notes(db, note_id, current_user.id, limit)


@router.post("/extract-wikilinks/{note_id}")
def extract_wikilinks(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bir nottaki [[wikilink]]'leri bulup edge olarak kaydet
    """
    note = db.query(VoiceNote).filter(
        VoiceNote.id == note_id,
        VoiceNote.user_id == current_user.id
    ).first()
    
    if not note:
        raise HTTPException(404, "Not bulunamadi")
    
    edges = create_wikilink_edges(db, note)
    
    return {
        "created_edges": len(edges),
        "links": [
            {
                "source": e.source_note_id,
                "target": e.target_note_id,
                "title": e.target_note.title if e.target_note else None
            }
            for e in edges
        ]
    }


@router.get("/backlinks/{note_id}")
def get_note_backlinks(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bir nota işaret eden (backlink) notları getir
    """
    note = db.query(VoiceNote).filter(
        VoiceNote.id == note_id,
        VoiceNote.user_id == current_user.id
    ).first()
    
    if not note:
        raise HTTPException(404, "Not bulunamadi")
    
    return get_backlinks(db, note_id, current_user.id)


@router.post("/auto-link")
def auto_link(
    min_similarity: float = 0.3,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Benzer notları otomatik olarak bağla (batch işlemi)
    """
    count = auto_link_notes(db, current_user.id, min_similarity)
    return {
        "message": f"{count} yeni baglanti olusturuldu",
        "created_edges": count
    }

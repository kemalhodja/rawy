"""Metin tabanlı minimal asistan (LLM yok): haftalık özet, arama, yarın planı."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.services.assistant_lindy import (
    dispatch_message,
    interpret_user_message,
    search_ideas_transcripts,
    suggest_tomorrow_plan,
    weekly_what_did_i_do,
)

router = APIRouter()


class SearchBody(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


@router.post("/weekly-summary")
def assistant_weekly_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """«Bu hafta ne yaptım?» — özet + sesli notlardan kısa alıntılar."""
    return weekly_what_did_i_do(db, current_user)


@router.post("/search")
def assistant_search(
    body: SearchBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transkript/başlıkta anahtar kelime; ilişkili not id'leri ile."""
    return search_ideas_transcripts(db, current_user, body.query)


@router.post("/tomorrow-plan")
def assistant_tomorrow_plan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Yarın için kural tabanlı ajanda / görev önerisi."""
    return suggest_tomorrow_plan(db, current_user)


@router.post("/chat")
def assistant_chat(
    body: ChatBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Serbest metin — sınırlı kalıplarla yönlendirme.
    Örnek: «Bu hafta ne yaptım?», «Fikirlerimde 'ürün' geçenleri bul», «Yarın için plan öner»
    """
    return dispatch_message(db, current_user, body.message)


@router.get("/interpret-preview")
def assistant_interpret_preview(
    message: str = Query(..., min_length=1, max_length=2000),
    current_user: User = Depends(get_current_user),
):
    """Sadece niyet önizlemesi (DB sorgusu yok)."""
    _ = current_user
    return interpret_user_message(message)

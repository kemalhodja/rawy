"""
Speaker Recognition Router

Endpointler:
- POST /speaker/enroll - Ses kaydı (voice enrollment)
- POST /speaker/verify - Ses doğrulama
- POST /speaker/identify - Kimin sesi?
- GET /speaker/profile - Kullanıcı ses profili
- DELETE /speaker/profile/{id} - Ses kaydını sil
- POST /speaker/auth - Ses şifresi ile giriş

Toplantı:
- GET /speaker/diarize/{voice_note_id} - Toplantıyı konuşmacılara ayır
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, VoiceEmbedding, SpeakerSegment, VoiceNote
from app.services.speaker_recognition import SpeakerRecognition, VoiceAuthenticator

router = APIRouter(prefix="/speaker", tags=["speaker-recognition"])


# ========== SCHEMAS ==========

class EnrollResponse(BaseModel):
    success: bool
    embedding_id: Optional[int]
    confidence: float
    message: str
    model: str


class VerifyResponse(BaseModel):
    is_match: bool
    confidence: float
    threshold: float
    message: str


class IdentifyResponse(BaseModel):
    recognized: bool
    user_id: Optional[int]
    email: Optional[str]
    confidence: float
    message: str


class VoiceAuthResponse(BaseModel):
    authenticated: bool
    user_id: Optional[int]
    email: Optional[str]
    confidence: float
    access_token: Optional[str]
    message: str


class SpeakerProfileOut(BaseModel):
    id: int
    model: str
    sample_duration: Optional[float]
    confidence_score: Optional[float]
    is_active: bool
    created_at: datetime


class DiarizationSegmentOut(BaseModel):
    start_time: float
    end_time: float
    speaker_label: Optional[str]
    transcript: Optional[str]
    confidence: Optional[float]


class DiarizationResponse(BaseModel):
    voice_note_id: int
    segments: list[DiarizationSegmentOut]
    speaker_count: int
    message: str


class PersonalizedQuery(BaseModel):
    audio: Optional[str] = None  # Base64 ses veya önceki kayıt
    query_type: str = "tasks"  # tasks, reminders, notes


class PersonalizedResponse(BaseModel):
    user_id: int
    recognized: bool
    confidence: float
    type: str
    items: list[dict]
    message: str


# ========== ENROLLMENT ==========

@router.post("/enroll", response_model=EnrollResponse)
async def enroll_voice(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ses kaydı (enrollment) - Kullanıcının ses profilini oluştur.
    
    En az 5-10 saniyelik net bir ses kaydı önerilir.
    "Merhaba ben [Adım], bu benim ses şifrem" gibi bir cümle söyleyin.
    """
    # Dosyayı geçici kaydet
    import tempfile
    import shutil
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    
    try:
        # Enrollment yap
        embedding, confidence = SpeakerRecognition.enroll(
            db, tmp_path, current_user.id
        )
        
        if embedding is None:
            return EnrollResponse(
                success=False,
                embedding_id=None,
                confidence=0.0,
                message="Ses işlenemedi. Lütfen tekrar deneyin.",
                model=SpeakerRecognition.MODEL_NAME
            )
        
        return EnrollResponse(
            success=True,
            embedding_id=embedding.id,
            confidence=confidence,
            message=f"Ses kaydınız başarıyla oluşturuldu (güven: {confidence:.2f})",
            model=SpeakerRecognition.MODEL_NAME
        )
        
    finally:
        import os
        os.unlink(tmp_path)


@router.get("/profile", response_model=list[SpeakerProfileOut])
def get_voice_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kullanıcının tüm ses kayıtlarını listele"""
    embeddings = db.query(VoiceEmbedding).filter(
        VoiceEmbedding.user_id == current_user.id
    ).order_by(VoiceEmbedding.created_at.desc()).all()
    
    return [
        SpeakerProfileOut(
            id=e.id,
            model=e.embedding_model,
            sample_duration=e.sample_duration,
            confidence_score=e.confidence_score,
            is_active=e.is_active,
            created_at=e.created_at,
        )
        for e in embeddings
    ]


@router.delete("/profile/{embedding_id}")
def delete_voice_profile(
    embedding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Belirli bir ses kaydını sil (pasif yap)"""
    embedding = db.query(VoiceEmbedding).filter(
        VoiceEmbedding.id == embedding_id,
        VoiceEmbedding.user_id == current_user.id
    ).first()
    
    if not embedding:
        raise HTTPException(404, "Ses kaydı bulunamadı")
    
    embedding.is_active = False
    db.commit()
    
    return {"deleted": True, "id": embedding_id}


# ========== VERIFICATION ==========

@router.post("/verify", response_model=VerifyResponse)
async def verify_voice(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ses doğrulama - Bu ses kaydı kullanıcıya ait mi?
    
    Enrollment sonrası test için kullanılır.
    """
    import tempfile
    import shutil
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    
    try:
        is_match, confidence = SpeakerRecognition.verify(
            db, tmp_path, current_user.id
        )
        
        if is_match:
            message = f"Ses doğrulandı (güven: {confidence:.2f})"
        else:
            message = f"Ses eşleşmedi (güven: {confidence:.2f}, eşik: {SpeakerRecognition.SIMILARITY_THRESHOLD})"
        
        return VerifyResponse(
            is_match=is_match,
            confidence=confidence,
            threshold=SpeakerRecognition.SIMILARITY_THRESHOLD,
            message=message
        )
        
    finally:
        import os
        os.unlink(tmp_path)


@router.post("/identify", response_model=IdentifyResponse)
async def identify_speaker(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # Sadece giriş yapmış kullanıcılar
):
    """
    Ses tanımlama - Bu ses kime ait?
    
    Tüm kayıtlı kullanıcılar arasından eşleşme arar.
    """
    import tempfile
    import shutil
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    
    try:
        user_id, confidence = SpeakerRecognition.identify(db, tmp_path)
        
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            return IdentifyResponse(
                recognized=True,
                user_id=user_id,
                email=user.email if user else None,
                confidence=confidence,
                message=f"Ses tanımlandı: {user.email if user else 'Unknown'} (güven: {confidence:.2f})"
            )
        else:
            return IdentifyResponse(
                recognized=False,
                user_id=None,
                email=None,
                confidence=confidence,
                message=f"Ses tanımlanamadı (en yüksek güven: {confidence:.2f})"
            )
            
    finally:
        import os
        os.unlink(tmp_path)


# ========== VOICE AUTHENTICATION ==========

@router.post("/auth", response_model=VoiceAuthResponse)
async def voice_authentication(
    file: UploadFile = File(...),
    email: Optional[str] = None,  # Biliniyorsa
    db: Session = Depends(get_db),
):
    """
    Ses şifresi ile giriş (Voice Password Login)
    
    Önce enrollment yapılmış olmalı.
    email biliniyorsa sadece o kullanıcıyı kontrol eder.
    """
    from app.services.security import create_access_token
    import tempfile
    import shutil
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    
    try:
        authenticator = VoiceAuthenticator(db)
        
        # Email biliniyorsa sadece o kullanıcıyı kontrol et
        if email:
            user = db.query(User).filter(User.email == email).first()
            if not user:
                return VoiceAuthResponse(
                    authenticated=False,
                    user_id=None,
                    email=None,
                    confidence=0.0,
                    access_token=None,
                    message="Kullanıcı bulunamadı"
                )
            
            is_match, confidence, matched_id = authenticator.authenticate(
                tmp_path, user.id
            )
            matched_user = user if is_match else None
        else:
            # Tüm kullanıcılar arasından bul
            is_match, confidence, matched_id = authenticator.authenticate(tmp_path)
            matched_user = db.query(User).filter(User.id == matched_id).first() if matched_id else None
        
        if is_match and matched_user:
            # Token oluştur
            token = create_access_token({"sub": str(matched_user.id)})
            
            return VoiceAuthResponse(
                authenticated=True,
                user_id=matched_user.id,
                email=matched_user.email,
                confidence=confidence,
                access_token=token,
                message=f"Giriş başarılı! Hoş geldiniz, {matched_user.email}"
            )
        else:
            return VoiceAuthResponse(
                authenticated=False,
                user_id=None,
                email=None,
                confidence=confidence,
                access_token=None,
                message="Ses şifresi eşleşmedi. Lütfen tekrar deneyin."
            )
            
    finally:
        import os
        os.unlink(tmp_path)


# ========== DIARIZATION ==========

@router.post("/diarize/{voice_note_id}", response_model=DiarizationResponse)
def diarize_meeting(
    voice_note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Toplantı sesini konuşmacılara ayır.
    
    NOT: Ses dosyası önce Whisper ile transkript edilmeli.
    """
    # Notu kontrol et
    note = db.query(VoiceNote).filter(
        VoiceNote.id == voice_note_id,
        VoiceNote.user_id == current_user.id
    ).first()
    
    if not note:
        raise HTTPException(404, "Ses kaydı bulunamadı")
    
    # Ses dosyası var mı?
    if not note.storage_path:
        raise HTTPException(400, "Ses dosyası bulunamadı")
    
    # Diarization yap
    segments = SpeakerRecognition.diarize_meeting(
        db, voice_note_id, note.storage_path
    )
    
    # Benzersiz konuşmacı sayısı
    unique_speakers = set(seg.speaker_label for seg in segments if seg.speaker_label)
    
    return DiarizationResponse(
        voice_note_id=voice_note_id,
        segments=[
            DiarizationSegmentOut(
                start_time=seg.start_time,
                end_time=seg.end_time,
                speaker_label=seg.speaker_label,
                transcript=seg.transcript,
                confidence=seg.confidence,
            )
            for seg in segments
        ],
        speaker_count=len(unique_speakers),
        message=f"{len(segments)} segment, {len(unique_speakers)} farklı konuşmacı bulundu"
    )


@router.get("/diarize/{voice_note_id}/transcript")
def get_diarized_transcript(
    voice_note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Toplantı transkriptini konuşmacı etiketleriyle getir.
    
    Format: "[Ali]: Merhaba...\n[Ayşe]: Nasılsınız?"
    """
    # Notu kontrol et
    note = db.query(VoiceNote).filter(
        VoiceNote.id == voice_note_id,
        VoiceNote.user_id == current_user.id
    ).first()
    
    if not note:
        raise HTTPException(404, "Ses kaydı bulunamadı")
    
    # Segmentleri getir
    segments = db.query(SpeakerSegment).filter(
        SpeakerSegment.voice_note_id == voice_note_id
    ).order_by(SpeakerSegment.start_time.asc()).all()
    
    if not segments:
        return {
            "voice_note_id": voice_note_id,
            "formatted_transcript": note.transcript or "Transkript yok",
            "segments": []
        }
    
    # Formatlanmış transkript
    lines = []
    for seg in segments:
        speaker = seg.speaker_label or "Unknown"
        text = seg.transcript or "..."
        time_str = f"[{int(seg.start_time//60):02d}:{int(seg.start_time%60):02d}]"
        lines.append(f"{time_str} [{speaker}]: {text}")
    
    return {
        "voice_note_id": voice_note_id,
        "formatted_transcript": "\n".join(lines),
        "segments": [
            {
                "start": seg.start_time,
                "end": seg.end_time,
                "speaker": seg.speaker_label,
                "text": seg.transcript,
            }
            for seg in segments
        ]
    }


# ========== PERSONALIZED COMMANDS ==========

@router.post("/personalized", response_model=PersonalizedResponse)
async def personalized_voice_command(
    query: PersonalizedQuery,
    file: Optional[UploadFile] = None,
    db: Session = Depends(get_db),
):
    """
    Sesden kullanıcıyı tanıyarak kişiselleştirilmiş içerik getir.
    
    Örnek: "Benim görevlerimi getir" komutu
    - Sesi tanır (kim olduğunu bulur)
    - O kullanıcının görevlerini getirir
    """
    import tempfile
    import shutil
    
    if not file:
        raise HTTPException(400, "Ses dosyası gerekli")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    
    try:
        # Kimin sesi?
        user_id, confidence = SpeakerRecognition.identify(db, tmp_path)
        
        if not user_id:
            return PersonalizedResponse(
                user_id=0,
                recognized=False,
                confidence=confidence,
                type=query.query_type,
                items=[],
                message="Ses tanımlanamadı"
            )
        
        # Kişiselleştirilmiş içerik getir
        context = SpeakerRecognition.get_personalized_context(
            db, user_id, query.query_type
        )
        
        return PersonalizedResponse(
            user_id=user_id,
            recognized=True,
            confidence=confidence,
            type=query.query_type,
            items=context["items"],
            message=f"Kullanıcı {user_id} tanındı, {len(context['items'])} öğe bulundu"
        )
        
    finally:
        import os
        os.unlink(tmp_path)

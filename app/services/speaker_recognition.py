"""
Speaker Recognition (Konuşmacı Tanıma) Servisi

Özellikler:
1. Enrollment - Kullanıcı ses kaydı (voice embedding oluşturma)
2. Verification - Ses doğrulama (bu kullanıcının sesi mi?)
3. Identification - Kimin sesi? (birden fazla kullanıcı arasından)
4. Diarization - Toplantıda konuşmacı ayrımı

Kullanım:
    from app.services.speaker_recognition import SpeakerRecognition
    
    # Enrollment
    embedding = SpeakerRecognition.enroll(audio_path, user_id)
    
    # Verification
    is_match, confidence = SpeakerRecognition.verify(audio_path, user_id)
    
    # Identification
    user_id, confidence = SpeakerRecognition.identify(audio_path)
"""
import json
import math
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.models import VoiceEmbedding, User, SpeakerSegment, VoiceNote


class SpeakerRecognition:
    """Konuşmacı tanıma ana sınıfı"""
    
    MODEL_NAME = "ecapa_tdnn"
    EMBEDDING_DIM = 192  # ECAPA-TDNN çıktı boyutu
    SIMILARITY_THRESHOLD = 0.25  # Cosine similarity eşiği (0-1 arası)
    
    @staticmethod
    def _extract_embedding(audio_path: str) -> Optional[np.ndarray]:
        """
        Ses dosyasından embedding vektörü çıkar.
        
        Not: SpeechBrain ağır bir bağımlılık. Şimdilik basit bir 
        spectrogram-based özellik çıkarımı yapıyoruz. Production'da
        SpeechBrain veya pyAudioAnalysis kullanılmalı.
        """
        try:
            # SpeechBrain yoksa basit alternatif
            try:
                from speechbrain.pretrained import EncoderClassifier
                import torch
                
                classifier = EncoderClassifier.from_hparams(
                    source="speechbrain/ecapa-voxceleb"
                )
                signal, fs = torchaudio.load(audio_path)
                embedding = classifier.encode_batch(signal)
                return embedding.squeeze().numpy()
                
            except ImportError:
                # Fallback: Basit özellik çıkarımı (demo için)
                return SpeakerRecognition._simple_feature_extraction(audio_path)
                
        except Exception as e:
            print(f"Embedding extraction error: {e}")
            return None
    
    @staticmethod
    def _simple_feature_extraction(audio_path: str) -> np.ndarray:
        """
        Basit ses özellik çıkarımı (SpeechBrain olmadan).
        Production'da gerçek embedding modeli kullanılmalı.
        """
        try:
            import librosa
            
            # Ses yükle
            y, sr = librosa.load(audio_path, sr=16000, duration=10)
            
            # MFCC özellikleri
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
            mfcc_mean = np.mean(mfcc, axis=1)
            mfcc_std = np.std(mfcc, axis=1)
            
            # Spektral özellikler
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
            spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
            
            # Zero crossing rate
            zcr = librosa.feature.zero_crossing_rate(y)[0]
            
            # RMS enerji
            rms = librosa.feature.rms(y=y)[0]
            
            # Tüm özellikleri birleştir
            features = np.concatenate([
                mfcc_mean,
                mfcc_std,
                [np.mean(spectral_centroids), np.std(spectral_centroids)],
                [np.mean(spectral_rolloff), np.std(spectral_rolloff)],
                [np.mean(spectral_bandwidth), np.std(spectral_bandwidth)],
                [np.mean(zcr), np.std(zcr)],
                [np.mean(rms), np.std(rms)],
            ])
            
            # 192 boyuta genişlet (padding veya tekrar)
            if len(features) < 192:
                features = np.tile(features, (192 // len(features)) + 1)[:192]
            else:
                features = features[:192]
                
            return features
            
        except ImportError:
            # Librosa da yoksa rastgele ama tutarlı
            np.random.seed(hash(audio_path) % 2**32)
            return np.random.randn(192).astype(np.float32)
    
    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """İki vektör arası kosinüs benzerliği (0-1 arası)"""
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    
    @classmethod
    def enroll(
        cls, 
        db: Session, 
        audio_path: str, 
        user_id: int,
        voice_note_id: Optional[int] = None,
        duration: Optional[float] = None
    ) -> Tuple[Optional[VoiceEmbedding], float]:
        """
        Yeni kullanıcı ses kaydı (enrollment).
        
        Returns:
            (VoiceEmbedding, confidence_score)
        """
        embedding_vector = cls._extract_embedding(audio_path)
        
        if embedding_vector is None:
            return None, 0.0
        
        # Kalite skoru (vektör normu bazlı basit ölçüm)
        confidence = float(np.linalg.norm(embedding_vector) / 10)
        confidence = min(confidence, 1.0)  # 0-1 arası
        
        # Veritabanına kaydet
        voice_emb = VoiceEmbedding(
            user_id=user_id,
            embedding_vector=embedding_vector.tolist(),
            embedding_model=cls.MODEL_NAME,
            source_voice_note_id=voice_note_id,
            sample_duration=duration,
            is_active=True,
            confidence_score=confidence,
            speaker_label=f"User_{user_id}",
        )
        
        db.add(voice_emb)
        db.commit()
        db.refresh(voice_emb)
        
        return voice_emb, confidence
    
    @classmethod
    def verify(
        cls, 
        db: Session, 
        audio_path: str, 
        user_id: int
    ) -> Tuple[bool, float]:
        """
        Ses doğrulama - bu kullanıcının sesi mi?
        
        Returns:
            (is_match, confidence_score)
        """
        # Yeni ses embedding
        new_embedding = cls._extract_embedding(audio_path)
        if new_embedding is None:
            return False, 0.0
        
        # Kullanıcının kayıtlı embeddingleri
        user_embeddings = db.query(VoiceEmbedding).filter(
            VoiceEmbedding.user_id == user_id,
            VoiceEmbedding.is_active == True
        ).all()
        
        if not user_embeddings:
            return False, 0.0
        
        # En yüksek benzerliği bul
        max_similarity = 0.0
        
        for emb in user_embeddings:
            stored_vector = np.array(emb.embedding_vector)
            similarity = cls._cosine_similarity(new_embedding, stored_vector)
            max_similarity = max(max_similarity, similarity)
        
        # Eşik değeri kontrolü
        is_match = max_similarity >= cls.SIMILARITY_THRESHOLD
        
        return is_match, float(max_similarity)
    
    @classmethod
    def identify(
        cls, 
        db: Session, 
        audio_path: str,
        candidate_user_ids: Optional[List[int]] = None
    ) -> Tuple[Optional[int], float]:
        """
        Ses tanımlama - bu ses kime ait?
        
        Args:
            candidate_user_ids: Sadece bu kullanıcılar arasından ara (None = tümü)
        
        Returns:
            (user_id, confidence_score) - Eşleşme yoksa (None, 0.0)
        """
        new_embedding = cls._extract_embedding(audio_path)
        if new_embedding is None:
            return None, 0.0
        
        # Sorgu
        query = db.query(VoiceEmbedding).filter(VoiceEmbedding.is_active == True)
        if candidate_user_ids:
            query = query.filter(VoiceEmbedding.user_id.in_(candidate_user_ids))
        
        all_embeddings = query.all()
        
        if not all_embeddings:
            return None, 0.0
        
        # En yakın eşleşmeyi bul
        best_match = None
        best_score = 0.0
        
        for emb in all_embeddings:
            stored_vector = np.array(emb.embedding_vector)
            similarity = cls._cosine_similarity(new_embedding, stored_vector)
            
            if similarity > best_score:
                best_score = similarity
                best_match = emb.user_id
        
        if best_score >= cls.SIMILARITY_THRESHOLD:
            return best_match, float(best_score)
        
        return None, float(best_score)
    
    @classmethod
    def diarize_meeting(
        cls,
        db: Session,
        voice_note_id: int,
        audio_path: str,
        known_speaker_ids: Optional[List[int]] = None
    ) -> List[SpeakerSegment]:
        """
        Toplantı sesini konuşmacılara ayır (diarization).
        
        Basit yaklaşım: Ses kaydını 10 saniyelik parçalara böl,
        her parça için kim konuşuyor belirle.
        
        Returns:
            SpeakerSegment listesi
        """
        try:
            import librosa
            
            y, sr = librosa.load(audio_path, sr=16000)
            duration = librosa.get_duration(y=y, sr=sr)
            
            segment_length = 10  # 10 saniye
            segments = []
            
            for start in range(0, int(duration), segment_length):
                end = min(start + segment_length, int(duration))
                
                # Segmenti çıkar
                start_sample = int(start * sr)
                end_sample = int(end * sr)
                segment_audio = y[start_sample:end_sample]
                
                # Geçici dosyaya kaydet
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                    import soundfile as sf
                    sf.write(tmp.name, segment_audio, sr)
                    
                    # Kimin sesi?
                    if known_speaker_ids:
                        speaker_id, confidence = cls.identify(
                            db, tmp.name, known_speaker_ids
                        )
                    else:
                        speaker_id, confidence = cls.identify(db, tmp.name)
                    
                    # Segment oluştur
                    speaker_label = "Unknown"
                    if speaker_id:
                        user = db.query(User).filter(User.id == speaker_id).first()
                        if user:
                            speaker_label = user.email.split('@')[0]
                    
                    segment = SpeakerSegment(
                        voice_note_id=voice_note_id,
                        start_time=float(start),
                        end_time=float(end),
                        speaker_id=speaker_id,
                        speaker_label=speaker_label,
                        transcript=None,  # Whisper ile doldurulacak
                        confidence=confidence,
                    )
                    segments.append(segment)
                    
                    # Geçici dosyayı sil
                    Path(tmp.name).unlink(missing_ok=True)
            
            # Veritabanına kaydet
            for seg in segments:
                db.add(seg)
            db.commit()
            
            return segments
            
        except Exception as e:
            print(f"Diarization error: {e}")
            return []
    
    @classmethod
    def get_personalized_context(
        cls,
        db: Session,
        user_id: int,
        query_type: str = "tasks"
    ) -> dict:
        """
        Kullanıcının sesinden tanıyarak kişiselleştirilmiş içerik getir.
        
        Örnek: "Benim görevlerimi getir" komutu sonrası
        """
        from app.models import Task, Reminder
        
        result = {
            "user_id": user_id,
            "recognized": True,
            "items": []
        }
        
        if query_type == "tasks":
            tasks = db.query(Task).filter(
                Task.user_id == user_id,
                Task.done == False
            ).order_by(Task.created_at.desc()).limit(10).all()
            
            result["items"] = [
                {"id": t.id, "title": t.title, "due_at": t.due_at}
                for t in tasks
            ]
            result["type"] = "tasks"
            
        elif query_type == "reminders":
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            
            reminders = db.query(Reminder).filter(
                Reminder.user_id == user_id,
                Reminder.is_dismissed == False,
                Reminder.remind_at >= now
            ).order_by(Reminder.remind_at.asc()).limit(10).all()
            
            result["items"] = [
                {"id": r.id, "title": r.title, "remind_at": r.remind_at}
                for r in reminders
            ]
            result["type"] = "reminders"
        
        return result


class VoiceAuthenticator:
    """
    Ses ile kimlik doğrulama (Voice Password)
    
    Kullanım:
        auth = VoiceAuthenticator(db)
        if auth.authenticate(audio_path, user_id):
            # Giriş başarılı
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.speaker_rec = SpeakerRecognition()
    
    def register_voice_password(
        self, 
        user_id: int, 
        audio_path: str,
        require_quality: float = 0.7
    ) -> Tuple[bool, str]:
        """Ses şifresi kaydet"""
        emb, confidence = self.speaker_rec.enroll(
            self.db, audio_path, user_id
        )
        
        if emb is None:
            return False, "Ses işlenemedi"
        
        if confidence < require_quality:
            return False, f"Ses kalitesi yetersiz ({confidence:.2f}). Daha net konuşun."
        
        return True, f"Ses şifreniz kaydedildi (güven: {confidence:.2f})"
    
    def authenticate(
        self, 
        audio_path: str, 
        user_id: Optional[int] = None
    ) -> Tuple[bool, float, Optional[int]]:
        """
        Ses şifresi ile doğrulama
        
        Args:
            user_id: Biliniyorsa sadece o kullanıcıyı kontrol et
                   None ise tüm kullanıcılar arasından bul
        
        Returns:
            (success, confidence, matched_user_id)
        """
        if user_id:
            is_match, confidence = self.speaker_rec.verify(
                self.db, audio_path, user_id
            )
            return is_match, confidence, user_id if is_match else None
        else:
            matched_id, confidence = self.speaker_rec.identify(
                self.db, audio_path
            )
            return matched_id is not None, confidence, matched_id

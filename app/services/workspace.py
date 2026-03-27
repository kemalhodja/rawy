"""
Workspace/Takım yönetimi servisi
B2B için kritik - paylaşımlı çalışma alanları
"""

from __future__ import annotations

import secrets
import string
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import User, VoiceNote, Workspace, WorkspaceMember


def generate_slug(name: str) -> str:
    """İsimden URL-friendly slug oluştur"""
    import re
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug[:50]


def generate_invite_token() -> str:
    """Güvenli davet token'ı oluştur"""
    return secrets.token_urlsafe(32)


def create_workspace(
    db: Session,
    name: str,
    owner_id: int,
    description: str = None
) -> Workspace:
    """Yeni workspace oluştur"""
    slug = generate_slug(name)
    
    # Benzersiz slug kontrolü
    existing = db.query(Workspace).filter(Workspace.slug == slug).first()
    if existing:
        slug = f"{slug}-{secrets.token_hex(4)}"
    
    workspace = Workspace(
        name=name,
        slug=slug,
        description=description,
        owner_id=owner_id,
        plan="starter",
        invite_token=generate_invite_token()
    )
    db.add(workspace)
    db.flush()  # ID almak için
    
    # Owner'ı admin olarak ekle
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=owner_id,
        role="owner"
    )
    db.add(member)
    db.commit()
    db.refresh(workspace)
    
    return workspace


def get_user_workspaces(db: Session, user_id: int) -> list[Workspace]:
    """Kullanıcının üye olduğu workspace'leri getir"""
    memberships = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == user_id)
        .all()
    )
    
    workspace_ids = [m.workspace_id for m in memberships]
    if not workspace_ids:
        return []
    
    return (
        db.query(Workspace)
        .filter(Workspace.id.in_(workspace_ids))
        .order_by(Workspace.created_at.desc())
        .all()
    )


def get_workspace_by_slug(db: Session, slug: str) -> Optional[Workspace]:
    """Slug ile workspace bul"""
    return db.query(Workspace).filter(Workspace.slug == slug).first()


def get_workspace_by_invite_token(db: Session, token: str) -> Optional[Workspace]:
    """Davet token'ı ile workspace bul"""
    return db.query(Workspace).filter(Workspace.invite_token == token).first()


def add_member(
    db: Session,
    workspace_id: int,
    user_id: int,
    role: str = "member",
    invited_by: int = None
) -> WorkspaceMember:
    """Workspace'e üye ekle"""
    # Zaten üye mi kontrol et
    existing = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id
        )
        .first()
    )
    
    if existing:
        return existing
    
    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user_id,
        role=role,
        invited_by=invited_by
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def remove_member(db: Session, workspace_id: int, user_id: int) -> bool:
    """Workspace'ten üye çıkar"""
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id
        )
        .first()
    )
    
    if member:
        db.delete(member)
        db.commit()
        return True
    return False


def update_member_role(
    db: Session,
    workspace_id: int,
    user_id: int,
    new_role: str
) -> Optional[WorkspaceMember]:
    """Üye rolünü güncelle"""
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id
        )
        .first()
    )
    
    if member:
        member.role = new_role
        db.commit()
        db.refresh(member)
    
    return member


def get_workspace_members(db: Session, workspace_id: int) -> list[dict]:
    """Workspace üyelerini getir"""
    members = (
        db.query(WorkspaceMember, User)
        .join(User, WorkspaceMember.user_id == User.id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .all()
    )
    
    return [
        {
            "user_id": m.user_id,
            "email": u.email,
            "role": m.role,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None
        }
        for m, u in members
    ]


def get_user_role_in_workspace(
    db: Session,
    workspace_id: int,
    user_id: int
) -> Optional[str]:
    """Kullanıcının workspace'teki rolünü getir"""
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id
        )
        .first()
    )
    return member.role if member else None


def has_workspace_permission(
    db: Session,
    workspace_id: int,
    user_id: int,
    min_role: str = "member"
) -> bool:
    """Kullanıcının workspace'te yetkisi var mı kontrol et"""
    role = get_user_role_in_workspace(db, workspace_id, user_id)
    if not role:
        return False
    
    # Rol hiyerarşisi
    hierarchy = {"viewer": 1, "member": 2, "admin": 3, "owner": 4}
    return hierarchy.get(role, 0) >= hierarchy.get(min_role, 2)


def share_note_to_workspace(
    db: Session,
    note_id: int,
    workspace_id: int,
    user_id: int
) -> Optional[VoiceNote]:
    """Notu workspace'e paylaş"""
    # Yetki kontrolü
    if not has_workspace_permission(db, workspace_id, user_id, "member"):
        return None
    
    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == note_id, VoiceNote.user_id == user_id)
        .first()
    )
    
    if note:
        note.workspace_id = workspace_id
        db.commit()
        db.refresh(note)
    
    return note


def get_workspace_notes(
    db: Session,
    workspace_id: int,
    limit: int = 50
) -> list[VoiceNote]:
    """Workspace'teki paylaşımlı notları getir"""
    return (
        db.query(VoiceNote)
        .filter(VoiceNote.workspace_id == workspace_id)
        .order_by(VoiceNote.created_at.desc())
        .limit(limit)
        .all()
    )


def regenerate_invite_token(db: Session, workspace_id: int, owner_id: int) -> Optional[str]:
    """Davet token'ını yenile"""
    workspace = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.owner_id == owner_id
    ).first()
    
    if workspace:
        workspace.invite_token = generate_invite_token()
        db.commit()
        return workspace.invite_token
    
    return None

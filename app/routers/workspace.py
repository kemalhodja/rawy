"""
Workspace/Takım API - B2B için kritik
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, Workspace
from app.services import workspace as workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    name: str
    description: str = None


class WorkspaceUpdate(BaseModel):
    name: str = None
    description: str = None


class MemberRoleUpdate(BaseModel):
    role: str  # admin, member, viewer


@router.get("")
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kullanıcının üye olduğu workspace'leri listele"""
    workspaces = workspace_service.get_user_workspaces(db, current_user.id)
    return [
        {
            "id": w.id,
            "name": w.name,
            "slug": w.slug,
            "description": w.description,
            "plan": w.plan,
            "owner_id": w.owner_id,
            "is_owner": w.owner_id == current_user.id,
            "invite_token": w.invite_token if w.owner_id == current_user.id else None,
            "created_at": w.created_at.isoformat() if w.created_at else None
        }
        for w in workspaces
    ]


@router.post("")
def create_workspace(
    data: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Yeni workspace oluştur"""
    workspace = workspace_service.create_workspace(
        db,
        name=data.name,
        owner_id=current_user.id,
        description=data.description
    )
    return {
        "id": workspace.id,
        "name": workspace.name,
        "slug": workspace.slug,
        "invite_token": workspace.invite_token,
        "message": "Workspace olusturuldu"
    }


@router.get("/{slug}")
def get_workspace(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Workspace detayını getir"""
    workspace = workspace_service.get_workspace_by_slug(db, slug)
    if not workspace:
        raise HTTPException(404, "Workspace bulunamadi")
    
    # Yetki kontrolü
    if not workspace_service.has_workspace_permission(db, workspace.id, current_user.id, "viewer"):
        raise HTTPException(403, "Erisim yetkiniz yok")
    
    members = workspace_service.get_workspace_members(db, workspace.id)
    
    return {
        "id": workspace.id,
        "name": workspace.name,
        "slug": workspace.slug,
        "description": workspace.description,
        "plan": workspace.plan,
        "owner_id": workspace.owner_id,
        "is_owner": workspace.owner_id == current_user.id,
        "members": members,
        "member_count": len(members),
        "created_at": workspace.created_at.isoformat() if workspace.created_at else None
    }


@router.get("/{slug}/members")
def get_members(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Workspace üyelerini listele"""
    workspace = workspace_service.get_workspace_by_slug(db, slug)
    if not workspace:
        raise HTTPException(404, "Workspace bulunamadi")
    
    if not workspace_service.has_workspace_permission(db, workspace.id, current_user.id, "viewer"):
        raise HTTPException(403, "Erisim yetkiniz yok")
    
    return workspace_service.get_workspace_members(db, workspace.id)


@router.post("/{slug}/invite")
def invite_member(
    slug: str,
    user_email: str,
    role: str = "member",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Workspace'e üye davet et (email ile)"""
    workspace = workspace_service.get_workspace_by_slug(db, slug)
    if not workspace:
        raise HTTPException(404, "Workspace bulunamadi")
    
    # Sadece admin ve owner davet edebilir
    if not workspace_service.has_workspace_permission(db, workspace.id, current_user.id, "admin"):
        raise HTTPException(403, "Uye davet etme yetkiniz yok")
    
    # Kullanıcıyı bul
    from app.models import User
    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise HTTPException(404, "Kullanici bulunamadi")
    
    member = workspace_service.add_member(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
        invited_by=current_user.id
    )
    
    return {
        "message": f"{user_email} davet edildi",
        "role": member.role
    }


@router.post("/join/{invite_token}")
def join_workspace(
    invite_token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Davet token'i ile workspace'e katıl"""
    workspace = workspace_service.get_workspace_by_invite_token(db, invite_token)
    if not workspace:
        raise HTTPException(404, "Gecersiz davet linki")
    
    member = workspace_service.add_member(
        db,
        workspace_id=workspace.id,
        user_id=current_user.id,
        role="member"
    )
    
    return {
        "message": f"'{workspace.name}' workspace'ine katildiniz",
        "workspace_slug": workspace.slug
    }


@router.patch("/{slug}/members/{user_id}/role")
def update_member_role(
    slug: str,
    user_id: int,
    data: MemberRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Üye rolünü güncelle"""
    workspace = workspace_service.get_workspace_by_slug(db, slug)
    if not workspace:
        raise HTTPException(404, "Workspace bulunamadi")
    
    # Sadece admin ve owner rol değiştirebilir
    if not workspace_service.has_workspace_permission(db, workspace.id, current_user.id, "admin"):
        raise HTTPException(403, "Rol degistirme yetkiniz yok")
    
    # Owner'ın rolünü değiştirmeye çalışıyor mu kontrol et
    if user_id == workspace.owner_id and data.role != "owner":
        raise HTTPException(403, "Owner'in rolü degistirilemez")
    
    member = workspace_service.update_member_role(
        db,
        workspace_id=workspace.id,
        user_id=user_id,
        new_role=data.role
    )
    
    if not member:
        raise HTTPException(404, "Uye bulunamadi")
    
    return {"message": "Rol guncellendi", "new_role": member.role}


@router.delete("/{slug}/members/{user_id}")
def remove_member(
    slug: str,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Workspace'ten üye çıkar"""
    workspace = workspace_service.get_workspace_by_slug(db, slug)
    if not workspace:
        raise HTTPException(404, "Workspace bulunamadi")
    
    # Kendini çıkarmaya çalışıyor mu?
    if user_id == current_user.id:
        raise HTTPException(400, "Kendinizi cikaramazsiniz")
    
    # Yetki kontrolü (owner herkesi çıkarabilir, admin member'ları çıkarabilir)
    current_role = workspace_service.get_user_role_in_workspace(
        db, workspace.id, current_user.id
    )
    target_role = workspace_service.get_user_role_in_workspace(
        db, workspace.id, user_id
    )
    
    if not current_role:
        raise HTTPException(403, "Erisim yetkiniz yok")
    
    if current_role == "admin" and target_role in ["admin", "owner"]:
        raise HTTPException(403, "Admin admin'i veya owner'i cikaramaz")
    
    if current_role not in ["admin", "owner"]:
        raise HTTPException(403, "Uye cikarma yetkiniz yok")
    
    success = workspace_service.remove_member(db, workspace.id, user_id)
    
    if success:
        return {"message": "Uye cikarildi"}
    raise HTTPException(404, "Uye bulunamadi")


@router.post("/{slug}/notes/{note_id}/share")
def share_note(
    slug: str,
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Notu workspace'e paylaş"""
    workspace = workspace_service.get_workspace_by_slug(db, slug)
    if not workspace:
        raise HTTPException(404, "Workspace bulunamadi")
    
    note = workspace_service.share_note_to_workspace(
        db,
        note_id=note_id,
        workspace_id=workspace.id,
        user_id=current_user.id
    )
    
    if not note:
        raise HTTPException(403, "Not paylasilamadi")
    
    return {"message": "Not paylasildi", "note_id": note.id}


@router.get("/{slug}/notes")
def get_shared_notes(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Workspace'teki paylaşımlı notları getir"""
    workspace = workspace_service.get_workspace_by_slug(db, slug)
    if not workspace:
        raise HTTPException(404, "Workspace bulunamadi")
    
    if not workspace_service.has_workspace_permission(db, workspace.id, current_user.id, "viewer"):
        raise HTTPException(403, "Erisim yetkiniz yok")
    
    notes = workspace_service.get_workspace_notes(db, workspace.id)
    
    return [
        {
            "id": n.id,
            "title": n.title or "Isimsiz Not",
            "preview": (n.transcript or "")[:100] + "..." if n.transcript else "",
            "author_id": n.user_id,
            "created_at": n.created_at.isoformat() if n.created_at else None
        }
        for n in notes
    ]


@router.post("/{slug}/regenerate-invite")
def regenerate_invite(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Davet token'ını yenile"""
    workspace = workspace_service.get_workspace_by_slug(db, slug)
    if not workspace:
        raise HTTPException(404, "Workspace bulunamadi")
    
    if workspace.owner_id != current_user.id:
        raise HTTPException(403, "Sadece owner davet linkini yenileyebilir")
    
    new_token = workspace_service.regenerate_invite_token(
        db,
        workspace_id=workspace.id,
        owner_id=current_user.id
    )
    
    return {
        "message": "Davet linki yenilendi",
        "invite_token": new_token,
        "invite_url": f"/workspaces/join/{new_token}"
    }

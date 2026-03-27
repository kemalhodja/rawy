"""
SAML/SSO API - Enterprise için
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, Workspace
from app.services import saml as saml_service
from app.services import workspace as workspace_service

router = APIRouter(prefix="/saml", tags=["saml-sso"])


class SamlConfigCreate(BaseModel):
    idp_entity_id: str
    idp_sso_url: str
    idp_slo_url: str = None
    idp_x509_cert: str
    email_attribute: str = "email"
    name_attribute: str = "name"


@router.get("/{workspace_id}/metadata")
def get_metadata(
    workspace_id: int,
    db: Session = Depends(get_db),
):
    """SP (Service Provider) Metadata XML'i"""
    config = saml_service.get_saml_config(db, workspace_id)
    if not config:
        raise HTTPException(404, "SAML konfigurasyonu bulunamadi")
    
    metadata = saml_service.get_sp_metadata(config)
    
    return HTMLResponse(
        content=metadata,
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename=rawy-sp-{workspace_id}.xml"}
    )


@router.get("/{workspace_id}/login")
def saml_login(
    workspace_id: int,
    db: Session = Depends(get_db),
):
    """SAML SSO login başlat"""
    config = saml_service.get_saml_config(db, workspace_id)
    if not config:
        raise HTTPException(404, "SAML SSO bu workspace icin aktif degil")
    
    # SAML Request oluştur
    saml_request = saml_service.generate_saml_request(config)
    
    # IdP'ye yönlendir (POST form)
    html = f"""<!DOCTYPE html>
<html>
<head><title>SSO Login</title></head>
<body onload="document.forms[0].submit()">
    <form method="POST" action="{config.idp_sso_url}">
        <input type="hidden" name="SAMLRequest" value="{saml_request}" />
        <input type="hidden" name="RelayState" value="{workspace_id}" />
        <p>Yonlendiriliyor...</p>
        <noscript><button type="submit">Devam et</button></noscript>
    </form>
</body>
</html>"""
    
    return HTMLResponse(content=html)


@router.post("/acs/{workspace_id}")
def saml_acs(
    workspace_id: int,
    saml_response: str = Form(..., alias="SAMLResponse"),
    relay_state: str = Form(None, alias="RelayState"),
    db: Session = Depends(get_db),
):
    """SAML Assertion Consumer Service - IdP'den gelen yanıt"""
    config = saml_service.get_saml_config(db, workspace_id)
    if not config:
        raise HTTPException(404, "SAML konfigurasyonu bulunamadi")
    
    # SAML Response parse et
    attributes = saml_service.parse_saml_response(saml_response)
    
    if "error" in attributes:
        raise HTTPException(400, f"SAML parse hatasi: {attributes['error']}")
    
    # Email bul
    email = attributes.get(config.email_attribute) or attributes.get("email")
    name = attributes.get(config.name_attribute) or attributes.get("name")
    
    if not email:
        raise HTTPException(400, "Email attribute bulunamadi")
    
    # Kullanıcı provision et
    user = saml_service.provision_user(db, workspace_id, email, name)
    
    # JWT token oluştur
    from app.security import create_access_token
    token = create_access_token(str(user.id))
    
    # Frontend'e yönlendir (token ile)
    redirect_url = f"/app?token={token}&sso=success"
    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/{workspace_id}/config")
def create_config(
    workspace_id: int,
    data: SamlConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SAML konfigürasyonu oluştur (sadece workspace owner)"""
    workspace = workspace_service.get_workspace_by_slug(db, str(workspace_id))
    if not workspace:
        raise HTTPException(404, "Workspace bulunamadi")
    
    if workspace.owner_id != current_user.id:
        raise HTTPException(403, "Sadece owner SAML yapilandirabilir")
    
    config = saml_service.create_saml_config(
        db,
        workspace_id=workspace_id,
        idp_entity_id=data.idp_entity_id,
        idp_sso_url=data.idp_sso_url,
        idp_x509_cert=data.idp_x509_cert,
        idp_slo_url=data.idp_slo_url,
        email_attribute=data.email_attribute,
        name_attribute=data.name_attribute
    )
    
    return {
        "message": "SAML konfigurasyonu olusturuldu",
        "workspace_id": config.workspace_id,
        "sp_entity_id": config.sp_entity_id,
        "metadata_url": f"/saml/{workspace_id}/metadata",
        "login_url": f"/saml/{workspace_id}/login"
    }


@router.get("/{workspace_id}/config")
def get_config(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SAML konfigürasyonunu getir (maskeli)"""
    workspace = workspace_service.get_workspace_by_slug(db, str(workspace_id))
    if not workspace:
        raise HTTPException(404, "Workspace bulunamadi")
    
    if not workspace_service.has_workspace_permission(db, workspace_id, current_user.id, "admin"):
        raise HTTPException(403, "Erisim yetkiniz yok")
    
    config = saml_service.get_saml_config(db, workspace_id)
    if not config:
        raise HTTPException(404, "SAML konfigurasyonu bulunamadi")
    
    return {
        "workspace_id": config.workspace_id,
        "idp_entity_id": config.idp_entity_id,
        "idp_sso_url": config.idp_sso_url,
        "idp_slo_url": config.idp_slo_url,
        "sp_entity_id": config.sp_entity_id,
        "email_attribute": config.email_attribute,
        "is_active": config.is_active,
        "cert_preview": config.idp_x509_cert[:50] + "..." if config.idp_x509_cert else None,
        "metadata_url": f"/saml/{workspace_id}/metadata",
        "login_url": f"/saml/{workspace_id}/login",
        "acs_url": f"/saml/acs/{workspace_id}"
    }


@router.delete("/{workspace_id}/config")
def delete_config(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SAML konfigürasyonunu sil"""
    workspace = workspace_service.get_workspace_by_slug(db, str(workspace_id))
    if not workspace:
        raise HTTPException(404, "Workspace bulunamadi")
    
    if workspace.owner_id != current_user.id:
        raise HTTPException(403, "Sadece owner silebilir")
    
    config = saml_service.get_saml_config(db, workspace_id)
    if config:
        config.is_active = False
        db.commit()
        return {"message": "SAML konfigurasyonu devre disi birakildi"}
    
    raise HTTPException(404, "SAML konfigurasyonu bulunamadi")

"""
SAML/SSO servisi - Enterprise için
Basit SAML 2.0 implementasyonu
"""

from __future__ import annotations

import base64
import re
import secrets
import zlib
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from app.models import SamlConfig, User, WorkspaceMember


def create_saml_config(
    db: Session,
    workspace_id: int,
    idp_entity_id: str,
    idp_sso_url: str,
    idp_x509_cert: str,
    idp_slo_url: str = None,
    email_attribute: str = "email",
    name_attribute: str = "name"
) -> SamlConfig:
    """SAML konfigürasyonu oluştur"""
    
    # Sertifikayı temizle
    cert = idp_x509_cert.replace("-----BEGIN CERTIFICATE-----", "").replace("-----END CERTIFICATE-----", "").replace("\n", "").strip()
    
    # SP Entity ID (bizim taraf)
    sp_entity_id = f"https://rawy.app/saml/{workspace_id}"
    
    config = SamlConfig(
        workspace_id=workspace_id,
        idp_entity_id=idp_entity_id,
        idp_sso_url=idp_sso_url,
        idp_slo_url=idp_slo_url,
        idp_x509_cert=cert,
        sp_entity_id=sp_entity_id,
        email_attribute=email_attribute,
        name_attribute=name_attribute
    )
    
    db.add(config)
    db.commit()
    db.refresh(config)
    
    return config


def get_saml_config(db: Session, workspace_id: int) -> Optional[SamlConfig]:
    """Workspace SAML konfigürasyonunu getir"""
    return (
        db.query(SamlConfig)
        .filter(SamlConfig.workspace_id == workspace_id, SamlConfig.is_active == True)
        .first()
    )


def generate_saml_request(config: SamlConfig) -> str:
    """SAML AuthnRequest oluştur (base64 encoded)"""
    
    request_id = f"_{secrets.token_hex(16)}"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    saml_request_xml = f"""<?xml version="1.0"?>
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="{request_id}"
    Version="2.0"
    IssueInstant="{timestamp}"
    Destination="{config.idp_sso_url}"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
    AssertionConsumerServiceURL="https://rawy.app/saml/acs/{config.workspace_id}">
    <saml:Issuer>{config.sp_entity_id}</saml:Issuer>
    <samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress" AllowCreate="true"/>
</samlp:AuthnRequest>"""
    
    # Deflate + Base64
    compressed = zlib.compress(saml_request_xml.encode('utf-8'))[2:-4]  # zlib header/footer kaldır
    return base64.b64encode(compressed).decode('utf-8')


def parse_saml_response(saml_response: str) -> dict:
    """SAML Assertion'ı parse et (basit implementasyon)"""
    
    try:
        # Base64 decode
        decoded = base64.b64decode(saml_response)
        
        # XML parse
        root = ET.fromstring(decoded)
        
        # Namespace map
        ns = {
            'saml': 'urn:oasis:names:tc:SAML:2.0:assertion',
            'samlp': 'urn:oasis:names:tc:SAML:2.0:protocol'
        }
        
        # Attribute'ları bul
        attributes = {}
        
        # NameID (email genelde)
        name_id = root.find('.//saml:NameID', ns)
        if name_id is not None:
            attributes['email'] = name_id.text
        
        # AttributeStatement
        attr_statement = root.find('.//saml:AttributeStatement', ns)
        if attr_statement is not None:
            for attr in attr_statement.findall('saml:Attribute', ns):
                name = attr.get('Name')
                value_elem = attr.find('saml:AttributeValue', ns)
                if value_elem is not None:
                    attributes[name] = value_elem.text
        
        return attributes
        
    except Exception as e:
        return {"error": str(e)}


def get_sp_metadata(config: SamlConfig) -> str:
    """Service Provider metadata XML'i oluştur"""
    
    metadata = f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="{config.sp_entity_id}">
    <md:SPSSODescriptor AuthnRequestsSigned="false" WantAssertionsSigned="true" protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>
        <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" Location="https://rawy.app/saml/acs/{config.workspace_id}" index="1"/>
    </md:SPSSODescriptor>
    <md:Organization>
        <md:OrganizationName xml:lang="en">Rawy</md:OrganizationName>
        <md:OrganizationDisplayName xml:lang="en">Rawy Voice OS</md:OrganizationDisplayName>
        <md:OrganizationURL xml:lang="en">https://rawy.app</md:OrganizationURL>
    </md:Organization>
</md:EntityDescriptor>"""
    
    return metadata


def provision_user(
    db: Session,
    workspace_id: int,
    email: str,
    name: str = None
) -> User:
    """SAML'den gelen kullanıcıyı provision et (varsa bul, yoksa oluştur)"""
    
    # Kullanıcı var mı kontrol et
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        # Yeni kullanıcı oluştur (SSO'dan geldiği için şifre yok)
        from app.security import pwd_context
        
        user = User(
            email=email,
            hashed_password=pwd_context.hash(secrets.token_urlsafe(32)),  # Rastgele şifre
            is_active=True,
            is_verified=True,  # SSO'dan geldiği için verified
            plan="starter"
        )
        db.add(user)
        db.flush()
    
    # Workspace'e üye yap
    existing_member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id
        )
        .first()
    )
    
    if not existing_member:
        member = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=user.id,
            role="member"
        )
        db.add(member)
    
    db.commit()
    db.refresh(user)
    
    return user

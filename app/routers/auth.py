from typing import Annotated

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import LoginBody, RefreshBody, Token, UserCreate, UserOut, UserProfilePatch
from app.security import get_password_hash, issue_token_pair, verify_password

router = APIRouter()


def _authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email.lower()).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya şifre hatalı",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Hesap devre dışı")
    return user


@router.post("/register", response_model=UserOut)
def register(data: UserCreate, db: Session = Depends(get_db)) -> User:
    if db.query(User).filter(User.email == data.email.lower()).first():
        raise HTTPException(status_code=400, detail="Bu e-posta zaten kayıtlı")

    trial_end = datetime.now(timezone.utc) + timedelta(days=settings.TRIAL_DAYS)
    user = User(
        email=data.email.lower(),
        hashed_password=get_password_hash(data.password),
        is_active=True,
        plan="starter",
        trial_ends_at=trial_end,
        timezone=data.timezone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(data: LoginBody, db: Session = Depends(get_db)) -> dict[str, str]:
    user = _authenticate_user(db, data.email, data.password)
    return issue_token_pair(user.id)


@router.post("/token", response_model=Token)
def login_oauth2_form(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """OAuth2 uyumlu form girişi (Swagger \"Authorize\" ve klasik OAuth istemcileri için)."""
    user = _authenticate_user(db, form_data.username, form_data.password)
    return issue_token_pair(user.id)


@router.post("/refresh", response_model=Token)
def refresh_tokens(data: RefreshBody, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        payload = jwt.decode(
            data.refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya süresi dolmuş yenileme jetonu",
        ) from None

    if payload.get("typ") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz yenileme jetonu",
        )

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="Geçersiz yenileme jetonu")

    try:
        user_id = int(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Geçersiz yenileme jetonu") from None

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı veya pasif")

    return issue_token_pair(user.id)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserOut)
def update_me(
    data: UserProfilePatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    try:
        ZoneInfo(data.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(400, "Geçersiz IANA saat dilimi (örn. Europe/Istanbul)") from None
    current_user.timezone = data.timezone
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user

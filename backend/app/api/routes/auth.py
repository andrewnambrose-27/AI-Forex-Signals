from datetime import datetime, timedelta, timezone

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.config import get_settings
from app.models.user import User
from app.schemas.auth import Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


def create_access_token(subject: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: DbSession) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email is already registered")

    user = User(email=payload.email, hashed_password=password_context.hash(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> Token:
    user = db.scalar(select(User).where(User.email == form.username))
    if not user or not password_context.verify(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    return Token(access_token=create_access_token(str(user.id)))

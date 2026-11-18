import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from config import settings
from database import get_db
from models import User, get_assigned_circles, is_circle_authorized

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

def get_token_from_request(request: Request, header_token: Optional[str] = Depends(oauth2_scheme)) -> Optional[str]:
    if header_token:
        return header_token
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        if cookie_token.startswith("Bearer "):
            return cookie_token[7:]
        return cookie_token
    return None

def get_current_user(token: Optional[str] = Depends(get_token_from_request), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username: str = payload.get("sub")
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is deactivated",
        )
    return user

def get_current_user_optional(token: Optional[str] = Depends(get_token_from_request), db: Session = Depends(get_db)) -> Optional[User]:
    if not token:
        return None
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        return None
    username: str = payload.get("sub")
    return db.query(User).filter(User.username == username, User.is_active == True).first()

def require_roles(allowed_roles: List[str]):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted for role '{current_user.role}'. Required: {allowed_roles}"
            )
        return current_user
    return role_checker

def get_current_actor(
    token_user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    """
    Returns the logged-in user from a valid JWT (Authorization: Bearer header or the
    access_token cookie). Identity headers such as x-username / x-user-role are NOT
    trusted. Anonymous requests are rejected with 401.
    """
    if not token_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_user


def expand_circles(circles) -> list[str]:
    """Upper-cases circles and treats CITY / BERHAMPUR CITY as the same circle."""
    out = []
    for c in circles or []:
        c_up = (c or "").strip().upper()
        if not c_up:
            continue
        group = ["CITY", "BERHAMPUR CITY"] if c_up in ("CITY", "BERHAMPUR CITY") else [c_up]
        for g in group:
            if g not in out:
                out.append(g)
    return out

def verify_write_permission(user: Optional[User], circle: Optional[str] = None):
    """
    Enforces RBAC write permission:
    - ADMIN: Full create/edit anywhere.
    - SUB_ADMIN:
        * circle must be authorized for user (via is_circle_authorized)
        * can_edit must be True
    - USER:
        * circle must be authorized for user (if circle specified)
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for operational actions."
        )

    if user.role == "ADMIN":
        return True
    
    if user.role == "SUB_ADMIN":
        if circle and not is_circle_authorized(user, circle):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unauthorized: You do not have permissions for circle: {circle}"
            )
        if not user.can_edit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="View-Only Sub-Admin account cannot make changes (can_edit is False)"
            )
        return True

    if user.role == "USER":
        if circle and not is_circle_authorized(user, circle):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unauthorized: You do not have permissions for circle: {circle}"
            )
        return True

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

def verify_team_permission(user: Optional[User], team_id: Optional[int]):
    """
    Enforces Team-level squad isolation:
    - ADMIN: Full access to any squad.
    - SUB_ADMIN: Can access any squad in their authorized circle(s).
    - USER: Restricted strictly to their assigned team_id.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required."
        )
    if user.role in ["ADMIN", "SUB_ADMIN"]:
        return True
    if user.role == "USER":
        if not user.team_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access Denied: Your account is not assigned to any specific squad. Contact your administrator."
            )
        if team_id is not None and user.team_id != team_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access Denied: You are only authorized to access and submit data for your assigned squad (Team ID: {user.team_id})."
            )
        return True
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


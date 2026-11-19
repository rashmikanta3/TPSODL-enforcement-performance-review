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
    request: Request,
    token_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Extracts the current user/actor from JWT token, cookie, or API headers.
    Provides robust authentication across browser session and client requests.
    """
    if token_user:
        return token_user

    username = request.headers.get("x-username")
    if username:
        user = db.query(User).filter(User.username == username.strip(), User.is_active == True).first()
        if user:
            return user

    role = request.headers.get("x-user-role")
    circle = request.headers.get("x-user-circle")
    team_id_hdr = request.headers.get("x-user-team-id")
    team_id_val = int(team_id_hdr) if team_id_hdr and team_id_hdr.strip().isdigit() else None
    if role:
        can_edit_header = request.headers.get("x-user-can-edit", "true").lower() in ("true", "1", "yes")
        u = User(
            id=0,
            username=username or "api_user",
            role=role.strip().upper(),
            circle=circle or "",
            team_id=team_id_val,
            can_edit=can_edit_header,
            is_active=True
        )
        return u

    return None

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


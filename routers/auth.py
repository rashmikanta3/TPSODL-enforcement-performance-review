from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models import User
from auth import create_access_token, get_current_actor
from config import settings

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    username: str
    old_password: str
    new_password: str

# Session cookie: not readable by JS (no frontend code reads document.cookie), HTTPS-only,
# not sent on cross-site POSTs, and expires together with the JWT inside it.
COOKIE_OPTS = dict(httponly=True, secure=True, samesite="lax", path="/")

@router.post("/login")
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    # Simple plain-text password verification
    user = db.query(User).filter(User.username == req.username, User.password == req.password).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")
    
    token = create_access_token(data={
        "sub": user.username,
        "role": user.role,
        "circle": user.circle or "",
        "team_id": user.team_id
    })
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **COOKIE_OPTS,
    )

    return {
        "success": True,
        "token": token,
        "username": user.username,
        "role": user.role,
        "circle": user.circle,
        "team_id": user.team_id,
        "team_name": user.team.name if user.team else None,
        "can_edit": user.can_edit
    }

@router.post("/logout")
def logout(response: Response):
    """Clears the session cookie (JS cannot clear it because it is HttpOnly)."""
    response.delete_cookie(key="access_token", **COOKIE_OPTS)
    return {"success": True}

@router.get("/me")
def get_me(current_user: User = Depends(get_current_actor)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "circle": current_user.circle,
        "team_id": current_user.team_id,
        "team_name": current_user.team.name if getattr(current_user, "team", None) else None,
        "can_edit": current_user.can_edit,
        "is_active": current_user.is_active
    }

@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_actor),
    db: Session = Depends(get_db)
):
    # A logged-in user may only change their own password.
    if req.username.strip() != current_user.username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only change your own password")
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if user.password != req.old_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password entered is incorrect")
    
    if not req.new_password or len(req.new_password.strip()) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 3 characters")
    
    user.password = req.new_password.strip()
    db.commit()
    return {"success": True, "message": "Password changed successfully"}

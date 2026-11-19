from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models import User
from auth import create_access_token, get_current_actor
from typing import Optional

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    username: str
    old_password: str
    new_password: str

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
    response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=False)

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

@router.get("/me")
def get_me(current_user: Optional[User] = Depends(get_current_actor)):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
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
def change_password(req: ChangePasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if user.password != req.old_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password entered is incorrect")
    
    if not req.new_password or len(req.new_password.strip()) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 3 characters")
    
    user.password = req.new_password.strip()
    db.commit()
    return {"success": True, "message": "Password changed successfully"}

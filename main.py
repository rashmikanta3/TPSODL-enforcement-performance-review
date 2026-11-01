import os
from contextlib import asynccontextmanager
from datetime import date
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from config import settings
from database import init_db, get_db, SessionLocal
from models import User, Team, Employee, VCRMaster
from auth import get_current_user_optional, get_token_from_request

# Import Routers
from routers.auth import router as auth_router
from routers.admin import router as admin_router
from routers.attendance import router as attendance_router
from routers.logbook import router as logbook_router
from routers.load_booking import router as load_booking_router
from routers.dc import router as dc_router
from routers.collection import router as collection_router
from routers.analytics import router as analytics_router
from routers.reports import router as reports_router
from routers.vcr import router as vcr_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception as e:
        print(f"Warning: init_db failed on startup: {e}")
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description="MIS & Enforcement Performance Tracking System TPSODL",
    version="2.0.0",
    lifespan=lifespan
)

# Static and Templates configuration
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Register API routers
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(attendance_router, prefix="/api/attendance", tags=["Attendance"])
app.include_router(logbook_router, prefix="/api/logbook", tags=["LogBook"])
app.include_router(load_booking_router, prefix="/api/load-booking", tags=["LoadBooking"])
app.include_router(dc_router, prefix="/api/dc", tags=["Disconnection"])
app.include_router(collection_router, prefix="/api/collection", tags=["Collection"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(reports_router, prefix="/api/reports", tags=["Reports"])
app.include_router(vcr_router, prefix="/api/vcr", tags=["VCR"])

# =========================================================================
# HTML UI Page Controllers
# =========================================================================
@app.get("/", response_class=RedirectResponse)
def index():
    return RedirectResponse(url="/dashboard")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"active_page": "dashboard"})

@app.get("/attendance", response_class=HTMLResponse)
def attendance_page(request: Request):
    return templates.TemplateResponse(request=request, name="attendance.html", context={"active_page": "attendance"})

@app.get("/logbook", response_class=HTMLResponse)
def logbook_page(request: Request):
    return templates.TemplateResponse(request=request, name="logbook.html", context={"active_page": "logbook"})

@app.get("/load-booking", response_class=HTMLResponse)
def load_booking_page(request: Request):
    return templates.TemplateResponse(request=request, name="load_booking.html", context={"active_page": "load_booking"})

@app.get("/dc", response_class=HTMLResponse)
def dc_page(request: Request):
    return templates.TemplateResponse(request=request, name="dc.html", context={"active_page": "dc"})

@app.get("/collection", response_class=HTMLResponse)
def collection_page(request: Request):
    return templates.TemplateResponse(request=request, name="collection.html", context={"active_page": "collection"})

@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    return templates.TemplateResponse(request=request, name="reports.html", context={"active_page": "reports"})

@app.get("/vcr-desk", response_class=HTMLResponse)
@app.get("/vcr", response_class=HTMLResponse)
def vcr_page(request: Request):
    return templates.TemplateResponse(request=request, name="vcr.html", context={"active_page": "vcr"})

@app.get("/admin-desk", response_class=HTMLResponse)
@app.get("/admin", response_class=HTMLResponse)
def admin_desk(request: Request):
    return templates.TemplateResponse(request=request, name="admin.html", context={"request": request, "active_page": "admin"})

@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    return templates.TemplateResponse(request=request, name="profile.html", context={"active_page": "profile"})

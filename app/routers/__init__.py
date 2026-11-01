import os, sys
# Forward imports from routers
from routers.auth import router as auth
from routers.admin import router as admin
from routers.attendance import router as attendance
from routers.logbook import router as logbook
from routers.load_booking import router as load_booking
from routers.dc import router as dc
from routers.collection import router as collection
from routers.analytics import router as analytics
from routers.reports import router as reports


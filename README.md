# TPSODL Enforcement & Squad Operations Portal

FastAPI + Jinja/Bootstrap portal for TPSODL enforcement squads (attendance, vehicle log,
load booking, disconnection, collection, VCR, reports, PVR).

## PVR module: Google Drive setup

PVR PDFs are stored in the owner's **personal Google Drive** using OAuth with a refresh
token. A service account is not used, because service accounts have no storage quota on
personal Drives and uploads fail with `storageQuotaExceeded`. The app uses the
`drive.file` scope, so it can only see the folders and files it creates itself
(`TPSODL_PVR/...`). Files are never shared publicly. Every view and download goes
through the backend after a permission check.

### 1. Google Cloud Console (one time)
1. Open <https://console.cloud.google.com/> and create (or pick) a project.
2. **APIs & Services → Library → "Google Drive API" → Enable.**
3. **APIs & Services → OAuth consent screen**:
   - User type: **External**. Fill in the app name and your email.
   - Scopes: add `.../auth/drive.file`.
   - **Publishing status: click "Publish app" so it shows "In production".**
     In "Testing" mode, refresh tokens expire after 7 days and PVR uploads stop working.
     For a personal app that only you authorize, you don't need Google verification.
     Just click through the "unverified app" warning when you authorize.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID →
   Application type "Desktop app"** → download the JSON (`client_secret_....json`).

### 2. Get the refresh token (on your laptop, not the VPS)
```bash
pip install google-auth-oauthlib
python scripts/gdrive_get_token.py path/to/client_secret.json
```
Sign in with the Google account that owns the 1 TB Drive and allow access. The script
prints the values to put in `.env`.

### 3. `.env` on the server
```env
GDRIVE_CLIENT_ID=...apps.googleusercontent.com
GDRIVE_CLIENT_SECRET=...
GDRIVE_REFRESH_TOKEN=...
GDRIVE_ROOT_FOLDER_NAME=TPSODL_PVR
# optional limits (defaults shown)
PVR_MAX_UPLOAD_MB=25
PVR_ZIP_MAX_DAYS=62
PVR_ZIP_MAX_FILES=1000
```
If the `GDRIVE_*` values are empty, the portal still runs normally. The PVR page then
shows "Google Drive not configured", and upload and download are disabled.

### Drive folder layout
```
TPSODL_PVR/2026/11-November/20-11-2026/Ramesh Sahu/PVR_20-11-2026_ASKA_TL045_Ramesh-Sahu.pdf
```
The app caches folder IDs in the `pvr_drive_folders` table. If you delete or rename
folders by hand in Drive, the app recreates them on the next upload.

### Redeploy
```bash
cd /home/ubuntu/enf_load
git pull
docker compose up -d --build
docker compose logs -f fastapi-web     # check startup
```

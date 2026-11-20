"""
One-time helper: get a Google Drive OAuth refresh token for YOUR personal Google account.

Run this on your laptop (it opens a browser), NOT on the VPS:

    pip install google-auth-oauthlib
    python scripts/gdrive_get_token.py path/to/client_secret.json

`client_secret.json` is the OAuth client of type "Desktop app" downloaded from
Google Cloud Console -> APIs & Services -> Credentials.

It prints GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET / GDRIVE_REFRESH_TOKEN lines to paste
into the server's .env. Keep them secret. Do not commit client_secret.json.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    secrets_path = sys.argv[1]

    flow = InstalledAppFlow.from_client_secrets_file(secrets_path, scopes=SCOPES)
    try:
        # Opens the browser; a temporary localhost server receives the redirect.
        # access_type=offline + prompt=consent guarantees a refresh token is returned.
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent",
                                      authorization_prompt_message="Opening browser to authorize Google Drive access: {url}")
    except Exception as e:  # e.g. no browser available
        print(f"Browser flow failed ({e}). Run this script on a machine with a web browser.")
        return 1

    if not creds.refresh_token:
        print("No refresh token returned. Remove the app's access at https://myaccount.google.com/permissions "
              "and run this script again.")
        return 1

    with open(secrets_path, encoding="utf-8") as f:
        info = json.load(f)
    client = info.get("installed") or info.get("web") or {}

    print("\nAdd these lines to the server's .env file:\n")
    print(f"GDRIVE_CLIENT_ID={client.get('client_id', creds.client_id)}")
    print(f"GDRIVE_CLIENT_SECRET={client.get('client_secret', creds.client_secret)}")
    print(f"GDRIVE_REFRESH_TOKEN={creds.refresh_token}")
    print("GDRIVE_ROOT_FOLDER_NAME=TPSODL_PVR\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

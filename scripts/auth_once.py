from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv
import json, os


load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
]

EMAIL = os.environ["USER_GOOGLE_EMAIL"]  # e.g. you@gmail.com
CRED_DIR = os.path.join(os.environ["APPDATA"], "workspace-mcp", "credentials")

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    },
    SCOPES,
)

creds = flow.run_local_server(port=0)  # port=0 picks a free port, avoids clash with uvicorn on 8000

os.makedirs(CRED_DIR, exist_ok=True)

# Save token as <email>.json — this is what workspace-mcp looks for
token_path = os.path.join(CRED_DIR, f"{EMAIL}.json")
with open(token_path, "w") as f:
    f.write(creds.to_json())

print(f"Done. Token saved to: {token_path}")
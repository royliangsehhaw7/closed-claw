from google_auth_oauthlib.flow import InstalledAppFlow

import json, os
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
]

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

creds = flow.run_local_server(port=8000)

# Save where workspace-mcp expects it
os.makedirs(r"C:\Users\liang\.google_workspace_mcp\credentials", exist_ok=True)
with open(r"C:\Users\liang\.google_workspace_mcp\credentials\token.json", "w") as f:
    f.write(creds.to_json())

print("Done. Token saved.")
"""
Run this script once to authenticate with Google Calendar.
It opens a browser window for the OAuth flow and saves the token to credentials/token.json.

Usage:
    python scripts/auth.py
"""
import os
import sys

# Allow imports from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv()

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main() -> None:
    secrets_path = os.getenv("GOOGLE_CLIENT_SECRETS_PATH", "credentials/client_secrets.json")
    token_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials/token.json")

    if not os.path.exists(secrets_path):
        print(f"Error: {secrets_path} not found.")
        print()
        print("Steps to fix:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Enable the Google Calendar API")
        print("  3. Create an OAuth 2.0 Client ID (type: Desktop app)")
        print(f"  4. Download the JSON and save it as: {secrets_path}")
        sys.exit(1)

    print("Opening browser for Google authorization...")
    flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
    creds = flow.run_local_server(port=8080)

    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    with open(token_path, "w") as f:
        f.write(creds.to_json())

    print(f"\nAuthentication successful! Token saved to: {token_path}")
    print("You can now start the bot with: python bot.py")


if __name__ == "__main__":
    main()

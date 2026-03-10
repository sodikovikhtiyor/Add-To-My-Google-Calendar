"""
NOTE: This standalone script is no longer the way to authenticate.

The bot now handles Google Calendar authentication directly via the /auth Telegram command,
using a web-based OAuth flow (google_auth_oauthlib.flow.Flow) that stores tokens
per-user in the SQLite database.

To authenticate:
  1. Start the bot: python bot.py
  2. Send /start to the bot in Telegram (register if needed)
  3. Send /auth to the bot — it will send you a Google authorization link
  4. Click the link, complete the OAuth consent screen
  5. You'll be redirected back and the bot will confirm the connection

Requirements for /auth to work:
  - GOOGLE_CLIENT_SECRETS_PATH: path to a Web Application OAuth 2.0 client secrets JSON
    (NOT Desktop app — must be "Web application" type from Google Cloud Console)
  - OAUTH_REDIRECT_URI: public HTTPS URL registered in Google Cloud Console,
    e.g. https://yourdomain.com/oauth/callback
  - The aiohttp callback server (web/oauth_server.py) must be reachable at that URL
"""

import sys

print(__doc__)
sys.exit(0)

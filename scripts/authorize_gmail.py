"""Authorize this Gmail account locally; save its refresh token in ignored .env."""

from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key
from google_auth_oauthlib.flow import InstalledAppFlow


REDIRECT_URI = "http://127.0.0.1:8765/"


def main() -> None:
    path = Path.cwd() / ".env"
    values = dotenv_values(path)
    address = values.get("GMAIL_ADDRESS")
    client_id = values.get("GOOGLE_CLIENT_ID")
    client_secret = values.get("GOOGLE_CLIENT_SECRET")
    if not all((address, client_id, client_secret)):
        raise SystemExit("Set GMAIL_ADDRESS, GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in local .env first.")

    flow = InstalledAppFlow.from_client_config(
        {"web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }},
        scopes=[
            "https://www.googleapis.com/auth/gmail.send",
            "openid", "email",
        ],
    )
    try:
        credentials = flow.run_local_server(
            host="127.0.0.1", port=8765, prompt="consent",
            access_type="offline", include_granted_scopes="true",
        )
        access_token = credentials.token
        refresh_token = credentials.refresh_token
    except Warning as warning:
        # Google may return a different scope set than the requested aliases.
        # Check the issued token rather than trusting the consent-screen label.
        token = getattr(warning, "token", {})
        access_token = token.get("access_token")
        refresh_token = token.get("refresh_token")
    if not refresh_token or not access_token:
        raise SystemExit("Google did not provide a refresh token; authorization was not saved.")
    try:
        token_info = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"access_token": access_token},
            timeout=10.0,
        )
        token_info.raise_for_status()
        if "https://www.googleapis.com/auth/gmail.send" not in (
            token_info.json().get("scope", "").split()
        ):
            raise SystemExit(
                "Google did not grant gmail.send to this token; no token was saved."
            )
        response = httpx.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        raise SystemExit("Could not verify the authorized Gmail account; token was not saved.") from None
    if response.json().get("email", "").lower() != address.lower():
        raise SystemExit("Authorized account does not match GMAIL_ADDRESS; token was not saved.")
    set_key(path, "GOOGLE_REFRESH_TOKEN", refresh_token, quote_mode="always")
    print("Saved a Gmail refresh token in Git-ignored .env. Do not share or commit it.")


if __name__ == "__main__":
    main()

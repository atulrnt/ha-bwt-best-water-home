from __future__ import annotations

import base64
import hashlib
import json
import secrets
import string
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request
from urllib.parse import parse_qs, urlencode, urlparse


class AuthRedirectError(ValueError):
    """The pasted OAuth redirect/code cannot be used."""


@dataclass(frozen=True)
class ManualAuthSession:
    """State Home Assistant must keep between auth URL generation and pasted redirect."""

    authorization_url: str
    state: str
    code_verifier: str


def generate_code_verifier(length: int = 64) -> str:
    """Generate an RFC 7636 PKCE code verifier."""

    if not 43 <= length <= 128:
        raise ValueError("PKCE code verifier length must be between 43 and 128 characters")
    alphabet = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def code_challenge_s256(code_verifier: str) -> str:
    """Return the base64url SHA-256 PKCE challenge for a verifier."""

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorization_url(
    *,
    authorize_url: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scope: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> str:
    """Build the BWT/AIDU app-style authorization URL.

    The redirect URI is passed through exactly as supplied except for normal URL
    query encoding. This matters because the provider appears to strictly match
    the mobile app redirect URI.
    """

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if scope:
        params["scope"] = scope
    if extra_params:
        params.update(extra_params)
    separator = "&" if "?" in authorize_url else "?"
    return f"{authorize_url}{separator}{urlencode(params)}"


def create_manual_auth_session(
    *,
    authorize_url: str,
    client_id: str,
    redirect_uri: str,
    scope: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> ManualAuthSession:
    """Create a manual browser auth session for the HA config flow."""

    state = secrets.token_urlsafe(32)
    verifier = generate_code_verifier()
    return ManualAuthSession(
        authorization_url=build_authorization_url(
            authorize_url=authorize_url,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge_s256(verifier),
            scope=scope,
            extra_params=extra_params,
        ),
        state=state,
        code_verifier=verifier,
    )


def create_bwt_manual_auth_session() -> ManualAuthSession:
    """Create a manual browser auth session using confirmed BWT app OAuth values."""

    from .const import BWT_AUTHORIZATION_URL, BWT_CLIENT_ID, BWT_REDIRECT_URI, BWT_SCOPE

    return create_manual_auth_session(
        authorize_url=BWT_AUTHORIZATION_URL,
        client_id=BWT_CLIENT_ID,
        redirect_uri=BWT_REDIRECT_URI,
        scope=BWT_SCOPE,
    )


def extract_authorization_code(pasted_value: str, *, expected_state: str | None = None) -> str:
    """Extract an OAuth authorization code from a pasted redirect URL or raw code.

    Accepting the raw code is useful when a browser or mobile OS strips the
    custom-scheme URL but exposes/copies only the code value.
    """

    value = pasted_value.strip()
    if not value:
        raise AuthRedirectError("Paste the redirected URL or authorization code.")

    parsed = urlparse(value)
    if not parsed.scheme and "?" not in value and "=" not in value:
        return value

    query = parse_qs(parsed.query, keep_blank_values=True)
    if "error" in query:
        error = query["error"][0] or "OAuth error"
        description = (query.get("error_description") or [""])[0]
        raise AuthRedirectError(f"BWT authorization failed: {error} {description}".strip())

    state = (query.get("state") or [None])[0]
    if expected_state is not None and state != expected_state:
        raise AuthRedirectError("The pasted redirect state does not match this Home Assistant auth session.")

    code = (query.get("code") or [None])[0]
    if not code:
        raise AuthRedirectError("The pasted value does not contain an authorization code.")
    return code


def build_token_exchange_form(
    *,
    client_id: str,
    redirect_uri: str,
    code: str,
    code_verifier: str,
    extra_params: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build an OAuth authorization-code + PKCE token exchange form."""

    form = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code": code,
        "code_verifier": code_verifier,
    }
    if extra_params:
        form.update(extra_params)
    return form


def exchange_token_sync(token_url: str, form: dict[str, str]) -> dict[str, Any]:
    """Exchange an OAuth form for a token response using stdlib urllib."""

    req = request.Request(
        token_url,
        data=parse.urlencode(form).encode(),
        headers={"content-type": "application/x-www-form-urlencoded", "accept": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"message": body}
        raise AuthRedirectError(f"BWT token exchange failed with HTTP {exc.code}: {parsed}") from exc


def exchange_bwt_authorization_code_sync(*, code: str, code_verifier: str) -> dict[str, Any]:
    """Exchange a BWT authorization code for OAuth tokens."""

    from .const import BWT_CLIENT_ID, BWT_REDIRECT_URI, BWT_TOKEN_URL

    return exchange_token_sync(
        BWT_TOKEN_URL,
        build_token_exchange_form(
            client_id=BWT_CLIENT_ID,
            redirect_uri=BWT_REDIRECT_URI,
            code=code,
            code_verifier=code_verifier,
        ),
    )


def extract_access_token(token_response: dict[str, Any]) -> str:
    """Extract the access token from an OAuth token response."""

    token = token_response.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise AuthRedirectError("BWT token response did not include an access token.")
    return token.strip()

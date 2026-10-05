"""OAuth sign-in for the HTTP mode (single owner, password login).

claude.ai custom connectors speak OAuth 2.1: they register themselves, send you to a login page on
this server, and then receive a token. This module implements the authorization-server side with
the MCP SDK's provider interface. State is kept in memory, so restarting the server signs everyone
out.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import secrets
import time
from collections import deque
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

MIN_PASSWORD_LENGTH = 8
ACCESS_TOKEN_TTL = 3600            # 1 hour
REFRESH_TOKEN_TTL = 30 * 24 * 3600  # 30 days
AUTH_CODE_TTL = 300                # 5 minutes
PENDING_TTL = 600                  # login page must be used within 10 minutes
MAX_FAILURES = 10                  # failed password attempts allowed per window
FAILURE_WINDOW = 600               # seconds

DEFAULT_REDIRECT_HOSTS = ("claude.ai", "claude.com", "localhost", "127.0.0.1")
_LOOPBACK = ("localhost", "127.0.0.1", "::1")


def _redirect_host_allowed(uri: str, allowed: Iterable[str]) -> bool:
    host = (urlparse(uri).hostname or "").lower()
    for entry in allowed:
        entry = entry.lower()
        if host == entry or (entry not in _LOOPBACK and host.endswith("." + entry)):
            return True
    return False


class PasswordAuthProvider:
    """In-memory OAuth authorization server protected by one owner password."""

    def __init__(self, password: str, public_url: str,
                 allowed_redirect_hosts: Iterable[str] = DEFAULT_REDIRECT_HOSTS):
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"The password must be at least {MIN_PASSWORD_LENGTH} characters.")
        # Compare digests so the comparison time doesn't depend on the password length.
        self._password_digest = hashlib.sha256(password.encode("utf-8")).digest()
        self.public_url = public_url.rstrip("/")
        self.allowed_redirect_hosts = tuple(allowed_redirect_hosts)

        self._clients: Dict[str, OAuthClientInformationFull] = {}
        self._pending: Dict[str, Tuple[OAuthClientInformationFull, AuthorizationParams, float]] = {}
        self._codes: Dict[str, AuthorizationCode] = {}
        self._access: Dict[str, AccessToken] = {}
        self._refresh: Dict[str, RefreshToken] = {}
        self._failures: deque = deque()

    # ----- clients -----
    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = [str(u) for u in (client_info.redirect_uris or [])]
        if not uris:
            raise RegistrationError("invalid_redirect_uri", "At least one redirect URI is required.")
        for uri in uris:
            if not _redirect_host_allowed(uri, self.allowed_redirect_hosts):
                raise RegistrationError(
                    "invalid_redirect_uri",
                    f"Redirect host not allowed by this server: {urlparse(uri).hostname}")
        if client_info.client_id:
            self._clients[client_info.client_id] = client_info

    # ----- authorization (login page) -----
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        self._prune()
        pending_id = secrets.token_urlsafe(24)
        self._pending[pending_id] = (client, params, time.time() + PENDING_TTL)
        return f"{self.public_url}/login?p={pending_id}"

    def pending_info(self, pending_id: str) -> Optional[Tuple[str, str]]:
        """(client name, redirect host) for the login page, or None if expired/unknown."""
        self._prune()
        entry = self._pending.get(pending_id)
        if not entry:
            return None
        client, params, _ = entry
        return (client.client_name or "an application", urlparse(str(params.redirect_uri)).hostname or "")

    def locked_out(self) -> bool:
        now = time.time()
        while self._failures and now - self._failures[0] > FAILURE_WINDOW:
            self._failures.popleft()
        return len(self._failures) >= MAX_FAILURES

    def complete_login(self, pending_id: str, password: str) -> Optional[str]:
        """Check the password; return the URL to send the browser back to the client, or None."""
        self._prune()
        entry = self._pending.get(pending_id)
        if not entry:
            return None
        digest = hashlib.sha256(password.encode("utf-8")).digest()
        if not hmac.compare_digest(digest, self._password_digest):
            self._failures.append(time.time())
            return None
        client, params, _ = self._pending.pop(pending_id)
        code = secrets.token_urlsafe(32)
        self._codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + AUTH_CODE_TTL,
            client_id=client.client_id or "",
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject="owner",
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    # ----- tokens -----
    async def load_authorization_code(self, client: OAuthClientInformationFull,
                                      authorization_code: str) -> Optional[AuthorizationCode]:
        code = self._codes.get(authorization_code)
        if code and code.client_id == client.client_id and code.expires_at > time.time():
            return code
        return None

    async def exchange_authorization_code(self, client: OAuthClientInformationFull,
                                          authorization_code: AuthorizationCode) -> OAuthToken:
        # Codes are single use.
        if self._codes.pop(authorization_code.code, None) is None:
            raise TokenError("invalid_grant", "Authorization code already used or expired.")
        return self._issue(client.client_id or "", authorization_code.scopes,
                           authorization_code.resource, authorization_code.subject)

    async def load_refresh_token(self, client: OAuthClientInformationFull,
                                 refresh_token: str) -> Optional[RefreshToken]:
        token = self._refresh.get(refresh_token)
        if token and token.client_id == client.client_id and (
                token.expires_at is None or token.expires_at > time.time()):
            return token
        return None

    async def exchange_refresh_token(self, client: OAuthClientInformationFull,
                                     refresh_token: RefreshToken, scopes: list) -> OAuthToken:
        self._refresh.pop(refresh_token.token, None)  # rotate
        return self._issue(client.client_id or "", scopes or refresh_token.scopes,
                           refresh_token.resource, refresh_token.subject)

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        entry = self._access.get(token)
        if entry and (entry.expires_at is None or entry.expires_at > time.time()):
            return entry
        self._access.pop(token, None)
        return None

    async def revoke_token(self, token) -> None:
        self._access.pop(getattr(token, "token", ""), None)
        self._refresh.pop(getattr(token, "token", ""), None)

    def _issue(self, client_id: str, scopes: list, resource: Optional[str],
               subject: Optional[str]) -> OAuthToken:
        now = int(time.time())
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        self._access[access] = AccessToken(
            token=access, client_id=client_id, scopes=scopes,
            expires_at=now + ACCESS_TOKEN_TTL, resource=resource, subject=subject)
        self._refresh[refresh] = RefreshToken(
            token=refresh, client_id=client_id, scopes=scopes,
            expires_at=now + REFRESH_TOKEN_TTL, resource=resource, subject=subject)
        return OAuthToken(access_token=access, token_type="Bearer", expires_in=ACCESS_TOKEN_TTL,
                          scope=" ".join(scopes) if scopes else None, refresh_token=refresh)

    def _prune(self) -> None:
        now = time.time()
        for key in [k for k, v in self._pending.items() if v[2] < now]:
            del self._pending[key]
        for key in [k for k, v in self._codes.items() if v.expires_at < now]:
            del self._codes[key]


# ----- login page -----
_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in - CapCut MCP</title>
<style>
body{{font-family:system-ui,sans-serif;background:#f5f5f7;margin:0;display:flex;min-height:100vh;
align-items:center;justify-content:center}}
main{{background:#fff;padding:2rem;border-radius:12px;max-width:380px;width:100%;
box-shadow:0 2px 12px rgba(0,0,0,.1);margin:1rem}}
h1{{font-size:1.25rem;margin:0 0 .75rem}} p{{color:#444;line-height:1.4}}
input{{width:100%;box-sizing:border-box;padding:.6rem;font-size:1rem;margin:.5rem 0 1rem}}
button{{width:100%;padding:.7rem;font-size:1rem;border:0;border-radius:8px;background:#111;color:#fff}}
.err{{color:#b00020}}
</style></head><body><main>
<h1>Sign in to CapCut MCP</h1>
{body}
</main></body></html>"""


def login_page(pending_id: str, client_name: str, redirect_host: str, error: str = "") -> str:
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    body = (
        f"<p><b>{html.escape(client_name)}</b> (redirecting to <b>{html.escape(redirect_host)}</b>) "
        "wants to edit CapCut drafts on this computer. Only continue if you started this.</p>"
        f"{err}"
        '<form method="post" action="/login">'
        f'<input type="hidden" name="p" value="{html.escape(pending_id)}">'
        '<label>Password<input type="password" name="password" autofocus required></label>'
        "<button type=\"submit\">Sign in</button></form>"
    )
    return _PAGE.format(body=body)


def error_page(message: str) -> str:
    return _PAGE.format(body=f"<p class=\"err\">{html.escape(message)}</p>")


def parse_form(body: bytes) -> Dict[str, str]:
    return {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True).items()}

import asyncio
import time

import pytest
from mcp.server.auth.provider import AuthorizationParams, RegistrationError, TokenError
from mcp.shared.auth import OAuthClientInformationFull

from capcut_mcp import auth
from capcut_mcp.auth import PasswordAuthProvider

PUBLIC = "https://example.trycloudflare.com"


def _client(uri="https://claude.ai/api/mcp/auth_callback", cid="cid"):
    return OAuthClientInformationFull(client_id=cid, client_secret="s", client_name="Claude",
                                      redirect_uris=[uri], token_endpoint_auth_method="client_secret_post")


def _params(uri="https://claude.ai/api/mcp/auth_callback"):
    return AuthorizationParams(state="st", scopes=None, code_challenge="c" * 43, redirect_uri=uri,
                               redirect_uri_provided_explicitly=True)


def _login_url(provider, client):
    return asyncio.run(provider.authorize(client, _params(str(client.redirect_uris[0]))))


def test_rejects_short_password():
    with pytest.raises(ValueError):
        PasswordAuthProvider("short", PUBLIC)


@pytest.mark.parametrize("uri,allowed", [
    ("https://claude.ai/api/mcp/auth_callback", True),
    ("https://sub.claude.com/cb", True),
    ("http://localhost:3000/cb", True),
    ("https://evil.example.com/cb", False),
    ("https://claude.ai.evil.com/cb", False),
    ("https://notclaude.ai/cb", False),
])
def test_redirect_host_allowlist(uri, allowed):
    provider = PasswordAuthProvider("correct-horse", PUBLIC)
    if allowed:
        asyncio.run(provider.register_client(_client(uri)))
    else:
        with pytest.raises(RegistrationError):
            asyncio.run(provider.register_client(_client(uri)))


def test_login_issues_single_use_code_then_tokens():
    provider = PasswordAuthProvider("correct-horse", PUBLIC)
    client = _client()
    asyncio.run(provider.register_client(client))
    pid = _login_url(provider, client).split("p=")[1]

    assert provider.complete_login(pid, "wrong") is None
    redirect = provider.complete_login(pid, "correct-horse")
    assert redirect.startswith("https://claude.ai/api/mcp/auth_callback?") and "code=" in redirect
    assert provider.complete_login(pid, "correct-horse") is None  # login link is single use

    code = redirect.split("code=")[1].split("&")[0]
    stored = asyncio.run(provider.load_authorization_code(client, code))
    token = asyncio.run(provider.exchange_authorization_code(client, stored))
    assert asyncio.run(provider.load_access_token(token.access_token)) is not None
    with pytest.raises(TokenError):
        asyncio.run(provider.exchange_authorization_code(client, stored))  # code can't be replayed

    old_refresh = asyncio.run(provider.load_refresh_token(client, token.refresh_token))
    new = asyncio.run(provider.exchange_refresh_token(client, old_refresh, []))
    assert new.access_token != token.access_token
    assert asyncio.run(provider.load_refresh_token(client, token.refresh_token)) is None  # rotated


def test_other_clients_cannot_use_a_code():
    provider = PasswordAuthProvider("correct-horse", PUBLIC)
    a, b = _client(cid="a"), _client(cid="b")
    asyncio.run(provider.register_client(a))
    asyncio.run(provider.register_client(b))
    redirect = provider.complete_login(_login_url(provider, a).split("p=")[1], "correct-horse")
    code = redirect.split("code=")[1].split("&")[0]
    assert asyncio.run(provider.load_authorization_code(b, code)) is None


def test_lockout_after_repeated_failures():
    provider = PasswordAuthProvider("correct-horse", PUBLIC)
    client = _client()
    asyncio.run(provider.register_client(client))
    pid = _login_url(provider, client).split("p=")[1]
    assert not provider.locked_out()
    for _ in range(auth.MAX_FAILURES):
        provider.complete_login(pid, "nope")
    assert provider.locked_out()


def test_unknown_access_token():
    provider = PasswordAuthProvider("correct-horse", PUBLIC)
    assert asyncio.run(provider.load_access_token("nonsense")) is None


def test_login_page_escapes_html():
    page = auth.login_page("pid", "<script>alert(1)</script>", "x\"><b>")
    assert "<script>alert" not in page and "&lt;script&gt;" in page

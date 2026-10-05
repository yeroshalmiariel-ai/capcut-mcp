"""MCP stdio server exposing CapCut draft editing as tools."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore
    from mcp.server.fastmcp.exceptions import ToolError  # type: ignore

from .core import CapCutError, DraftManager

INSTRUCTIONS = """\
Builds CapCut draft projects on disk. CapCut has no public API, so this edits
draft files; the user must reopen/refresh CapCut to see the result.

Typical flow: create_draft -> add_track (one per layer, background first) ->
add_video / add_audio / add_text / import_srt -> optional add_transition,
add_animation, add_fade, add_keyframe, add_filter -> save_draft.
All times are in seconds. Close the draft in CapCut before overwriting it.
Effect names (filters, transitions, animations, fonts) come from list_effects.
"""

TOOLS: list = []


def _tool(fn):
    """Collect a tool function; each server instance registers all of them."""
    TOOLS.append(fn)
    return fn


def new_server(**kwargs):
    """Create a server with every tool registered (kwargs: auth settings/provider)."""
    server = _Server("capcut", instructions=INSTRUCTIONS, **kwargs)
    for fn in TOOLS:
        server.tool()(fn)
    return server


_manager: Optional[DraftManager] = None


def manager() -> DraftManager:
    global _manager
    if _manager is None:
        _manager = DraftManager()
    return _manager


def _run(fn, *args, **kwargs) -> str:
    """Call a manager method and return JSON; surface CapCutError as a clear message."""
    try:
        result = fn(*args, **kwargs)
    except CapCutError as exc:
        # ToolError is shown to the client verbatim; other exceptions are masked.
        raise ToolError(str(exc)) from None
    return json.dumps(result, ensure_ascii=False, indent=2)


@_tool
def list_drafts() -> str:
    """List the draft projects in the CapCut drafts folder."""
    return _run(lambda: {"drafts_dir": manager().drafts_dir, "drafts": manager().list_drafts()})


@_tool
def create_draft(name: str, width: int = 1920, height: int = 1080, fps: int = 30,
                 replace: bool = False) -> str:
    """Create a new draft and open it for editing. replace=true deletes an existing draft of the same name."""
    return _run(manager().create_draft, name, width, height, fps, replace)


@_tool
def add_track(draft: str, track_type: str, track_name: str, mute: bool = False) -> str:
    """Add a track. track_type: video, audio, text, effect, filter or sticker. Later tracks sit on top."""
    return _run(manager().add_track, draft, track_type, track_name, mute)


@_tool
def add_video(draft: str, track: str, path: str, start: float, duration: float,
              source_start: Optional[float] = None, speed: Optional[float] = None,
              volume: float = 1.0, opacity: float = 1.0, scale: float = 1.0,
              x: float = 0.0, y: float = 0.0, rotation: float = 0.0) -> str:
    """Add a video clip or still image at `start` for `duration` seconds.
    x/y are offsets in half-canvas units; rotation is in degrees. Returns a segment_id."""
    return _run(manager().add_video, draft, track, path, start, duration,
                source_start=source_start, speed=speed, volume=volume,
                opacity=opacity, scale=scale, x=x, y=y, rotation=rotation)


@_tool
def add_audio(draft: str, track: str, path: str, start: float, duration: float,
              source_start: Optional[float] = None, volume: float = 1.0,
              fade_in: float = 0.0, fade_out: float = 0.0) -> str:
    """Add an audio clip. Returns a segment_id."""
    return _run(manager().add_audio, draft, track, path, start, duration,
                source_start=source_start, volume=volume, fade_in=fade_in, fade_out=fade_out)


@_tool
def add_text(draft: str, track: str, text: str, start: float, duration: float,
             font: Optional[str] = None, size: float = 8.0, color: str = "#FFFFFF",
             x: float = 0.0, y: float = -0.8, bold: bool = False, italic: bool = False) -> str:
    """Add a text overlay. color is a hex string; y=-0.8 is near the bottom. Returns a segment_id."""
    return _run(manager().add_text, draft, track, text, start, duration, font=font,
                size=size, color=color, x=x, y=y, bold=bold, italic=italic)


@_tool
def import_srt(draft: str, track: str, srt_path: str, time_offset: float = 0.0) -> str:
    """Import an .srt subtitle file as text segments on a (new) text track."""
    return _run(manager().import_srt, draft, track, srt_path, time_offset)


@_tool
def add_filter(draft: str, track: str, filter_name: str, start: float, duration: float,
               intensity: float = 100.0) -> str:
    """Add a filter over a time range on a filter track (intensity 0-100)."""
    return _run(manager().add_filter, draft, track, filter_name, start, duration, intensity)


@_tool
def add_transition(draft: str, segment_id: str, transition: str,
                   duration: Optional[float] = None) -> str:
    """Add a transition after a video segment (it joins this clip to the next one on the track)."""
    return _run(manager().add_transition, draft, segment_id, transition, duration)


@_tool
def add_animation(draft: str, segment_id: str, catalog: str, animation: str,
                  duration: Optional[float] = None) -> str:
    """Add an animation. catalog: intro, outro, group_animation (video) or text_intro, text_outro, text_loop_anim (text)."""
    return _run(manager().add_animation, draft, segment_id, catalog, animation, duration)


@_tool
def add_fade(draft: str, segment_id: str, fade_in: float = 0.0, fade_out: float = 0.0) -> str:
    """Add an audio fade-in/out (seconds) to an audio or video segment."""
    return _run(manager().add_fade, draft, segment_id, fade_in, fade_out)


@_tool
def add_keyframe(draft: str, segment_id: str, property: str, time_offset: float,
                 value: float) -> str:
    """Add a keyframe at `time_offset` seconds into the segment. See KeyframeProperty names (e.g. position_x, scale_x, alpha, rotation, volume)."""
    return _run(manager().add_keyframe, draft, segment_id, property, time_offset, value)


@_tool
def list_effects(catalog: str, query: str = "", limit: int = 50) -> str:
    """Browse built-in effect names. catalog: filter, transition, intro, outro, group_animation, mask, font, video_scene_effect, video_character_effect, text_intro, text_outro, text_loop_anim."""
    return _run(manager().list_effects, catalog, query, limit)


@_tool
def describe_draft(draft: str) -> str:
    """Summarize an open draft: size, duration, tracks and segment ids."""
    return _run(manager().describe, draft)


@_tool
def save_draft(draft: str) -> str:
    """Write the draft to disk so CapCut can open it. Close the draft in CapCut first."""
    return _run(manager().save, draft)


mcp = new_server()

MIN_SECRET_LENGTH = 16


def build_http_app(secret: str):
    """ASGI app serving the MCP endpoint at /<secret>/mcp (everything else is a 404).

    The secret in the path is the only access control, so it must be long and random.
    """
    from starlette.applications import Starlette
    from starlette.routing import Mount

    if len(secret) < MIN_SECRET_LENGTH or "/" in secret:
        raise ValueError(
            f"The secret must be at least {MIN_SECRET_LENGTH} characters and contain no '/'.")

    try:  # mcp >= 2.0
        from mcp.server.transport_security import TransportSecuritySettings

        # The default host check only allows localhost, which would reject tunnel hostnames.
        inner = mcp.streamable_http_app(
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    except TypeError:  # mcp 1.x: configured through settings
        from mcp.server.transport_security import TransportSecuritySettings

        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False)
        inner = mcp.streamable_http_app()

    return Starlette(
        routes=[Mount(f"/{secret}", app=inner)],
        lifespan=inner.router.lifespan_context,
    )


LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def build_oauth_app(public_url: str, password: str, allowed_redirect_hosts=None):
    """ASGI app with OAuth sign-in: clients are sent to a password page before getting a token.

    public_url is the address clients reach this server at (for example your tunnel's https URL);
    the MCP endpoint is <public_url>/mcp.
    """
    import asyncio

    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, RedirectResponse

    from .auth import DEFAULT_REDIRECT_HOSTS, PasswordAuthProvider, error_page, login_page, parse_form

    public_url = public_url.rstrip("/")
    provider = PasswordAuthProvider(
        password, public_url, allowed_redirect_hosts or DEFAULT_REDIRECT_HOSTS)
    server = new_server(
        auth=AuthSettings(
            issuer_url=public_url,
            resource_server_url=f"{public_url}/mcp",
            client_registration_options=ClientRegistrationOptions(enabled=True),
            revocation_options=RevocationOptions(enabled=True),
            validate_token_resource=False,
        ),
        auth_server_provider=provider,
    )
    headers = {"Cache-Control": "no-store", "X-Frame-Options": "DENY",
               "Referrer-Policy": "no-referrer",
               "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
                                          "frame-ancestors 'none'"}

    def page(markup: str, status: int = 200) -> HTMLResponse:
        return HTMLResponse(markup, status_code=status, headers=headers)

    @server.custom_route("/login", methods=["GET", "POST"])
    async def login(request: Request):
        if request.method == "GET":
            pending_id = request.query_params.get("p", "")
            info = provider.pending_info(pending_id)
            if info is None:
                return page(error_page("This sign-in link has expired. Start again from the app."), 400)
            return page(login_page(pending_id, *info))

        if provider.locked_out():
            return page(error_page("Too many failed attempts. Try again in a few minutes."), 429)
        body = await request.body()
        if len(body) > 4096:
            return page(error_page("Request too large."), 413)
        form = parse_form(body)
        pending_id = form.get("p", "")
        redirect_to = provider.complete_login(pending_id, form.get("password", ""))
        if redirect_to is not None:
            return RedirectResponse(redirect_to, status_code=303, headers=headers)
        info = provider.pending_info(pending_id)
        if info is None:
            return page(error_page("This sign-in link has expired. Start again from the app."), 400)
        await asyncio.sleep(1)  # slow down guessing
        return page(login_page(pending_id, *info, error="Wrong password."), 401)

    inner = server.streamable_http_app(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    return inner


def build_local_app():
    """ASGI app serving /mcp with no secret, for use on this computer only.

    The SDK's default host check stays on, so only requests addressed to localhost are
    accepted. A tunnel pointing at this server will be rejected unless it rewrites the
    Host header, so do not tunnel this mode.
    """
    return mcp.streamable_http_app()


def main(argv: Optional[list] = None) -> None:
    import argparse
    import os
    import secrets
    import sys

    parser = argparse.ArgumentParser(
        prog="capcut-mcp", description="MCP server for building CapCut draft projects.")
    parser.add_argument("--http", action="store_true",
                        help="serve over HTTP instead of stdio (for remote connectors via a tunnel)")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default 8000)")
    parser.add_argument("--secret", default=os.environ.get("CAPCUT_MCP_SECRET"),
                        help="secret path segment protecting the URL "
                             "(default: $CAPCUT_MCP_SECRET, or a random one is generated)")
    parser.add_argument("--no-secret", action="store_true",
                        help="HTTP mode without a secret, reachable from this computer only "
                             "(binds to localhost; do not put a tunnel in front of it)")
    parser.add_argument("--public-url", default=os.environ.get("CAPCUT_MCP_PUBLIC_URL"),
                        help="sign-in mode: the address clients reach this server at, e.g. your "
                             "tunnel's https URL. Enables OAuth with a password login page")
    parser.add_argument("--password", default=os.environ.get("CAPCUT_MCP_PASSWORD"),
                        help="sign-in password (default: $CAPCUT_MCP_PASSWORD, or one is generated)")
    parser.add_argument("--allow-redirect-host", action="append", default=[],
                        help="extra host clients may redirect back to after sign-in "
                             "(claude.ai, claude.com and localhost are always allowed)")
    args = parser.parse_args(argv)

    if args.no_secret and not args.http:
        parser.error("--no-secret only applies together with --http")
    if not args.http:
        mcp.run(transport="stdio")
        return

    import uvicorn

    if args.no_secret:
        if args.host not in LOOPBACK_HOSTS:
            parser.error("--no-secret only works with a localhost --host (127.0.0.1, localhost or ::1)")
        if args.secret:
            parser.error("--no-secret cannot be combined with --secret / CAPCUT_MCP_SECRET")
        print(f"capcut-mcp (local only) listening on http://{args.host}:{args.port}/mcp",
              file=sys.stderr)
        print("Reachable from this computer only. Don't expose it with a tunnel.", file=sys.stderr)
        uvicorn.run(build_local_app(), host=args.host, port=args.port, log_level="warning")
        return

    if args.public_url:
        if args.no_secret or args.secret:
            parser.error("--public-url (sign-in mode) can't be combined with --no-secret or --secret")
        from .auth import DEFAULT_REDIRECT_HOSTS

        password = args.password
        generated_pw = password is None
        if generated_pw:
            password = secrets.token_urlsafe(12)
        try:
            app = build_oauth_app(args.public_url, password,
                                  DEFAULT_REDIRECT_HOSTS + tuple(args.allow_redirect_host))
        except ValueError as exc:
            parser.error(str(exc))
        print(f"capcut-mcp (sign-in) listening on http://{args.host}:{args.port}", file=sys.stderr)
        print(f"Connector URL: {args.public_url.rstrip('/')}/mcp", file=sys.stderr)
        if generated_pw:
            print(f"Sign-in password (generated for this run): {password}", file=sys.stderr)
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
        return

    secret = args.secret
    generated = secret is None
    if generated:
        secret = secrets.token_urlsafe(32)
    try:
        app = build_http_app(secret)
    except ValueError as exc:
        parser.error(str(exc))

    print(f"capcut-mcp listening on http://{args.host}:{args.port}/{secret}/mcp", file=sys.stderr)
    print("Anyone with this URL can create and edit drafts on this computer. Keep it private.",
          file=sys.stderr)
    if generated:
        print("This secret was generated for this run; set CAPCUT_MCP_SECRET to keep the same "
              "URL across restarts.", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

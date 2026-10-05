# capcut-mcp

An [MCP](https://modelcontextprotocol.io) server that lets Claude (or any MCP client) build CapCut
projects: video/image clips, audio, text, SRT subtitles, transitions, animations, filters and keyframes.

> **CapCut has no public API.** This server does not control the CapCut app. It writes *draft
> projects* to disk (via [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)), which you
> then open in CapCut. Not affiliated with ByteDance or CapCut.

## Install

```bash
git clone https://github.com/yeroshalmiariel-ai/capcut-mcp
cd capcut-mcp
pip install -e .
```

Requires Python 3.9+. If `pip install pyJianYingDraft` fails on your platform, install it from
source: `pip install git+https://github.com/GuanYixuan/pyJianYingDraft.git`.

## Configure

Point the server at your CapCut drafts folder with `CAPCUT_DRAFTS_DIR` (it also tries the default
location on Windows and macOS):

| OS | Default drafts folder |
|----|-----------------------|
| Windows | `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft` |
| macOS | `~/Movies/CapCut/User Data/Projects/com.lveditor.draft` |

**Claude Code**

```bash
claude mcp add capcut -e CAPCUT_DRAFTS_DIR="/path/to/com.lveditor.draft" -- capcut-mcp
```

**Claude Desktop / other clients** — see [`mcp.json.example`](mcp.json.example).

## Local URL (no secret)

For a client on the same computer that wants a URL instead of launching a subprocess (for example
Claude Code), run the server in local-only mode:

```bash
capcut-mcp --http --no-secret --port 8000
claude mcp add --transport http capcut http://127.0.0.1:8000/mcp
```

This mode only accepts connections from your own computer and only requests addressed to
`localhost`. It refuses to start on any other `--host` and can't be combined with a secret. **Don't put a
tunnel in front of it.** claude.ai connectors run in the cloud and can't reach `127.0.0.1`; use the
remote mode below for those.

## Get a URL (remote connector, e.g. claude.ai)

By default the server talks over stdio. To get a URL, run it in HTTP mode **on the computer that has
CapCut** and expose it with a tunnel:

```bash
# 1. pick a long random secret and start the server
export CAPCUT_DRAFTS_DIR="/path/to/com.lveditor.draft"
export CAPCUT_MCP_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
capcut-mcp --http --port 8000
# prints: capcut-mcp listening on http://127.0.0.1:8000/<secret>/mcp

# 2. in a second terminal, expose it (either one)
cloudflared tunnel --url http://127.0.0.1:8000
ngrok http 8000
```

Your connector URL is the tunnel's `https://...` address plus `/<secret>/mcp`, for example
`https://example.trycloudflare.com/<secret>/mcp`. In claude.ai go to Settings -> Connectors -> Add
custom connector and paste it.

**Security:** the secret in the URL is the only protection. Anyone who has the URL can create, edit and
overwrite drafts in your drafts folder, so treat it like a password, don't share it, and stop the
tunnel when you're done. The server refuses secrets shorter than 16 characters and returns 404 for any
other path. Free tunnel URLs usually change on every restart, so you'll need to update the connector.
HTTP mode is tested with `mcp` 2.x.

## Tools

| Tool | What it does |
|------|--------------|
| `list_drafts` | List existing drafts |
| `create_draft` | Start a new draft (size, fps). `replace=true` overwrites an existing one |
| `add_track` | Add a `video`, `audio`, `text`, `effect`, `filter` or `sticker` track |
| `add_video` | Add a clip or still image (trim, speed, volume, opacity, scale, position, rotation) |
| `add_audio` | Add audio with volume and fades |
| `add_text` | Add a text overlay (font, size, color, position) |
| `import_srt` | Import subtitles from an `.srt` file |
| `add_filter` | Apply a filter over a time range |
| `add_transition` | Add a transition after a clip |
| `add_animation` | Intro/outro/group animations for video, intro/outro/loop for text |
| `add_fade` | Audio fade in/out on a segment |
| `add_keyframe` | Keyframe position, scale, rotation, alpha or volume |
| `list_effects` | Browse available filter/transition/animation/font names |
| `describe_draft` | Summarize tracks, duration and segment ids |
| `save_draft` | Write the draft so CapCut can open it |

All times are in **seconds**. Tools that create segments return a `segment_id` you can pass to
`add_transition`, `add_animation`, `add_fade` and `add_keyframe`.

Example prompt: *"Make a 1080x1920 draft called `promo`. Put `clip1.mp4` and `clip2.mp4` back to back
(4 s each) with a transition between them, add `music.mp3` underneath with a 1 s fade-out, and
caption it with `captions.srt`. Save it."*

## Caveats

- **Close the draft in CapCut before saving over it**, and restart CapCut (or re-enter the drafts
  list) to see new drafts.
- The draft format is proprietary and changes between CapCut versions, and effect/transition/font
  catalogs come from the pyJianYingDraft library, which is oriented around Jianying (the Chinese
  edition). Some catalog entries may not exist in CapCut International. Keep backups of drafts you care about.
- Editing *existing* drafts is not supported yet; the server creates new drafts.
- Draft names are restricted to plain folder names (no path separators), because `replace=true`
  deletes the existing folder.

## Development

```bash
pip install -e ".[dev]"
pytest
```

CI runs the tests on Linux, macOS and Windows.

## License

MIT. Built on [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft); see its repository for its license.

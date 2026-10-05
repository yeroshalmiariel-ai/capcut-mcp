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

## Get a URL with sign-in (claude.ai connector)

claude.ai connectors run in the cloud, so the server must be reachable from the internet. Sign-in mode
protects it with a password login page (OAuth): claude.ai sends you to your own server's login page,
and only gets access after you enter the password. Run it **on the computer that has CapCut**:

```bash
# 1. expose a local port with a tunnel and note the https address it prints (either one)
cloudflared tunnel --url http://127.0.0.1:8000
ngrok http 8000

# 2. in another terminal, start the server with that address and a password of your choice
export CAPCUT_DRAFTS_DIR="/path/to/com.lveditor.draft"
export CAPCUT_MCP_PASSWORD="choose-a-long-password"
capcut-mcp --http --port 8000 --public-url https://YOUR-TUNNEL-ADDRESS
# prints: Connector URL: https://YOUR-TUNNEL-ADDRESS/mcp
```

In claude.ai go to Settings -> Connectors -> Add custom connector, paste the connector URL, and
connect. You'll be sent to the login page; enter your password and you're done.

How it's protected:
- Nothing works without signing in: the MCP endpoint answers 401 to anyone without a token.
- The password is compared in constant time; after 10 wrong attempts in 10 minutes, sign-in is
  blocked for the rest of that window (so someone guessing can lock you out briefly).
- Tokens expire after an hour and are refreshed automatically; authorization codes work once.
- Apps can only register redirect addresses on `claude.ai`, `claude.com` or `localhost`, so a
  malicious link can't send your login to someone else's site. Add more with `--allow-redirect-host`.
- If you don't set a password, one is generated and printed when the server starts.

Limits: use a long, unique password and keep the tunnel closed when you're not using it. Sessions are
kept in memory, so restarting the server signs you out. Free tunnel addresses usually change on every
restart, so you'll need to update the connector URL and `--public-url`. Sign-in mode is tested with
`mcp` 2.x.

### Simpler alternative: secret in the URL

If you'd rather not use a login page, `capcut-mcp --http --port 8000` serves the connector at
`<tunnel address>/<secret>/mcp`, where the secret comes from `CAPCUT_MCP_SECRET` (16+ characters, or one
is generated). Anyone who learns the full URL has full access, so sign-in mode is the better choice.

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

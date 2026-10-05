# capcut-mcp

An [MCP](https://modelcontextprotocol.io) server that lets Claude (or any MCP client) build CapCut
projects: video/image clips, audio, text, SRT subtitles, transitions, animations, filters and keyframes.

> **CapCut has no public API.** This server does not control the CapCut app. It writes *draft
> projects* to disk (via [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)), which you
> then open in CapCut. Not affiliated with ByteDance or CapCut.

## Install

```bash
git clone https://github.com/<you>/capcut-mcp
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

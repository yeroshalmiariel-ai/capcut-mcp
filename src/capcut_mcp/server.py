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

mcp = _Server("capcut", instructions=INSTRUCTIONS)

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


@mcp.tool()
def list_drafts() -> str:
    """List the draft projects in the CapCut drafts folder."""
    return _run(lambda: {"drafts_dir": manager().drafts_dir, "drafts": manager().list_drafts()})


@mcp.tool()
def create_draft(name: str, width: int = 1920, height: int = 1080, fps: int = 30,
                 replace: bool = False) -> str:
    """Create a new draft and open it for editing. replace=true deletes an existing draft of the same name."""
    return _run(manager().create_draft, name, width, height, fps, replace)


@mcp.tool()
def add_track(draft: str, track_type: str, track_name: str, mute: bool = False) -> str:
    """Add a track. track_type: video, audio, text, effect, filter or sticker. Later tracks sit on top."""
    return _run(manager().add_track, draft, track_type, track_name, mute)


@mcp.tool()
def add_video(draft: str, track: str, path: str, start: float, duration: float,
              source_start: Optional[float] = None, speed: Optional[float] = None,
              volume: float = 1.0, opacity: float = 1.0, scale: float = 1.0,
              x: float = 0.0, y: float = 0.0, rotation: float = 0.0) -> str:
    """Add a video clip or still image at `start` for `duration` seconds.
    x/y are offsets in half-canvas units; rotation is in degrees. Returns a segment_id."""
    return _run(manager().add_video, draft, track, path, start, duration,
                source_start=source_start, speed=speed, volume=volume,
                opacity=opacity, scale=scale, x=x, y=y, rotation=rotation)


@mcp.tool()
def add_audio(draft: str, track: str, path: str, start: float, duration: float,
              source_start: Optional[float] = None, volume: float = 1.0,
              fade_in: float = 0.0, fade_out: float = 0.0) -> str:
    """Add an audio clip. Returns a segment_id."""
    return _run(manager().add_audio, draft, track, path, start, duration,
                source_start=source_start, volume=volume, fade_in=fade_in, fade_out=fade_out)


@mcp.tool()
def add_text(draft: str, track: str, text: str, start: float, duration: float,
             font: Optional[str] = None, size: float = 8.0, color: str = "#FFFFFF",
             x: float = 0.0, y: float = -0.8, bold: bool = False, italic: bool = False) -> str:
    """Add a text overlay. color is a hex string; y=-0.8 is near the bottom. Returns a segment_id."""
    return _run(manager().add_text, draft, track, text, start, duration, font=font,
                size=size, color=color, x=x, y=y, bold=bold, italic=italic)


@mcp.tool()
def import_srt(draft: str, track: str, srt_path: str, time_offset: float = 0.0) -> str:
    """Import an .srt subtitle file as text segments on a (new) text track."""
    return _run(manager().import_srt, draft, track, srt_path, time_offset)


@mcp.tool()
def add_filter(draft: str, track: str, filter_name: str, start: float, duration: float,
               intensity: float = 100.0) -> str:
    """Add a filter over a time range on a filter track (intensity 0-100)."""
    return _run(manager().add_filter, draft, track, filter_name, start, duration, intensity)


@mcp.tool()
def add_transition(draft: str, segment_id: str, transition: str,
                   duration: Optional[float] = None) -> str:
    """Add a transition after a video segment (it joins this clip to the next one on the track)."""
    return _run(manager().add_transition, draft, segment_id, transition, duration)


@mcp.tool()
def add_animation(draft: str, segment_id: str, catalog: str, animation: str,
                  duration: Optional[float] = None) -> str:
    """Add an animation. catalog: intro, outro, group_animation (video) or text_intro, text_outro, text_loop_anim (text)."""
    return _run(manager().add_animation, draft, segment_id, catalog, animation, duration)


@mcp.tool()
def add_fade(draft: str, segment_id: str, fade_in: float = 0.0, fade_out: float = 0.0) -> str:
    """Add an audio fade-in/out (seconds) to an audio or video segment."""
    return _run(manager().add_fade, draft, segment_id, fade_in, fade_out)


@mcp.tool()
def add_keyframe(draft: str, segment_id: str, property: str, time_offset: float,
                 value: float) -> str:
    """Add a keyframe at `time_offset` seconds into the segment. See KeyframeProperty names (e.g. position_x, scale_x, alpha, rotation, volume)."""
    return _run(manager().add_keyframe, draft, segment_id, property, time_offset, value)


@mcp.tool()
def list_effects(catalog: str, query: str = "", limit: int = 50) -> str:
    """Browse built-in effect names. catalog: filter, transition, intro, outro, group_animation, mask, font, video_scene_effect, video_character_effect, text_intro, text_outro, text_loop_anim."""
    return _run(manager().list_effects, catalog, query, limit)


@mcp.tool()
def describe_draft(draft: str) -> str:
    """Summarize an open draft: size, duration, tracks and segment ids."""
    return _run(manager().describe, draft)


@mcp.tool()
def save_draft(draft: str) -> str:
    """Write the draft to disk so CapCut can open it. Close the draft in CapCut first."""
    return _run(manager().save, draft)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

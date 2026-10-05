"""Core draft-editing logic, independent of the MCP layer.

CapCut has no public API. This module generates/edits CapCut (and Jianying)
*draft projects* on disk using the open-source pyJianYingDraft library, so the
result can be opened in the desktop app.

All times in the public API are expressed in **seconds** (floats).
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import pyJianYingDraft as draft
from pyJianYingDraft import SEC, ClipSettings, TrackSpec, TrackType, trange

ENV_DRAFTS_DIR = "CAPCUT_DRAFTS_DIR"

_DEFAULT_DRAFT_DIRS = {
    "win32": [
        r"%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft",
        r"%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft",
    ],
    "darwin": [
        "~/Movies/CapCut/User Data/Projects/com.lveditor.draft",
        "~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft",
    ],
}

# Effect catalogs that can be browsed/applied by member name.
_CATALOGS: Dict[str, Any] = {
    "filter": draft.FilterType,
    "transition": draft.TransitionType,
    "intro": draft.IntroType,
    "outro": draft.OutroType,
    "group_animation": draft.GroupAnimationType,
    "mask": draft.MaskType,
    "font": draft.FontType,
    "video_scene_effect": draft.VideoSceneEffectType,
    "video_character_effect": draft.VideoCharacterEffectType,
    "text_intro": draft.TextIntro,
    "text_outro": draft.TextOutro,
    "text_loop_anim": draft.TextLoopAnim,
}

_DRAFT_NAME_RE = re.compile(r"^[^\x00-\x1f/\\:*?\"<>|]+$")


class CapCutError(Exception):
    """A user-correctable error (bad name, missing file, unknown draft...)."""


def find_drafts_dir() -> str:
    """Resolve the drafts folder from $CAPCUT_DRAFTS_DIR or OS defaults."""
    env = os.environ.get(ENV_DRAFTS_DIR)
    if env:
        path = os.path.expandvars(os.path.expanduser(env))
        if not os.path.isdir(path):
            raise CapCutError(f"{ENV_DRAFTS_DIR} points to a folder that does not exist: {path}")
        return path
    for candidate in _DEFAULT_DRAFT_DIRS.get(sys.platform, []):
        path = os.path.expandvars(os.path.expanduser(candidate))
        if os.path.isdir(path):
            return path
    raise CapCutError(
        f"Could not locate the CapCut drafts folder. Set the {ENV_DRAFTS_DIR} environment "
        "variable to your CapCut 'com.lveditor.draft' folder."
    )


def _check_draft_name(name: str) -> str:
    if not name or name in (".", "..") or not _DRAFT_NAME_RE.match(name) or name != name.strip():
        raise CapCutError(
            f"Invalid draft name {name!r}: use a plain folder name without path separators "
            "or special characters."
        )
    return name


def _check_media(path: str) -> str:
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        raise CapCutError(f"Media file not found: {path}")
    return path


def _enum_member(catalog: str, name: str) -> Enum:
    enum_cls = _CATALOGS.get(catalog)
    if enum_cls is None:
        raise CapCutError(f"Unknown catalog {catalog!r}. Options: {sorted(_CATALOGS)}")
    try:
        return enum_cls[name]
    except KeyError:
        close = [n for n in enum_cls.__members__ if name.lower() in n.lower()][:8]
        hint = f" Did you mean: {close}?" if close else ""
        raise CapCutError(
            f"No {catalog} named {name!r}.{hint} Use list_effects(catalog='{catalog}') to browse."
        ) from None


def _secs(value: float, field_name: str, *, allow_zero: bool = True) -> int:
    if value < 0 or (value == 0 and not allow_zero):
        raise CapCutError(f"{field_name} must be {'>= 0' if allow_zero else '> 0'} (seconds).")
    return int(round(value * SEC))


@dataclass
class _OpenDraft:
    name: str
    script: Any
    segments: Dict[str, Any] = field(default_factory=dict)
    counters: Dict[str, int] = field(default_factory=dict)
    saved: bool = False

    def register(self, track: str, segment: Any) -> str:
        n = self.counters.get(track, 0) + 1
        self.counters[track] = n
        seg_id = f"{track}#{n}"
        self.segments[seg_id] = segment
        return seg_id


class DraftManager:
    """Holds open drafts in memory and exposes editing operations."""

    def __init__(self, drafts_dir: Optional[str] = None):
        self.drafts_dir = drafts_dir or find_drafts_dir()
        self.folder = draft.DraftFolder(self.drafts_dir)
        self._open: Dict[str, _OpenDraft] = {}

    # ---------- helpers ----------
    def _get(self, name: str) -> _OpenDraft:
        try:
            return self._open[name]
        except KeyError:
            raise CapCutError(
                f"Draft {name!r} is not open. Call create_draft first "
                f"(open drafts: {sorted(self._open) or 'none'})."
            ) from None

    def _segment(self, od: _OpenDraft, segment_id: str) -> Any:
        try:
            return od.segments[segment_id]
        except KeyError:
            raise CapCutError(
                f"Unknown segment {segment_id!r} in draft {od.name!r}. "
                f"Known: {sorted(od.segments)}"
            ) from None

    # ---------- drafts ----------
    def list_drafts(self) -> List[str]:
        return sorted(self.folder.list_drafts())

    def create_draft(self, name: str, width: int = 1920, height: int = 1080,
                     fps: int = 30, replace: bool = False) -> Dict[str, Any]:
        _check_draft_name(name)
        if width <= 0 or height <= 0 or not (1 <= fps <= 240):
            raise CapCutError("width/height must be positive and fps between 1 and 240.")
        if self.folder.has_draft(name) and not replace:
            raise CapCutError(
                f"Draft {name!r} already exists. Pass replace=true to overwrite it "
                "(this deletes the existing draft folder)."
            )
        script = self.folder.create_draft(name, width, height, fps, allow_replace=replace)
        self._open[name] = _OpenDraft(name=name, script=script)
        return {"draft": name, "width": width, "height": height, "fps": fps,
                "path": os.path.join(self.drafts_dir, name)}

    def add_track(self, draft_name: str, track_type: str, track_name: str,
                  mute: bool = False) -> Dict[str, Any]:
        od = self._get(draft_name)
        try:
            ttype = TrackType[track_type]
        except KeyError:
            raise CapCutError(
                f"Unknown track_type {track_type!r}. Options: {[t.name for t in TrackType]}"
            ) from None
        od.script.append_track(TrackSpec(ttype, track_name, mute=mute))
        return {"draft": draft_name, "track": track_name, "type": track_type}

    # ---------- segments ----------
    def add_video(self, draft_name: str, track_name: str, path: str, start: float,
                  duration: float, *, source_start: Optional[float] = None,
                  speed: Optional[float] = None, volume: float = 1.0,
                  opacity: float = 1.0, scale: float = 1.0,
                  x: float = 0.0, y: float = 0.0, rotation: float = 0.0) -> Dict[str, Any]:
        """Add a video clip or still image (images are treated as video segments)."""
        od = self._get(draft_name)
        path = _check_media(path)
        if not (0.0 <= opacity <= 1.0):
            raise CapCutError("opacity must be between 0 and 1.")
        target = trange(_secs(start, "start"), _secs(duration, "duration", allow_zero=False))
        source = None
        if source_start is not None:
            source = trange(_secs(source_start, "source_start"),
                            _secs(duration, "duration", allow_zero=False))
        seg = draft.VideoSegment(
            path, target, source_timerange=source, speed=speed, volume=volume,
            clip_settings=ClipSettings(alpha=opacity, scale_x=scale, scale_y=scale,
                                       transform_x=x, transform_y=y, rotation=rotation),
        )
        od.script.add_segment(seg, track_name)
        return {"segment_id": od.register(track_name, seg), "track": track_name,
                "start": start, "duration": duration}

    def add_audio(self, draft_name: str, track_name: str, path: str, start: float,
                  duration: float, *, source_start: Optional[float] = None,
                  volume: float = 1.0, fade_in: float = 0.0,
                  fade_out: float = 0.0) -> Dict[str, Any]:
        od = self._get(draft_name)
        path = _check_media(path)
        target = trange(_secs(start, "start"), _secs(duration, "duration", allow_zero=False))
        source = None
        if source_start is not None:
            source = trange(_secs(source_start, "source_start"),
                            _secs(duration, "duration", allow_zero=False))
        seg = draft.AudioSegment(path, target, source_timerange=source, volume=volume)
        if fade_in or fade_out:
            seg.add_fade(_secs(fade_in, "fade_in"), _secs(fade_out, "fade_out"))
        od.script.add_segment(seg, track_name)
        return {"segment_id": od.register(track_name, seg), "track": track_name,
                "start": start, "duration": duration}

    def add_text(self, draft_name: str, track_name: str, text: str, start: float,
                 duration: float, *, font: Optional[str] = None, size: float = 8.0,
                 color: str = "#FFFFFF", x: float = 0.0, y: float = -0.8,
                 bold: bool = False, italic: bool = False) -> Dict[str, Any]:
        od = self._get(draft_name)
        if not text.strip():
            raise CapCutError("text must not be empty.")
        rgb = _hex_to_rgb(color)
        font_member = _enum_member("font", font) if font else None
        seg = draft.TextSegment(
            text, trange(_secs(start, "start"), _secs(duration, "duration", allow_zero=False)),
            font=font_member,
            style=draft.TextStyle(size=size, color=rgb, bold=bold, italic=italic),
            clip_settings=ClipSettings(transform_x=x, transform_y=y),
        )
        od.script.add_segment(seg, track_name)
        return {"segment_id": od.register(track_name, seg), "track": track_name,
                "start": start, "duration": duration}

    def import_srt(self, draft_name: str, track_name: str, srt_path: str,
                   time_offset: float = 0.0) -> Dict[str, Any]:
        od = self._get(draft_name)
        srt_path = _check_media(srt_path)
        od.script.import_srt(srt_path, track_name, time_offset=_secs(time_offset, "time_offset"))
        return {"draft": draft_name, "track": track_name, "imported_from": srt_path}

    def add_filter(self, draft_name: str, track_name: str, filter_name: str,
                   start: float, duration: float, intensity: float = 100.0) -> Dict[str, Any]:
        od = self._get(draft_name)
        meta = _enum_member("filter", filter_name)
        od.script.add_filter(
            meta, trange(_secs(start, "start"), _secs(duration, "duration", allow_zero=False)),
            track_name, intensity=intensity)
        return {"draft": draft_name, "filter": filter_name, "start": start, "duration": duration}

    # ---------- segment decorations ----------
    def add_transition(self, draft_name: str, segment_id: str, transition_name: str,
                       duration: Optional[float] = None) -> Dict[str, Any]:
        """Transitions attach to the *earlier* of the two clips they join."""
        od = self._get(draft_name)
        seg = self._segment(od, segment_id)
        meta = _enum_member("transition", transition_name)
        seg.add_transition(meta, duration=None if duration is None else _secs(duration, "duration"))
        return {"segment_id": segment_id, "transition": transition_name}

    def add_animation(self, draft_name: str, segment_id: str, catalog: str,
                      animation_name: str, duration: Optional[float] = None) -> Dict[str, Any]:
        od = self._get(draft_name)
        seg = self._segment(od, segment_id)
        if catalog not in ("intro", "outro", "group_animation", "text_intro",
                           "text_outro", "text_loop_anim"):
            raise CapCutError("catalog must be one of: intro, outro, group_animation, "
                              "text_intro, text_outro, text_loop_anim.")
        meta = _enum_member(catalog, animation_name)
        seg.add_animation(meta, None if duration is None else _secs(duration, "duration"))
        return {"segment_id": segment_id, "animation": animation_name}

    def add_fade(self, draft_name: str, segment_id: str, fade_in: float = 0.0,
                 fade_out: float = 0.0) -> Dict[str, Any]:
        od = self._get(draft_name)
        seg = self._segment(od, segment_id)
        seg.add_fade(_secs(fade_in, "fade_in"), _secs(fade_out, "fade_out"))
        return {"segment_id": segment_id, "fade_in": fade_in, "fade_out": fade_out}

    def add_keyframe(self, draft_name: str, segment_id: str, prop: str,
                     time_offset: float, value: float) -> Dict[str, Any]:
        od = self._get(draft_name)
        seg = self._segment(od, segment_id)
        try:
            kprop = draft.KeyframeProperty[prop]
        except KeyError:
            raise CapCutError(
                f"Unknown keyframe property {prop!r}. Options: "
                f"{[p.name for p in draft.KeyframeProperty]}") from None
        seg.add_keyframe(kprop, _secs(time_offset, "time_offset"), value)
        return {"segment_id": segment_id, "property": prop, "time_offset": time_offset,
                "value": value}

    # ---------- inspection / saving ----------
    def list_effects(self, catalog: str, query: str = "", limit: int = 50) -> Dict[str, Any]:
        enum_cls = _CATALOGS.get(catalog)
        if enum_cls is None:
            raise CapCutError(f"Unknown catalog {catalog!r}. Options: {sorted(_CATALOGS)}")
        q = query.lower()
        names = [n for n in enum_cls.__members__ if q in n.lower()]
        return {"catalog": catalog, "total_matches": len(names), "names": names[:limit]}

    def describe(self, draft_name: str) -> Dict[str, Any]:
        od = self._get(draft_name)
        script = od.script
        return {
            "draft": draft_name,
            "width": script.width, "height": script.height, "fps": script.fps,
            "duration_seconds": script.duration / SEC,
            "tracks": [
                {"name": name, "type": t.track_type.name, "segments": len(t.segments)}
                for name, t in script.tracks.items()
            ],
            "segments": sorted(od.segments),
            "saved": od.saved,
        }

    def save(self, draft_name: str) -> Dict[str, Any]:
        od = self._get(draft_name)
        od.script.save()
        od.saved = True
        return {"draft": draft_name, "path": os.path.join(self.drafts_dir, draft_name),
                "note": "Restart CapCut or re-enter the drafts list to see the new draft."}


def _hex_to_rgb(color: str) -> tuple:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", color.strip())
    if not m:
        raise CapCutError(f"color must be a 6-digit hex string like '#FFCC00', got {color!r}")
    h = m.group(1)
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

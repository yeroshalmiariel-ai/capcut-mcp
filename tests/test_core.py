import json
import os

import pytest

from capcut_mcp.core import CapCutError, DraftManager, find_drafts_dir


def test_create_and_save_empty_draft(manager, drafts_dir):
    manager.create_draft("empty", 1280, 720, 24)
    manager.save("empty")
    content = drafts_dir / "empty" / "draft_content.json"
    assert content.is_file()
    data = json.loads(content.read_text(encoding="utf-8"))
    assert data["canvas_config"]["width"] == 1280
    assert data["canvas_config"]["height"] == 720
    assert (drafts_dir / "empty" / "draft_meta_info.json").is_file()
    assert manager.list_drafts() == ["empty"]


@pytest.mark.parametrize("bad", ["", "..", ".", "a/b", "a\\b", "x:y", " pad ", "../evil"])
def test_rejects_unsafe_draft_names(manager, bad):
    with pytest.raises(CapCutError):
        manager.create_draft(bad)


def test_replace_requires_flag(manager):
    manager.create_draft("d")
    manager.save("d")
    with pytest.raises(CapCutError, match="already exists"):
        manager.create_draft("d")
    manager.create_draft("d", replace=True)


def test_unopened_draft_error(manager):
    with pytest.raises(CapCutError, match="not open"):
        manager.add_track("nope", "video", "v")


def test_full_edit_flow(manager, drafts_dir, image, audio, srt):
    manager.create_draft("flow")
    manager.add_track("flow", "audio", "music")
    manager.add_track("flow", "video", "main")
    manager.add_track("flow", "text", "titles")

    a = manager.add_audio("flow", "music", audio, 0, 3, volume=0.5, fade_in=0.5, fade_out=0.5)
    v1 = manager.add_video("flow", "main", image, 0, 1.5, scale=0.9, y=0.1)
    v2 = manager.add_video("flow", "main", image, 1.5, 1.5)
    t = manager.add_text("flow", "titles", "Hello CapCut", 0, 3, color="#FFCC00")
    manager.add_keyframe("flow", v1["segment_id"], "alpha", 0.0, 0.0)
    manager.add_keyframe("flow", v1["segment_id"], "alpha", 1.0, 1.0)
    manager.import_srt("flow", "subs", srt)

    info = manager.describe("flow")
    assert info["duration_seconds"] == pytest.approx(3.0, abs=0.01)
    assert {tr["name"] for tr in info["tracks"]} >= {"music", "main", "titles", "subs"}
    assert {a["segment_id"], v1["segment_id"], v2["segment_id"], t["segment_id"]} <= set(info["segments"])

    manager.save("flow")
    data = json.loads((drafts_dir / "flow" / "draft_content.json").read_text(encoding="utf-8"))
    assert len(data["tracks"]) == 4
    texts = json.dumps(data["materials"]["texts"], ensure_ascii=False)
    assert "Hello CapCut" in texts and "World" in texts


def test_overlapping_segments_rejected(manager, image):
    manager.create_draft("o")
    manager.add_track("o", "video", "main")
    manager.add_video("o", "main", image, 0, 2)
    with pytest.raises(Exception):
        manager.add_video("o", "main", image, 1, 2)


def test_missing_media(manager):
    manager.create_draft("m")
    manager.add_track("m", "video", "main")
    with pytest.raises(CapCutError, match="not found"):
        manager.add_video("m", "main", "/no/such/file.mp4", 0, 1)


def test_validation_errors(manager, image):
    manager.create_draft("v")
    manager.add_track("v", "video", "main")
    manager.add_track("v", "text", "t")
    with pytest.raises(CapCutError, match="duration"):
        manager.add_video("v", "main", image, 0, 0)
    with pytest.raises(CapCutError, match="opacity"):
        manager.add_video("v", "main", image, 0, 1, opacity=2)
    with pytest.raises(CapCutError, match="color"):
        manager.add_text("v", "t", "hi", 0, 1, color="red")
    with pytest.raises(CapCutError, match="empty"):
        manager.add_text("v", "t", "  ", 0, 1)
    with pytest.raises(CapCutError, match="track_type"):
        manager.add_track("v", "hologram", "x")
    with pytest.raises(CapCutError, match="Unknown segment"):
        manager.add_fade("v", "main#99", 1, 1)


def test_transition_and_animation_by_name(manager, image):
    manager.create_draft("fx")
    manager.add_track("fx", "video", "main")
    seg = manager.add_video("fx", "main", image, 0, 2)["segment_id"]
    manager.add_video("fx", "main", image, 2, 2)

    names = manager.list_effects("transition")["names"]
    assert names, "transition catalog should not be empty"
    manager.add_transition("fx", seg, names[0])

    intros = manager.list_effects("intro")["names"]
    manager.add_animation("fx", seg, "intro", intros[0])

    with pytest.raises(CapCutError, match="No transition named"):
        manager.add_transition("fx", seg, "definitely-not-a-transition")
    with pytest.raises(CapCutError, match="catalog"):
        manager.add_animation("fx", seg, "filter", "x")


def test_list_effects_search_and_unknown_catalog(manager):
    full = manager.list_effects("filter", limit=5)
    assert full["total_matches"] >= len(full["names"]) == 5
    with pytest.raises(CapCutError, match="Unknown catalog"):
        manager.list_effects("nope")


def test_find_drafts_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CAPCUT_DRAFTS_DIR", str(tmp_path))
    assert find_drafts_dir() == str(tmp_path)
    monkeypatch.setenv("CAPCUT_DRAFTS_DIR", str(tmp_path / "missing"))
    with pytest.raises(CapCutError):
        find_drafts_dir()


def test_server_tools_registered():
    from capcut_mcp import server

    tools = ["list_drafts", "create_draft", "add_track", "add_video", "add_audio", "add_text",
             "import_srt", "add_filter", "add_transition", "add_animation", "add_fade",
             "add_keyframe", "list_effects", "describe_draft", "save_draft"]
    for name in tools:
        assert callable(getattr(server, name)), name


@pytest.mark.parametrize("bad", ["short", "has/slash_0123456789abcdef", ""])
def test_http_app_rejects_weak_secret(bad):
    from capcut_mcp.server import build_http_app

    with pytest.raises(ValueError):
        build_http_app(bad)


def test_http_app_builds_with_good_secret():
    from capcut_mcp.server import build_http_app

    app = build_http_app("a-long-random-secret-0123456789")
    assert app is not None

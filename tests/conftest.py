import struct
import wave
import zlib

import pytest

from capcut_mcp.core import DraftManager


def _write_png(path, width=64, height=36):
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x20\x80\xff" * width for _ in range(height))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    path.write_bytes(png)


def _write_wav(path, seconds=3, rate=8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * rate * seconds)


@pytest.fixture
def drafts_dir(tmp_path):
    d = tmp_path / "drafts"
    d.mkdir()
    return d


@pytest.fixture
def manager(drafts_dir):
    return DraftManager(str(drafts_dir))


@pytest.fixture
def image(tmp_path):
    p = tmp_path / "pic.png"
    _write_png(p)
    return str(p)


@pytest.fixture
def audio(tmp_path):
    p = tmp_path / "tone.wav"
    _write_wav(p)
    return str(p)


@pytest.fixture
def srt(tmp_path):
    p = tmp_path / "subs.srt"
    p.write_text("1\n00:00:00,000 --> 00:00:01,500\nHello\n\n2\n00:00:01,500 --> 00:00:03,000\nWorld\n\n",
                 encoding="utf-8")
    return str(p)

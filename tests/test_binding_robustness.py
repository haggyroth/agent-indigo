"""Native-call failures are surfaced, input is released, state files are all-or-nothing, the core can be closed (#381)."""
import os
import types

import pytest

core = pytest.importorskip("game.mgba_core", exc_type=ImportError)       # needs the compiled binding (skipped in the dependency-light CI job)
from game.watchdog import SkillBudgetExceeded  # noqa: E402

NULL = core.ffi.NULL


def _client(monkeypatch, **lib_funcs):
    """A NativeMGBAClient without a ROM: the C calls are the test's fakes."""
    lib = types.SimpleNamespace(**lib_funcs)
    monkeypatch.setattr(core, "lib", lib)
    c = core.NativeMGBAClient.__new__(core.NativeMGBAClient)
    c._h, c._viewer, c.watchdog = 1, None, None
    c._session_saves, c._save_seq = {}, 0
    return c, lib


# ── a failed screenshot is a failure, never a stale frame ────────────────────────────────────────

def test_screenshot_reports_failure_and_removes_the_stale_file(monkeypatch, tmp_path):
    p = tmp_path / "frame.png"
    p.write_bytes(b"the PREVIOUS frame")
    c, _ = _client(monkeypatch, pycore_screenshot=lambda h, path: 0)
    assert c.screenshot(str(p)) is False
    assert not p.exists()


def test_screenshot_success_returns_true(monkeypatch, tmp_path):
    c, _ = _client(monkeypatch, pycore_screenshot=lambda h, path: (open(path, "wb").write(b"png"), 1)[1])
    assert c.screenshot(str(tmp_path / "f.png")) is True


pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402


def test_capture_screenshot_is_none_when_the_write_failed_not_the_old_image(tmp_path, monkeypatch):
    import agent.lm_studio_client as lsc
    old = tmp_path / "frame.png"
    old.write_bytes(b"OLD FRAME")
    monkeypatch.setattr(lsc, "SCREENSHOT_PATH", str(old))
    c = AgentClient.__new__(AgentClient)
    c.mgba = types.SimpleNamespace(screenshot=lambda path: False)           # no framebuffer_png: the disk path
    assert c.capture_screenshot() is None


def test_capture_screenshot_prefers_the_in_memory_png():
    c = AgentClient.__new__(AgentClient)
    c.mgba = types.SimpleNamespace(framebuffer_png=lambda: b"\x89PNG-bytes", screenshot=lambda p: pytest.fail("must not touch the disk"))
    import base64
    assert base64.b64decode(c.capture_screenshot()) == b"\x89PNG-bytes"


# ── the watchdog tripping inside a press never leaves the key held ────────────────────────────────

@pytest.mark.parametrize("method,args", [("tap", ("A",)), ("run_step", ("Up",)), ("hold", ("A", 30))])
def test_keys_are_released_when_the_watchdog_trips_mid_press(monkeypatch, method, args):
    keys = []
    c, _ = _client(monkeypatch, pycore_set_keys=lambda h, k: keys.append(k), pycore_run_frame=lambda h: None)

    class Trip:
        def advance(self, n):
            raise SkillBudgetExceeded("over budget", 1, False)
    c.watchdog = Trip()
    with pytest.raises(SkillBudgetExceeded):
        getattr(c, method)(*args)
    assert keys and keys[-1] == 0                                            # released, not still held


# ── idle detection looks at the whole frame ──────────────────────────────────────────────────────

def test_idle_detection_sees_a_change_the_old_sparse_sample_never_looked_at(monkeypatch):
    """A single byte that flips every frame (a blinking arrow) at an offset the old stride-311 sample skipped: the screen is NOT idle."""
    n = 240 * 160 * 4
    assert 1000 % 311 != 0
    frames = [bytearray(n) for _ in range(2)]
    frames[1][1000] = 255
    tick = {"i": 0}
    c, lib = _client(monkeypatch, pycore_set_keys=lambda h, k: None, pycore_run_frame=lambda h: tick.__setitem__("i", tick["i"] + 1))
    c._video_bytes, c._video = n, NULL
    monkeypatch.setattr(core, "ffi", types.SimpleNamespace(buffer=lambda ptr, size: bytes(frames[tick["i"] % 2]), NULL=NULL))
    assert c.wait_until_idle(max_frames=60, stable=8) is False


def test_a_truly_still_screen_is_idle(monkeypatch):
    n = 240 * 160 * 4
    c, _ = _client(monkeypatch, pycore_set_keys=lambda h, k: None, pycore_run_frame=lambda h: None)
    c._video_bytes, c._video = n, NULL
    monkeypatch.setattr(core, "ffi", types.SimpleNamespace(buffer=lambda ptr, size: bytes(n), NULL=NULL))
    assert c.wait_until_idle(max_frames=60, stable=8) is True


# ── state files are all-or-nothing ───────────────────────────────────────────────────────────────

def test_a_failed_state_save_keeps_the_previous_file(monkeypatch, tmp_path):
    target = tmp_path / "slot.ss1"
    target.write_bytes(b"GOOD STATE")

    def write_partial_then_fail(h, path):
        open(path, "wb").write(b"half")
        return 0
    c, _ = _client(monkeypatch, pycore_save_state=write_partial_then_fail)
    assert c.save_state_file(str(target)) is False
    assert target.read_bytes() == b"GOOD STATE" and not (tmp_path / "slot.ss1.tmp").exists()


def test_a_good_state_save_replaces_the_file_whole(monkeypatch, tmp_path):
    target = tmp_path / "slot.ss1"
    c, _ = _client(monkeypatch, pycore_save_state=lambda h, path: (open(path, "wb").write(b"NEW"), 1)[1])
    assert c.save_state_file(str(target)) is True and target.read_bytes() == b"NEW" and not (tmp_path / "slot.ss1.tmp").exists()


# ── read bounds, lifecycle ───────────────────────────────────────────────────────────────────────

def test_read_range_refuses_an_absurd_length(monkeypatch):
    c, _ = _client(monkeypatch, pycore_read_range=lambda *a: None)
    for bad in (-1, core.NativeMGBAClient.MAX_READ + 1, 2 ** 32 - 1):
        with pytest.raises(ValueError):
            c.read_range(0x02000000, bad)
    assert c.read_range(0x02000000, 16) == bytes(16)


def test_close_is_idempotent_and_the_frame_buffer_is_not_readable_afterwards(monkeypatch):
    destroyed = []
    c, _ = _client(monkeypatch, pycore_destroy=lambda h: destroyed.append(h))
    c.close()
    c.close()
    assert destroyed == [1] and c._h is None
    with pytest.raises(RuntimeError):
        c.framebuffer()


def test_context_manager_closes(monkeypatch):
    destroyed = []
    c, _ = _client(monkeypatch, pycore_destroy=lambda h: destroyed.append(h))
    with c:
        pass
    assert destroyed == [1]


# ── against the real core (needs the ROM) ────────────────────────────────────────────────────────

from config import ROM_PATH  # noqa: E402

rom = pytest.mark.skipif(not os.path.isfile(ROM_PATH), reason="ROM not present")


@rom
def test_the_in_memory_png_matches_libmgbas_own_screenshot(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    with core.NativeMGBAClient(show_window=False) as m:
        m.run_frames(600)                                                    # past the boot logos: a frame with real content
        ref = tmp_path / "ref.png"
        assert m.screenshot(str(ref)) is True
        mine = tmp_path / "mine.png"
        mine.write_bytes(m.framebuffer_png())
        a, b = Image.open(ref).convert("RGB"), Image.open(mine).convert("RGB")
        assert a.size == b.size == (240, 160)
        assert a.tobytes() == b.tobytes()


@rom
def test_closing_the_real_core_twice_and_building_another():
    m = core.NativeMGBAClient(show_window=False)
    m.close()
    m.close()
    with core.NativeMGBAClient(show_window=False) as m2:
        assert m2.verify_connection()

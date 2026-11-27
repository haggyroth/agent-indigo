"""Native libmgba binding checks — gated on availability.

The compiled binding requires `brew install mgba` + `python -m game._mgba_build`;
loading a core additionally requires a real ROM at ROM_PATH (copyrighted, never
in CI). Each test skips cleanly when its prerequisite is absent, so this file is
safe to run everywhere while still exercising the binding where possible.
"""
import os
import pytest

try:
    from game import _mgba_native  # noqa: F401
    HAVE_BINDING = True
except Exception:
    HAVE_BINDING = False

from config import ROM_PATH

binding = pytest.mark.skipif(not HAVE_BINDING, reason="binding not built (python -m game._mgba_build)")
rom = pytest.mark.skipif(not os.path.isfile(ROM_PATH), reason=f"ROM not present at {ROM_PATH}")


@binding
def test_binding_exposes_expected_symbols():
    from game._mgba_native import lib
    for name in ("pycore_load", "pycore_read8", "pycore_set_keys",
                 "pycore_run_frame", "pycore_screenshot", "pycore_video_ptr",
                 "pycore_load_save", "pycore_reset"):
        assert hasattr(lib, name), f"missing binding symbol {name}"


@binding
@rom
def test_loads_leafgreen_and_reads_header():
    from game.mgba_core import NativeMGBAClient
    m = NativeMGBAClient(show_window=False)
    assert m.verify_connection()
    assert m.get_game_code() == "AGB-BPGE"
    assert m.get_game_title() == "POKEMON LEAF"


@binding
@rom
def test_framebuffer_size_matches_gba():
    from game.mgba_core import NativeMGBAClient
    m = NativeMGBAClient(show_window=False)
    m.tick(2)
    assert len(m.framebuffer()) == 240 * 160 * 4


@binding
@rom
def test_reset_reboots_without_crashing():
    from game.mgba_core import NativeMGBAClient
    m = NativeMGBAClient(show_window=False)
    m.tick(120)                 # advance into the boot sequence
    m.reset()                   # power-cycle
    m.tick(2)
    # ROM header is still readable after a reset (core is alive and re-booting).
    assert m.get_game_code() == "AGB-BPGE"


@binding
@rom
def test_load_save_returns_bool(tmp_path):
    from game.mgba_core import NativeMGBAClient
    m = NativeMGBAClient(show_window=False)
    # mGBA opens the cartridge save (creating it if absent) and reports success.
    result = m.load_save(str(tmp_path / "fresh.sav"))
    assert result is True
    m.reset()  # load-then-reset is the intended "Continue" sequence; must not crash
    m.tick(2)
    assert m.get_game_code() == "AGB-BPGE"


def test_load_flags_keep_the_cartridge_save():
    """#380: SAVE_FLAGS carries everything, LOAD_FLAGS leaves SAVEDATA (2) out on purpose — and the comment must say so, not 'everything except screenshot'."""
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "game" / "_mgba_build.py").read_text()
    save = int(re.search(r"SAVE_FLAGS = (\d+)", src).group(1))
    load = int(re.search(r"LOAD_FLAGS = (\d+)", src).group(1))
    SAVEDATA = 2
    assert save == 31
    assert not load & SAVEDATA and load & ~SAVEDATA & 31 == load            # nothing but known flags, SAVEDATA excluded
    assert "deliberately NOT restored" in src and "everything except screenshot" not in src


def test_the_link_module_exports_the_lockstep_host_functions():
    """#363: when game/_mgba_link is compiled and loads, it exposes the two-core link API; skipped (like the rest of this file) where it cannot load."""
    try:
        from game import _mgba_link as mod
    except Exception as e:                                   # not built, or libmgba's own dependencies (ffmpeg) do not load on this machine
        pytest.skip(f"link module unavailable: {e}")
    for name in ("link_create", "link_attach", "link_run", "link_frame_counter", "link_destroy"):
        assert hasattr(mod.lib, name), name

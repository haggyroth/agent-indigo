"""A warp is never a menu, even when an earlier menu left MENU_OPEN stale (#402): golden register vectors for detect_context."""
import pytest

from conftest import FakeClient
from game.constants import Addr
from game.memory_reader import LeafGreenReader
from game.state import GameContext

FIELD, LOAD = Addr.CB2_OVERWORLD, Addr.CB2_MAP_LOAD


def _ctx(cb2, menu, fade, script=0, tasks=()):
    fc = FakeClient()
    fc.set32(Addr.GMAIN_CALLBACK2, cb2)
    fc.set8(Addr.MENU_OPEN, menu)
    fc.set8(Addr.SCREEN_FADE, fade)
    fc.set8(Addr.SCRIPT_RAM, script)
    for i, func in enumerate(tasks):                       # gTasks: func u32, isActive u8 at +4
        base = Addr.TASKS_BASE + i * Addr.TASK_STRIDE
        fc.set32(base, func)
        fc.set8(base + 4, 1)
    return LeafGreenReader(fc, decrypt=False).detect_context()


def test_the_map_load_callbacks_are_a_transition_whatever_the_menu_byte_says():
    for cb2 in Addr.CB2_MAP_LOAD_SET:
        for menu in (0, 1, 252):
            assert _ctx(cb2, menu, 0) == GameContext.TRANSITIONING and _ctx(cb2, menu, 1) == GameContext.TRANSITIONING


def test_a_warp_fade_with_a_stale_menu_byte_is_a_transition_not_a_menu():
    for task in Addr.WARP_TASKS:
        assert _ctx(FIELD, 1, 1, tasks=(task,)) == GameContext.TRANSITIONING
        assert _ctx(FIELD, 252, 1, tasks=(0x0806E811, task)) == GameContext.TRANSITIONING          # (other field tasks are running too)


def test_the_start_menu_is_still_a_menu_even_during_a_warp_task():
    assert _ctx(FIELD, 1, 1, tasks=(Addr.START_MENU_TASK,)) == GameContext.IN_MENU
    assert _ctx(FIELD, 1, 1, tasks=(Addr.START_MENU_TASK, Addr.WARP_TASKS[0])) == GameContext.IN_MENU       # the menu task wins


def test_an_overlay_with_no_warp_task_keeps_the_old_reading():
    assert _ctx(FIELD, 1, 1, tasks=(0x0806E811,)) == GameContext.IN_MENU            # menu byte + fade + nothing warp-like: an overlay (the Save prompt …)
    assert _ctx(FIELD, 1, 1) == GameContext.IN_MENU
    assert _ctx(FIELD, 0, 1) == GameContext.TRANSITIONING                           # no menu byte: a plain fade
    assert _ctx(FIELD, 1, 0) == GameContext.OVERWORLD                               # the stale byte on the stable field
    assert _ctx(FIELD, 0, 0, script=1) == GameContext.DIALOG_OPEN


def test_a_full_screen_menu_is_still_a_menu_and_a_battle_is_a_battle():
    assert _ctx(0x08088331, 1, 1) == GameContext.IN_MENU                            # a full-screen screen's own callback + the menu byte
    assert _ctx(0x08088331, 0, 0) == GameContext.TRANSITIONING
    assert _ctx(Addr.CB2_BATTLE, 1, 1) == GameContext.IN_BATTLE


pytest.importorskip("game.mgba_core", exc_type=ImportError)

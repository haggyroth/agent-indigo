"""PC error messages, PC recovery and failure screenshots (no emulator) — from a watched run whose PC never worked."""
import time
from types import SimpleNamespace as NS

import pytest

from agent.failure_shots import MAX_SHOTS, looks_like_failure, should_save
from agent.skills.pc import resolve_boxed

BOXES = [{"box": 0, "slot": 4, "nickname": "Sandy", "species_name": "Sandshrew", "level": 6}]


def test_the_literal_box_placeholder_gets_a_hint_and_loose_references_resolve():
    mon, why = resolve_boxed("box:4", BOXES)
    assert mon is None and "'1:4'" in why and "BOX NUMBER" in why
    assert resolve_boxed("1:4", BOXES)[0] is BOXES[0]
    assert resolve_boxed("box 1:4", BOXES)[0] is BOXES[0] and resolve_boxed("Box1 slot 4", BOXES)[0] is BOXES[0]
    assert "Nothing at" in resolve_boxed("1:9", BOXES)[1] and "'1:4'" in resolve_boxed("1:9", BOXES)[1]
    assert resolve_boxed("sandy", BOXES)[0] is BOXES[0]


pytest.importorskip("openai")
from game.state import GameContext   # noqa: E402


def client():
    from agent.lm_studio_client import AgentClient
    return AgentClient.__new__(AgentClient)


def test_the_no_match_errors_list_the_boxes_instead_of_printing_a_bound_method():
    c = client()
    c.reader = NS(read_boxes=lambda: [], read_party=lambda: [])
    assert "<bound method" not in c._pc_withdraw("zzz") and "empty" in c._pc_withdraw("zzz")
    c._pick_party = lambda *a: (0, "")
    assert "<bound method" not in c._pc_swap("Pidgey", "zzz") and "Nothing was deposited" in c._pc_swap("Pidgey", "zzz")


def test_failure_results_from_the_watched_runs_are_recognised_and_normal_results_are_not():
    for bad in ("The PC didn't open the storage screen.", "Open the PC from the overworld inside a Pokémon Center.", "Couldn't open the Mart buy menu — walk up to the clerk.",
                "heal was stopped: no progress for 3.4 min of game time. Now: IN_BATTLE on map 3/21 at (17,5).", "Stopped at (3,5) while heading to (3,4).",
                "Heading to Power Plant: stuck at Route 10 (Stopped at (18,4) while heading to (18,31).).", "Could not use Tackle — the battle menu did not respond as expected."):
        assert looks_like_failure(bad), bad
    for ok in ("Healed the party to full HP at the Pokémon Center.", "Used Tackle. [foe Rattata 9/15; yours 19/22] Still in battle", "Arrived at Pewter City.",
               "Not travelling yet — sort this out first:", "Deposited Sandy into Box 1.", "Pressed A × 1"):
        assert not looks_like_failure(ok), ok


def test_the_limiter_spaces_shots_dedupes_a_retry_loop_and_caps_the_run():
    log = {}
    fail = "The PC didn't open the storage screen."
    assert should_save(log, "pc", fail, 100.0)
    assert not should_save(log, "pc", fail, 102.0)                       # inside the gap
    assert not should_save(log, "pc", fail, 110.0)                       # the same failure again within a minute: one picture
    assert should_save(log, "shop", "Couldn't open the Mart buy menu.", 110.0)
    assert should_save(log, "pc", fail, 200.0)                           # much later: worth another look
    assert not should_save(log, "pc", "Healed the party.", 500.0)
    capped = {"n": MAX_SHOTS}
    assert not should_save(capped, "pc", fail, 1e6)


def test_a_failure_saves_a_frame_under_the_run_directory(tmp_path):
    c = client()
    c.run_log = NS(dir=tmp_path, t0=time.time() - 12.5)
    c.mgba = NS(screenshot=lambda path: open(path, "wb").write(b"png"))
    rel = c._failure_shot("pc", "The PC didn't open the storage screen.")
    assert rel.startswith("shots/") and rel.endswith("_pc.png") and (tmp_path / rel).read_bytes() == b"png"
    assert c._failure_shot("pc", "The PC didn't open the storage screen.") == ""            # the same failure right away: no second picture
    assert c._failure_shot("pc", "Deposited Sandy.") == ""
    c.run_log = NS(dir=None, t0=0)
    assert c._failure_shot("pc", "Couldn't do the thing.") == ""                               # no run directory (eval / tests): nothing is written


def _pc_client(results, ctx=GameContext.OVERWORLD):
    c = client()
    calls = {"backout": 0, "once": 0}
    seq = list(results)
    c._in_storage = lambda: False
    c.reader = NS(detect_context=lambda: ctx, read_player_pos=lambda: (11, 2), read_current_map=lambda: (7, 3))
    c.mgba = NS(read32=lambda a: 0x80565B5)
    c._mcur = lambda: 0

    def once(mode=1):
        calls["once"] += 1
        return seq.pop(0)

    def backout():
        calls["backout"] += 1
    c._open_pc_once, c._pc_backout = once, backout
    return c, calls


def test_a_failed_open_backs_out_and_retries_once():
    c, calls = _pc_client(["The PC didn't open the storage screen.", None])
    assert c._open_pc() is None and calls == {"backout": 1, "once": 2} and c._pc_fail_streak == 0


def test_two_failures_report_the_screen_and_the_second_call_says_stop_retrying():
    fail = "The PC didn't open the storage screen."
    c, calls = _pc_client([fail, fail, fail, fail])
    first = c._open_pc()
    assert "Tried twice" in first and "(screen: callback 0x80565b5" in first and "stop retrying" not in first and c._pc_fail_streak == 1
    second = c._open_pc()
    assert "failed 2 calls in a row" in second and "stop retrying" in second and calls["backout"] == 4


def test_other_errors_are_returned_untouched_and_a_stale_menu_is_cleared_first():
    c, calls = _pc_client(["Couldn't find the PC in this Pokémon Center."])
    assert c._open_pc() == "Couldn't find the PC in this Pokémon Center." and calls == {"backout": 0, "once": 1}
    c, calls = _pc_client([None], ctx=GameContext.IN_MENU)
    assert c._open_pc() is None and calls["backout"] == 1                                  # a menu left open by an earlier failure: backed out before trying


def _pc_menu_sim(first_menu_live):
    """The PC dialogue: dialogue boxes, the 4-entry 'Which PC?' menu, more dialogue, then the 5-entry storage menu (cursor starts on WITHDRAW). A on the storage menu opens
    the screen for whichever mode the cursor is on."""
    st = {"i": 0, "cursor": 0, "opened": None, "presses": []}
    screens = ["dialogue", "which_pc", "dialogue", "storage_menu"]

    def cur():
        return screens[min(st["i"], len(screens) - 1)]

    def read8(addr):
        from game.constants import Addr
        assert addr == Addr.MENU_CURSOR + 2
        return {"which_pc": 3, "storage_menu": 4}.get(cur(), 0)               # sMenu.maxCursorPos

    def hold(btn, n):
        if cur() == "storage_menu":
            st["opened"] = st["cursor"]
        else:
            st["i"] += 1

    c = client()
    c.mgba = NS(read8=read8, hold=hold, tick=lambda n: None)
    c._in_storage = lambda: st["opened"] is not None
    c._menu_driver = NS(choice_live=lambda: cur() == "storage_menu" or (cur() == "which_pc" and first_menu_live))
    c._mcur = lambda: st["cursor"]

    def press(btn, n):
        st["presses"].append(btn)
        st["cursor"] += 1 if btn == "Down" else -1
    c._press = press
    return c, st


@pytest.mark.parametrize("first_menu_live", [True, False])
def test_the_storage_menu_is_steered_to_the_mode_even_when_the_which_pc_menu_reads_as_no_menu(first_menu_live):
    """The watched run's stuck swap: 'Which PC?' read as not-a-menu, so the old menu counting steered nothing and A took WITHDRAW with a full party, forever."""
    for mode in (0, 1, 2):
        c, st = _pc_menu_sim(first_menu_live)
        assert c._pc_to_storage(mode) is None and st["opened"] == mode, (mode, st)
        assert st["presses"] == ["Down"] * mode                                  # and the 4-entry menu before it was never steered

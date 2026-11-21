"""The level-up move-learn driver must not press A unless the battle script is really waiting on the box (no emulator).

learnMoveState lingers at 1 after a decline, so it alone read as a live "Delete a move?" box in an ordinary battle menu: the driver pressed A into it, FIGHT → move 1, and a watched
run used Foresight ~24 times (HP 40 → 0) until the Pokémon fainted. The script pointer (gBattlescriptCurrInstr) sits on the prompt's command only while it is up."""
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402
from game.constants import Addr  # noqa: E402


def client(ptr, lms=1, cb2=None, offered=141):
    c = AgentClient.__new__(AgentClient)
    mem = {Addr.LEARN_MOVE_STATE: lms, Addr.GMAIN_CALLBACK2: Addr.CB2_BATTLE if cb2 is None else cb2, Addr.BATTLE_SCRIPT_PTR: ptr, Addr.MOVE_TO_LEARN: offered}
    c.mgba = NS(read8=lambda a: mem[a], read16=lambda a: mem[a], read32=lambda a: mem[a], tap=lambda b: None, tick=lambda n=1: None, hold=lambda b, n: None)
    c.reader = NS(read_party=lambda: [NS(species_id=48, level=24, move_ids=[193, 48, 93, 77], move_names=["Foresight", "Supersonic", "Confusion", "Poison Powder"])])
    c._wait_idle = lambda: None
    return c, mem


def test_a_lingering_learn_state_in_the_normal_battle_menu_is_not_a_live_box():
    c, _ = client(ptr=0x081D8000)                                 # script pointer somewhere else: lms == 1 is stale
    assert c._delete_box_live() is False


def test_the_box_is_live_only_while_the_script_waits_on_it():
    c, mem = client(ptr=Addr.SCRIPT_LEARN_DELETE)
    assert c._delete_box_live() is True
    mem[Addr.LEARN_MOVE_STATE] = 4
    assert c._delete_box_live() is False
    mem[Addr.LEARN_MOVE_STATE], mem[Addr.MOVE_TO_LEARN] = 1, 0     # nothing offered
    assert c._delete_box_live() is False


def test_the_driver_presses_nothing_for_a_phantom_box():
    c, _ = client(ptr=0x081D8000)
    pressed = []
    c.mgba.tap = pressed.append
    c._learn_armed, c._offer_resolved, c._learn_in_battle, c._levels_seen = True, 0, True, None
    c.reader.detect_context = lambda: __import__("game.state", fromlist=["GameContext"]).GameContext.IN_BATTLE
    assert c._maybe_drive_learn() is None
    assert pressed == []


def test_a_prompt_that_will_not_resolve_is_left_alone_after_three_tries():
    c, _ = client(ptr=Addr.SCRIPT_LEARN_DELETE)
    calls = []
    c._resolve_move_learn = lambda: calls.append(1) or "couldn't steer"
    c.reader.detect_context = lambda: __import__("game.state", fromlist=["GameContext"]).GameContext.IN_BATTLE
    note = c._drive_pending_learn()
    assert len(calls) == 3 and "would not resolve" in note, (calls, note)


def test_accepting_never_presses_a_when_the_script_is_not_on_the_prompt():
    c, _ = client(ptr=0x081D8000)
    pressed = []
    c.mgba.tap = pressed.append
    assert c._accept_forget_slot(0) is False and pressed == []     # and no blind B / A back-out either

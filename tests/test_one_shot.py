"""One-shot encounters (#272, no emulator): which foes, the protocol text at each HP, the gentlest move, and the autopilot staying away."""
from types import SimpleNamespace as NS

import pytest

from knowledge.one_shot import ARTICUNO, MASTER_BALL, SAVE_SLOT, SNORLAX, gentlest_move, is_one_shot, protocol

POWER = {"Tackle": 35, "Body Slam": 85, "Vine Whip": 35, "Razor Leaf": 55, "Growl": 0, "Hyper Beam": 150}


def test_only_the_snorlaxes_the_birds_and_mewtwo_are_one_shot():
    assert all(is_one_shot(s) for s in (143, 144, 145, 146, 150)) and not is_one_shot(25) and not is_one_shot(151)


def test_the_gentlest_damaging_move_is_the_lowest_power_one_with_pp():
    assert gentlest_move(["Hyper Beam", "Razor Leaf", "Growl", "Vine Whip"], [5, 25, 40, 10], POWER) == "Vine Whip"
    assert gentlest_move(["Hyper Beam", "Razor Leaf", "Growl", "Vine Whip"], [5, 25, 40, 0], POWER) == "Razor Leaf"      # no PP left on Vine Whip
    assert gentlest_move(["Growl", ""], [40, 0], POWER) == ""


def test_the_protocol_walks_from_weakening_to_the_ball_and_always_names_the_reload():
    balls = {2: 5}
    full = protocol(SNORLAX, 143, 143, balls, "Catch setup you have: Sleep Powder.", "Vine Whip")
    assert f"slot {SAVE_SLOT}" in full and f"load_state({SAVE_SLOT})" in full and "Vine Whip" in full and "weaken it carefully" in full
    half = protocol(SNORLAX, 60, 143, balls, "", "Vine Whip")
    assert "nearly there" in half and "Ultra Ball" in half
    red = protocol(SNORLAX, 20, 143, balls, "", "", asleep_or_para=True)
    assert "STOP attacking" in red and "already asleep" in red and "catch()" in red
    assert protocol(SNORLAX, 0, 143, balls) == "" and protocol(25, 10, 20, balls) == "" and protocol(SNORLAX, 10, 0, balls) == ""


def test_a_legend_is_offered_the_master_ball_and_no_balls_means_reload_and_shop():
    assert "MASTER BALL" in protocol(ARTICUNO, 30, 100, {MASTER_BALL: 1, 2: 3}, "", "")
    assert "Ultra Ball" in protocol(SNORLAX, 30, 100, {MASTER_BALL: 1, 2: 3}, "", "")        # the Master Ball is for the legends, not the Snorlax
    out = protocol(ARTICUNO, 100, 100, {}, "", "")
    assert "no Poké Balls" in out and "load_state" in out


pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import GameContext                 # noqa: E402


def test_the_autopilot_leaves_a_wild_snorlax_to_the_model():
    c = AgentClient.__new__(AgentClient)
    foe = NS(species_id=143, max_hp=143, current_hp=143)
    c.reader = NS(read_enemy_lead=lambda: foe, detect_context=lambda: GameContext.IN_BATTLE, read_party=lambda: pytest.fail("autopilot started"))
    c.mgba = NS(read32=lambda a: 0)                                           # not a trainer battle
    c._send_next_mon = lambda: pytest.fail("autopilot started")
    c._auto_fight()                                                          # returns at once

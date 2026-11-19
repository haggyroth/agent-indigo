"""The four small problems a watched run showed (no emulator): the no-PP / stale-move replies, nickname shortening, switch_pokemon outside a battle, and heal()'s trainer hand-off."""
from types import SimpleNamespace as NS

import pytest

from knowledge.nicknames import MAX_NAME, shorten, usable


def test_a_too_long_nickname_is_shortened_not_refused():
    assert shorten("Sparky McZap") == "Sparky"                      # whole words while >= 5 characters survive
    assert shorten("Beaky Blinders") == "Beaky"
    assert shorten("Zap-a-doodle") == "Zap a" and shorten("Hyperactive Beast") == "Hyperactiv"      # a plain cut when even the first word is long
    assert shorten("Zubat") == "Zubat" and shorten("Sir Wiggle") == "Sir Wiggle"          # short names are left alone
    for n in ("Sparky McZap", "Beaky Blinders", "Zap-a-doodle", "Wolfgang Amadeus Mozart", "Supercalifragilistic"):
        assert len(shorten(n)) <= MAX_NAME and usable(shorten(n))


pytest.importorskip("openai")
from game.state import GameContext   # noqa: E402


def client():
    from agent.lm_studio_client import AgentClient
    return AgentClient.__new__(AgentClient)


def test_the_moves_with_pp_helper_and_the_no_pp_reply():
    from agent.skills.battle import BattleMixin
    assert BattleMixin._moves_with_pp(["Sleep Powder", "Vine Whip", "", ""], [15, 0, 0, 0]) == "Sleep Powder (PP 15), Vine Whip (PP 0)"
    assert BattleMixin._moves_with_pp([], []) == "none"


def test_switch_pokemon_outside_a_battle_settles_then_says_where_you_are():
    c = client()
    c.mgba = NS(read32=lambda a: 0, read8=lambda a: 0, read16=lambda a: 0)
    c.reader = NS(detect_context=lambda: GameContext.TRANSITIONING, read_current_map=lambda: (3, 21))
    settled = []
    c._advance_to_control = lambda tries=10: (settled.append(tries), GameContext.OVERWORLD)[1]
    out = c._switch_pokemon("Pikachu")
    assert settled == [20] and "no battle to switch" in out and "3/21" in out and "reorder_party" in out and "heal()" in out


def test_a_hurt_party_on_a_heal_trip_hands_the_trainer_to_the_model():
    from game.constants import Addr
    c = client()
    c.mgba = NS(read32=lambda a: Addr.BATTLE_TYPE_TRAINER if a == Addr.BATTLE_TYPE_FLAGS else 0)
    c._has_must_need = lambda: True
    c._auto_fight = lambda: pytest.fail("a hurt party must not auto-fight the trainer on a heal trip")
    c._yield_encounter = lambda target, trainer, resume, call=None: f"TRAINER on the way to {target}; resume with {call}"
    out = c._handle_travel_battle("Pokemon Center", mode="flee", resume="Pokemon Center", call="heal()")
    assert out.startswith("TRAINER on the way to Pokemon Center; resume with heal()") and "hurt" in out


def test_a_healthy_party_still_auto_fights_a_travel_trainer_in_flee_mode():
    from game.constants import Addr
    c = client()
    fought = []
    c.mgba = NS(read32=lambda a: Addr.BATTLE_TYPE_TRAINER if a == Addr.BATTLE_TYPE_FLAGS else 0, read8=lambda a: 0)
    c._has_must_need = lambda: False
    c._lagging_mons = lambda: []
    c._auto_fight = lambda: fought.append(1)
    c.reader = NS(read_current_map=lambda: (3, 21), read_party=lambda: [NS(current_hp=20, max_hp=20, hp_percent=1.0)], detect_context=lambda: GameContext.OVERWORLD)
    c._trainer_losses = {}
    assert c._handle_travel_battle("Pokemon Center", mode="flee") is None and fought == [1]

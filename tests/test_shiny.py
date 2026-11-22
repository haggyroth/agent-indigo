"""Shiny Pokémon: detection (PID ^ OT id), the catch-don't-KO protocol, and the autopilot gates."""
import pytest

from game.state import PokemonStatus, shiny_value
from knowledge.one_shot import is_one_shot, protocol


def _mon(pid, otid):
    return PokemonStatus(slot=0, level=20, current_hp=50, max_hp=50, status="healthy", species_id=114, species_name="TANGELA",
                         personality=pid, ot_id=otid)


def test_shiny_value_is_the_xor_of_all_four_halves():
    assert shiny_value(0x12345678, 0x9ABCDEF0) == 0x9ABC ^ 0xDEF0 ^ 0x1234 ^ 0x5678


@pytest.mark.parametrize("pid,otid,shiny", [
    (0x0001_0002, 0x0001_0002, True),        # value 0
    (0x0000_0007, 0x0000_0000, True),        # value 7: the last shiny
    (0x0000_0008, 0x0000_0000, False),       # value 8: ordinary
    (0xABCD_1234, 0x0000_0001, False),
])
def test_is_shiny_is_below_eight(pid, otid, shiny):
    assert _mon(pid, otid).is_shiny is shiny


def test_an_unread_pokemon_is_never_shiny():
    assert not PokemonStatus(slot=0, level=1, current_hp=1, max_hp=1, status="healthy").is_shiny


def test_a_shiny_is_a_one_shot_whatever_its_species():
    assert is_one_shot(114, shiny=True) and not is_one_shot(114)
    out = protocol(114, 60, 60, {2: 5}, "", "Vine Whip", shiny=True, species_name="TANGELA")
    assert "SHINY TANGELA" in out and "do NOT knock it out" in out and "Vine Whip" in out and "weaken it carefully" in out
    assert protocol(114, 60, 60, {2: 5}, "", "Vine Whip", shiny=False) == ""          # an ordinary Tangela is not
    assert "Ultra Ball" in protocol(114, 25, 60, {2: 5}, "", "", shiny=True, species_name="TANGELA")
    red = protocol(114, 10, 60, {2: 5}, "", "", shiny=True, species_name="TANGELA")
    assert "STOP attacking" in red
    assert "no Poké Balls" in protocol(114, 60, 60, {}, "", "", shiny=True, species_name="TANGELA")


def test_the_flee_battle_skill_refuses_to_run_from_a_shiny():
    pytest.importorskip("openai")
    from types import SimpleNamespace as NS
    from agent.lm_studio_client import AgentClient
    from game.state import GameContext
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(detect_context=lambda: GameContext.IN_BATTLE, read_wild_shiny=lambda: _mon(0x0001_0002, 0x0001_0002))
    c.mgba = NS(read32=lambda a: 0)
    c._battle_trapped = lambda: False
    c._ball_count = lambda: 3
    out = c._flee_battle()
    assert out.startswith("Not fleeing") and "SHINY" in out
    c._ball_count = lambda: 0                       # with no ball to throw, running is allowed again (it falls through to the normal flee code)
    c._wait_idle = lambda: (_ for _ in ()).throw(RuntimeError("reached the flee code"))
    with pytest.raises(RuntimeError, match="reached the flee code"):
        c._flee_battle()


def test_grind_autopilot_never_takes_a_shiny():
    pytest.importorskip("openai")
    from types import SimpleNamespace as NS
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    foe = NS(species_id=114, species_name="TANGELA", level=10, max_hp=40, is_shiny=True)
    c.reader = NS(read_enemy_lead=lambda: foe, read_active_battle_species=lambda: 6)
    party = [NS(species_id=6, level=40)]
    assert c._grind_auto_ok({"auto_left": 3, "catch": False}, False, party) is False
    foe.is_shiny = False
    assert c._grind_auto_ok({"auto_left": 3, "catch": False}, False, party) is True

"""The Pokémon Tower's ghost Marowak can't be caught (the game dodges every ball). A watched run threw 18 Poké Balls at it — "It broke free!" each time — until the watchdog fired,
because the encounter hand-off said "Worth a ball: a NEW Pokédex entry". No emulator."""
from types import SimpleNamespace as NS

import pytest

from game.constants import Addr

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import GameContext               # noqa: E402


def client(flags):
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(detect_context=lambda: GameContext.IN_BATTLE)
    c.mgba = NS(read32=lambda a: flags if a == Addr.BATTLE_TYPE_FLAGS else 0, read8=lambda a: 0)
    c._ball_count = lambda: pytest.fail("no ball may be counted or thrown for the ghost")
    return c


def test_the_ghost_flag_is_gBattleTypeFlags_bit_15():
    assert Addr.BATTLE_TYPE_GHOST == 1 << 15 and Addr.BATTLE_TYPE_GHOST not in (Addr.BATTLE_TYPE_TRAINER, Addr.BATTLE_TYPE_SAFARI, Addr.BATTLE_TYPE_DOUBLE)


def test_catch_refuses_the_ghost_before_touching_the_bag():
    out = client(Addr.BATTLE_TYPE_GHOST | 0x2000)._catch("Bonehead")                  # ghost + unveiled (1 << 13), as with the Silph Scope
    assert "ghost Marowak" in out and "can't be caught" in out and "use_move" in out


def test_the_battle_observation_says_not_to_catch_it():
    from agent.observation import _catch_advice
    t = NS(reader=NS(client=NS(read32=lambda a: Addr.BATTLE_TYPE_GHOST), read_bag=lambda: pytest.fail("not reached")), state=NS(party=[]), ltm=NS(data={}))
    out = _catch_advice(t, NS(species_id=105, species_name="Marowak", level=30), [], None)
    assert len(out) == 1 and "GHOST" in out[0] and "CAN'T be caught" in out[0]

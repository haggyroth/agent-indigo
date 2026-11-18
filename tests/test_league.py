"""quest('elite_four') (#259): the beat in the story chain, the room table against the decomp, and the driver's early returns (no emulator)."""
from types import SimpleNamespace as NS

import pytest

from knowledge import story_beats as sb

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402
from agent.skills import league                    # noqa: E402


def test_the_chain_ends_with_the_league_after_victory_road():
    b = sb.BY_KEY["elite_four"]
    assert b.needs == ("victory_road",) and b.driver == "elite_four" and ("flag", 0x82C) in b.done
    assert sb.resolve("champion") is b and sb.resolve("elite4") is b
    assert sb.CHAIN_KEYS[-1] == "elite_four"


def test_the_rooms_are_in_battle_order_with_distinct_maps_and_flags():
    assert [r[3] for r in league.ROOMS] == ["Lorelei", "Bruno", "Agatha", "Lance", "the Champion"]
    assert len({r[0] for r in league.ROOMS}) == 5 and len({r[1] for r in league.ROOMS}) == 5
    assert [r[1] for r in league.ROOMS] == [0x4B8, 0x4B9, 0x4BA, 0x4BB, 0x4BC]      # FLAG_DEFEATED_LORELEI .. CHAMP
    assert league.ROOMS[-1][1] == league.FLAG_DEFEATED_CHAMP


def client(flags=(), badges=0xFF, ctx="OVERWORLD", map_=(3, 9)):
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_flag=lambda f: f in flags, detect_context=lambda: NS(name=ctx) if False else getattr(__import__("game.state", fromlist=["x"]).GameContext, ctx),
                  read_badges=lambda: (bin(badges).count("1"), badges), read_current_map=lambda: map_)
    return c


def test_a_cleared_league_says_so_and_the_door_needs_eight_badges():
    assert "game is cleared" in client(flags={league.FLAG_GAME_CLEAR})._get_elite_four()
    assert "all eight badges" in client(badges=0b111)._get_elite_four()
    assert "in a battle" in client(ctx="IN_BATTLE")._get_elite_four()


def test_the_quest_warns_once_when_the_team_is_far_below_the_leagues_levels():
    from knowledge.beat_readiness import readiness
    out = readiness("elite_four", [NS(level=lv) for lv in (50, 40, 38, 36, 30, 20)])
    assert "Not ready for quest('elite_four')" in out and "no healing between them" in out
    assert readiness("elite_four", [NS(level=lv) for lv in (58, 52, 50, 48, 47, 46)]) == ""

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
    assert [k for k in sb.CHAIN_KEYS if sb.BY_KEY[k].tier != "post"][-1] == "elite_four"          # (post-game beats come after the League)


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


def test_a_run_started_after_the_game_is_cleared_does_not_end_at_step_zero():
    """main()'s goal is the hall_of_fame milestone recorded DURING the run — an earlier run's progress.json (or a post-credits save) must not end the next run at once."""
    import main
    done = NS(data={"milestones": ["hall_of_fame"]})
    assert main._cleared_this_run(done)(None, done) is False
    fresh = NS(data={"milestones": ["beat_brock"]})
    goal = main._cleared_this_run(fresh)
    assert goal(None, fresh) is False
    fresh.data["milestones"].append("hall_of_fame")                       # recorded by _apply_progress / the quest
    assert goal(None, fresh) is True


def test_a_cleared_league_points_at_the_network_machine_until_it_is_linked():
    assert "Network Machine" in client(flags={league.FLAG_GAME_CLEAR})._get_elite_four()
    assert not client(flags={league.FLAG_GAME_CLEAR})._league_rematch_open()
    assert client(flags={league.FLAG_GAME_CLEAR, league.FLAG_NETWORK_MACHINE})._league_rematch_open()
    assert not client(flags={league.FLAG_NETWORK_MACHINE})._league_rematch_open()                 # the game must be cleared as well


def test_the_rematch_league_asks_for_much_higher_levels_and_still_names_quest_elite_four():
    from knowledge.beat_readiness import EXTRA_NEEDS, NEEDS, REMATCH_KEY, readiness, recommendation
    assert EXTRA_NEEDS[REMATCH_KEY].top > NEEDS["elite_four"].top and EXTRA_NEEDS[REMATCH_KEY].floor > NEEDS["elite_four"].floor
    out = readiness(REMATCH_KEY, [NS(level=lv) for lv in (60, 58, 56, 55, 50, 45)])
    assert "Not ready for quest('elite_four')" in out and "L72" in out
    assert readiness(REMATCH_KEY, [NS(level=lv) for lv in (74, 70, 68, 66, 65, 64)]) == ""
    assert "Champion L72-75" in recommendation(REMATCH_KEY)


def test_the_rematch_levels_match_the_decomps_trainer_parties():
    """Lorelei2 L63-66, Bruno2 L65-68, Agatha2 L65-70, Lance2 L66-72, the Champion's rematch L72-75 (src/data/trainer_parties.h) — the Need's text quotes them."""
    from knowledge.beat_readiness import EXTRA_NEEDS, REMATCH_KEY
    why = EXTRA_NEEDS[REMATCH_KEY].why
    for text in ("L63-66", "L65-68", "L65-70", "L66-72", "L72-75"):
        assert text in why

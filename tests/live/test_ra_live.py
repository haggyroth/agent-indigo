"""RetroAchievements progress on the real game (#358): the checks of knowledge/ra_map.py read from real fixtures, and quest('achievements') reports them."""
import json

from agent import ra


def _states(live):
    return ra.states(live.r, live.c.ltm)


def test_an_early_game_reads_only_what_it_has_done(live):
    live.load("post_misty")                                              # Route 24: Brock and Misty beaten, Ivysaur L26
    st = _states(live)
    assert st[34785] == "yes" and st[34786] == "yes"                     # Boulder and Cascade badges
    assert st[34787] == "no" and st[34797] == "no"                       # no Thunder Badge, not the Champion
    out = live.c._execute("quest", json.dumps({"name": "achievements"}))
    assert out.startswith("Achievements ") and "/128" in out and "Local tracking only" in out, out
    assert "Can be lost for good" in out


def test_after_the_hall_of_fame_the_league_achievements_are_unlocked(live):
    live.load("post_hof")                                                # Pallet Town after the credits: FLAG_SYS_GAME_CLEAR, eight badges
    st = _states(live)
    assert st[34797] == "yes"                                            # The Real Champion!
    assert all(st[a] == "yes" for a in (34785, 34786, 34787, 34788, 34789, 34790, 34791, 34792))     # all eight badges
    done = live.c._execute("quest", json.dumps({"name": "achievements done"}))
    assert "The Real Champion!" in done and "A Stone Gray City" in done, done


def test_the_journal_count_is_refreshed_from_the_real_game(live, tmp_path):
    """#358: main._apply_progress puts the unlocked count into the journal (what the eval goals and the scorecard read) — here from the post-Hall-of-Fame fixture, into a scratch journal."""
    from types import SimpleNamespace

    import main
    from evals import goals
    from memory.long_term import LongTermMemory
    live.load("post_hof")
    ltm = LongTermMemory(path=tmp_path / "journal.json")
    run = main._RunState()
    run.step_count = 0
    main._apply_progress(run, SimpleNamespace(badges=8, party_count=6, party=[], badge_bits=255), SimpleNamespace(badges_changed=False), live.r, ltm)
    assert ltm.data["achievements"] >= 9 and ltm.data["achievement_points"] >= 9 * 10 - 5, ltm.data          # eight badges + The Real Champion at least
    assert goals.achievements_at_least(9)(None, ltm) and not goals.achievements_at_least(129)(None, ltm)


def test_the_observation_shows_the_achievement_baseline_once(live):
    """#358: on the free field after the Pokédex the observation carries the RA progress once (the baseline), and the next tick of the same run stays silent."""
    import copy

    import main
    from agent.observation import build_observation
    live.load("post_misty")
    run = main._RunState()

    def obs():
        s = live.r.read_state()
        return build_observation(state=s, diff=live.r.diff(None, s), in_battle=False, run=run, reader=live.r, tilemap=live.rt.tilemap,
                                 ltm=copy.deepcopy(live.rt.ltm), stm=copy.deepcopy(live.rt.stm), map_key=(s.map_bank, s.map_id))
    first = obs()
    assert "Achievements " in first and "/128" in first and "quest('achievements')" in first, first[-600:]
    assert "Achievements " not in obs()                                    # the same run, nothing new: silent


def test_the_game_stat_and_national_dex_readers_and_the_new_checks_on_real_fixtures(live):
    """#358: the Hall-of-Fame counter (gameStats[10], XOR'd with the encryption key), the national dex bits and the checks built on them read sensibly from real states."""
    from game.constants import Addr
    live.load("post_misty")
    assert live.r.read_game_stat(Addr.GAME_STAT_ENTERED_HOF) == 0
    live.load("post_hof")                                                # the Hall of Fame entered once
    assert live.r.read_game_stat(Addr.GAME_STAT_ENTERED_HOF) == 1
    assert live.r.read_dex_owned_count_national() == live.r.read_pokedex()[0]          # 21 caught: all Kanto, none of Johto's
    assert live.r.read_dex_owned_national(243) is False                  # no Raikou
    st = _states(live)
    assert st[34797] == "yes"                                            # champion once ...
    assert st[34802] == "no"                                             # ... not twice
    assert st[34808] == "no" and st[34812] == "no" and st[541985] == "no"        # no beasts, Selphy not rescued, an empty Fame Checker
    assert st[34809] == "no"                                             # 21 of 171

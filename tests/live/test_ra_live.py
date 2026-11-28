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

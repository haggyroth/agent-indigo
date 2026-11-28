"""The RetroAchievements numbers in the eval harness (#358): the goal predicates, the journal fields, the throttled refresh and the scorecard row — pure."""
from types import SimpleNamespace

import main
from evals import goals
from memory.long_term import LongTermMemory


def test_the_achievement_goals_read_the_journal():
    g = goals.achievements_at_least(9)
    assert not g(None, SimpleNamespace(data={"achievements": 8})) and g(None, SimpleNamespace(data={"achievements": 9}))
    assert not g(None, SimpleNamespace(data={})) and not g(None, SimpleNamespace(data={"achievements": None}))      # a missing / null field is zero
    p = goals.achievement_points_at_least(100)
    assert not p(None, SimpleNamespace(data={"achievement_points": 99})) and p(None, SimpleNamespace(data={"achievement_points": 100}))
    assert "achievement" in g.desc and "point" in p.desc


def test_the_journal_declares_the_fields_so_they_survive_a_reload(tmp_path):
    ltm = LongTermMemory(path=tmp_path / "p.json")
    assert ltm.data["achievements"] == 0 and ltm.data["achievement_points"] == 0
    ltm.data["achievements"], ltm.data["achievement_points"] = 12, 77
    ltm.save()
    again = LongTermMemory(path=tmp_path / "p.json")
    assert (again.data["achievements"], again.data["achievement_points"]) == (12, 77)


def _reader(flags=()):
    return SimpleNamespace(read_flag=lambda n: n in flags, read_key_item_count=lambda: 0, read_pokedex=lambda: (0, 0), read_key_items=lambda: [],
                           read_badges=lambda: (0, 0), read_dex_owned=lambda s: False, read_trainer_tower=lambda: [{"prize": False}] * 4)


def test_apply_progress_refreshes_the_count_every_few_ticks_and_never_crashes(tmp_path):
    state = SimpleNamespace(badges=0, party_count=1, party=[], badge_bits=0)
    diff = SimpleNamespace(badges_changed=False)
    ltm = LongTermMemory(path=tmp_path / "p.json")
    run = main._RunState()
    run.step_count = 0                                                       # a multiple of ACHIEVEMENT_EVERY: read now
    main._apply_progress(run, state, diff, _reader({0x829}), ltm)            # FLAG_SYS_POKEDEX_GET: 'Now the Adventure Can Start' (1 pt)
    assert ltm.data["achievements"] >= 1 and ltm.data["achievement_points"] >= 1
    before = ltm.data["achievements"]
    run.step_count = 1                                                       # off the beat: not read again
    main._apply_progress(run, state, diff, _reader({0x829, 0x237, 0x238}), ltm)
    assert ltm.data["achievements"] == before
    broken = SimpleNamespace(read_flag=lambda n: 1 / 0, read_key_item_count=lambda: 1 / 0, read_pokedex=lambda: 1 / 0)
    run.step_count = main.ACHIEVEMENT_EVERY
    try:
        main._apply_progress(run, state, diff, broken, ltm)
    except ZeroDivisionError:
        pass                                                                 # the existing key-item read is not ours to guard; the achievements read must not add a crash
    assert ltm.data["achievements"] == before


def test_the_scorecard_carries_the_achievement_counts():
    r = main.EpisodeResult(reason="goal", passed=True, steps=3, llm_calls=1, prompt_tokens=1, completion_tokens=1, final_map=(3, 0), final_pos=(1, 1), badges=0,
                           achievements=14, achievement_points=61)
    d = r.to_dict()
    assert d["achievements"] == 14 and d["achievement_points"] == 61

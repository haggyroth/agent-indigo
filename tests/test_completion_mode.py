"""RUN_GOAL=completion and the post-game briefing (#357): information, never a wall."""
import importlib
from types import SimpleNamespace

import pytest

from knowledge import completion
from knowledge import story_beats as sb
from test_story_beats import checker

ALL_DONE = sb.evaluate(lambda spec: True)


def _status(**kw):
    return sb.evaluate(checker(milestones=["delivered_oaks_parcel"], **kw))


# ── pure ─────────────────────────────────────────────────────────────────────────────────────────

def test_the_target_is_the_hall_of_fame_the_kanto_dex_and_every_side_quest():
    ctx_done = sb.SideCtx(badges=8, owned=151, game_clear=True, flags=(0x89B,))
    assert completion.reached(True, 151, ALL_DONE, ctx_done)
    assert not completion.reached(False, 151, ALL_DONE, ctx_done)                       # no Hall of Fame
    assert not completion.reached(True, 150, ALL_DONE, ctx_done)                         # one species short
    partial = _status(badges=range(8), flags=[0x234, 0x237])
    assert not completion.reached(True, 151, partial, sb.SideCtx(badges=8, owned=151, game_clear=True))        # side quests still open
    assert completion.open_side_quests(partial, sb.SideCtx(badges=8, owned=151, game_clear=True))


def test_the_post_game_text_orders_what_is_available_and_says_what_the_national_dex_needs():
    st = _status(badges=range(8), flags=[0x234, 0x237, 0x82C])
    text = completion.post_game_text(21, False, st, sb.SideCtx(badges=8, owned=21, game_clear=True))
    assert text.startswith("POST-GAME") and "Pokédex 21/151" in text and "side quests open now:" in text
    assert "39 more species caught" in text and "Sevii Islands (One Island)" in text and "Prof. Oak" in text
    assert "no script yet" in text                                                       # honest about what is not scripted
    ready = completion.post_game_text(80, False, st, sb.SideCtx(badges=8, owned=80, game_clear=True, flags=(0x89B,)))
    assert "he is waiting in Pallet Town" in ready
    done = completion.post_game_text(80, True, st, sb.SideCtx(badges=8, owned=80, game_clear=True, flags=(0x89B,)))
    assert "National Pokédex" not in done


def test_the_national_dex_is_a_post_game_beat_gated_on_the_game_clear_60_caught_and_one_island():
    b = sb.BY_KEY["national_dex"]
    assert b.tier == "post" and b.needs == ("elite_four",) and ("flag", completion.NATIONAL_DEX_FLAG) in b.done
    locked = sb.gate_unmet(b, sb.SideCtx(badges=8, owned=70, game_clear=False))
    assert locked == "after the Hall of Fame"
    assert sb.gate_unmet(b, sb.SideCtx(badges=8, owned=59, game_clear=True)) == "needs 60 species caught (you have 59)"
    assert "One Island" in sb.gate_unmet(b, sb.SideCtx(badges=8, owned=60, game_clear=True))
    assert sb.gate_unmet(b, sb.SideCtx(badges=8, owned=60, game_clear=True, flags=(0x89B,))) == ""


# ── config, goal, stats ──────────────────────────────────────────────────────────────────────────

def test_run_goal_is_validated(monkeypatch):
    import config
    monkeypatch.setenv("RUN_GOAL", "everything")
    with pytest.raises(SystemExit):
        importlib.reload(config)
    monkeypatch.setenv("RUN_GOAL", "Completion ")
    assert importlib.reload(config).RUN_GOAL == "completion"
    monkeypatch.delenv("RUN_GOAL")
    assert importlib.reload(config).RUN_GOAL == "hall_of_fame"


pytest.importorskip("openai")
import main  # noqa: E402
from agent import observation as obs  # noqa: E402
from memory.long_term import LongTermMemory  # noqa: E402


def _reader(owned=151, clear=True, flags=()):
    fl = set(flags) | ({0x82C} if clear else set())
    return SimpleNamespace(read_flag=lambda n: n in fl, read_pokedex=lambda: (owned, 160), read_badges=lambda: (8, 255), read_party=lambda: [], read_key_items=lambda: [],
                           read_key_item_count=lambda: 0)


def test_the_completion_goal_is_false_until_everything_is_done_and_never_throws(monkeypatch):
    import agent.story as story
    monkeypatch.setattr(story, "story_status", lambda reader, ltm, overrides=None: ALL_DONE)
    goal = main._completion_goal(SimpleNamespace(reader=_reader(151, True, [0x89B])))
    assert goal(None, SimpleNamespace(data={})) is True
    assert main._completion_goal(SimpleNamespace(reader=_reader(150, True, [0x89B])))(None, None) is False
    assert main._completion_goal(SimpleNamespace(reader=_reader(151, False)))(None, None) is False
    broken = SimpleNamespace(reader=SimpleNamespace(read_flag=lambda n: 1 / 0, read_pokedex=lambda: 1 / 0, read_badges=lambda: 1 / 0))
    assert main._completion_goal(broken)(None, None) is False                            # a read failure is 'not yet', not a crash


def test_apply_progress_keeps_the_dex_count_and_records_the_national_dex(tmp_path):
    ltm = LongTermMemory(path=tmp_path / "p.json")
    run = main._RunState()
    state = SimpleNamespace(badges=8, party_count=1, party=[], badge_bits=255)
    main._apply_progress(run, state, SimpleNamespace(badges_changed=False), _reader(77, True, [0x840]), ltm)
    assert ltm.data["dex_owned"] == 77
    assert {"hall_of_fame", "national_dex"} <= set(ltm.data["milestones"])
    assert LongTermMemory(path=tmp_path / "p.json").data["dex_owned"] == 77              # persisted (DEFAULTS declares it)


def test_the_scorecard_carries_post_game_steps_and_dex():
    r = main.EpisodeResult(reason="max_steps", passed=False, steps=5, llm_calls=1, prompt_tokens=1, completion_tokens=1, final_map=(3, 0), final_pos=(1, 1), badges=8,
                           post_game_steps=4, dex_owned=21)
    d = r.to_dict()
    assert d["post_game_steps"] == 4 and d["dex_owned"] == 21


def test_dex_goal_and_the_post_game_scenario():
    from evals import goals, scenarios
    g = goals.dex_owned_at_least(30)
    assert not g(None, SimpleNamespace(data={"dex_owned": 29})) and g(None, SimpleNamespace(data={"dex_owned": 30}))
    sc = scenarios.by_name("post_game_national_dex")
    assert sc and sc.start_state.endswith("post_hof.ss1") and sc.xfail


# ── observation + prompt ─────────────────────────────────────────────────────────────────────────

def _tick(reader, step=1):
    return SimpleNamespace(run=SimpleNamespace(postgame_sig=None, step_count=step), reader=reader, state=SimpleNamespace(party=[]), ltm=SimpleNamespace(data={}))


def test_the_post_game_line_is_silent_before_the_hall_of_fame_and_throttled_after(monkeypatch):
    monkeypatch.setattr(obs, "_story_status_for", lambda t: _status(badges=range(8), flags=[0x234, 0x237]))
    assert obs._post_game_line(_tick(_reader(30, clear=False))) == []
    t = _tick(_reader(30, clear=True))
    first = obs._post_game_line(t)
    assert len(first) == 1 and first[0].startswith("POST-GAME")
    t.run.step_count = 2
    assert obs._post_game_line(t) == []                                                  # nothing changed: silent
    t.run.step_count = 60
    assert len(obs._post_game_line(t)) == 1                                              # ...but a reminder every 60 ticks
    t.reader = _reader(31, clear=True)
    t.run.step_count = 61
    assert len(obs._post_game_line(t)) == 1                                              # a new species: shown again


def test_the_prompt_tells_the_post_game_story_only_once_the_game_is_cleared():
    from knowledge.system_prompt import build_system_prompt
    base = {"badges_earned": 8, "gyms_beaten": [], "towns_visited": [], "battles_won": 0, "battles_lost": 0, "starter": "x"}
    journal = SimpleNamespace(get_loss_lessons=lambda e: "")
    before = build_system_prompt(SimpleNamespace(data={**base, "milestones": ["beat_giovanni"]}), journal, use_vision=False)
    after = build_system_prompt(SimpleNamespace(data={**base, "milestones": ["beat_giovanni", "hall_of_fame"]}), journal, use_vision=False)
    assert "The game is cleared" not in before and "### The game is cleared" in after
    assert after.index("### The game is cleared") > after.index("## Current status")        # in the changing tail: the cacheable prefix stays identical

"""The eval harness can gate a change and its numbers are comparable (#378)."""
import sys
import types

import pytest

pytest.importorskip("openai")

import main  # noqa: E402
from evals import goals, runner, scenarios  # noqa: E402
from evals.provenance import file_sha1, provenance  # noqa: E402
from game.state import GameContext, GameState  # noqa: E402
from memory.short_term import ShortTermMemory  # noqa: E402


def _r(status, name="a", **kw):
    return dict(scenario=name, status=status, reason="x", steps=1, stats={}, final_map=(0, 0), stuck_ratio=0.0, llm_calls=0, total_tokens=0, elapsed_s=0.0, **kw)


# ── exit status ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("statuses,strict,code", [
    (["PASS", "XPASS", "xfail"], False, 0), (["PASS", "FAIL"], False, 1), (["SKIPPED"], False, 0), (["SKIPPED", "PASS"], True, 3),
    (["FAIL", "SKIPPED"], True, 1), ([], True, 3), ([], False, 0), (["PASS"], True, 0)])
def test_exit_code(statuses, strict, code):
    assert runner.exit_code([_r(s) for s in statuses], strict) == code


def test_cli_exits_with_that_code_and_accepts_a_positional_name_and_trials(monkeypatch):
    from evals import __main__ as cli
    seen = {}

    def fake_run_all(scs=None, verbose=False, trials=1):
        seen.update(scs=[s.name for s in scs] if scs else None, trials=trials)
        return [_r("FAIL")]
    monkeypatch.setattr(runner, "run_all", fake_run_all)
    monkeypatch.setattr(sys, "argv", ["evals", "full_chain", "-n", "3"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 1 and seen == {"scs": ["full_chain"], "trials": 3}
    monkeypatch.setattr(sys, "argv", ["evals", "no_such_scenario"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 2


# ── trials ───────────────────────────────────────────────────────────────────────────────────────

def test_pass_rate_counts_only_trials_that_ran():
    rows = [_r("PASS", "a"), _r("FAIL", "a"), _r("PASS", "a"), _r("SKIPPED", "a"), _r("FAIL", "b")]
    assert runner.pass_rates(rows) == {"a": (2, 3), "b": (0, 1)}


def test_run_all_runs_each_scenario_n_times(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "EVAL_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(runner, "run_scenario", lambda sc, verbose=False, trial=1: calls.append((sc.name, trial)) or _r("PASS", sc.name))
    sc = scenarios.Scenario(name="s", goal=goals.badges_at_least(1), max_steps=1)
    runner.run_all([sc], trials=3)
    assert calls == [("s", 1), ("s", 2), ("s", 3)]


# ── provenance ───────────────────────────────────────────────────────────────────────────────────

def test_the_scorecard_carries_what_made_it(tmp_path):
    fix = tmp_path / "f.ss1"
    fix.write_bytes(b"fixture")
    sc = scenarios.Scenario(name="s", goal=goals.badges_at_least(1), max_steps=1, start_state=str(fix))
    p = provenance(sc)
    for k in ("model", "temperature", "max_tokens", "use_vision", "git_sha", "rom_sha1", "fixture", "fixture_sha1", "python"):
        assert k in p
    assert p["fixture"] == "f.ss1" and p["fixture_sha1"] == file_sha1(fix) and len(p["fixture_sha1"]) == 40
    assert file_sha1(tmp_path / "missing") == ""


# ── a goal that is already true measures nothing ─────────────────────────────────────────────────

def _state(map_id=0, x=1, y=1, ctx=GameContext.OVERWORLD):
    return GameState(context=ctx, badges=0, badge_bits=0, party=[], party_count=0, map_bank=3, map_id=map_id, player_x=x, player_y=y, screen_fading=False)


def test_a_scenario_whose_goal_is_met_at_the_start_is_skipped_not_passed(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "EVAL_DIR", tmp_path)
    closed = []
    rt = types.SimpleNamespace(reader=types.SimpleNamespace(read_state=lambda: _state()), ltm=types.SimpleNamespace(data={"badges_earned": 8}),
                               mgba=types.SimpleNamespace(close=lambda: closed.append(1)))
    monkeypatch.setattr(main, "build_runtime", lambda **k: rt)
    monkeypatch.setattr(main, "run_episode", lambda *a, **k: pytest.fail("must not run an episode whose goal is already true"))
    r = runner.run_scenario(scenarios.Scenario(name="s", goal=goals.badges_at_least(1), max_steps=5))
    assert r["status"] == "SKIPPED" and r["reason"] == "goal_met_at_start" and closed == [1]


def test_an_unavailable_emulator_is_skipped_not_dropped(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(main, "build_runtime", lambda **k: None)
    r = runner.run_scenario(scenarios.Scenario(name="s", goal=goals.badges_at_least(1), max_steps=5))
    assert r["status"] == "SKIPPED" and r["reason"] == "emulator_unavailable"


def test_the_default_start_save_prefers_the_stable_live_fixture(monkeypatch, tmp_path):
    import importlib
    (tmp_path / "work.sav").write_bytes(b"sav")
    monkeypatch.delenv("EVAL_START_SAVE", raising=False)
    monkeypatch.setenv("LIVE_DIR", str(tmp_path))
    importlib.reload(scenarios)
    assert scenarios.DEFAULT_SAVE == str(tmp_path / "work.sav")
    monkeypatch.setenv("EVAL_START_SAVE", "/explicit.sav")
    importlib.reload(scenarios)
    assert scenarios.DEFAULT_SAVE == "/explicit.sav"
    monkeypatch.undo()
    importlib.reload(scenarios)


# ── stuck ratio ──────────────────────────────────────────────────────────────────────────────────

def _episode(monkeypatch, tmp_path, ticks):
    """Run run_episode over scripted ticks: [(state, actions)], ending at max_steps."""
    it = iter(ticks)

    def step(obs, shot, area_map_b64=None, area_map_name=""):
        return "", next(it)[1]
    client = types.SimpleNamespace(
        _in_evolution_scene=lambda: False, llm_calls=0, total_tokens=0, total_prompt_tokens=0, total_completion_tokens=0, total_cached_tokens=0,
        run_log=None, _current_opponent="", step=step, set_system=lambda p: None, capture_screenshot=lambda: None, _maintain_exp_share=lambda: None)
    # each tick reads the state the PREVIOUS step left behind (the first read is the starting state)
    seq = [ticks[0][0]] + [t[0] for t in ticks]                     # run_episode reads the starting state once before the first tick
    reads = {"i": 0}

    def read_state():
        s = seq[min(reads["i"], len(seq) - 1)]
        reads["i"] += 1
        return s
    ltm = types.SimpleNamespace(data={"badges_earned": 0, "milestones": []}, save=lambda: None, add_town=lambda n: False)
    reader = types.SimpleNamespace(read_state=read_state, diff=lambda a, b: None, read_enemy_lead=lambda: None, read_current_map=lambda: (3, 0), read_party=lambda: [])
    rt = main.AgentRuntime(mgba=types.SimpleNamespace(tick=lambda *a: None, read32=lambda a: 0), reader=reader, client=client, ltm=ltm, stm=ShortTermMemory(),
                           journal=types.SimpleNamespace(), tilemap=types.SimpleNamespace(refresh=lambda: None))
    monkeypatch.setattr(main, "ERRORS_LOG", tmp_path / "errors.log")
    for name, val in (("apply_battle_style", lambda *a: False), ("_apply_progress", lambda *a, **k: None), ("build_observation", lambda **k: "obs"),
                      ("build_system_prompt", lambda *a, **k: "sys"), ("USE_VISION", False), ("MAX_LLM_CALLS", 0), ("TOKEN_BUDGET", 0)):
        monkeypatch.setattr(main, name, val)
    monkeypatch.setattr(main.events, "observe", lambda *a, **k: None)
    return main.run_episode(rt, verbose=False, max_steps=len(ticks), max_wall_s=60)


def test_stuck_only_counts_ticks_after_a_movement_tool(monkeypatch, tmp_path):
    here, there = _state(x=1), _state(x=2)
    # tick1: shop (not movement) -> tick2 same tile is NOT stuck; tick2: go_to -> tick3 same tile IS stuck; tick3: go_to -> tick4 moved
    res = _episode(monkeypatch, tmp_path, [(here, ["shop"]), (here, ["go_to"]), (here, ["go_to"]), (there, ["advance_dialog"])])
    assert res.stuck_ratio == round(1 / 2, 3)                       # 2 ticks followed a movement tool; 1 of them went nowhere


def test_a_warp_to_the_same_coordinates_is_not_stuck(monkeypatch, tmp_path):
    a, b = _state(map_id=0, x=5, y=5), _state(map_id=1, x=5, y=5)
    res = _episode(monkeypatch, tmp_path, [(a, ["go_to"]), (b, ["go_to"])])
    assert res.stuck_ratio == 0.0


def test_no_movement_tools_means_no_stuck_ratio(monkeypatch, tmp_path):
    here = _state()
    assert _episode(monkeypatch, tmp_path, [(here, ["shop"]), (here, ["heal"]), (here, [])]).stuck_ratio == 0.0

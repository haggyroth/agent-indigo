"""Every iteration of the main loop is subject to the run caps, and a whiteout that never recovers gives up (#373)."""
import time
import types

import pytest

pytest.importorskip("openai")

import main  # noqa: E402
from game.state import GameContext, GameState, PokemonStatus  # noqa: E402
from memory.short_term import ShortTermMemory  # noqa: E402


def _mon(hp):
    return PokemonStatus(slot=0, level=10, current_hp=hp, max_hp=30, status="healthy", species_id=1, species_name="BULBASAUR")


def _state(hp=0):
    return GameState(context=GameContext.OVERWORLD, badges=0, badge_bits=0, party=[_mon(hp)], party_count=1, map_bank=3, map_id=0,
                     player_x=1, player_y=1, screen_fading=False)


class World:
    """A fake game: the party stays wiped until `heal_after` A-taps (None = never)."""
    def __init__(self, heal_after=None, fresh_hp=None):
        self.taps, self.heal_after, self.fresh_hp = 0, heal_after, fresh_hp
        self.steps = []

    def hp(self):
        return 30 if self.heal_after is not None and self.taps >= self.heal_after else 0


def _runtime(world, monkeypatch, tmp_path):
    def read_state():
        return _state(world.hp())
    reader = types.SimpleNamespace(
        read_state=read_state, diff=lambda a, b: None, read_enemy_lead=lambda: None, read_current_map=lambda: (3, 0),
        read_party=lambda: [_mon(world.hp())])
    if world.fresh_hp is not None:
        reader.read_party_fresh = lambda: [_mon(world.fresh_hp)]

    def step(obs, shot, area_map_b64=None, area_map_name=""):
        world.steps.append(obs)
        return "", []
    client = types.SimpleNamespace(
        _in_evolution_scene=lambda: False, llm_calls=0, total_tokens=0, total_prompt_tokens=0, total_completion_tokens=0,
        total_cached_tokens=0, run_log=None, _current_opponent="", step=step, set_system=lambda p: None,
        capture_screenshot=lambda: None, _maintain_exp_share=lambda: None)
    mgba = types.SimpleNamespace(tick=lambda *a: None, read32=lambda a: 0, tap=lambda b: setattr(world, "taps", world.taps + 1))
    ltm = types.SimpleNamespace(data={"badges_earned": 0, "milestones": []}, save=lambda: None, add_town=lambda n: False)
    monkeypatch.setattr(main, "ERRORS_LOG", tmp_path / "errors.log")
    monkeypatch.setattr(main, "apply_battle_style", lambda *a: False)
    monkeypatch.setattr(main.events, "observe", lambda *a, **k: None)
    monkeypatch.setattr(main, "_apply_progress", lambda *a, **k: None)
    monkeypatch.setattr(main, "build_observation", lambda **k: "obs")
    monkeypatch.setattr(main, "build_system_prompt", lambda *a, **k: "sys")
    monkeypatch.setattr(main, "USE_VISION", False)
    monkeypatch.setattr(main, "MAX_LLM_CALLS", 0)
    monkeypatch.setattr(main, "TOKEN_BUDGET", 0)
    return main.AgentRuntime(mgba=mgba, reader=reader, client=client, ltm=ltm, stm=ShortTermMemory(),
                             journal=types.SimpleNamespace(), tilemap=types.SimpleNamespace(refresh=lambda: None))


def test_a_wipe_that_never_recovers_still_obeys_the_wall_clock(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "MAX_BLACKOUT_PASSES", 10 ** 9)            # isolate the wall-clock guard from the pass cap
    rt = _runtime(World(), monkeypatch, tmp_path)
    t0 = time.time()
    res = main.run_episode(rt, verbose=False, max_wall_s=0.3)
    assert res.reason == "max_wall" and time.time() - t0 < 5


def test_a_wipe_that_never_recovers_ends_as_stalled_after_the_pass_cap(monkeypatch, tmp_path):
    world = World()
    rt = _runtime(world, monkeypatch, tmp_path)
    res = main.run_episode(rt, verbose=False, max_wall_s=60)
    assert res.reason == "stalled" and not res.passed
    assert world.taps == main.MAX_BLACKOUT_PASSES * 6 and world.steps == []     # it never reached the model


def test_a_whiteout_that_recovers_hands_control_back_and_resets_the_counter(monkeypatch, tmp_path):
    world = World(heal_after=14)                                         # three passes of six taps, then the Center healed us
    rt = _runtime(world, monkeypatch, tmp_path)
    res = main.run_episode(rt, verbose=False, max_steps=1, max_wall_s=60)
    assert res.reason == "max_steps" and world.steps == ["obs"]


def test_the_wipe_is_confirmed_with_a_fresh_read_not_a_stale_party(monkeypatch, tmp_path):
    world = World(fresh_hp=30)                                           # state.party says wiped (stale), memory says healthy
    rt = _runtime(world, monkeypatch, tmp_path)
    res = main.run_episode(rt, verbose=False, max_steps=1, max_wall_s=60)
    assert res.reason == "max_steps" and world.taps == 0                 # no A-mashing through a whiteout that is not happening


def test_the_caps_are_checked_before_any_continue_path(monkeypatch, tmp_path):
    rt = _runtime(World(heal_after=0), monkeypatch, tmp_path)
    run = main._RunState(step_count=5)
    assert main._guard_stop(run, rt.client, 0.0, 5)[0] == "max_steps"
    rt.client.llm_calls = 3
    monkeypatch.setattr(main, "MAX_LLM_CALLS", 3)
    assert main._guard_stop(main._RunState(), rt.client, 0.0, 0)[0] == "max_llm_calls"
    assert main._guard_stop(main._RunState(), rt.client, time.time() - 1, 0)[0] == "max_llm_calls"      # order: spend caps before the clock
    monkeypatch.setattr(main, "MAX_LLM_CALLS", 0)
    assert main._guard_stop(main._RunState(), rt.client, time.time() - 1, 0)[0] == "max_wall"
    assert main._guard_stop(main._RunState(), rt.client, 0.0, 0) is None


def test_a_failing_read_inside_an_exit_path_does_not_mask_the_exit_reason(monkeypatch, tmp_path):
    rt = _runtime(World(heal_after=0), monkeypatch, tmp_path)
    calls = []
    good = rt.reader.read_state

    def flaky():
        calls.append(1)
        if len(calls) > 2:                       # fine at the start and for the first tick, then the emulator hiccups
            raise RuntimeError("emulator hiccup")
        return good()
    rt.reader.read_state = flaky

    def interrupted(*a, **k):
        raise KeyboardInterrupt
    rt.client.step = interrupted
    res = main.run_episode(rt, verbose=False, max_wall_s=60)
    assert res.reason == "interrupted"           # not a RuntimeError out of _result

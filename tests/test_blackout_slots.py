"""A blackout is never undone by loading a save (a loss keeps its Exp; the whiteout heals the party). The model's load_state tool only accepts
slots saved by THIS process (a months-old leftover slot file once reset a run to the new-game intro)."""
from types import SimpleNamespace

import pytest

pytest.importorskip("openai")

import main                                      # noqa: E402
from agent.lm_studio_client import AgentClient    # noqa: E402
from game.state import PokemonStatus              # noqa: E402


class FakeMgba:
    def __init__(self, saved=()):
        self.saved, self.loaded, self.taps = list(saved), [], []

    def saved_this_session(self, slot):
        return slot in self.saved

    def load_state(self, slot=0):
        self.loaded.append(slot)
        return True

    def tick(self, *_a):
        pass

    def tap(self, b):
        self.taps.append(b)


def wiped_state():
    p = PokemonStatus(slot=0, level=10, current_hp=0, max_hp=30, status="healthy", species_id=1, species_name="BULBASAUR")
    return SimpleNamespace(party=[p])


def run_handler(mgba):
    run = main._RunState()
    reader = SimpleNamespace(read_party=lambda: [])
    ltm = SimpleNamespace(save=lambda: None)
    main._handle_blackout(run, wiped_state(), mgba, reader, ltm)
    return run


def test_blackout_never_reloads_a_save_even_when_one_exists_so_the_exp_a_loss_earned_is_kept():
    for saved in ([1], [3, 9], []):
        m = FakeMgba(saved=saved)                  # a pre-gym / pre-door / pre-fight save exists, or none does
        run_handler(m)
        assert m.loaded == [] and m.taps           # the game's whiteout is advanced with A instead


def test_load_state_tool_refuses_a_slot_this_session_never_saved():
    c = AgentClient.__new__(AgentClient)
    c.mgba = FakeMgba(saved=[1])
    out = c._execute("load_state", '{"slot": 0}')
    assert "THIS session" in out and c.mgba.loaded == []
    assert "loaded" in c._execute("load_state", '{"slot": 1}').lower() and c.mgba.loaded == [1]


def test_native_client_tracks_only_the_slots_it_wrote(monkeypatch):
    try:
        import game.mgba_core as core
    except Exception:
        pytest.skip("native binding unavailable")
    c = core.NativeMGBAClient.__new__(core.NativeMGBAClient)
    c._h, c._session_saves, c._save_seq = None, {}, 0
    monkeypatch.setattr(core, "lib", SimpleNamespace(pycore_save_state=lambda h, p: 1))
    assert not c.saved_this_session(0)                                           # slot_0.ss1 on disk does not count
    assert c.save_state(1) and c.save_state(3) and c.save_state(1)
    assert c.saved_this_session(1) and c.saved_this_session(3) and not c.saved_this_session(0)
    monkeypatch.setattr(core, "lib", SimpleNamespace(pycore_save_state=lambda h, p: 0))
    assert not c.save_state(7) and not c.saved_this_session(7)                  # a failed save is not recorded


def test_a_gym_loss_is_remembered_and_blocks_the_retry_until_the_team_grows():
    ltm = SimpleNamespace(data={}, save=lambda: None)
    party = [PokemonStatus(slot=i, level=lv, current_hp=0, max_hp=30, status="healthy", species_id=1, species_name="BULBASAUR")
             for i, lv in enumerate((35, 20, 16, 17))]
    state = SimpleNamespace(party=party)
    reader = SimpleNamespace(read_party=lambda: [], read_current_map=lambda: (10, 16))      # Celadon Gym
    main._handle_blackout(main._RunState(), state, FakeMgba(saved=[1]), reader, ltm)
    assert ltm.data["gym_losses"] == {"10/16": 88}
    # a loss on the overworld records nothing
    ltm2 = SimpleNamespace(data={}, save=lambda: None)
    main._handle_blackout(main._RunState(), state, FakeMgba(saved=[1]),
                          SimpleNamespace(read_party=lambda: [], read_current_map=lambda: (3, 26)), ltm2)
    assert "gym_losses" not in ltm2.data

    c = AgentClient.__new__(AgentClient)
    c.ltm = ltm
    now = {"lv": (35, 20, 16, 17)}
    c.reader = SimpleNamespace(read_current_map=lambda: (10, 16), detect_context=lambda: SimpleNamespace(name="OVERWORLD"),
                               read_party=lambda: [PokemonStatus(slot=i, level=lv, current_hp=30, max_hp=30, status="healthy", species_id=1,
                                                                  species_name="BULBASAUR") for i, lv in enumerate(now["lv"])])
    out = c._challenge_leader()
    assert "blacked out in this gym" in out and "96" in out                                 # 88 + 8 levels to gain
    now["lv"] = (35, 24, 22, 23)                                                            # 104 ≥ 96: the team grew
    c._lagging_mons = lambda party=None: []                                                 # (not under test: the lopsided-team warning)
    c._walk_to = lambda *a: "walked"
    c.mgba = SimpleNamespace(tap=lambda b: None, tick=lambda *_a: None, read32=lambda a: 0, read8=lambda a: 0, read16=lambda a: 0)
    assert "blacked out" not in c._challenge_leader()

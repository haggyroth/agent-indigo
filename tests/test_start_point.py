"""A start point the operator asked for either loads or the run does not start (#370) — no silent new game from the title screen."""
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("openai")

import main  # noqa: E402
from evals import runner, scenarios  # noqa: E402


class FakeEmu:
    """Stands in for NativeMGBAClient: a ROM that verifies, with load results the test controls."""
    state_ok = True
    save_ok = True
    loaded: list = []

    def __init__(self, *a, **k):
        pass

    def verify_connection(self):
        return True

    def get_game_title(self):
        return "POKEMON LEAF"

    def get_game_code(self):
        return "AGB-BPGE"

    def load_state_file(self, path):
        FakeEmu.loaded.append(("state", path))
        return FakeEmu.state_ok

    def load_save(self, path):
        FakeEmu.loaded.append(("save", path))
        return FakeEmu.save_ok

    def tick(self, *a):
        pass

    def run_frames(self, *a):
        pass

    def reset(self):
        pass


@pytest.fixture
def emu(monkeypatch):
    FakeEmu.state_ok = FakeEmu.save_ok = True
    FakeEmu.loaded = []
    monkeypatch.setitem(sys.modules, "game.mgba_core", SimpleNamespace(NativeMGBAClient=FakeEmu))
    return FakeEmu


def _build(tmp_path, **kw):
    return main.build_runtime(ltm_path=str(tmp_path / "ltm.json"), journal_path=str(tmp_path / "j.jsonl"), verbose=False, **kw)


def test_missing_state_file_raises_even_when_quiet(emu, tmp_path):
    with pytest.raises(main.StartPointError, match="not found"):
        _build(tmp_path, start_state=str(tmp_path / "nope.ss1"))
    assert emu.loaded == []                       # never even asked the core


def test_state_the_core_rejects_raises(emu, tmp_path):
    f = tmp_path / "bad.ss1"
    f.write_bytes(b"x")
    emu.state_ok = False
    with pytest.raises(main.StartPointError, match="could not load save state"):
        _build(tmp_path, start_state=str(f))


def test_missing_and_rejected_battery_save_raise(emu, tmp_path):
    with pytest.raises(main.StartPointError, match="not found"):
        _build(tmp_path, start_save=str(tmp_path / "nope.sav"))
    f = tmp_path / "g.sav"
    f.write_bytes(b"x")
    emu.save_ok = False
    with pytest.raises(main.StartPointError, match="could not load save"):
        _build(tmp_path, start_save=str(f))


def test_no_start_point_requested_is_not_an_error(emu, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "TilemapReader", lambda m: SimpleNamespace(), raising=True)
    monkeypatch.setattr(main, "AgentClient", lambda *a: SimpleNamespace(), raising=True)
    monkeypatch.setattr(main, "LeafGreenReader", lambda *a, **k: SimpleNamespace(read_badges=lambda: (0, 0)), raising=True)
    rt = _build(tmp_path, start_state="", start_save="")      # no start point requested: boots the ROM as-is, as before
    assert rt is not None and emu.loaded == []


def test_main_exits_2_with_the_reason(monkeypatch, capsys):
    def boom(**kw):
        raise main.StartPointError("start state not found: /x.ss1")
    monkeypatch.setattr(main, "build_runtime", boom)
    monkeypatch.setattr(main, "_resume_state", lambda: "")
    with pytest.raises(SystemExit) as e:
        main.main()
    assert e.value.code == 2


# ── the eval harness ─────────────────────────────────────────────────────────────────────────────

def _scenario(**kw):
    return scenarios.Scenario(name="t", goal=scenarios.goals.badges_at_least(1), max_steps=5, **kw)


def test_scenario_reports_its_missing_fixtures(tmp_path):
    here = tmp_path / "here.ss1"
    here.write_bytes(b"x")
    assert _scenario(start_state=str(here)).missing_fixtures() == []
    assert _scenario(start_state=str(tmp_path / "gone.ss1")).missing_fixtures() == [str(tmp_path / "gone.ss1")]
    assert _scenario().missing_fixtures() == []


def test_run_scenario_skips_a_missing_fixture_without_booting(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "build_runtime", lambda **k: pytest.fail("must not boot an emulator for a missing fixture"))
    r = runner.run_scenario(_scenario(start_state=str(tmp_path / "gone.ss1")))
    assert r["status"] == "SKIPPED" and r["reason"].startswith("fixture_missing") and r["steps"] == 0


def test_run_scenario_skips_when_the_start_point_will_not_load(monkeypatch, tmp_path):
    f = tmp_path / "bad.ss1"
    f.write_bytes(b"x")

    def refuse(**k):
        raise main.StartPointError("could not load save state: bad.ss1")
    monkeypatch.setattr(main, "build_runtime", refuse)
    monkeypatch.setattr(runner, "EVAL_DIR", tmp_path / "eval")
    r = runner.run_scenario(_scenario(start_state=str(f)))
    assert r["status"] == "SKIPPED" and r["reason"].startswith("start_point_failed")


def test_report_handles_skipped_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "EVAL_DIR", tmp_path / "eval")
    runner._report([runner._skipped(_scenario(), "fixture_missing: x")])      # must not raise on the placeholder row


def test_strict_flag_exits_nonzero_on_a_skip(monkeypatch):
    from evals import __main__ as cli
    monkeypatch.setattr(sys, "argv", ["evals", "--strict"])
    import evals.runner as r
    monkeypatch.setattr(r, "run_all", lambda verbose=False: [{"status": "SKIPPED"}])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 1
    monkeypatch.setattr(r, "run_all", lambda verbose=False: [{"status": "PASS"}])
    cli.main()                                                                   # no exit when nothing was skipped

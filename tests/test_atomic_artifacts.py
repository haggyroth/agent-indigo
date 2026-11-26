"""Run artefacts are never half-written, and the exit status says why a run stopped (#382)."""
import json
import os

import pytest

from memory import atomic
from memory.checkpoints import CheckpointManager, find_latest
from memory.run_log import RunLog


def _crash_on_replace(monkeypatch):
    def boom(a, b):
        raise OSError("disk went away")
    monkeypatch.setattr(os, "replace", boom)


def test_atomic_write_keeps_the_old_file_when_the_swap_fails(tmp_path, monkeypatch):
    p = tmp_path / "x.json"
    atomic.atomic_write_json(p, {"v": 1})
    _crash_on_replace(monkeypatch)
    with pytest.raises(OSError):
        atomic.atomic_write_json(p, {"v": 2})
    monkeypatch.undo()
    assert json.loads(p.read_text()) == {"v": 1}                # the old content, intact (not truncated)


def test_atomic_copy_and_no_temp_left_behind(tmp_path):
    src, dst = tmp_path / "a", tmp_path / "b"
    src.write_text("one")
    atomic.atomic_copy(src, dst)
    assert dst.read_text() == "one" and not list(tmp_path.glob(".*.tmp"))


def test_meta_json_survives_a_failed_rewrite(tmp_path, monkeypatch):
    log = RunLog(tmp_path)
    log.write_meta(model="m", step=1)
    _crash_on_replace(monkeypatch)
    log.write_meta(step=2)                                      # best-effort: must not raise
    monkeypatch.undo()
    assert json.loads((log.dir / "meta.json").read_text())["step"] == 1


def _mgr(tmp_path, save_ok=True, on_save=None, on_drop=None):
    def save_fn(path):
        open(path, "wb").write(b"state")
        return save_ok
    return CheckpointManager(tmp_path / "run1" / "checkpoints", save_fn, every_ticks=1, keep=2, on_save=on_save, on_drop=on_drop)


def test_latest_json_is_written_atomically_and_points_at_the_state(tmp_path):
    m = _mgr(tmp_path)
    path = m.save("ckpt_1", 1, {"k": 1})
    info = find_latest(tmp_path)
    assert info and info["path"] == str(path) and info["meta"] == {"k": 1}


def test_a_snapshot_failure_does_not_leave_an_orphan_state(tmp_path):
    dropped = []

    def bad_snapshot(p):
        raise OSError("journal copy failed")
    m = _mgr(tmp_path, on_save=bad_snapshot, on_drop=dropped.append)
    assert m.save("ckpt_1", 1) is None
    assert not list((tmp_path / "run1" / "checkpoints").glob("*.ss1")) and not (tmp_path / "run1" / "checkpoints" / "latest.json").exists()
    assert dropped                                              # the half-made journal snapshot is removed too


def test_a_core_that_fails_the_save_leaves_no_truncated_file(tmp_path):
    assert _mgr(tmp_path, save_ok=False).save("ckpt_1", 1) is None
    assert not list((tmp_path / "run1" / "checkpoints").glob("*.ss1"))


def test_a_failed_pointer_write_still_resumes_from_the_previous_checkpoint(tmp_path, monkeypatch):
    m = _mgr(tmp_path)
    first = m.save("ckpt_1", 1)
    _crash_on_replace(monkeypatch)
    assert m.save("ckpt_2", 2) is None
    monkeypatch.undo()
    assert find_latest(tmp_path)["path"] == str(first) and first.exists()


def test_the_battle_journal_appends_whole_lines(tmp_path):
    from memory.battle_journal import BattleJournal, BattleRecord
    j = BattleJournal(path=tmp_path / "b.jsonl")
    for i in range(3):
        j.log(BattleRecord("t", "loc", "RATTATA", 3, "BULBASAUR", "win", i, ["Tackle"], 0.5, "n"))
    lines = (tmp_path / "b.jsonl").read_text().splitlines()
    assert len(lines) == 3 and all(json.loads(x)["enemy_name"] == "RATTATA" for x in lines)


# ── exit status ──────────────────────────────────────────────────────────────────────────────────

main = pytest.importorskip("main")


@pytest.mark.parametrize("reason,code", [("goal", 0), ("max_steps", 0), ("max_llm_calls", 0), ("token_budget", 0), ("max_wall", 0),
                                         ("stalled", 1), ("error_budget", 1), ("llm_error", 1), ("interrupted", 130), ("something_new", 1)])
def test_exit_code_per_reason(reason, code):
    assert main.exit_code(reason) == code


def test_main_exits_with_the_reason_code(monkeypatch, tmp_path):
    import types
    for reason, expect in (("max_steps", None), ("error_budget", 1)):
        monkeypatch.setattr(main, "_resume_state", lambda: "")
        monkeypatch.setattr(main, "build_runtime", lambda **k: types.SimpleNamespace(ltm=types.SimpleNamespace(data={"milestones": []})))
        monkeypatch.setattr(main, "PROGRESS_PATH", tmp_path / "logs" / "progress.json")
        monkeypatch.setattr(main, "run_episode", lambda *a, **k: types.SimpleNamespace(reason=reason))
        if expect is None:
            main.main()                                          # a bounded run that reached its cap returns normally (exit 0)
        else:
            with pytest.raises(SystemExit) as e:
                main.main()
            assert e.value.code == expect

"""Loading a save or state selects the journal that belongs to it (memory.journals) — no emulator."""
from types import SimpleNamespace as NS

from memory import journals
from memory.checkpoints import CheckpointManager
from memory.long_term import LongTermMemory


def test_each_save_gets_its_own_profile_and_a_run_shares_one(tmp_path):
    a, b = tmp_path / "a" / "game.sav", tmp_path / "b" / "game.sav"
    assert journals.source_key(a) != journals.source_key(b)                       # same file name, different folders
    assert journals.source_key(a) == journals.source_key(a) and journals.source_key(a).startswith("game-")
    c1 = tmp_path / "logs" / "runs" / "20261125-235411" / "checkpoints" / "ckpt_00020_x.ss1"
    c2 = c1.with_name("badge3_00079.ss1")
    assert journals.source_key(c1) == journals.source_key(c2) == "run-20261125-235411"      # a run's checkpoints are one playthrough
    ltm, bat = journals.profile_paths(a, tmp_path / "j")
    assert ltm.name == "progress.json" and bat.name == "battles.jsonl" and ltm.parent == bat.parent


def test_select_reports_new_then_existing_and_never_touches_other_profiles(tmp_path):
    root, save = tmp_path / "j", tmp_path / "x.sav"
    ltm_path, _bat, origin = journals.select(save, root)
    assert origin == "new" and not ltm_path.exists()
    LongTermMemory(path=ltm_path).add_milestone("beat_brock")
    assert journals.select(save, root)[2] == "existing"
    assert journals.select(tmp_path / "other.sav", root)[2] == "new"            # another save does not see it


def test_a_checkpoint_restores_the_journal_as_it_was_when_saved(tmp_path):
    root = tmp_path / "j"
    state = tmp_path / "logs" / "runs" / "r1" / "checkpoints" / "ckpt_00020_x.ss1"
    state.parent.mkdir(parents=True)
    state.write_bytes(b"state")
    live = LongTermMemory(path=tmp_path / "live.json")
    live.add_milestone("beat_brock")
    jp = tmp_path / "live.jsonl"
    jp.write_text('{"a": 1}\n')
    journals.snapshot(state, live.path, jp)                                      # the checkpoint is written
    live.add_milestone("beat_misty")                                            # …the run carries on past it
    ltm_path, bat_path, origin = journals.select(state, root)
    assert origin == "checkpoint"
    assert LongTermMemory(path=ltm_path).data["milestones"] == ["beat_brock"]     # resuming sees exactly what was true then
    assert bat_path.read_text() == '{"a": 1}\n'
    journals.drop_snapshot(state)
    assert not (state.parent / (state.name + ".ltm.json")).exists()


def test_checkpoint_manager_writes_and_prunes_the_snapshot(tmp_path):
    saved, dropped = [], []
    def save_fn(p):
        open(p, "w").write("s")
        return True
    cm = CheckpointManager(tmp_path / "ck", save_fn, every_ticks=1, keep=1, on_save=saved.append, on_drop=dropped.append)
    first = cm.maybe(1, 0, "x")
    second = cm.maybe(2, 0, "x")
    assert saved == [first, second] and dropped == [first]                     # the pruned checkpoint's snapshot goes with it


def test_a_new_journal_is_derived_from_the_cartridge_not_copied_from_another_run(tmp_path):
    ltm = LongTermMemory(path=tmp_path / "p.json")
    flags = {0x892, 0x893}                                                       # Pewter, Cerulean visited
    reader = NS(read_party=lambda: [object()], read_badges=lambda: (0, 0b11), read_flag=lambda f: f in flags)
    added = journals.derive_from_cartridge(ltm, reader)
    assert set(added) == {"starter_chosen", "delivered_oaks_parcel", "Pewter City", "Cerulean City"}
    assert ltm.data["towns_visited"] == ["Pewter City", "Cerulean City"] and "got_cut" not in ltm.data["milestones"]
    assert journals.derive_from_cartridge(ltm, NS(read_party=lambda: (_ for _ in ()).throw(RuntimeError()))) == []   # an unreadable cartridge adds nothing, never raises

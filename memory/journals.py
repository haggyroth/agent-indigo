"""One journal per save / state (file logic only — no emulator, no network).

The agent's long-term journal (progress.json: badges, milestones, towns, battle counters) and its battle journal (battles.jsonl) used to be ONE global pair, whatever
save or state a run started from. Testing an old fixture then ran on the journal of the newest run: a badge-1 save arrived with Misty, Surge, Cut and 678 battles already
recorded, and "past losses" lessons from one playthrough leaked into another. Now loading a save or state selects its own journal:

  START_FROM_SAVE=a.sav           → logs/journals/a-<hash>/{progress.json,battles.jsonl}
  START_FROM_STATE=b.ss1          → logs/journals/b-<hash>/…
  RESUME=<run checkpoint>.ss1     → logs/journals/run-<timestamp>/…  (seeded from the snapshot written beside the checkpoint, so it holds exactly what was
                                    true when that state was saved)
  nothing / START_NEW_GAME        → the global logs/progress.json + logs/battles.jsonl, as before

A journal that does not exist yet is DERIVED from the cartridge (what the save provably has: badges, the starter, visited towns) rather than copied from another run.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from config import PROJECT_ROOT

JOURNALS_DIR = PROJECT_ROOT / "logs" / "journals"
SNAPSHOT_MAX_BYTES = 5_000_000          # a battle journal larger than this is not copied beside every checkpoint


def source_key(source) -> str:
    """The profile directory name for a save/state file: its stem + a hash of the absolute path (two saves called game.sav in different folders stay apart).
    A run's checkpoints (logs/runs/<ts>/checkpoints/*.ss1) all share ONE profile, 'run-<ts>', because they are one playthrough."""
    p = Path(source).expanduser()
    try:
        p = p.resolve()
    except OSError:
        pass
    if p.parent.name == "checkpoints" and p.parent.parent.parent.name == "runs":
        return "run-" + re.sub(r"[^\w.-]+", "_", p.parent.parent.name)
    stem = re.sub(r"[^\w.-]+", "_", p.stem)[:40] or "save"
    return f"{stem}-{hashlib.sha1(str(p).encode()).hexdigest()[:8]}"


def profile_paths(source, root: Path | None = None) -> tuple[Path, Path]:
    """(progress.json, battles.jsonl) for `source`."""
    d = (root or JOURNALS_DIR) / source_key(source)
    return d / "progress.json", d / "battles.jsonl"


def _sidecars(state) -> tuple[Path, Path]:
    p = Path(state)
    return p.with_name(p.name + ".ltm.json"), p.with_name(p.name + ".battles.jsonl")


def snapshot(state, ltm_path, journal_path) -> None:
    """Write the journal as of this moment beside a checkpoint state, so resuming it restores what was true THEN. Best-effort: never breaks a run."""
    try:
        ltm_side, bat_side = _sidecars(state)
        if Path(ltm_path).exists():
            shutil.copyfile(ltm_path, ltm_side)
        jp = Path(journal_path)
        if jp.exists() and jp.stat().st_size <= SNAPSHOT_MAX_BYTES:
            shutil.copyfile(jp, bat_side)
    except OSError:
        pass


def drop_snapshot(state) -> None:
    for p in _sidecars(state):
        p.unlink(missing_ok=True)


def select(source, root: Path | None = None) -> tuple[Path, Path, str]:
    """(progress path, journal path, origin) for the journal that goes with `source`. origin: 'existing' (this save has been played before), 'checkpoint' (restored from
    the snapshot beside a checkpoint state) or 'new' (nothing yet — the caller derives it from the cartridge)."""
    ltm_path, journal_path = profile_paths(source, root)
    ltm_side, bat_side = _sidecars(source)
    if ltm_side.exists():                                     # a checkpoint: the snapshot is the truth for THIS state, even over a later session of the same run
        try:
            ltm_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ltm_side, ltm_path)
            if bat_side.exists():
                shutil.copyfile(bat_side, journal_path)
            else:
                journal_path.unlink(missing_ok=True)
            return ltm_path, journal_path, "checkpoint"
        except OSError:
            pass
    return ltm_path, journal_path, ("existing" if ltm_path.exists() else "new")


def derive_from_cartridge(ltm, reader) -> list[str]:
    """Fill a NEW journal with what the loaded cartridge provably has: the starter and Oak's parcel once any badge is earned (a gym needs both) or a party exists, and
    every town whose Fly flag is set. Gym badges/milestones are adopted by the startup reconciliation that follows. Returns what was added."""
    added: list[str] = []
    try:
        has_party = bool(reader.read_party())
        badges = reader.read_badges()[1]
    except Exception:
        return added
    if has_party and ltm.add_milestone("starter_chosen", "from the save"):
        added.append("starter_chosen")
    if badges and ltm.add_milestone("delivered_oaks_parcel", "from the save"):
        added.append("delivered_oaks_parcel")
    try:
        from agent.skills.hm import FLY_SPOTS
        for key, (_map, _cell, flag) in FLY_SPOTS.items():
            if reader.read_flag(flag) and ltm.add_town(key.title()):
                added.append(key.title())
    except Exception:
        pass
    return added

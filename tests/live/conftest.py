"""Live tests: drive the REAL ROM through the native libmgba binding.

They are skipped automatically when the binding, the ROM, or the fixtures are missing (so CI, which has
no ROM, just skips them). Run locally with:

    python -m pytest tests/live -v

Fixtures live in `saves/live/` (gitignored — ROM-derived). See tests/live/README.md for what each one is.
"""
import hashlib
import os
import shutil
import sys
from pathlib import Path

import pytest

# Force a headless, text-only run BEFORE any project module (config reads .env at import — a developer's
# SHOW_WINDOW=true would otherwise open a paced window and make these tests crawl).
os.environ.update(USE_VISION="false", SHOW_WINDOW="false")
os.environ.pop("START_FROM_STATE", None)
os.environ.pop("RESUME", None)

ROOT = Path(__file__).resolve().parents[2]
LIVE_DIR = Path(os.environ.get("LIVE_DIR", ROOT / "saves" / "live"))
ROM = Path(os.path.expanduser(os.environ.get("ROM_PATH", "~/mgba-http/Pokemon_LeafGreen.gba")))


@pytest.fixture(scope="session", autouse=True)
def _work_sav_is_never_written():
    """No test may write the real work.sav (the cartridge save is file-backed: boot from a copy). A change fails the session, loudly, so a poisoned fixture is caught at once."""
    sav = LIVE_DIR / "work.sav"
    before = hashlib.md5(sav.read_bytes()).hexdigest() if sav.exists() else None
    yield
    if before is not None:
        assert hashlib.md5(sav.read_bytes()).hexdigest() == before, f"{sav} was modified during the live session: something booted from or loaded it directly instead of from a copy"


@pytest.fixture(scope="session")
def rt(tmp_path_factory):
    """One emulator runtime for the whole live session (booting takes a few seconds)."""
    if not ROM.exists():
        pytest.skip(f"ROM not found at {ROM}")
    sav = LIVE_DIR / "work.sav"
    if not sav.exists():
        pytest.skip(f"fixture {sav} missing — see tests/live/README.md")
    try:
        import game.mgba_core as mgba_core   # needs the compiled cffi binding
    except Exception as e:      # ImportError / OSError when libmgba isn't built
        pytest.skip(f"native binding unavailable: {e}")
    # tests/conftest.py imports config (→ .env) before this file runs, so a developer's SHOW_WINDOW=true
    # is already baked in: override the module constants directly. A paced window makes tests crawl.
    mgba_core.SHOW_WINDOW = False
    sys.path.insert(0, str(ROOT))
    import main
    tmp = tmp_path_factory.mktemp("live")
    # Boot from a COPY: the runtime's cartridge save is file-backed, so an in-game save (the Cable Club asks "Would you like to save?" before every link-up) would otherwise overwrite the
    # fixture and every later test would boot from it.
    boot_sav = tmp / "work.sav"
    shutil.copyfile(sav, boot_sav)
    os.environ["START_FROM_SAVE"] = str(boot_sav)
    try:
        runtime = main.build_runtime(start_save=str(boot_sav), ltm_path=str(tmp / "ltm.json"), journal_path=str(tmp / "j.jsonl"),
                                     verbose=False)
    except main.StartPointError as e:
        pytest.skip(f"start point could not be loaded: {e}")
    if runtime is None:
        pytest.skip("emulator runtime could not be built")
    return runtime


@pytest.fixture
def live(rt):
    """Per-test handle: `live.load('threemon')` restores a fixture state; helpers from harness.py."""
    from live.harness import Live
    return Live(rt, LIVE_DIR)

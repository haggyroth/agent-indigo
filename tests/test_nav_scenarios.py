"""Tier-1 deterministic nav-skill scenarios (ROM-gated; skip without hardware).

These exercise the navigation SKILL directly — no LLM in the loop — so a failure
is unambiguously a pathfinding/routing bug, not a reasoning one. They need the
native binding, the ROM, and the standard battery save, so they SKIP cleanly in
CI (which has none of those) and run locally.

The Route 2 → Pewter case is the reproduction of #59; it's marked xfail so it
documents the open bug and flips to an unexpected-pass the day routing learns to
warp through Viridian Forest instead of walking to the sealed north edge.
"""
import os
import pytest

pytest.importorskip("openai")   # AgentClient/main import openai

# The native binding must be built, or there's no emulator to drive.
pytest.importorskip("game._mgba_native", exc_type=ImportError)  # also skip on dlopen failure

import main  # noqa: E402
from evals import scenarios  # noqa: E402
from game.state import GameContext  # noqa: E402

SAVE = scenarios.DEFAULT_SAVE
_HAVE_SAVE = os.path.isfile(SAVE)

# These boot a real emulator and drive it for many seconds, and they're
# non-deterministic (wild encounters), so they must NOT run in the fast default
# suite even when the hardware is present. Opt in explicitly:
#   RUN_NAV_EVALS=1 pytest tests/test_nav_scenarios.py
_OPT_IN = os.getenv("RUN_NAV_EVALS") == "1"

pytestmark = [
    pytest.mark.skipif(not _OPT_IN,
                       reason="set RUN_NAV_EVALS=1 to run the ROM-gated nav skill tests"),
    pytest.mark.skipif(not _HAVE_SAVE, reason=f"standard save not present at {SAVE}"),
]


@pytest.fixture
def runtime(tmp_path):
    """A fresh emulator from the standard save for EVERY test (no test inherits another's position), with scratch journals: the real
    logs/journals/<save>/ journal of the maintainer is never written to."""
    try:
        rt = main.build_runtime(start_save=SAVE, start_state="", verbose=False, fresh_session=False,
                                ltm_path=str(tmp_path / "ltm.json"), journal_path=str(tmp_path / "battles.jsonl"))
    except main.StartPointError as e:
        pytest.skip(f"start point unavailable: {e}")
    if rt is None:
        pytest.skip("emulator/ROM not available")
    yield rt
    close = getattr(rt.mgba, "close", None)         # (NativeMGBAClient.close, #381)
    if close:
        close()


def _drive_go_to(rt, destination, tries=12):
    """Call the nav skill repeatedly and return the final (map, message). A WILD battle that interrupts it is fled (the same skill the model uses), so a
    route full of encounters is walked through instead of skipped; a trainer battle cannot be fled and fails the test loudly."""
    from game.constants import Addr
    msg = ""
    for _ in range(tries):
        msg = rt.client._go_to(destination)
        if rt.reader.detect_context() == GameContext.IN_BATTLE:
            if rt.mgba.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER:
                pytest.fail(f"a trainer battle interrupted go_to({destination!r}) — this no-LLM drive cannot fight: {msg}")
            rt.client._flee_battle()
            continue
        if "Arrived" in msg:
            break
    return rt.reader.read_current_map(), msg


def test_go_to_viridian_from_pallet(runtime):
    # Baseline: Pallet → Viridian City is a straight shot north up Route 1.
    cur, msg = _drive_go_to(runtime, "Viridian City")
    assert cur == (3, 1), f"expected Viridian City (3,1), got {cur} — {msg}"


@pytest.mark.xfail(strict=True, raises=pytest.fail.Exception,
                   reason="Viridian Forest has trainers that cannot be fled and this no-LLM drive cannot fight them; the full LLM eval "
                          "(python -m evals reach_pewter) is what confirms Pewter is reachable end to end. strict: if the drive ever gets through, say so.")
def test_go_to_pewter_crosses_viridian_forest(runtime):
    cur, msg = _drive_go_to(runtime, "Pewter City", tries=20)
    assert cur == (3, 2), f"expected Pewter City (3,2), got {cur} — {msg}"

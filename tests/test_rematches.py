"""VS Seeker rematch progress from the game's flags (#367): the generated ladders pinned to the decomp, the counting logic, the generator's parser, the observation line."""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from knowledge import rematches
from knowledge import story_beats as sb
from knowledge.rematch_data import REMATCHES, TIER_UNLOCK

CELADON, FUCHSIA, CLEAR, LINK = 2198, 2199, 0x82C, 2116


def test_the_generated_table_matches_the_decomp():
    assert len(REMATCHES) == 221
    assert TIER_UNLOCK == {1: 0x292, 2: CELADON, 3: FUCHSIA, 4: CLEAR, 5: LINK}        # TryGetRematchTrainerIdGivenGameState: VS Seeker, Celadon, Fuchsia, Hall of Fame, Network Machine
    for name, mp, tiers in REMATCHES:
        assert name.startswith("TRAINER_") and mp.startswith("MAP_") and 1 <= len(tiers) <= 6
        assert any(t is not None for t in tiers), name
        assert all(t is None or 0x500 <= t <= 0x7FF for t in tiers), name               # trainer defeat flags
    ben = next(r for r in REMATCHES if r[0] == "TRAINER_YOUNGSTER_BEN")
    assert ben[1] == "MAP_ROUTE3" and [t is None for t in ben[2]] == [False, False, True, False, False]       # {BEN, BEN_2, SKIP, BEN_3, BEN_4}


def test_a_ladder_drops_skipped_and_repeated_rungs():
    assert rematches.ladder([100, 101, None, 102, 103]) == [(0, 100), (1, 101), (3, 102), (4, 103)]
    assert rematches.ladder([100, 100]) == [(0, 100)]                                    # {CALVIN, CALVIN}: one party only
    assert rematches.ladder([None, 7, None, 8]) == [(1, 7), (3, 8)]


def _flags(*on):
    s = set(on)
    return lambda f: f in s


def test_status_counts_started_top_ready_and_waiting():
    ben = next(r for r in REMATCHES if r[0] == "TRAINER_YOUNGSTER_BEN")[2]
    base, second = ben[0], ben[1]
    st = rematches.status(_flags(base))                       # beaten once, no VS Seeker yet: rung 1 needs the VS Seeker
    assert st["started"] >= 1 and st["waiting"].get(0x292, 0) >= 1 and st["at_top"] == 0
    st = rematches.status(_flags(base, 0x292))                # the Seeker is in the bag: rung 1 is ready
    assert st["ready"] >= 1 and 0x292 not in st["waiting"]
    st = rematches.status(_flags(base, second, 0x292))        # the next rung (rung 3 = Fuchsia) is waiting for the Fuchsia visit
    assert st["waiting"].get(FUCHSIA, 0) >= 1
    top = [f for f in ben if f is not None]
    st = rematches.status(_flags(*top, 0x292, CELADON, FUCHSIA, CLEAR, LINK))
    assert st["at_top"] >= 1
    assert rematches.status(lambda f: False) == {"total": 221, "started": 0, "at_top": 0, "ready": 0, "waiting": {}}      # nothing fought: nothing to rematch


def test_the_line_names_what_waits_for_what():
    ben = next(r for r in REMATCHES if r[0] == "TRAINER_YOUNGSTER_BEN")[2]
    text = rematches.line(_flags(ben[0]))
    assert text.startswith("REMATCHES: 0/221 trainers at their top team") and "wait for the VS Seeker" in text
    text = rematches.line(_flags(ben[0], 0x292))
    assert "have a rematch ready — use the VS Seeker outdoors near them" in text


def test_the_vs_seeker_is_a_side_quest_with_its_flag():
    b = sb.BY_KEY["vs_seeker"]
    assert b.tier == "side" and ("flag", 0x292) in b.done and b.needs == ("misty",) and "VS Seeker" in b.payoff


def test_the_generator_parses_a_table(tmp_path):
    pf = tmp_path
    (pf / "include" / "constants").mkdir(parents=True)
    (pf / "src").mkdir()
    (pf / "include" / "constants" / "flags.h").write_text("#define TRAINER_FLAGS_START (FLAG_0x4FF + 1)\n#define FLAG_0x4FF 0x4FF\n#define SYS_FLAGS 0x800\n"
                                                         "#define FLAG_GOT_VS_SEEKER 0x292\n#define FLAG_WORLD_MAP_CELADON_CITY (SYS_FLAGS + 0x96)\n")
    (pf / "include" / "constants" / "opponents.h").write_text("#define TRAINER_A 1\n#define TRAINER_A_2 2\n#define TRAINER_B 3\n")
    (pf / "src" / "vs_seeker.c").write_text("static const struct RematchData sRematches[] = {\n   { {TRAINER_A, TRAINER_A_2, SKIP}, MAP(MAP_ROUTE3) },\n"
                                              "   { {TRAINER_B, TRAINER_B},\n      MAP(MAP_ROUTE4) },\n};\n"
                                              "static void TryGetRematchTrainerIdGivenGameState(const u16 * t, u8 * p)\n{\n    switch (*p)\n    {\n     case 0:\n         break;\n"
                                              "     case 1:\n         if (!FlagGet(FLAG_GOT_VS_SEEKER))\n             *p = 0;\n         break;\n"
                                              "     case 2:\n         if (!FlagGet(FLAG_WORLD_MAP_CELADON_CITY))\n             *p = 0;\n         break;\n    }\n}\n")
    out = subprocess.run([sys.executable, str(Path(__file__).resolve().parent.parent / "tools" / "gen_rematches.py"), str(pf)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    ns: dict = {}
    exec(out.stdout, ns)
    assert ns["REMATCHES"] == [("TRAINER_A", "MAP_ROUTE3", [0x501, 0x502, None]), ("TRAINER_B", "MAP_ROUTE4", [0x503, 0x503])]
    assert ns["TIER_UNLOCK"] == {1: 0x292, 2: 0x896}


pytest.importorskip("openai")
import agent.observation as obs  # noqa: E402


def test_the_rematch_line_needs_the_vs_seeker_and_shows_changes_only():
    ben = next(r for r in REMATCHES if r[0] == "TRAINER_YOUNGSTER_BEN")[2]
    flags = {ben[0]}
    t = SimpleNamespace(run=SimpleNamespace(rematch_sig=None), reader=SimpleNamespace(read_flag=lambda f: f in flags))
    assert obs._rematch_line(t) == []                                                    # no VS Seeker: silent
    flags.add(0x292)
    first = obs._rematch_line(t)
    assert len(first) == 1 and first[0].startswith("REMATCHES:") and "ready" in first[0]
    assert obs._rematch_line(t) == []                                                    # unchanged
    flags.add(ben[1])
    assert len(obs._rematch_line(t)) == 1                                                # a rung beaten: shown again

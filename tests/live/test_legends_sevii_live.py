"""quest('moltres') on the real game (#361): from Vermilion the driver rides the ferry to One Island and travels on to Mt. Ember (the summit's boulder / rock puzzle is a separate issue)."""
import json

from game.constants import Addr


def _setvar(live, n, v):
    sb1 = live.m.read32(Addr.SAVEBLOCK1_PTR)
    live.m.write16(sb1 + Addr.VARS_OFFSET + 2 * (n - 0x4000), v)


def test_quest_moltres_ferries_to_one_island_and_reaches_mt_ember(live):
    import sys
    sys.path.insert(0, "tests/live")
    from test_sweep_live import _end_battle
    live.load("vermilion")
    live.league_ready(45)
    live.patch_mon(0, moves=[57, 70, 15, 249], pps=[15, 15, 30, 15])        # Surf, Strength, Cut, Rock Smash
    live.set_badges(0xFF)
    live.set_flag(0x89B)                                                      # FLAG_WORLD_MAP_ONE_ISLAND
    _setvar(live, 0x407E, 3)                                                  # a Seagallop at Vermilion's pier
    _setvar(live, 0x4076, 5)                                                  # the Rainbow Pass stage
    c = live.c
    out = ""
    for _ in range(60):
        live.repel()
        out = c._execute("quest", json.dumps({"name": "moltres", "auto_trainers": False}))
        if live.r.detect_context().name == "IN_BATTLE":
            _end_battle(live)
            continue
        if tuple(live.r.read_current_map()) == (1, 97):                        # MtEmber_Exterior
            break
    assert tuple(live.r.read_current_map()) == (1, 97), out                    # ferried to Kindle Road, walked on, and reached Mt. Ember's exterior without a crash

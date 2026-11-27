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


def test_quest_mewtwo_surfs_up_the_river_to_the_cave_beach_and_reaches_mewtwo(live):
    """#436: Cerulean's cave door is on a beach reached only by Surf from Route 24's river across the map seam; the route is hand data in map_graph and the trip goes all the way to Mewtwo."""
    import sys
    sys.path.insert(0, "tests/live")
    from test_sweep_live import _end_battle
    live.load("vermilion")
    live.league_ready(60)
    live.set_badges(0xFF)
    for f in (0x896, 0x893, 0x844, 0x05C):                                    # visited Celadon / Cerulean, the Network Machine, the cave guard gone
        live.set_flag(f)
    live.fly_to("Cerulean City", badges=0xFF)
    live.patch_mon(0, moves=[57, 70, 15, 19], pps=[15, 15, 30, 15])           # Surf, Strength, Cut, Fly (fly_to had left the lead only Fly)
    live.set_flag(0x81, False)                                                # FLAG_HIDE_MEWTWO: Mewtwo is there
    c = live.c
    out, foe = "", None
    for _ in range(60):
        live.repel()
        out = c._execute("quest", json.dumps({"name": "mewtwo", "auto_trainers": False}))
        if live.r.detect_context().name == "IN_BATTLE":
            foe = live.r.read_enemy_lead()
            if foe and foe.species_id == 150:
                break
            _end_battle(live)
    assert foe is not None and foe.species_id == 150 and foe.level == 70, out
    assert "Mewtwo (L70) is in front of you" in out, out

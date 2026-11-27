"""tutor('Explosion') on the real game (#360): from Vermilion the Seagallop to One Island, the walk to the Hiker at Mt. Ember's south entrance and the lesson."""
import json

from game.constants import Addr
from knowledge.tutors import LEARNSETS, TUTORS

VOLTORB = 100


def _setvar(live, n, v):
    sb1 = live.m.read32(Addr.SAVEBLOCK1_PTR)
    live.m.write16(sb1 + Addr.VARS_OFFSET + 2 * (n - 0x4000), v)


def test_tutor_explosion_ferries_to_one_island_and_teaches_it(live):
    name, bit, _tmap, _npc, flag, *_ = TUTORS["explosion"]
    assert LEARNSETS[VOLTORB] & (1 << bit)
    live.load("vermilion")
    live.league_ready(45)
    live.patch_mon(0, moves=[57, 15, 249, 0], pps=[15, 30, 15, 0], species=VOLTORB)   # Surf, Cut, Rock Smash (Kindle Road is across water) and a free slot: nothing is forgotten
    live.set_badges(0xFF)
    live.set_flag(0x89B)                                                                  # FLAG_WORLD_MAP_ONE_ISLAND
    _setvar(live, 0x407E, 3)                                                              # a Seagallop at Vermilion's pier
    _setvar(live, 0x4076, 5)                                                              # the Rainbow Pass stage
    assert not live.r.read_flag(flag)
    out = ""
    for _ in range(12):
        live.repel()
        out = live.c._execute("tutor", json.dumps({"move": "Explosion", "pokemon": "Voltorb"}))
        if live.r.read_flag(flag):
            break
        if live.r.detect_context().name == "IN_BATTLE":
            live.c._flee_battle()
            live.c._advance_to_control(tries=20)
    assert live.r.read_flag(flag), out
    assert name in live.r.read_party()[0].move_names, out


def test_tutor_swords_dance_ferries_to_seven_island_and_teaches_it(live):
    """Seven Island is on the Rainbow Pass menu's second page: the ferry, the walk up from the harbor and the lesson."""
    name, bit, _tmap, _npc, flag, *_ = TUTORS["swords_dance"]
    bulbasaur = 1
    assert LEARNSETS[bulbasaur] & (1 << bit)
    live.load("vermilion")
    live.league_ready(45)
    live.patch_mon(0, moves=[57, 15, 249, 0], pps=[15, 30, 15, 0], species=bulbasaur)
    live.set_badges(0xFF)
    live.set_flag(0x89B)
    _setvar(live, 0x407E, 3)
    _setvar(live, 0x4076, 5)
    out = ""
    for _ in range(12):
        live.repel()
        out = live.c._execute("tutor", json.dumps({"move": "Swords Dance", "pokemon": "Bulbasaur"}))
        if live.r.read_flag(flag):
            break
        if live.r.detect_context().name == "IN_BATTLE":
            live.c._flee_battle()
            live.c._advance_to_control(tries=20)
    assert live.r.read_flag(flag), out
    assert name in live.r.read_party()[0].move_names, out

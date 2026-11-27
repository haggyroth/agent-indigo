"""quest('ferry <island>') on the real game (#360): Vermilion's pier, the Tri-Pass and Rainbow Pass menus, and a trip between two islands."""
import json

from game.constants import Addr


def _setvar(live, n, v):
    sb1 = live.m.read32(Addr.SAVEBLOCK1_PTR)
    live.m.write16(sb1 + Addr.VARS_OFFSET + 2 * (n - 0x4000), v)


def _stage(live, one_island_scene):
    live.load("vermilion")
    _setvar(live, 0x407E, 3)                                     # VAR_MAP_SCENE_VERMILION_CITY: a Seagallop is at the pier
    _setvar(live, 0x4076, one_island_scene)                      # the Celio chain stage: 1+ Tri-Pass, 5+ Rainbow Pass


def test_the_ferry_lists_where_it_can_go_and_refuses_without_a_pass(live):
    live.load("vermilion")
    c = live.c
    _setvar(live, 0x4076, 0)
    assert "needs a pass" in c._execute("quest", json.dumps({"name": "ferry three"}))
    _setvar(live, 0x4076, 1)
    assert "needs the Rainbow Pass" in c._execute("quest", json.dumps({"name": "ferry five"}))
    assert "Tri-Pass" in c._execute("quest", json.dumps({"name": "ferry"}))


def test_the_tri_pass_menu_takes_the_player_to_three_island(live):
    _stage(live, 1)
    out = live.c._execute("quest", json.dumps({"name": "ferry three"}))
    assert tuple(live.r.read_current_map())[0] != 3 or tuple(live.r.read_current_map())[1] != 5, out         # left Vermilion
    assert out.startswith("Sailed from Vermilion City to Three Island"), out


def test_the_rainbow_pass_menu_reaches_the_second_page_for_five_island(live):
    _stage(live, 5)
    out = live.c._execute("quest", json.dumps({"name": "ferry five"}))
    assert out.startswith("Sailed from Vermilion City to Five Island"), out
    assert tuple(live.r.read_current_map())[0] == 36, out                                             # Five Island's map group


def test_a_trip_island_to_island_and_back_to_vermilion(live):
    _stage(live, 5)
    c = live.c
    assert c._execute("quest", json.dumps({"name": "ferry five"})).startswith("Sailed from Vermilion City to Five Island")
    out = c._execute("quest", json.dumps({"name": "ferry seven"}))                                  # from Five: page 1 is [Four, Six, Seven]: OTHER, then the third row
    assert out.startswith("Sailed from Five Island to Seven Island"), out
    assert tuple(live.r.read_current_map())[0] == 31, out                                           # Seven Island's map group
    out = c._execute("quest", json.dumps({"name": "ferry vermilion"}))
    assert out.startswith("Sailed from Seven Island to Vermilion City"), out
    assert tuple(live.r.read_current_map()) == (3, 5), out

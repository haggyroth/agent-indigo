"""Doors, arrow mats and staircases (no emulator): which tile go_to aims at, and which button fires it."""
from types import SimpleNamespace as NS

import pytest

from game.tilemap_reader import TilemapReader

pytest.importorskip("openai")


def reader_with(behaviors):
    t = TilemapReader.__new__(TilemapReader)
    t.metatile_behavior = lambda x, y: behaviors.get((x, y))
    return t


def test_the_directional_stairs_and_arrow_mats_name_the_button_that_fires_them():
    t = reader_with({(4, 2): 0x6D, (9, 2): 0x6C, (6, 18): 0x65, (1, 1): 0x62, (2, 2): 0x69, (3, 3): 0x00})
    assert [t.warp_press(*p) for p in ((4, 2), (9, 2), (6, 18), (1, 1))] == ["Left", "Right", "Down", "Right"]
    assert t.warp_press(2, 2) is None and t.warp_press(3, 3) is None and t.warp_press(9, 9) is None      # an ordinary door fires on entry


def test_only_tiles_the_game_warps_from_count_as_real_warps():
    t = reader_with({(2, 14): 0x65, (1, 15): 0x00, (6, 1): 0x69, (4, 2): 0x6D, (5, 5): 0x67})
    assert [t.is_real_warp(*p) for p in ((2, 14), (1, 15), (6, 1), (4, 2), (5, 5), (8, 8))] == [True, False, True, True, True, False]


def client(warps, behaviors):
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.tilemap = reader_with(behaviors)
    c.tilemap.refresh = lambda: None
    c.tilemap.read_warps = lambda: warps
    return c


def test_go_to_aims_at_the_real_exit_mat_not_the_listed_wall_tile():
    """Celadon Dept. Store 1F lists warps at (1,15) (2,14) (3,15) — only (2,14) is an arrow mat. The old door-centre rule picked (1,15), a wall, and pressed Down into it ~70 times."""
    warps = [(1, 15), (2, 14), (3, 15), (9, 15), (10, 14), (11, 15), (6, 1), (4, 2)]
    beh = {(2, 14): 0x65, (10, 14): 0x65, (6, 1): 0x69, (4, 2): 0x6D}
    c = client(warps, beh)
    assert c._warp_exit_tile((1, 15)) == (2, 14) and c._warp_exit_tile((3, 15)) == (2, 14)
    assert c._warp_exit_tile((9, 15)) == (10, 14) and c._warp_exit_tile((4, 2)) == (4, 2) and c._warp_exit_tile((6, 1)) == (6, 1)


def test_without_any_real_warp_tile_the_old_door_centre_rule_still_applies():
    c = client([(6, 8), (7, 8), (8, 8)], {})                       # unreadable behaviors: fall back
    assert c._warp_exit_tile((6, 8)) == (7, 8)


def test_a_staircase_gets_its_own_button_before_any_other_nudge():
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    pressed, st = [], {"map": (10, 0)}
    c.tilemap = reader_with({(4, 2): 0x6D})
    c.reader = NS(read_player_pos=lambda: (4, 2), read_current_map=lambda: st["map"])
    c.mgba = NS(hold=lambda b, n: (pressed.append(b), st.update(map=(10, 1))), tick=lambda n: None)
    assert c._press_on_warp((4, 2)) is True and pressed == ["Left"]
    c.reader = NS(read_player_pos=lambda: (4, 3), read_current_map=lambda: st["map"])
    assert c._press_on_warp((4, 2)) is False                       # not on the tile: nothing pressed

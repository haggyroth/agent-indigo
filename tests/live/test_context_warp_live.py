"""A warp after a closed menu never reads IN_MENU, and real menus still do (#402), on the real core."""
from game.constants import Addr
from game.state import GameContext


def test_a_warp_after_a_closed_menu_is_never_a_menu_and_the_start_menu_still_is(live):
    from game.mgba_core import lib                           # the native binding: imported here so collection works on CI, which has none
    live.load("fullparty")                                   # inside a Pokémon Center, facing the door
    m, r = live.m, live.r
    m.tap("Start")
    m.tick(30)
    assert r.detect_context() == GameContext.IN_MENU         # the real Start menu
    for _ in range(5):
        m.tap("B")
        m.tick(20)
    assert r.detect_context() == GameContext.OVERWORLD and m.read8(Addr.MENU_OPEN) != 0            # closed, and the menu byte is left over (the stale case)
    start_map = r.read_current_map()
    seen = set()
    lib.pycore_set_keys(m._h, 1 << 7)                        # walk Down, out of the building: a warp, sampled on EVERY frame
    for _ in range(160):
        lib.pycore_run_frame(m._h)
        seen.add(r.detect_context())
    lib.pycore_set_keys(m._h, 0)
    assert r.read_current_map() != start_map                 # it really warped
    assert GameContext.IN_MENU not in seen and GameContext.TRANSITIONING in seen

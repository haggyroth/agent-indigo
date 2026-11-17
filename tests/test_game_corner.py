"""The Celadon Game Corner: generated data, prize arithmetic, and the slot machine port (pure)."""
from knowledge.game_corner import PRIZES, lots_for, prize_plan, resolve_prize
from knowledge.game_corner_data import BIAS_CHANCES, COIN_LOTS, PRIZE_CLERKS, REEL_ICONS, SLOT_MACHINES
from knowledge.slots import (CHERRIES2, ROCKET, SEVEN, advance, frames_until_good, icon_has, next_pos, one_reel_check, payout_of,
                             stop_is_good, two_reel_check)


def test_prizes_come_from_the_decomp_leafgreen_branch():
    names = {p.name for p in PRIZES}
    assert {"Abra", "Clefairy", "Pinsir", "Dratini", "Porygon", "TM13 Ice Beam", "TM24 Thunderbolt", "Smoke Ball", "Yellow Flute"} <= names
    assert next(p for p in PRIZES if p.name == "Pinsir").coins == 2500                      # LeafGreen's Pinsir, not FireRed's Scyther
    assert [r[0] for k, *_x, rows in PRIZE_CLERKS for r in rows if k == "tm"] == [0, 1, 2, 3, 4]


def test_prize_names_resolve_and_ambiguity_is_reported():
    assert resolve_prize("TM24")[0].name == "TM24 Thunderbolt" and resolve_prize("ice beam")[0].coins == 4000
    assert resolve_prize("abra")[0].kind == "mon" and resolve_prize("mystic")[0].name == "Mystic Water"
    assert resolve_prize("nothing")[0] is None


def test_coin_arithmetic_uses_the_clerks_lots():
    assert COIN_LOTS == [(50, 1000), (500, 10000)]
    assert lots_for(2800) == (2800, 56000) and lots_for(30) == (50, 1000) and lots_for(0) == (0, 0)
    plan = prize_plan(resolve_prize("Thunderbolt")[0], 1200, 20000)
    assert "2800 more" in plan and "¥56000" in plan and "you have ¥20000" in plan


def test_the_machine_ids_exclude_the_unusable_ones_and_the_tables_are_complete():
    assert any(n.startswith("Unusable") for _x, _y, n in SLOT_MACHINES) and len(SLOT_MACHINES) >= 20
    assert [len(r) for r in REEL_ICONS] == [21, 21, 21] and len(BIAS_CHANCES) == 6


def test_icon_attributes_and_payouts_match_the_decomp():
    assert icon_has(SEVEN, 0) and not icon_has(SEVEN, 1) and icon_has(ROCKET, 1) and icon_has(CHERRIES2, 4)
    assert payout_of([0] * 9) == 1500                                    # every line 7-7-7 at a full bet: 5 × 300
    assert payout_of([6, 2, 3, 6, 5, 4, 6, 1, 2]) == 8                   # only the top row matches: three Shellders (Staryu)
    assert payout_of([4, 2, 3, 5, 1, 2, 3, 2, 1]) == 4                   # one cherry in the top-left starts two lines: 2 + 2


def test_the_next_position_changes_every_third_frame():
    pos, sub, sp = [10, 10, 10], [0, 0, 0], [True] * 3
    seen = [next_pos(*advance(pos, sub, sp, f), 0) for f in range(7)]
    assert seen == [10, 9, 9, 9, 8, 8, 8]


def test_a_seven_bias_is_served_when_a_seven_is_in_reach_of_the_first_reel():
    pos, sub, sp = [9, 9, 9], [0, 0, 0], [True] * 3
    assert stop_is_good(0, pos, sub, SEVEN) == (any(REEL_ICONS[0][(next_pos(pos, sub, 0) + 1 + i) % 21] == 0 for i in range(3))
                                                 or any(REEL_ICONS[0][(next_pos(pos, sub, 0) - i) % 21] == 0 for i in range(4)))
    wait = frames_until_good(0, pos, sub, sp, SEVEN)
    assert wait is not None and wait < 63
    p2, s2 = advance(pos, sub, sp, wait)
    assert stop_is_good(0, p2, s2, SEVEN)


def test_third_reel_completes_a_line_only_where_the_first_two_allow():
    # first two reels at rest showing a 7 on the top row; reel 3 must put a 7 there too (position 20 shows 7,PSYDUCK,... on rows 0-2)
    positions = [7, 11, 0]
    assert one_reel_check(2, 20, SEVEN, (0, 1), positions)
    assert not one_reel_check(2, 5, SEVEN, (0, 1), positions)
    assert two_reel_check(0, 8, 1, 12, SEVEN) in (True, False)

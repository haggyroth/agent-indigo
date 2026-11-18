"""What shop(sell=true) will sell (#270, no emulator): treasure by default, a named item on request, never what the team can use."""
from knowledge.selling import PROTECTED, TREASURE, resolve, sell_plan


def test_no_item_sells_every_treasure_in_the_bag_and_nothing_else():
    bag = {110: 3, 109: 1, 13: 5, 4: 10, 106: 2}                         # Nugget, Star Piece, Potion, Poké Ball, Pearl
    plan, msg = sell_plan(bag)
    assert plan == [(106, 2), (109, 1), (110, 3)]
    assert "3× Nugget" in msg and "about ¥" in msg
    assert sum(TREASURE[i][1] * n for i, n in plan) == 2 * 700 + 4900 + 3 * 5000


def test_an_empty_treasure_bag_says_so_and_how_to_sell_something_anyway():
    plan, msg = sell_plan({13: 5, 4: 10})
    assert plan == [] and "Nothing spare to sell" in msg and "item='Nugget'" in msg


def test_a_named_item_sells_that_many_capped_at_what_is_held():
    assert sell_plan({110: 3}, "nugget", 2)[0] == [(110, 2)]
    assert sell_plan({110: 3}, "Nugget", 9)[0] == [(110, 3)]
    assert sell_plan({110: 3}, "star piece")[0] == []                    # none held
    assert "don't have any" in sell_plan({110: 3}, "star piece")[1]


def test_things_the_team_can_use_are_never_sold_even_when_named():
    for name, iid in (("Potion", 13), ("Super Repel", 83), ("Fire Stone", 95), ("Poke Ball", 4), ("Protein", 64)):
        assert iid in PROTECTED, name
        plan, msg = sell_plan({iid: 5}, name)
        assert plan == [] and "Not selling" in msg, name


def test_resolve_is_exact_first_and_refuses_ambiguity():
    assert resolve("big pearl") == 107 and resolve("pearl") == 106 and resolve("Nugget") == 110
    assert resolve("mushroom") is None and resolve("") is None and resolve("zzz") is None

"""PP items (knowledge.pp_items): who needs them and which move an Ether refills (pure)."""
from types import SimpleNamespace as NS

from knowledge.pp_items import ELIXIR, ETHER, move_deficits, pick_move, pick_pp_target


def mon(names, pps, hp=50):
    return NS(move_names=list(names), pp=list(pps), current_hp=hp, species_name="X")


def test_deficits_are_measured_against_each_moves_base_pp():
    m = mon(["Thunder", "Thunder Shock", "Slam", ""], [2, 30, 0, 0])       # base PP 10 / 30 / 20 / —
    assert move_deficits(m) == [8, 0, 20, 0]


def test_an_ether_goes_to_the_biggest_single_gap_an_elixir_to_the_biggest_total():
    a = mon(["Thunder", "Slam", "", ""], [0, 20, 0, 0])                      # one move empty: gap 10
    b = mon(["Surf", "Ice Beam", "Body Slam", "Hydro Pump"], [10, 5, 10, 2])  # 5 / 5 / 10 / 3 short ... totals 23
    assert pick_pp_target([a, b], ETHER) == 0
    assert pick_pp_target([a, b], ELIXIR) == 1
    assert pick_pp_target([mon(["Surf"], [15]), mon(["Slam"], [20])], ETHER) is None       # nobody short
    assert pick_pp_target([mon(["Thunder"], [0], hp=0)], ETHER) is None                    # a fainted mon is not worth a PP item


def test_the_ether_move_is_the_named_one_else_the_most_depleted():
    m = mon(["Surf", "Ice Beam", "Body Slam", "Hydro Pump"], [10, 5, 10, 2])
    assert pick_move(m, "ice beam") == 1 and pick_move(m, "Hydro") == 3
    assert pick_move(m) == 0                                                  # Surf, Ice Beam and Body Slam are each 5 short: the first of the tie
    assert pick_move(mon(["Surf", "Ice Beam", "Body Slam", "Hydro Pump"], [10, 0, 10, 2])) == 1       # Ice Beam is empty: the biggest gap wins
    status_first = mon(["Growl", "Slam"], [40, 5])                             # Growl 40/40 is full; Slam 5/20 is short
    assert pick_move(status_first) == 1

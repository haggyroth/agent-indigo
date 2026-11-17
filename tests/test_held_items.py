"""Held items, battle boosters and Repel strategy (pure)."""
from types import SimpleNamespace as P

from game.constants import SPECIES_NAMES
from knowledge.bag import booster_note
from knowledge.held_items import describe, holder_for, holding_line, suggest
from knowledge.repel import note as repel_note

ID = {v: k for k, v in SPECIES_NAMES.items()}
LEFTOVERS, EXP_SHARE, MYSTIC_WATER, EVERSTONE, LIGHT_BALL = 200, 182, 209, 195, 202


def mon(name, level, moves=("Tackle",), held=0):
    return P(species_id=ID[name], species_name=name, nickname="", level=level, move_names=list(moves), max_hp=40, current_hp=40,
             held_item=held)


def test_effects_are_described_from_the_decomp_data():
    assert "1/16" in describe(LEFTOVERS) and "+10% to Water" in describe(MYSTIC_WATER) and "Exp." in describe(EXP_SHARE)


def test_holders_follow_the_item():
    party = [mon("Squirtle", 30, ["Water Gun", "Tackle"]), mon("Pidgey", 12, ["Gust"]), mon("Pikachu", 20, ["Thunder Shock"])]
    assert holder_for(MYSTIC_WATER, party).species_name == "Squirtle"        # the one that attacks with Water
    assert holder_for(EXP_SHARE, party).species_name == "Pidgey"             # the one that lags
    assert holder_for(LEFTOVERS, party).species_name == "Squirtle"           # the ace
    assert holder_for(LIGHT_BALL, party).species_name == "Pikachu"
    assert holder_for(EVERSTONE, party) is None                              # never suggested: it stops evolution


def test_suggestions_skip_items_already_held_and_name_the_call():
    party = [mon("Squirtle", 30, ["Water Gun"]), mon("Pidgey", 12, ["Gust"])]
    lines = suggest(party, [(EXP_SHARE, 1), (EVERSTONE, 1), (13, 5)])
    assert len(lines) == 1 and "give_item('Exp. Share', 'Pidgey')" in lines[0]
    party[1].held_item = EXP_SHARE
    assert suggest(party, [(EXP_SHARE, 1)]) == [] and holding_line(party) == "Holding: Pidgey — Exp. Share"


def test_boosters_are_listed_with_when_to_spend_them():
    assert booster_note([(13, 3)], True) == ""
    t = booster_note([(75, 2), (74, 1)], True)
    assert "X Attack ×2" in t and "Dire Hit" in t and "Gym Leader" in t
    assert "not worth it against a wild" in booster_note([(75, 1)], False)


def test_repel_only_when_the_route_is_beneath_the_lead():
    route2 = (3, 20)                                                         # wild L2-5
    assert "Repel" in repel_note(route2, 20, 0, 2, 5)
    assert repel_note(route2, 4, 0, 2, 5) == ""                              # lead too weak: a Repel would not work
    assert repel_note(route2, 20, 0, 0, 5) == "" and repel_note(route2, 20, 0, 2, 2) == ""    # no Repel / still building a team
    assert repel_note(route2, 20, 0, 2, 5, wanted_here=True) == ""
    assert "40 steps left" in repel_note(route2, 20, 40, 0, 5)

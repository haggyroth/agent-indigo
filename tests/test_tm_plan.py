"""The Celadon TM shopping plan (knowledge.tm_plan) against synthetic parties — no emulator."""
from types import SimpleNamespace as NS

from knowledge import tm_plan
from knowledge.tmhm import ITEM_TM01, TMHM


def mon(species_id, name, moves, level=40):
    return NS(species_id=species_id, species_name=name, nickname="", level=level, max_hp=100, move_names=list(moves), move_ids=[], types=None)


def test_the_stock_is_the_six_celadon_tms_with_the_decomp_prices():
    assert tm_plan.STOCK == {"TM05": 1000, "TM15": 7500, "TM28": 2000, "TM31": 3000, "TM43": 3000, "TM45": 3000}
    for label in tm_plan.STOCK:
        assert TMHM[ITEM_TM01 + int(label[2:]) - 1][0] == label


def test_a_team_gets_one_useful_stock_tm_per_pokemon_with_its_price():
    party = [mon(143, "Snorlax", ["Body Slam", "Rest", "Headbutt", "Amnesia"])]
    rows = tm_plan.plan(party, money=10000)
    assert len(rows) == 1                                                  # tm_advice gives one suggestion per Pokémon
    adv, price, ok = rows[0]
    assert adv.tm in tm_plan.STOCK and price == tm_plan.STOCK[adv.tm] and ok and adv.mon == "Snorlax"
    text = tm_plan.line(party, money=10000)
    assert text.startswith("TM shop (Celadon Dept. Store 2F") and f"{adv.tm} {adv.move} ¥{price:,} for Snorlax" in text


def test_owned_tms_are_skipped_and_affordability_is_reported():
    party = [mon(143, "Snorlax", ["Body Slam", "Rest", "Headbutt", "Amnesia"])]
    adv, _price, ok = tm_plan.plan(party, money=0)[0]
    assert not ok and "not enough money yet" in tm_plan.line(party, money=0)
    again = tm_plan.plan(party, owned_labels=[adv.tm], money=0)
    assert all(a.tm != adv.tm for a, _p, _o in again)                     # what is already in the TM Case is never suggested again
    everything = tm_plan.plan(party, owned_labels=list(tm_plan.STOCK), money=0)
    assert everything == [] and tm_plan.line(party, owned_labels=list(tm_plan.STOCK), money=0) == ""

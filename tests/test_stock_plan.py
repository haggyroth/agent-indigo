"""Shopping by what the mart actually sells, with spare money put to work, and the evolution stones (pure; no emulator)."""
from types import SimpleNamespace as NS

from knowledge.shop_stock import SHOPS
from knowledge.shopping import SOLD_STONES, compute_stock_plan, stone_wants


def sold_at(bank, mid):
    return set(next(items for b, m, _x, _y, items in SHOPS if (b, m) == (bank, mid)))


FUCHSIA, SAFFRON, CELADON_2F, VIRIDIAN, INDIGO = sold_at(11, 1), sold_at(14, 5), sold_at(10, 1), sold_at(5, 3), sold_at(13, 0)


def got(plan):
    return {l["item_id"]: l["qty"] for l in plan["lines"]}


def test_a_rich_player_gets_ultra_balls_where_they_are_sold_and_great_balls_where_they_are_not():
    assert 2 in got(compute_stock_plan({}, 5, 26000, FUCHSIA)) and 3 not in got(compute_stock_plan({}, 5, 26000, FUCHSIA))
    g = got(compute_stock_plan({}, 5, 26000, SAFFRON))
    assert 3 in g and 2 not in g and 21 in g                          # Saffron: Great Balls and Hyper Potions, no Ultra
    assert 3 in got(compute_stock_plan({}, 5, 26000, CELADON_2F))


def test_a_poor_player_buys_the_cheaper_tier_and_still_gets_potions():
    g = got(compute_stock_plan({}, 5, 3000, FUCHSIA))
    assert 3 in g and 22 in g and 2 not in g                          # ¥3000: Great Balls + Super Potions, not 2 Ultra Balls and nothing else


def test_spare_money_is_put_to_work_beyond_the_old_par_of_ten():
    plan = compute_stock_plan({4: 17, 13: 1}, 5, 26000, FUCHSIA)
    g = got(plan)
    assert g[22] >= 8 and g[23] >= 5 and g[24] >= 2 and 2 in g       # Super Potions, Full Heals, Revives, Ultra Balls
    assert plan["total"] > 15000 and plan["total"] <= 26000 - 500


def test_cheaper_balls_in_the_bag_count_half_toward_a_better_tier():
    full = got(compute_stock_plan({}, 5, 26000, FUCHSIA))[2]
    assert got(compute_stock_plan({4: 17}, 5, 26000, FUCHSIA))[2] < full


def test_a_family_cannot_eat_all_the_money_and_the_total_never_exceeds_it():
    for money in (700, 1500, 3000, 8000, 26000, 60000):
        for sold in (FUCHSIA, SAFFRON, VIRIDIAN, INDIGO):
            plan = compute_stock_plan({}, 5, money, sold, reserve=500)
            assert plan["total"] <= max(0, money - 500), (money, plan)
    g = got(compute_stock_plan({}, 5, 8000, FUCHSIA, reserve=500))
    assert 22 in g and 3 in g                                         # ¥8000: both a ball tier and potions


def test_it_says_which_better_grade_another_mart_sells():
    assert "Ultra Ball" in compute_stock_plan({}, 5, 26000, CELADON_2F)["missing"]
    assert compute_stock_plan({}, 5, 26000, FUCHSIA)["missing"] in ([], ["Full Restore"])


def test_early_game_marts_still_work():
    g = got(compute_stock_plan({}, 0, 1000, VIRIDIAN, reserve=0))
    assert 4 in g and 13 in g
    assert compute_stock_plan({}, 0, 0, VIRIDIAN)["lines"] == []


def mon(species_id, name="X", nick=""):
    return NS(species_id=species_id, species_name=name, nickname=nick)


def test_stones_are_wanted_for_party_members_that_evolve_with_one_sold_at_the_dept_store():
    party = [mon(25, "Pikachu", "Sparky"), mon(58, "Growlithe"), mon(133, "Eevee"), mon(35, "Clefairy")]
    wants = stone_wants(party, {}, 20000)
    assert {w[0] for w in wants} == {96, 95}                          # Thunderstone, Fire Stone — not Eevee (three outcomes), not Clefairy (Moon Stone isn't sold)
    assert all(w[0] in SOLD_STONES for w in wants) and wants[0][1] in ("Sparky", "Growlithe")


def test_no_stone_is_wanted_when_one_is_held_unaffordable_or_nobody_evolves_with_it():
    party = [mon(25, "Pikachu")]
    assert stone_wants(party, {96: 1}, 20000) == []
    assert stone_wants(party, {}, 1000) == []
    assert stone_wants([mon(26, "Raichu")], {}, 20000) == []

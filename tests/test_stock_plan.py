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


# ── the League's shopping: Revives and Hyper Potions, not Max Potions and Full Restores ──────────────────────────────────

def test_the_plateau_clerk_buys_revives_first_and_max_potions_before_full_restores():
    plan = compute_stock_plan({}, 8, 11000, INDIGO, reserve=500)
    g = got(plan)
    assert g.get(24, 0) >= 3                                          # Revives are funded before the heals
    assert 19 not in g and g.get(20, 0) <= 3                          # no Full Restores while Max Potions are sold; few Max Potions at ¥2500
    assert "Hyper Potion" in plan["missing"]                          # and it says where the better value is


def test_a_mart_that_sells_hyper_potions_gets_hypers_and_revives_late():
    g = got(compute_stock_plan({}, 8, 20000, SAFFRON, reserve=500))
    assert g.get(21, 0) >= 8 and g.get(24, 0) >= 4
    assert 20 not in g and 19 not in g


def test_the_late_family_shares_never_overspend():
    for money in (1500, 4000, 11000, 30000):
        for sold in (INDIGO, SAFFRON, FUCHSIA):
            assert compute_stock_plan({}, 8, money, sold, reserve=500)["total"] <= max(0, money - 500)


def test_a_hyper_mart_trip_is_wanted_from_seven_badges_with_money_unless_already_at_one():
    from knowledge.shopping import hyper_marts, wants_hyper_mart
    assert hyper_marts()[0] == (14, 5) and (12, 7) in hyper_marts() and all(b <= 14 for b, _m in hyper_marts())
    assert wants_hyper_mart(8, 11000, (13, 0)) and not wants_hyper_mart(8, 11000, (14, 5))
    assert not wants_hyper_mart(8, 2000, (13, 0)) and not wants_hyper_mart(5, 11000, (13, 0))

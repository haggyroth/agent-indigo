"""Purchase-policy engine: par levels, badge-gated unlocks, affordability. Pure."""
from knowledge.shopping import compute_shopping_list, shopping_summary


def _ids(plan):
    return {ln["item_id"]: ln["qty"] for ln in plan["lines"]}


def test_empty_bag_no_badges_buys_balls_and_potions():
    plan = compute_shopping_list(bag={}, badges=0, money=99999)
    got = _ids(plan)
    assert got[4] == 10          # Poké Ball to par 10
    assert got[13] == 6          # Potion to par 6
    assert 22 not in got         # no Super Potion pre-Surge
    assert 3 not in got          # no Great Ball yet


def test_par_level_only_buys_the_shortfall():
    plan = compute_shopping_list(bag={4: 7, 13: 6}, badges=0, money=99999)
    got = _ids(plan)
    assert got[4] == 3           # 10 - 7
    assert 13 not in got         # already at par


def test_surge_upgrades_potions_and_balls():
    # 3 badges (post-Surge): Super Potion supersedes Potion, Great Ball supersedes Poké.
    plan = compute_shopping_list(bag={}, badges=3, money=99999)
    got = _ids(plan)
    assert 22 in got and 13 not in got      # Super Potion, not Potion
    assert 3 in got and 4 not in got        # Great Ball, not Poké Ball


def test_five_badges_upgrades_to_ultra_and_hyper():
    plan = compute_shopping_list(bag={}, badges=5, money=99999)
    got = _ids(plan)
    assert 2 in got and 3 not in got and 4 not in got   # Ultra Ball only
    assert 21 in got and 22 not in got                  # Hyper Potion only


def test_full_heal_supersedes_status_cures_after_badge4():
    early = _ids(compute_shopping_list(bag={}, badges=0, money=99999))
    assert 14 in early and 23 not in early    # Antidote yes, Full Heal no
    late = _ids(compute_shopping_list(bag={}, badges=4, money=99999))
    assert 23 in late and 14 not in late      # Full Heal supersedes Antidote
    assert 24 in late                         # Revive unlocked at 4


def test_money_limits_purchase_in_priority_order():
    # Only enough for a few Poké Balls (200 each) — balls are top priority.
    plan = compute_shopping_list(bag={}, badges=0, money=650)
    got = _ids(plan)
    assert got.get(4) == 3       # 3 balls = 600, then 50 left, nothing else fits
    assert 13 not in got
    assert plan["total"] == 600
    assert plan["affordable"] is False


def test_reserve_is_withheld():
    plan = compute_shopping_list(bag={}, badges=0, money=650, reserve=500)
    # only ¥150 spendable → nothing (cheapest useful is ¥100 antidote? balls first at 200)
    assert plan["total"] <= 150


def test_fully_stocked_buys_nothing():
    bag = {4: 10, 13: 6, 14: 2, 18: 2, 17: 2, 15: 1, 16: 1}
    plan = compute_shopping_list(bag=bag, badges=0, money=99999)
    assert plan["lines"] == []
    assert shopping_summary(bag, 0, 99999) == ""


def test_summary_string_is_readable():
    s = shopping_summary(bag={}, badges=0, money=99999)
    assert "Poké Ball" in s and "¥" in s


# ── late game: the Elite Four wants ~12 strong heals and sealed rooms sell none ─────────────────────────────────────
def _plan(sold, badges, money, bag=None):
    from knowledge.shopping import compute_stock_plan
    return {ln["item_id"]: ln["qty"] for ln in compute_stock_plan(bag or {}, badges, money, sold, reserve=500)["lines"]}


FUCHSIA = (2, 3, 21, 22, 23, 24)


def test_before_the_late_badges_the_plan_is_unchanged():
    assert _plan(FUCHSIA, 6, 9000, {13: 9}) == {3: 5, 21: 2, 23: 3}


def test_with_seven_badges_hyper_potions_win_and_balls_take_a_smaller_share():
    late = _plan(FUCHSIA, 8, 9000, {13: 9})
    assert late[21] >= 3 and late.get(24, 0) >= 1 and late.get(3, 0) <= 2   # Hyper Potions and a Revive, not 6 Super Potions + 5 Great Balls
    assert _plan(FUCHSIA, 8, 20000, {13: 9})[21] >= 8                  # a rich player stocks toward the 12


def test_weak_potions_are_no_stock_toward_the_late_hyper_potion_par():
    assert _plan(FUCHSIA, 8, 20000, {13: 15})[21] == _plan(FUCHSIA, 8, 20000, {})[21]


def test_a_mart_without_hyper_potions_still_gets_the_best_full_heal_it_has():
    assert _plan((2, 3, 19, 20, 24, 23), 8, 9000).get(20, 0) >= 1

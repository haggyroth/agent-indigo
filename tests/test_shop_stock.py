"""shop(item=…): which clerk sells what (generated from the decomp), name resolution, where to stand (pure)."""
from knowledge.shop_stock import PRICES, SHOP_NAMES, SHOPS
from knowledge.shopping import FREE_SOURCES, approach_options, item_label, resolve_item, shops_selling

TM28, SUPER_REPEL, PROTEIN, X_ATTACK, FIRE_STONE = 316, 83, 64, 75, 95
DEPT_2F, DEPT_5F = (10, 1), (10, 4)


def test_the_dept_store_sells_tms_vitamins_and_x_items_each_on_its_own_floor():
    assert {(b, m) for b, m, _x, _y in shops_selling(TM28)} == {DEPT_2F}
    assert (10, 4, 1, 6) in shops_selling(PROTEIN) and (10, 4, 1, 7) in shops_selling(X_ATTACK)
    assert PRICES[TM28] == 2000 and PRICES[SUPER_REPEL] == 500
    assert SHOP_NAMES[DEPT_2F] == "Celadon City Dept. Store 2F"


def test_two_clerks_on_one_floor_are_kept_apart():
    clerks = [s for s in SHOPS if (s[0], s[1]) == DEPT_2F]
    assert len(clerks) == 2 and TM28 in next(c for c in clerks if c[3] == 6)[4] and SUPER_REPEL in next(c for c in clerks if c[3] == 8)[4]


def test_names_resolve_to_items():
    assert resolve_item("TM28")[0] == TM28 and resolve_item("dig")[0] == TM28 and resolve_item("Super Repel")[0] == SUPER_REPEL
    assert resolve_item("protein")[0] == PROTEIN and resolve_item("potion")[0] == 13
    none, close = resolve_item("max")
    assert none is None and "Max Potion" in close
    assert resolve_item("Masterball") == (None, [])
    assert item_label(TM28) == "TM28 Dig"


def test_tm28_is_flagged_as_also_a_free_reward():
    assert "Cerulean" in FREE_SOURCES[TM28]


def test_approach_is_the_customer_side_even_across_a_counter():
    # Dept. Store 2F: clerk at (1,6) inside an enclosure, counter column x=2, shop floor x>=3.
    floor = {(x, y) for x in range(0, 12) for y in range(2, 14)} - {(2, y) for y in range(5, 8)}
    reach = {p for p in floor if p[0] >= 3}
    spots = approach_options((1, 6), lambda x, y: (x, y) in floor, lambda x, y: (x, y) in reach)
    assert spots == [((3, 6), "Left")]                                # across the counter, facing the clerk
    # A standard mart: clerk (2,3), floor directly in front.
    floor = {(x, y) for x in range(0, 6) for y in range(4, 8)}
    assert approach_options((2, 3), lambda x, y: (x, y) in floor) == [((2, 4), "Up")]

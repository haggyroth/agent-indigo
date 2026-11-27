"""The Seagallop menus (#360): the rows the game draws from each dock, and the cursor presses to a destination (pure)."""
from knowledge import ferry as fy


def test_page_zero_is_four_rows_without_the_dock_you_stand_at():
    assert fy.page0(0) == [1, 2, 3, 4]                       # Vermilion: One, Two, Three, Four (the first screenshot)
    assert fy.page0(1) == [0, 2, 3, 4] and fy.page0(4) == [0, 1, 2, 3] and fy.page0(5) == [0, 1, 2, 3] and fy.page0(7) == [0, 1, 2, 3]


def test_page_one_is_the_three_far_islands():
    assert fy.page1(0) == [5, 6, 7] and fy.page1(3) == [5, 6, 7]
    assert fy.page1(5) == [4, 6, 7] and fy.page1(6) == [4, 5, 7] and fy.page1(7) == [4, 5, 6]


def test_the_presses_to_a_destination_open_the_second_page_through_other():
    assert fy.rainbow_menu(0, 3) == [(2, 0)]                                   # Three Island: third row of page 0
    assert fy.rainbow_menu(0, 5) == [(4, 0), (0, 1)]                           # OTHER is the row after the four, then Five is page 1's first
    assert fy.rainbow_menu(5, 7) == [(4, 0), (2, 1)]                           # from Five: OTHER, then Seven (page 1 is Four, Six, Seven)
    assert fy.rainbow_menu(5, 4) == [(4, 0), (0, 1)] and fy.rainbow_menu(5, 5) == []        # (you are there)


def test_the_tri_pass_lists_and_the_map_to_island_rule():
    assert fy.tri_pass_rows(0, False) == [1, 2, 3] and fy.tri_pass_rows(2, False) == [1, 3] and fy.tri_pass_rows(2, True) == [0, 1, 3]
    assert fy.island_of_map((3, 5)) == 0 and fy.island_of_map((36, 2)) == 5 and fy.island_of_map((3, 6)) is None
    assert set(fy.HARBORS) == {1, 2, 3, 4, 5, 6, 7} and "Four Island" in fy.route_text(0, 5) and "Four" not in fy.route_text(0, 1)

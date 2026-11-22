"""The Elite Four's rooms are sealed: pure data + the observation notice."""
from types import SimpleNamespace as NS

from knowledge.league_rooms import LEAGUE_ROOMS, SEALED, league_notice


def test_the_rooms_match_the_league_driver():
    pytest = __import__("pytest")
    pytest.importorskip("openai")
    from agent.skills.league import ROOMS
    assert {r[0]: r[3] for r in ROOMS} == {k: v for k, v in LEAGUE_ROOMS.items()}


def test_no_notice_outside_the_league():
    assert league_notice((3, 9)) == "" and league_notice((13, 0)) == ""


def test_the_notice_says_no_leaving_and_what_is_left_to_heal_with():
    note = league_notice((1, 75), [NS(current_hp=10), NS(current_hp=0)], {19: 2, 24: 1, 25: 1, 13: 3, 21: 1})
    assert note.startswith("You are SEALED IN") and SEALED in note
    assert "2 Full Restore, 2 Revive, 4 Potions" in note and "Standing: 1/2" in note

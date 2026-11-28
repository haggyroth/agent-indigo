"""The imported RetroAchievements set (#358): the checklist data, as the owner saw it on the page (128 achievements, 781 points)."""
from collections import Counter

from knowledge.ra_set import ACHIEVEMENTS, GAME_ID, TITLE


def test_the_set_is_leafgreens_with_the_counts_from_the_page():
    assert GAME_ID == 788 and TITLE == "Pokémon LeafGreen Version"
    assert len(ACHIEVEMENTS) == 128 and sum(a[3] for a in ACHIEVEMENTS) == 781
    assert Counter(a[4] for a in ACHIEVEMENTS) == {"": 82, "missable": 24, "progression": 21, "win_condition": 1}


def test_every_achievement_is_well_formed_and_unique():
    ids = [a[0] for a in ACHIEVEMENTS]
    assert len(set(ids)) == len(ids)
    assert len({a[1] for a in ACHIEVEMENTS}) == len(ACHIEVEMENTS)                 # titles are unique too
    for aid, title, desc, points, kind in ACHIEVEMENTS:
        assert aid > 0 and title and desc and points > 0
        assert kind in ("", "progression", "win_condition", "missable")

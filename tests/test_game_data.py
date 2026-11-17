"""Hard-coded game facts vs the pokefirered decomp (#211) and trade-evolution handling (#215)."""
import os
import re
from pathlib import Path

import pytest

from knowledge.leafgreen_data import CHAMPION, ELITE_FOUR, HM_REQUIREMENTS, KEY_ITEMS
from knowledge.species_data import SPECIES_DATA

DECOMP = Path(os.path.expanduser("~/Projects/pokefirered"))
needs_decomp = pytest.mark.skipif(not DECOMP.exists(), reason="pokefirered decomp not checked out")

ABRA, KADABRA, MACHOP, MACHOKE, GEODUDE, GRAVELER, GASTLY, HAUNTER = 63, 64, 66, 67, 74, 75, 92, 93
EEVEE, GROWLITHE = 133, 58


def test_trade_evolutions_are_not_counted_as_reachable():
    # The line's best form stops at the last non-trade evolution.
    for first, last in ((ABRA, KADABRA), (MACHOP, MACHOKE), (GEODUDE, GRAVELER), (GASTLY, HAUNTER)):
        assert SPECIES_DATA[first][2] == SPECIES_DATA[last][0] == SPECIES_DATA[last][2]


def test_stone_evolutions_still_count():
    assert SPECIES_DATA[GROWLITHE][2] > SPECIES_DATA[GROWLITHE][0]   # Arcanine via Fire Stone
    assert SPECIES_DATA[EEVEE][2] > SPECIES_DATA[EEVEE][0]


def test_champion_is_not_an_elite_four_member():
    assert [e["trainer"] for e in ELITE_FOUR] == ["Lorelei", "Bruno", "Agatha", "Lance"]
    assert CHAMPION["trainer"] == "Gary"


def test_item_sources():
    assert "Secret House" in HM_REQUIREMENTS["Surf"]["location"]
    assert "Warden" in HM_REQUIREMENTS["Strength"]["location"]
    tm26 = next(k for k in KEY_ITEMS if k["item"].startswith("TM26"))
    assert "Viridian" in tm26["location"]


@needs_decomp
@pytest.mark.parametrize("trainer,species,party_fn", [
    ("Lorelei", "LAPRAS", "sParty_EliteFourLorelei"), ("Bruno", "MACHAMP", "sParty_EliteFourBruno"),
    ("Agatha", "GENGAR", "sParty_EliteFourAgatha"), ("Lance", "DRAGONITE", "sParty_EliteFourLance"),
])
def test_elite_four_ace_levels_match_decomp(trainer, species, party_fn):
    txt = (DECOMP / "src/data/trainer_parties.h").read_text()
    body = re.search(rf"{party_fn}\[\] = \{{(.*?)\n\}};", txt, re.S).group(1)
    levels = [int(l) for l, s in re.findall(r"\.lvl = (\d+),\s*\.species = SPECIES_(\w+)", body) if s == species]
    from knowledge.gym_advice import ace_levels
    assert ace_levels()[trainer] == max(levels)


# ── advice text is generated from the decomp parties (#211) ─────────────────────────────────────────
def test_briefs_are_built_from_the_generated_parties():
    from knowledge.gym_advice import ace, brief, weak_to
    assert ace("Koga") == ("Weezing", 43) and ace("Lance") == ("Dragonite", 60)
    b = brief("Koga")
    assert "Weezing L43" in b and "Ground" in b and "Self-Destruct" in b
    assert any(t == "ICE" for t, _n, _m in weak_to("Lance"))
    assert "Blastoise" in brief("Gary")


def test_navigation_prose_never_contradicts_the_generated_levels():
    """Any 'Species L<n>' in the hand-written navigation text must be a level the decomp gives that species."""
    from game.constants import SPECIES_NAMES
    from knowledge import navigation
    from knowledge.gym_teams import TRAINER_TEAMS
    by_name = {}
    for team in TRAINER_TEAMS.values():
        for sid, lvl, _m in team:
            by_name.setdefault(SPECIES_NAMES[sid], set()).add(lvl)
    text = " ".join(str(v) for v in vars(navigation).values() if isinstance(v, (str, list, dict, tuple)))
    for name, lvl in re.findall(r"([A-Z][a-z]+) L(\d+)", text):
        if name in by_name:
            assert int(lvl) in by_name[name], f"navigation says {name} L{lvl}; the decomp has {sorted(by_name[name])}"

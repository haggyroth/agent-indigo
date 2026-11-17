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
    claimed = int(re.search(r"L(\d+)", next(e for e in ELITE_FOUR if e["trainer"] == trainer)["key_threat"]).group(1))
    assert claimed == max(levels)

"""The Safari Zone hunt (#362): which species live in the grass and where, name matching, and the refusals of quest('safari') (a fake game)."""
from types import SimpleNamespace

import pytest

from game.constants import SPECIES_NAMES
from game.state import GameContext
from knowledge import safari as sf

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402


def test_the_decomps_safari_grass_tables_are_read_by_species():
    assert [m for m, _lo, _hi in sf.areas_for(113)] == [(1, 63), (1, 65)]                 # Chansey: Center and North
    assert [m for m, _lo, _hi in sf.areas_for(128)] == [(1, 65), (1, 66)]                 # Tauros: North and West
    assert sf.areas_for(60) == [] and sf.areas_for(60, "good rod")                         # Poliwag is a fishing species here, not grass
    assert sf.areas_for(25) == []                                                           # Pikachu is not in the Safari at all


def test_names_resolve_loosely_and_non_safari_species_do_not():
    assert sf.species_by_name("Chansey", SPECIES_NAMES) == 113 and sf.species_by_name("kanga", SPECIES_NAMES) == 115
    assert sf.species_by_name("pikachu", SPECIES_NAMES) is None and sf.species_by_name("", SPECIES_NAMES) is None
    assert sf.species_by_name("nido", SPECIES_NAMES) is None                                # several Nidos: ambiguous
    assert "Chansey (Center L23, North L26)" in sf.listing(SPECIES_NAMES)


def _client(ctx=GameContext.OVERWORLD):
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(detect_context=lambda: ctx)
    return c


def test_the_listing_the_refusals_and_the_field_check():
    assert "quest('safari <species>') hunts one" in _client()._safari_hunt("")
    assert "No Safari Zone grass Pokémon called 'pikachu'" in _client()._safari_hunt("pikachu")
    assert "open field" in _client(GameContext.IN_MENU)._safari_hunt("chansey")

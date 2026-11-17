"""One resolver for 'which Pokémon?' (pure)."""
from types import SimpleNamespace as P

from knowledge.targets import resolve_mon

PARTY = [P(species_name="Bulbasaur", nickname="Bulby"), P(species_name="Pidgey", nickname=""),
         P(species_name="Rattata", nickname=""), P(species_name="Pidgey", nickname="Zippy"), P(species_name="Raticate", nickname="")]


def test_slot_numbers_are_one_based_and_checked():
    assert resolve_mon("1", PARTY).index == 0 and resolve_mon(5, PARTY).index == 4
    for bad in ("0", "6"):
        r = resolve_mon(bad, PARTY)
        assert r.index is None and "no slot" in r.error


def test_species_and_nicknames_both_work_case_insensitively():
    assert resolve_mon("bulbasaur", PARTY).index == 0 and resolve_mon("BULBY", PARTY).index == 0
    assert resolve_mon("zippy", PARTY).index == 3


def test_two_of_a_species_is_ambiguous_until_named_by_slot_or_nickname():
    r = resolve_mon("Pidgey", PARTY)
    assert r.index is None and "slots 2, 4" in r.error and "slot number" in r.error
    assert resolve_mon("Zippy", PARTY).index == 3 and resolve_mon("2", PARTY).index == 1


def test_partial_matches_must_be_unique_too():
    assert resolve_mon("bulba", PARTY).index == 0
    r = resolve_mon("rat", PARTY)                                  # Rattata and Raticate
    assert r.index is None and "slots 3, 5" in r.error
    assert "Couldn't find" in resolve_mon("Charmander", PARTY).error and "Which Pokémon" in resolve_mon("", PARTY).error

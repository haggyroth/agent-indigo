"""Battle-end logging records the fighting mon, not always the lead (#2)."""
from game.state import PokemonStatus, newly_fainted_slots


def mon(slot, species, hp, max_hp=30):
    return PokemonStatus(slot=slot, level=10, current_hp=hp, max_hp=max_hp,
                         status="healthy", species_id=slot + 1, species_name=species,
                         move_ids=[0, 0, 0, 0], move_names=["", "", "", ""], pp=[0, 0, 0, 0])


PARTY = [mon(0, "Bulbasaur", 5), mon(1, "Pidgey", 22), mon(2, "Rattata", 0)]


def test_newly_fainted_detects_alive_to_zero():
    before = [mon(0, "Bulbasaur", 10), mon(1, "Pidgey", 5)]
    after = [mon(0, "Bulbasaur", 0), mon(1, "Pidgey", 5)]
    assert newly_fainted_slots(before, after) == [0]


def test_newly_fainted_ignores_already_fainted():
    before = [mon(0, "Bulbasaur", 0)]
    after = [mon(0, "Bulbasaur", 0)]
    assert newly_fainted_slots(before, after) == []


def test_newly_fainted_multiple():
    before = [mon(0, "A", 3), mon(1, "B", 3)]
    after = [mon(0, "A", 0), mon(1, "B", 0)]
    assert newly_fainted_slots(before, after) == [0, 1]

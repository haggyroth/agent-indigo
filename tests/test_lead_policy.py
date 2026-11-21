"""Who leads: the lowest viable Pokémon outside boss fights, the strongest in them (pure; no emulator)."""
from types import SimpleNamespace as NS

from knowledge.party import boss_lead, travel_lead


def mon(name, level, hp=100, max_hp=100, attacks=True):
    return NS(species_name=name, level=level, current_hp=hp, max_hp=max_hp, move_names=["Tackle"] if attacks else ["Growl"], pp=[10] if attacks else [10])


def test_the_lowest_level_close_to_the_top_leads_not_the_ace():
    party = [mon("Charizard", 45), mon("Butterfree", 37), mon("Pikachu", 38), mon("Dugtrio", 37)]
    assert travel_lead(party) == 1                         # the first of the L37s — a tie keeps the earlier slot


def test_a_member_far_behind_the_top_does_not_lead_grind_trains_it():
    party = [mon("Ace", 45), mon("Tiny", 20), mon("Mid", 36)]
    assert travel_lead(party) == 2                         # Tiny is 25 under: not for the road


def test_a_hurt_or_attackless_or_fainted_member_never_leads():
    party = [mon("Ace", 45), mon("Hurt", 30, hp=20), mon("Mute", 31, attacks=False), mon("Down", 32, hp=0), mon("Fit", 40)]
    assert travel_lead(party) == 4
    assert travel_lead([mon("A", 40, hp=0), mon("B", 30, hp=0)]) is None


def test_when_nobody_else_is_close_enough_the_strongest_leads():
    assert travel_lead([mon("Ace", 50), mon("Low", 12), mon("Low2", 14)]) == 0


def test_the_boss_lead_is_the_strongest_healthy_attacker():
    party = [mon("Mid", 38), mon("Ace", 45), mon("Hurt", 50, hp=10), mon("Mute", 60, attacks=False)]
    assert boss_lead(party) == 1
    assert boss_lead([mon("A", 40, hp=0)]) is None
    assert boss_lead([mon("A", 40), mon("B", 40)]) == 0     # a tie keeps the earlier slot


def test_the_ace_gap_closes_a_single_party_of_one_stays_put():
    assert travel_lead([mon("Solo", 22)]) == 0 and boss_lead([mon("Solo", 22)]) == 0

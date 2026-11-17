"""Battle roster + switch-in matchups (#246): the whole party against the current foe, fainted ones marked (no emulator)."""
from game.state import PokemonStatus
from knowledge.matchup import better_matchup, best_attack, foe_pressure, label, roster, switch_options


def mon(species, sid, hp, mx, moves=(), nick="", level=10):
    names = list(moves) + [""] * (4 - len(moves))
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=mx, status="healthy", species_id=sid, species_name=species,
                         nickname=nick, move_names=names, pp=[20 if n else 0 for n in names])


# the party from a watched run: a fainted Ivysaur in slot 1 while Kakuna fights an Ekans
IVY = mon("IVYSAUR", 2, 0, 50, ["Vine Whip", "Tackle"], level=16)
PIKA = mon("PIKACHU", 25, 0, 21, ["Thunder Shock"], nick="Zappy Boy", level=6)
KAK = mon("KAKUNA", 14, 16, 25, ["Poison Sting", "Harden"], nick="Sir Wiggle", level=8)
PID = mon("PIDGEY", 16, 7, 22, ["Gust", "Tackle"], nick="Sky High", level=6)


def test_roster_marks_fainted_and_active_and_scores_the_rest():
    line = roster([IVY, PIKA, KAK, PID], active_species=14, foe_name="EKANS", foe_level=11)
    assert "1 Ivysaur FAINTED" in line and "Zappy Boy(Pikachu) FAINTED" in line
    assert "3 Sir Wiggle(Kakuna) ACTIVE 16/25" in line
    assert "4 Sky High(Pidgey) 7/22" in line and "FAINTED ones cannot be switched in" in line
    assert roster([KAK], 14, "EKANS") == ""                            # nobody to compare with


def test_pressure_and_best_attack_use_real_types():
    assert foe_pressure(("POI",), mon("PIDGEY", 16, 5, 5)) == 1          # Normal/Flying takes Poison neutrally
    assert foe_pressure(("POI",), mon("PIKACHU", 25, 5, 5)) == 1
    assert foe_pressure(("FLY",), mon("BULBASAUR", 1, 5, 5)) == 2        # Grass/Poison hit by Flying: ×2 (Grass), Poison ×1
    move, mult = best_attack(PID, ("BUG", "POI"), 9)
    assert move == "Gust" and mult == 2                                  # Flying vs Bug ×2


def test_better_matchup_names_the_switch_only_when_it_is_clearly_better():
    # Poison Sting is resisted by Poison Ekans (×0.5) and Pidgey hits it neutrally without being hurt: switch
    fit_pid = mon("PIDGEY", 16, 20, 22, ["Gust", "Tackle"], nick="Sky High", level=6)
    assert better_matchup([IVY, PIKA, KAK, PID], 14, "EKANS", 11) == ""            # 7/22 is too hurt to be offered
    tip = better_matchup([IVY, PIKA, KAK, fit_pid], 14, "EKANS", 11)
    assert "switch_pokemon('Sky High')" in tip and "Poison Sting) is ×0.5" in tip
    # an Electric attacker against Rock/Ground Onix: immune AND the foe's Ground hits it ×2 — Bulbasaur's Vine Whip is ×4
    pika = mon("PIKACHU", 25, 20, 20, ["Thunder Shock"], nick="Zappy Boy")
    bulb = mon("BULBASAUR", 1, 30, 30, ["Vine Whip"])
    tip = better_matchup([pika, bulb], 25, "ONIX", 12)
    assert "switch_pokemon('BULBASAUR')" in tip and "Vine Whip ×4" in tip and "×0" in tip
    assert better_matchup([pika, bulb], 1, "ONIX", 12) == ""                       # the best mon is already out
    hurt = mon("BULBASAUR", 1, 2, 30, ["Vine Whip"])
    assert better_matchup([pika, hurt], 25, "ONIX", 12) == ""                      # too hurt to be offered
    assert better_matchup([IVY, PIKA, KAK, PID], 14, "CATERPIE", 9) == ""          # a fair fight: no needless free hit


def test_switch_options_lists_only_the_living_and_not_the_active():
    out = switch_options([IVY, PIKA, KAK, PID], active_species=14)
    assert out == "Can switch to: 4:Sky High(Pidgey) (7/22)"
    assert switch_options([IVY, PIKA], 14) == "Nobody else is able to fight."
    assert label(mon("RATTATA", 19, 1, 1)) == "Rattata"


def test_roster_labels_are_valid_switch_targets():
    """The model copies 'Sir Wiggle(Kakuna)' from the roster line straight into switch_pokemon."""
    from knowledge.targets import resolve_mon
    party = [IVY, PIKA, KAK, PID]
    for p in party:
        assert resolve_mon(label(p), party).index == party.index(p)

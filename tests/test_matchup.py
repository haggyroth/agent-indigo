"""Battle roster + switch-in matchups (#246): the whole party against the current foe, fainted ones marked (no emulator)."""
from game.state import PokemonStatus
from knowledge.matchup import better_matchup, best_attack, foe_hit, foe_pressure, label, my_speed, roster, switch_options


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


# ── speed, real foe moves, abilities, KO risk, low-HP advice ────────────────────────────────────────────────────
from knowledge.matchup import Foe, low_hp_advice                      # noqa: E402


def stat_mon(species, sid, hp, mx, moves, stats, nick="", level=10, status="healthy"):
    m = mon(species, sid, hp, mx, moves, nick=nick, level=level)
    m.stats, m.status = stats, status
    return m


def test_known_foe_moves_replace_the_stab_guess():
    pid = mon("PIDGEY", 16, 20, 22, ["Gust"])
    assert foe_pressure(("ELE",), pid) == 2                                    # no moves known: STAB guess, Electric vs Flying
    assert foe_pressure(("ELE",), pid, ("Thunder Shock",)) == 2
    assert foe_pressure(("ELE",), pid, ("Quick Attack", "Growl")) == 1         # an Electric mon that only knows Quick Attack: ×1


def test_levitate_makes_ground_moves_count_as_immune():
    dig = mon("SANDSHREW", 27, 20, 20, ["Earthquake", "Tackle"], level=30)
    assert best_attack(dig, ("POI",), 20) == ("Earthquake", 2.0)               # Ground is super effective on Poison…
    assert best_attack(dig, ("POI",), 20, foe_ability=26) == ("Tackle", 1.0)   # …until Levitate makes it do nothing
    line = roster([dig, KAK], 27, foe=Foe(name="KOFFING", level=20, ability=26))
    assert "Levitate: Ground moves do nothing" in line


def test_speed_shows_in_the_roster_and_paralysis_halves_it():
    fast = stat_mon("PIDGEY", 16, 20, 22, ["Gust"], (22, 10, 10, 30, 8, 8))
    slow = stat_mon("KAKUNA", 14, 20, 25, ["Poison Sting"], (25, 8, 12, 5, 6, 6))
    foe = Foe(name="EKANS", level=10, speed=20)
    line = roster([slow, fast], 14, foe=foe)
    assert "Pidgey 20/22 — Gust ×1, takes ×1, outspeeds" in line and "ACTIVE 20/25" in line and "outsped" in line
    assert my_speed(stat_mon("PIDGEY", 16, 5, 5, [], (5, 1, 1, 30, 1, 1), status="paralyzed")) == 15


def test_foe_hit_uses_the_gen3_formula_and_physical_special_split():
    # L20 Raticate-like Normal attacker, Atk 40, Tackle (35): (2*20//5+2)=10 → 10*35*40//30//50+2 = 11, no STAB for a Pidgey-typed mon vs ...
    foe = Foe(name="RATICATE", level=20, attack=40, sp_attack=30, moves=("Tackle", "Growl"))
    target = stat_mon("PIDGEY", 16, 20, 22, ["Gust"], (22, 10, 30, 20, 8, 25))
    assert foe_hit(foe, target) == 10 * 35 * 40 // 30 // 50 + 2 + (10 * 35 * 40 // 30 // 50 + 2) // 2     # STAB ×1.5, Normal ×1 vs Pidgey
    assert foe_hit(Foe(name="RATICATE"), target) is None                       # nothing known → no guess
    assert foe_hit(foe, mon("PIDGEY", 16, 5, 5)) is None                        # our stats unknown


def test_low_hp_advice_ko_risk_switch_and_heal():
    foe = Foe(name="RATICATE", level=20, hp=40, max_hp=40, attack=40, sp_attack=30, speed=40, moves=("Tackle",))
    weak = stat_mon("KAKUNA", 14, 6, 25, ["Poison Sting"], (25, 8, 12, 5, 6, 6), nick="Sir Wiggle")
    ok = stat_mon("PIDGEY", 16, 22, 22, ["Gust"], (22, 10, 30, 20, 8, 25), nick="Sky High")
    tip = low_hp_advice([weak, ok], 14, foe, heals=[("Potion", 20), ("Super Potion", 50)], wild=True)
    assert "Low HP: Sir Wiggle(Kakuna) 6/25" in tip and "enough to KO it" in tip
    assert "switch_pokemon('Sky High')" in tip and "only way to keep this one alive" in tip
    assert "use_item('Super Potion')" in tip and "survives the hit" in tip and "flee_battle()" in tip
    assert "use_item('Potion')" not in tip                                      # a plain Potion (+20) would not outlast a 37 hit
    weaker = stat_mon("KAKUNA", 14, 6, 25, ["Poison Sting"], (25, 8, 12, 5, 6, 6))
    assert "would not survive" in low_hp_advice([weaker, ok], 14, Foe(**{**foe.__dict__, "attack": 400}), heals=[("Potion", 20)])
    healthy = stat_mon("KAKUNA", 14, 25, 25, ["Poison Sting"], (25, 8, 12, 5, 6, 6))
    assert low_hp_advice([healthy, ok], 14, foe) == ""                         # healthy and not in danger: silence


def test_low_hp_advice_prefers_finishing_a_nearly_dead_foe_when_faster():
    foe = Foe(name="RATTATA", level=5, hp=2, max_hp=20, attack=10, sp_attack=8, speed=10, moves=("Tackle",))
    me = stat_mon("PIDGEY", 16, 3, 22, ["Gust"], (22, 10, 10, 30, 8, 8))
    tip = low_hp_advice([me, KAK], 16, foe)
    assert "use_move('Gust') may finish it first" in tip

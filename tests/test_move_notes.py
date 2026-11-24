"""What the model is told about its moves (no emulator): STAB, type immunities, and status moves a foe's type blocks."""
from knowledge.battle import annotate_moves, battle_summary
from knowledge.move_semantics import gets_stab, status_blocked


def test_a_move_of_the_attackers_own_type_is_marked_stab_and_others_are_not():
    out = annotate_moves(["Wing Attack", "Thunder Wave", "Quick Attack"], "RATTATA", attacker_types=("NOR", "FLY"))
    assert "Wing Attack[Flying/Phys ×1 STAB" in out and "Quick Attack[Normal/Phys ×1 STAB" in out
    assert "Thunder Wave" in out and "STAB" not in out.split("Thunder Wave")[1].split("Quick Attack")[0]
    assert "STAB" not in annotate_moves(["Thunder Shock"], "RATTATA", attacker_types=("NOR", "FLY"))


def test_fixed_damage_and_status_moves_never_get_stab():
    assert not gets_stab("Seismic Toss", ("FIG",)) and not gets_stab("Toxic", ("POI",)) and gets_stab("Earthquake", ("GRD",))


def test_an_immune_target_says_no_effect_and_drops_stab():
    out = annotate_moves(["Tackle", "Earthquake", "Shadow Ball"], "GASTLY", attacker_types=("NOR", "GRD"))
    assert "STAB" not in out.split("Tackle")[1].split("Earthquake")[0]                   # an immune move earns nothing
    assert "×0 IMMUNE — NO EFFECT" in out.split("Tackle")[1].split("Earthquake")[0]
    out = annotate_moves(["Earthquake"], "PIDGEOT", attacker_types=("GRD",))
    assert "×0 IMMUNE — NO EFFECT]" in out                                   # ground vs flying


def test_status_moves_say_when_the_foes_type_blocks_them():
    assert "NO EFFECT on this foe" in annotate_moves(["Thunder Wave"], "DUGTRIO")
    assert "NO EFFECT on this foe" in annotate_moves(["Toxic"], "BEEDRILL")
    assert "NO EFFECT on this foe" in annotate_moves(["Leech Seed"], "BULBASAUR") and "NO EFFECT" not in annotate_moves(["Leech Seed"], "RATTATA")
    assert "NO EFFECT" not in annotate_moves(["Thunder Wave"], "PIDGEY")
    assert status_blocked("Will-O-Wisp", ("FIR",)) and not status_blocked("Will-O-Wisp", ("WAT",)) and not status_blocked("Growl", ("GRD",))


def test_the_best_move_line_names_stab():
    out = battle_summary(["Earthquake", "Tackle"], "GEODUDE", 100, [10, 10], attacker_types=("GRD",))
    assert "Best move: Earthquake" in out and "+ STAB" in out

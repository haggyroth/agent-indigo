"""Move semantics (#204): expected damage that knows accuracy and what moves actually do (no emulator)."""
import pytest

from knowledge.battle import annotate_moves, battle_summary
from knowledge.move_effects import MOVE_FX
from knowledge.move_semantics import catch_setup_hint, kind_of, move_score, role_tag


def test_generated_table_matches_the_decomp_for_known_moves():
    assert MOVE_FX["Fissure"][:2] == ("OHKO", 30)
    assert MOVE_FX["Dream Eater"][0] == "DREAM_EATER"
    assert MOVE_FX["Mean Look"][0] == "MEAN_LOOK"
    assert MOVE_FX["Swift"][1] == 0                      # never misses
    assert MOVE_FX["Quick Attack"][2] == 1               # priority


def test_dream_eater_only_scores_against_a_sleeping_foe():
    assert move_score("Dream Eater") == 0
    assert move_score("Dream Eater", foe_asleep=True) == pytest.approx(100)


def test_one_hit_kos_reactive_and_suicide_moves_are_never_auto_picked():
    for m in ("Fissure", "Guillotine", "Horn Drill", "Sheer Cold", "Counter", "Mirror Coat", "Bide",
              "Focus Punch", "Explosion", "Self-Destruct", "Snore"):
        assert move_score(m) == 0, m


def test_accuracy_and_two_turn_and_recharge_are_priced_in():
    assert move_score("Thunder") < move_score("Thunderbolt")                 # 120 @70% vs 95 @100%
    assert move_score("Hyper Beam") == pytest.approx(150 * 0.9 * 0.5)       # recharge turn
    assert move_score("Solar Beam") == pytest.approx(120 * 1.0 * 0.5)       # charge turn
    assert move_score("Swift") == pytest.approx(60)                          # never misses


def test_fixed_damage_ignores_stab_and_super_effective_but_respects_immunity():
    assert move_score("Seismic Toss", ("FIG",), ("NOR",), user_level=30) == pytest.approx(
        move_score("Seismic Toss", (), (), user_level=30))
    assert move_score("Night Shade", (), ("NOR",), user_level=30) == 0       # Ghost vs Normal
    assert move_score("Seismic Toss", (), ("GHO",), user_level=30) == 0      # Fighting vs Ghost
    assert move_score("Seismic Toss", user_level=50) > move_score("Seismic Toss", user_level=10)


def test_friendship_and_hp_scaled_moves():
    assert move_score("Return", friendship=255) > move_score("Return", friendship=70) == pytest.approx(28)
    assert move_score("Frustration", friendship=70) > move_score("Frustration", friendship=255)
    assert move_score("Flail", user_hp_frac=0.05) > move_score("Flail", user_hp_frac=1.0)
    assert move_score("Eruption", user_hp_frac=1.0) > move_score("Eruption", user_hp_frac=0.2)


def test_status_moves_score_zero_and_hidden_power_ignores_type_guesses():
    for m in ("Growl", "Mean Look", "Splash", "Protect", "Whirlwind", "Disable", "Sleep Powder", "Toxic"):
        assert move_score(m) == 0, m
    assert move_score("Hidden Power", (), ("GHO",)) == move_score("Hidden Power", (), ())    # type unknown (IVs)


def test_roles_cover_the_moves_the_review_called_out():
    assert kind_of("Mean Look") == "mean_look" and "can't run" in role_tag("Mean Look")
    assert "ENDS" in role_tag("Roar", wild=True) and "random switch" in role_tag("Roar", wild=False)
    assert "ESCAPES" in role_tag("Teleport", wild=True)
    assert "twice in a row" in role_tag("Protect")
    assert "does nothing" in role_tag("Splash")
    assert "holds the foe" in role_tag("Wrap")
    assert role_tag("Disable")
    assert "asleep" in role_tag("Dream Eater") and role_tag("Dream Eater", foe_asleep=True).startswith("foe is asleep")
    assert "FAILS" in role_tag("Fissure", user_level=10, foe_level=20)
    assert role_tag("Tackle") == "" and "70%" in role_tag("Blizzard")


def test_annotated_moves_show_the_role_tag():
    out = annotate_moves(["Mean Look", "Dream Eater", "Tackle"], "RATTATA", [5, 15, 35], wild=True)
    assert "traps the foe" in out and "FAILS unless the foe is asleep" in out
    assert "Tackle[Normal/Phys ×1 PP:35]" in out


def test_best_move_never_suggests_a_move_that_cannot_work():
    out = battle_summary(["Dream Eater", "Tackle"], "RATTATA", 1.0, pp_list=[15, 35])
    assert "Best move: Tackle" in out
    out = battle_summary(["Dream Eater", "Tackle"], "RATTATA", 1.0, pp_list=[15, 35], opponent_status="asleep (3 turns)")
    assert "Best move: Dream Eater" in out


def test_catch_setup_hint_prefers_false_swipe_then_status_and_skips_empty_pp():
    h = catch_setup_hint(["False Swipe", "Sleep Powder", "Mean Look", "Tackle"], [10, 5, 5, 30])
    assert h.startswith("Catch setup you have: False Swipe") and "Sleep Powder" in h and "Mean Look" in h
    assert catch_setup_hint(["False Swipe", "Tackle"], [0, 30]) == ""
    assert catch_setup_hint(["Tackle"], [30]) == ""

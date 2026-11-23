"""Status cures in the Bag, the battle nudge, and the Elite Four's level wall (pure)."""
from types import SimpleNamespace as NS

from knowledge.beat_readiness import hard_wall, level_shortfall
from knowledge.status_cure import cure_hint, cure_ids, status_key


def test_status_words_from_the_reader():
    assert status_key("asleep (3 turns)") == "asleep" and status_key("paralyzed") == "paralyzed"
    assert status_key("healthy") == "" and status_key("") == "" and status_key("unknown") == ""


def test_the_specific_cure_comes_first_then_full_heal_then_full_restore():
    bag = {18: 2, 23: 5, 19: 1}
    assert cure_ids("paralyzed", bag) == [18, 23, 19]
    assert cure_ids("paralyzed", {23: 1}) == [23]
    assert cure_ids("frozen", {18: 2}) == []                          # a Paralyze Heal does nothing for ice
    assert cure_ids("healthy", bag) == []


def test_the_battle_nudge_names_the_item_the_bag_holds():
    line = cure_hint("Lapras", "paralyzed", {23: 5})
    assert "Lapras is paralyzed" in line and "use_item('Full Heal')" in line and "you hold 5" in line
    assert cure_hint("Lapras", "asleep (2 turns)", {17: 1, 23: 2}).startswith("STATUS: Lapras is asleep") and "Cure it now" in cure_hint("Lapras", "frozen", {23: 1})
    assert cure_hint("Lapras", "paralyzed", {}) == "" and cure_hint("Lapras", "healthy", {23: 5}) == ""


def test_a_full_restore_is_not_spent_on_a_status_while_the_mon_is_healthy_enough():
    assert cure_hint("Lapras", "paralyzed", {19: 3}, hp_frac=0.9) == ""
    assert "Full Restore" in cure_hint("Lapras", "paralyzed", {19: 3}, hp_frac=0.3)


def test_the_elite_four_level_wall_has_no_second_call_override():
    weak = [NS(level=lv) for lv in (52, 46, 46, 45, 44, 44)]
    strong = [NS(level=lv) for lv in (58, 52, 50, 48, 47, 46)]
    assert level_shortfall("elite_four", weak) and not level_shortfall("elite_four", strong)
    wall = hard_wall("elite_four", weak)
    assert wall.startswith("Not ready for quest('elite_four')") and "cannot be skipped" in wall and "grind()" in wall
    assert hard_wall("elite_four", weak) == wall                       # every call, not once
    assert hard_wall("elite_four", strong) == ""
    assert hard_wall("victory_road", weak) == ""                       # other beats keep their one-time warning


# ── the optional League loss rule ──────────────────────────────────────────────────────────────────
from knowledge.beat_readiness import MAX_FLOOR, MAX_TOP, league_need, loss_advice  # noqa: E402


def _team(*levels):
    return [NS(level=lv) for lv in levels]


def test_each_loss_raises_the_levels_by_the_bump_up_to_a_cap():
    assert (league_need(0, 2).top, league_need(0, 2).floor) == (54, 46)
    assert (league_need(2, 2).top, league_need(2, 2).floor) == (58, 50)
    assert (league_need(50, 3).top, league_need(50, 3).floor) == (MAX_TOP, MAX_FLOOR)
    assert league_need(3, 0).top == 54                                  # a bump of 0 is the rule switched off


def test_the_advice_is_silent_without_losses_or_when_the_rule_is_off_or_the_team_is_ready():
    weak = _team(55, 50, 49, 48, 47, 46)
    assert loss_advice(weak, 0, 2) == "" and loss_advice(weak, 3, 0) == "" and loss_advice(weak, 3, 2, "off") == ""
    assert loss_advice(_team(60, 55, 52, 51, 50, 50), 2, 2) == ""


def test_the_advice_says_training_is_encouraged_not_required():
    out = loss_advice(_team(55, 50, 49, 48, 47, 46), 2, 2)               # the base levels are met; two losses raise them to L58 / L50
    assert "lost in the Pokémon League 2 losses" in out and "L58" in out and "L50+" in out
    assert "encouraged, not required" in out and "call quest('elite_four') again to go anyway" in out
    assert "refuse" in loss_advice(_team(55, 50, 49, 48, 47, 46), 2, 2, "wall")


def test_in_wall_mode_the_raised_levels_are_the_wall():
    team = _team(55, 50, 49, 48, 47, 46)                                 # meets the base (54 / 46) but not 2 losses' worth (58 / 50)
    assert hard_wall("elite_four", team) == "" and hard_wall("elite_four", team, 2, 2, "advise") == ""
    assert "L58" in hard_wall("elite_four", team, 2, 2, "wall")
    assert hard_wall("elite_four", team, 0, 2, "wall") == ""             # no losses, no escalation

"""Late-game / vision-only prompt sections are left out until they can matter (token trim, #246). No emulator."""
from types import SimpleNamespace as NS

from knowledge.system_prompt import build_system_prompt


def prompt(badges, vision):
    ltm = NS(data={"badges_earned": badges, "gyms_beaten": [], "towns_visited": [], "milestones": [],
                   "battles_won": 0, "battles_lost": 0, "starter": "x"})
    return build_system_prompt(ltm, NS(get_loss_lessons=lambda e: ""), use_vision=vision)


def test_early_game_text_only_prompt_is_lean():
    s = prompt(0, False)
    assert "Preparing for a Gym" in s                                    # Brock prep while there is no badge
    assert "Game Corner" not in s and "Safari Zone" not in s and "Screenshot — How to Read" not in s
    assert "Battle Menu Navigation" not in s and "PP rules" in s


def test_sections_unlock_with_badges_and_vision():
    assert "Preparing for a Gym" not in prompt(1, False)
    assert "Game Corner" in prompt(3, False) and "Safari Zone" not in prompt(3, False)
    assert "Safari Zone" in prompt(4, False)
    assert "Screenshot — How to Read" in prompt(0, True) and "Overworld Orientation" in prompt(0, True)
    assert len(prompt(1, False)) < len(prompt(4, True)) - 2500           # the trim is real (~700+ tokens)


def test_the_prompt_says_six_is_a_ceiling_and_the_party_is_free_to_reshape():
    """A watched team of filler (Wigglytuff, Raichu, a Pidgeot…) followed 'aim for a full party of 6': quality over slots, and the PC is the model's to use."""
    for s in (prompt(0, False), prompt(8, False)):
        assert "quality over slots" in s and "CEILING, not a goal" in s
        assert "FREE to restructure the party" in s and "leaving a slot EMPTY is fine" in s
        assert "full party of 6" not in s

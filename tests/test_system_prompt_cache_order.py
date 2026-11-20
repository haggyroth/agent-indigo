"""The system prompt keeps what changes as you play LAST, so the long static rules stay an identical prefix the server can reuse from its prompt cache (a watched run: 54% of prompt tokens cached,
and only ~224 on the first call of most steps, because 'Battles: N won' sat at the top and changed nearly every step). No emulator."""
import os
from types import SimpleNamespace as NS

from knowledge.system_prompt import build_system_prompt


def prompt(**over):
    data = {"badges_earned": 1, "gyms_beaten": ["Brock"], "towns_visited": ["Pallet Town"], "milestones": ["starter_chosen"], "battles_won": 10, "battles_lost": 0, "starter": "squirtle"}
    data.update(over)
    return build_system_prompt(NS(data=data), NS(get_loss_lessons=lambda e: "LESSON: lead with water" if e else ""), use_vision=True, current_enemy=over.get("enemy", ""))


def test_play_progress_only_changes_the_end_of_the_prompt():
    a = prompt()
    b = prompt(battles_won=11, towns_visited=["Pallet Town", "Viridian City"], milestones=["starter_chosen", "got_cut"], battles_lost=1)
    c = prompt(enemy="Misty")                                                       # a battle with loss lessons
    for other in (b, c):
        shared = len(os.path.commonprefix([a, other]))
        assert shared / len(a) > 0.9, f"only {shared / len(a):.0%} of the prompt is a shared prefix"
        assert shared > a.index("## Current status") - 5                            # nothing before the status block differs


def test_the_changing_blocks_are_in_the_final_status_section():
    s = prompt()
    head, _, tail = s.partition("## Current status")
    assert "Battles: 10 won" in tail and "Gyms beaten: Brock" in tail and "### Navigation" in tail
    assert "Battles:" not in head and "Towns visited" not in head and "### Navigation" not in head

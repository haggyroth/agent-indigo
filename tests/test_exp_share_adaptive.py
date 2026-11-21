"""The Exp. Share follows the lowest-level Pokémon (no emulator): the plan, the upkeep and its failure handling."""
from types import SimpleNamespace as NS

import pytest

from knowledge.held_items import EXP_SHARE, exp_share_plan


def mon(name, level, held=0, hp=50, pid=None):
    return NS(species_name=name, nickname="", level=level, held_item=held, max_hp=hp, personality=pid if pid is not None else hash(name) & 0xFFFF)


def test_nothing_to_do_without_an_exp_share():
    assert exp_share_plan([mon("A", 30), mon("B", 10)], owns_one=False) is None


def test_it_goes_to_the_lowest_level_when_it_is_in_the_bag():
    holder, target = exp_share_plan([mon("Ace", 40), mon("Mid", 25), mon("Tiny", 12)], owns_one=True)
    assert holder is None and target.species_name == "Tiny"


def test_it_moves_when_the_holder_is_no_longer_the_lowest():
    party = [mon("Ace", 40), mon("Mid", 25), mon("Tiny", 26, held=EXP_SHARE)]            # Tiny levelled past Mid
    holder, target = exp_share_plan(party, owns_one=False)
    assert holder.species_name == "Tiny" and target.species_name == "Mid"


def test_the_holder_stays_when_it_is_the_lowest_or_tied():
    assert exp_share_plan([mon("Ace", 40), mon("Tiny", 12, held=EXP_SHARE)], False) is None
    assert exp_share_plan([mon("Ace", 40), mon("Mid", 25), mon("Tiny", 25, held=EXP_SHARE)], False) is None       # a tie never thrashes
    assert exp_share_plan([mon("A", 25, held=EXP_SHARE), mon("B", 25)], False) is None


def test_a_fainted_member_still_counts_and_an_empty_party_is_ignored():
    holder, target = exp_share_plan([mon("Ace", 40), mon("Down", 5, hp=30)], True)
    assert target.species_name == "Down"
    assert exp_share_plan([], True) is None and exp_share_plan([NS(level=3, held_item=0, max_hp=0)], True) is None


pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402
from game.state import GameContext  # noqa: E402


def client(party, bag=((182, 1),), ctx=GameContext.OVERWORLD):
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(detect_context=lambda: ctx, read_party=lambda: party, read_items_pocket=lambda: list(bag))
    c.calls = []
    return c


def test_the_upkeep_takes_it_from_the_old_holder_then_gives_it_to_the_new_lowest():
    party = [mon("Ace", 40), mon("Mid", 25), mon("Tiny", 26, held=EXP_SHARE)]
    c = client(party)
    c._take_item = lambda who: (c.calls.append(("take", who)), "Took the Exp. Share back from Tiny.")[1]
    c._give_item = lambda item, who: (c.calls.append(("give", item, who)), "Mid now holds Exp. Share.")[1]
    note = c._maintain_exp_share()
    assert c.calls == [("take", "Tiny"), ("give", "Exp. Share", "Mid")] and "Mid L25" in note and "from Tiny" in note


def test_the_upkeep_only_gives_when_nobody_holds_it_and_is_silent_when_nothing_is_needed():
    c = client([mon("Ace", 40), mon("Tiny", 12)])
    c._take_item = lambda who: pytest.fail("nobody to take it from")
    c._give_item = lambda item, who: (c.calls.append(("give", who)), "Tiny now holds Exp. Share.")[1]
    assert "Tiny" in c._maintain_exp_share() and c.calls == [("give", "Tiny")]
    quiet = client([mon("Ace", 40), mon("Tiny", 12, held=EXP_SHARE)], bag=())
    assert quiet._maintain_exp_share() is None


def test_the_upkeep_does_nothing_off_the_field():
    c = client([mon("Ace", 40), mon("Tiny", 12)], ctx=GameContext.IN_BATTLE)
    c._give_item = lambda *a: pytest.fail("not in a battle")
    assert c._maintain_exp_share() is None


def test_a_move_that_keeps_failing_is_dropped_after_two_tries_until_the_party_changes():
    party = [mon("Ace", 40), mon("Tiny", 12)]
    c = client(party)
    c._give_item = lambda item, who: (c.calls.append(who), "Couldn't give it.")[1]
    assert "Couldn't" in c._maintain_exp_share() and "Couldn't" in c._maintain_exp_share()
    assert c._maintain_exp_share() is None and len(c.calls) == 2
    party[1].level = 13                                                                 # the party changed: a fresh attempt
    assert c._maintain_exp_share() is not None

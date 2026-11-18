"""quest('dig') / quest('hitmon') / quest('magikarp') (#278): the early returns, the beat wiring and the constants (no emulator)."""
from types import SimpleNamespace as NS

import pytest

from knowledge import story_beats as sb

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402
from agent.skills import errands                   # noqa: E402


def client(flags=(), money=2000, items=(), party=3, ctx="OVERWORLD", tea=True):
    from game.state import GameContext
    c = AgentClient.__new__(AgentClient)
    flags = set(flags) | ({errands.FLAG_GOT_TEA} if tea else set())
    c.reader = NS(read_flag=lambda f: f in flags, read_money=lambda: money, count_item=lambda i: 1 if i in items else 0,
                  read_party=lambda: [object()] * party, read_key_items=lambda: [], detect_context=lambda: getattr(GameContext, ctx))
    c._gift_errand = lambda *a, **k: pytest.fail("should not have travelled")
    return c


def test_the_beats_exist_with_drivers_flags_and_a_sane_chain_position():
    for key, flag, needs in (("dig", 0x23F, ("misty",)), ("magikarp", 0x249, ("brock",)), ("hitmon", 0x278, ("tea",))):
        b = sb.BY_KEY[key]
        assert b.driver == key and b.optional and ("flag", flag) in b.done and b.needs == needs, key
    assert errands.FLAG_BEAT_KOICHI == 0x63D and errands.FLAG_GOT_TM28 == 0x23F


def test_each_gift_says_so_when_it_is_already_yours():
    assert "already have TM28" in client(flags={errands.FLAG_GOT_TM28})._get_dig()
    assert "already have TM28" in client(items={errands.TM28_ITEM})._get_dig()
    assert "already took a Pokémon" in client(flags={errands.FLAG_GOT_HITMON})._get_hitmon()
    assert "already bought" in client(flags={errands.FLAG_BOUGHT_MAGIKARP})._get_magikarp()


def test_the_dojo_wants_tea_and_the_magikarp_wants_500_yen():
    assert "Tea first" in client(tea=False)._get_hitmon()
    assert "costs ¥500 and you have ¥120" in client(money=120)._get_magikarp()
    assert "in a battle" in client(ctx="IN_BATTLE")._get_dig()


def test_the_errands_pass_the_right_yes_no_answers_and_the_magikarp_notes_a_full_party():
    seen = []
    c = client(party=6)
    c._gift_errand = lambda call, dest, dm, spots, flag, who, auto, answers=("yes",): (seen.append((dest, answers)), None)[1]
    out = c._get_magikarp()
    assert seen == [("Route 4 Magikarp House", ("yes", "no"))] and "PC box" in out          # buy = YES, the nickname box = NO
    c = client(party=6)
    c._gift_errand = lambda call, dest, dm, spots, flag, who, auto, answers=("yes",): (seen.append((who, answers)), None)[1]
    c.reader.read_flag = lambda f: f in {errands.FLAG_GOT_TEA, errands.FLAG_BEAT_KOICHI}          # Koichi already beaten: straight to the ball
    out = c._get_hitmon()
    assert seen[-1] == ("the Hitmonchan ball", ("yes", "no")) and "PC box" in out

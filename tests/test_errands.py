"""quest('flash') / quest('fly') (#268): the early returns before any travel (no emulator)."""
from types import SimpleNamespace as NS

import pytest

from knowledge import story_beats as sb

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402
from agent.skills import errands                   # noqa: E402


def client(flags=(), seen=52, key_items=(), ctx="OVERWORLD"):
    from game.state import GameContext
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_flag=lambda f: f in flags, read_pokedex=lambda: (10, seen), read_key_items=lambda: list(key_items),
                  detect_context=lambda: getattr(GameContext, ctx))
    c._gift_errand = lambda *a, **k: pytest.fail("should not have travelled")
    return c


def test_the_two_beats_have_drivers_and_the_hms_are_recognised_as_done():
    assert sb.BY_KEY["flash"].driver == "flash" and sb.BY_KEY["fly"].driver == "fly"
    assert ("flag", errands.FLAG_GOT_HM05) in sb.BY_KEY["flash"].done and ("flag", errands.FLAG_GOT_HM02) in sb.BY_KEY["fly"].done


def test_flash_waits_for_ten_species_seen_and_says_when_it_is_already_yours():
    assert "have seen 6" in client(seen=6)._get_flash()
    assert "already have HM05" in client(flags={errands.FLAG_GOT_HM05})._get_flash()
    assert "in a battle" in client(ctx="IN_BATTLE")._get_flash()


def test_fly_needs_the_flute_and_the_snorlax_gone_before_it_will_travel():
    assert "Poké Flute first" in client()._get_fly()
    out = client(key_items=[errands.POKE_FLUTE_ITEM])._get_fly()
    assert "sleeping Snorlax at (31, 13)" in out and "(#272" not in out
    assert "already have HM02" in client(flags={errands.FLAG_GOT_HM02})._get_fly()
    c = client(flags={errands.FLAG_GOT_FLUTE, errands.FLAG_HIDE_ROUTE16_SNORLAX})
    c._gift_errand = lambda call, dest, *a, **k: f"went to {dest}"                       # past both checks: it travels to the house
    assert c._get_fly() == "went to Route 16 House"

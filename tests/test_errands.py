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
    c._can_use_cut = lambda: True
    return c


def test_the_two_beats_have_drivers_and_the_hms_are_recognised_as_done():
    assert sb.BY_KEY["flash"].driver == "flash" and sb.BY_KEY["fly"].driver == "fly"
    assert ("flag", errands.FLAG_GOT_HM05) in sb.BY_KEY["flash"].done and ("flag", errands.FLAG_GOT_HM02) in sb.BY_KEY["fly"].done


def test_flash_waits_for_ten_species_seen_and_says_when_it_is_already_yours():
    assert "have seen 6" in client(seen=6)._get_flash()
    assert "already have HM05" in client(flags={errands.FLAG_GOT_HM05})._get_flash()
    assert "in a battle" in client(ctx="IN_BATTLE")._get_flash()


def test_fly_needs_cut_not_the_flute_and_then_travels_to_the_house():
    c = client()
    c._can_use_cut = lambda: False
    out = c._get_fly()
    assert "cut the tree at (41,11)" in out and "quest('cut')" in out and "Poké Flute" not in out
    assert "already have HM02" in client(flags={errands.FLAG_GOT_HM02})._get_fly()
    c = client()
    c._can_use_cut = lambda: True
    c._gift_errand = lambda call, dest, *a, **k: f"went to {dest}"                       # past the Cut check: it travels to the house, no flute / Snorlax needed
    assert c._get_fly() == "went to Route 16 House"


def test_a_no_walking_route_message_is_reported_not_retried():
    """Route 4's Magikarp house from Cerulean's side: go_to says there is no walking route — the errand must hand that on, not loop 'didn't reach it yet'."""
    from agent.skills.errands import ErrandsMixin
    c = AgentClient.__new__(AgentClient)
    from game.state import GameContext
    c.reader = NS(read_current_map=lambda: (3, 22), detect_context=lambda: GameContext.OVERWORLD, read_flag=lambda f: False)
    c._go_to = lambda *a, **k: "There is no walking route to Route 4 Magikarp House from here: Route 4's ledges only go one way."
    out = ErrandsMixin._gift_errand(c, "quest('magikarp')", "Route 4 Magikarp House", (16, 0), (), 0x249, "the salesman", False)
    assert out.startswith("Can't reach Route 4 Magikarp House: There is no walking route")

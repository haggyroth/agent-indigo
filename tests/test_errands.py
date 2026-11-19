"""quest('flash') / quest('fly') (#268): the early returns before any travel (no emulator)."""
from types import SimpleNamespace as NS

import pytest

from knowledge import story_beats as sb

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402
from agent.skills import errands                   # noqa: E402


def client(flags=(), caught=19, key_items=(), ctx="OVERWORLD"):
    from game.state import GameContext
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_flag=lambda f: f in flags, read_pokedex=lambda: (caught, 52), read_key_items=lambda: list(key_items),
                  detect_context=lambda: getattr(GameContext, ctx))
    c._gift_errand = lambda *a, **k: pytest.fail("should not have travelled")
    c._can_use_cut = lambda: True
    return c


def test_the_two_beats_have_drivers_and_the_hms_are_recognised_as_done():
    assert sb.BY_KEY["flash"].driver == "flash" and sb.BY_KEY["fly"].driver == "fly"
    assert ("flag", errands.FLAG_GOT_HM05) in sb.BY_KEY["flash"].done and ("flag", errands.FLAG_GOT_HM02) in sb.BY_KEY["fly"].done


def test_flash_waits_for_ten_species_caught_and_says_when_it_is_already_yours():
    assert "have caught 6" in client(caught=6)._get_flash()
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


def test_the_itemfinder_and_exp_share_aides_count_species_caught():
    from knowledge.aides import AIDES, next_reward, ready
    assert [(k, n) for k, n, _f, _l in AIDES] == [("flash", 10), ("itemfinder", 30), ("exp_share", 50)]
    assert [k for k, _l, _n in ready(35, lambda f: False)] == ["flash", "itemfinder"]
    assert [k for k, _l, _n in ready(35, lambda f: f == 0x23B)] == ["itemfinder"]          # Flash already collected
    assert next_reward(35, lambda f: False) == ("the Exp. Share", 15) and next_reward(60, lambda f: True) is None
    assert "caught 12" in client(caught=12)._get_itemfinder()
    assert "wants 50 species CAUGHT for the Exp. Share and you have caught 31" in client(caught=31, flags={errands.FLAG_GOT_ITEMFINDER})._get_exp_share()
    assert "already have the Itemfinder" in client(flags={errands.FLAG_GOT_ITEMFINDER})._get_itemfinder()


def test_the_exp_share_goes_to_the_pokemon_that_lags():
    c = client(caught=60)
    party = [NS(level=40, nickname="", species_name="Ace", held_item=0, max_hp=100), NS(level=12, nickname="Tiny", species_name="Rattata", held_item=0, max_hp=30)]
    c.reader.read_party = lambda: party
    c._gift_errand = lambda *a, **k: None
    gave = []
    c._give_item = lambda item, who: (gave.append((item, who)), "Tiny now holds it.")[1]
    out = c._get_exp_share()
    assert gave == [("Exp. Share", "Tiny")] and "Got the Exp. Share" in out and "Tiny now holds it" in out         # the L12, not the L40 ace

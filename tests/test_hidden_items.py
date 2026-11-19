"""Hidden items worth walking to (#276): the filter, the per-map lookup and the 'taken' bookkeeping (no emulator)."""
from types import SimpleNamespace as NS

import pytest

from knowledge.hidden_items import hidden_on, worthwhile


def test_the_filter_keeps_what_changes_a_run_and_drops_the_filler():
    keep = ["Rare Candy (hidden)", "Pp Up (hidden)", "Max Revive (hidden)", "Full Restore (hidden)", "Nugget (hidden)", "Protein (hidden)", "Ether (hidden)",
            "Big Mushroom (hidden)", "Moon Stone (hidden)", "Tm46", "Ultra Ball (hidden)"]
    drop = ["Potion (hidden)", "Antidote (hidden)", "Chesto Berry (hidden)", "Lava Cookie (hidden)", "Tinymushroom (hidden)", "Poké Ball (hidden)", "Tmx"]
    assert all(worthwhile(n) for n in keep), [n for n in keep if not worthwhile(n)]
    assert not any(worthwhile(n) for n in drop), [n for n in drop if worthwhile(n)]


def test_route_9_lists_its_two_hidden_items_and_taken_ones_drop_out():
    assert hidden_on((3, 27)) == [("Ether", 15, 7), ("Rare Candy", 63, 2)]
    assert hidden_on((3, 27), taken={"3/27/15/7"}) == [("Rare Candy", 63, 2)]
    assert hidden_on((3, 27), taken={"3/27/15/7", "3/27/63/2"}) == []
    assert hidden_on((3, 0)) == [] and hidden_on((99, 99)) == []                 # no worthwhile hidden item / unknown map
    assert all(n.count("(hidden)") == 0 for n, _x, _y in hidden_on((1, 2)))      # the '(hidden)' tag is stripped from the name


pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402


def client(results):
    c = AgentClient.__new__(AgentClient)
    c.ltm = NS(data={})
    c.reader = NS(read_current_map=lambda: (3, 27), detect_context=lambda: __import__("game.state", fromlist=["x"]).GameContext.OVERWORLD)
    calls = []

    def pick(x, y, hidden=False):
        calls.append((x, y, hidden))
        return results[(x, y)]
    c._pick_ball = pick
    return c, calls


def test_hidden_pickups_are_marked_taken_when_collected_or_empty_but_not_when_unreachable():
    c, calls = client({(15, 7): ("Ether", ""), (63, 2): ("", "couldn't reach the item at (63,2)")})
    assert c._pick_hidden_here() == ["Ether (hidden)"]
    assert c.ltm.data["hidden_taken"] == ["3/27/15/7"]                           # the unreachable one is NOT written off
    c._pick_hidden_here()
    assert [x for x, _y, _h in calls] == [15, 63, 63] and all(h for _x, _y, h in calls)
    c2, _ = client({(15, 7): ("", "the item at (15,7) didn't respond"), (63, 2): ("Rare Candy", "")})
    assert c2._pick_hidden_here() == ["Rare Candy (hidden)"]
    assert sorted(c2.ltm.data["hidden_taken"]) == ["3/27/15/7", "3/27/63/2"]      # an empty tile is remembered too

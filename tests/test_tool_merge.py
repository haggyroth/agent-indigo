"""#213: pc(action), quest(name), reorder_party(first[, second]) replace eight tools; one shared target resolver."""
import importlib.util
from types import SimpleNamespace

import pytest

from agent.tools import TOOLS
from knowledge.story_beats import BY_KEY, listing, resolve

NAMES = {t["function"]["name"] for t in TOOLS}


def test_the_merged_tools_are_gone_and_the_front_doors_exist():
    assert not NAMES & {"pc_boxes", "pc_deposit", "pc_withdraw", "pc_swap", "set_lead", "get_cut", "get_ss_ticket"}
    assert {"pc", "quest", "reorder_party"} <= NAMES


def test_schemas_require_only_what_is_always_needed():
    by = {t["function"]["name"]: t["function"]["parameters"] for t in TOOLS}
    assert by["pc"]["required"] == ["action"] and by["pc"]["properties"]["action"]["enum"] == ["list", "deposit", "withdraw", "swap"]
    assert by["quest"]["required"] == [] and by["reorder_party"]["required"] == ["first"]


def test_the_quest_tool_takes_any_story_beat_by_name():
    from agent.tools import TOOLS
    props = next(t for t in TOOLS if t["function"]["name"] == "quest")["function"]["parameters"]["properties"]
    assert props["name"]["type"] == "string" and "enum" not in props["name"]          # ~25 beats: a free name, resolved fuzzily
    for name in ("ss_ticket", "cut", "surf", "strength", "coin_case", "rocket_hideout", "tea", "pokemon_tower", "silph_co"):
        assert resolve(name).key == name
    assert resolve("Strength").key == "strength" and resolve("nope") is None


def test_the_quest_listing_shows_done_next_and_blocked():
    def nothing_done(_spec):
        return False
    from knowledge.story_beats import evaluate
    text = listing(evaluate(nothing_done))
    assert "▶ parcel" in text and "… brock" in text and "first: parcel" in text
    assert resolve("ss ticket").key == "ss_ticket" and resolve("Cut").key == "cut"


def test_the_rocket_hideout_quest_is_in_the_chain_and_runs_after_erika():
    q = BY_KEY["rocket_hideout"]
    assert q.needs == ("erika",) and q.driver == "rocket_hideout"
    assert resolve("rocket") is q


def test_hideout_geometry_b4f_halves():
    from agent.skills.hideout import b4f_east
    assert not b4f_east(11, 15) and not b4f_east(3, 3)           # the stairs arrive in the west half
    assert b4f_east(20, 23) and b4f_east(19, 5) and b4f_east(16, 16)    # the elevator lands south; Giovanni's room is east


@pytest.mark.skipif(importlib.util.find_spec("openai") is None, reason="openai not installed")
def test_pc_front_door_validates_before_touching_the_emulator():
    from agent.lm_studio_client import AgentClient
    me = SimpleNamespace()
    assert "needs `pokemon`" in AgentClient._pc_tool(me, "deposit")
    assert "box_pokemon" in AgentClient._pc_tool(me, "swap", "Pidgey")
    assert "one of: list, deposit, withdraw, swap" in AgentClient._pc_tool(me, "release", "Pidgey")

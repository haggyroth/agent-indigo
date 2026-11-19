"""quest('new_game') without an emulator (#260): option parsing, the beat wiring, and the dispatcher handing the words after the name to the driver."""
from types import SimpleNamespace

import pytest

from agent.skills.newgame import STARTERS, parse_options
from knowledge import story_beats as sb


def test_defaults_and_options():
    assert parse_options([]) == {"starter": "bulbasaur", "name": "RED", "rival": "BLUE", "girl": False}
    o = parse_options(["squirtle", "name=kyle", "rival=GaryLongName", "girl"])
    assert o == {"starter": "squirtle", "name": "KYLE", "rival": "GARYLON", "girl": True}                      # names are upper-cased and cut to the game's 7 letters
    assert parse_options(["charmander", "boy"])["starter"] == "charmander" and not parse_options(["boy"])["girl"]
    assert parse_options(["nonsense", "name="])["name"] == "RED"                                              # unknown words and an empty name change nothing


def test_the_parcel_beat_is_the_new_game_driver_and_every_alias_resolves_to_it():
    b = sb.BY_KEY["parcel"]
    assert b.driver == "new_game" and not b.needs and b.done == (("milestone", "delivered_oaks_parcel"), ("flag", 0x829))
    for alias in ("new_game", "newgame", "start", "start_game", "intro", "oak", "parcel"):
        assert sb.resolve(alias) is b, alias
    assert set(STARTERS) == {"bulbasaur", "charmander", "squirtle"}


pytest.importorskip("openai")


def test_the_quest_tool_passes_the_words_after_the_name_to_the_driver():
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_flag=lambda f: False, read_key_items=lambda: [], read_badges=lambda: (0, 0), read_current_map=lambda: (0, 0),
                               read_party=lambda: [], detect_context=lambda: SimpleNamespace(name="UNKNOWN"))
    c.ltm = SimpleNamespace(data={"milestones": []})
    seen = []
    c._get_new_game = lambda auto: (seen.append(list(c._quest_opts)), "ran")[1]
    assert c._quest_tool("new_game squirtle name=KYLE girl") == "ran" and seen == [["squirtle", "name=KYLE", "girl"]]
    assert c._quest_tool("parcel") == "ran" and seen[-1] == []                                                # the plain beat name works too, with no options

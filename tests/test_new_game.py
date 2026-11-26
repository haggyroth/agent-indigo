"""quest('new_game') without an emulator (#260): option parsing, the beat wiring, and the dispatcher handing the words after the name to the driver."""
from types import SimpleNamespace

import pytest

from agent.skills.newgame import STARTERS, parse_options
from knowledge import story_beats as sb


@pytest.fixture(autouse=True)
def _blank_env(monkeypatch):
    """The user's .env may set STARTER / PLAYER_NAME / RIVAL_NAME: start every test from the built-in defaults."""
    import config
    for k in ("STARTER", "PLAYER_NAME", "RIVAL_NAME"):
        monkeypatch.setattr(config, k, "")


def test_env_values_are_the_defaults_and_the_call_overrides_them(monkeypatch):
    import config
    from agent.skills.newgame import env_configured
    assert not env_configured()
    monkeypatch.setattr(config, "STARTER", " Squirtle ")
    monkeypatch.setattr(config, "PLAYER_NAME", "kyleculp")
    monkeypatch.setattr(config, "RIVAL_NAME", "Gary")
    assert env_configured()
    assert parse_options([]) == {"starter": "squirtle", "name": "KYLECUL", "rival": "GARY", "girl": False}               # upper-cased, cut to 7 letters
    assert parse_options(["charmander", "name=ash"]) == {"starter": "charmander", "name": "ASH", "rival": "GARY", "girl": False}   # the call wins, the rest stays from .env
    monkeypatch.setattr(config, "STARTER", "pikachu")                                                                  # not a starter: ignored, not a crash
    assert parse_options([])["starter"] == "bulbasaur"


def test_the_new_game_hint_names_the_env_choices_only_when_set(monkeypatch):
    pytest.importorskip("openai")
    import config
    from agent.observation import _env_choice_note
    assert _env_choice_note() == ""
    monkeypatch.setattr(config, "STARTER", "squirtle")
    monkeypatch.setattr(config, "RIVAL_NAME", "gary")
    note = _env_choice_note()
    assert "squirtle" in note and "you are RED" in note and "rival GARY" in note and "plain quest('new_game')" in note


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


def test_the_model_chooses_unless_env_or_defaults_decide_for_it(monkeypatch):
    import config
    from agent.skills.newgame import given_choices, model_chooses, nickname_by_model
    assert model_chooses([]) and model_chooses(["squirtle", "name=ASH"])
    assert nickname_by_model(["squirtle"]) and not nickname_by_model(["squirtle", "nonick"])          # `nonick`: choose everything, decline the nickname box
    assert not model_chooses(["defaults"]) and not nickname_by_model(["defaults"])                    # scripted runs and tests
    monkeypatch.setattr(config, "RIVAL_NAME", "gary")                                                  # a human fixed one choice: the model is not asked
    assert not model_chooses([]) and not nickname_by_model([])
    assert given_choices(["squirtle", "name=ASH", "rival=", "girl"]) == {"starter", "name"}           # an empty value is not a choice


def test_the_choices_reply_asks_for_exactly_what_is_missing_and_gives_the_call():
    from agent.skills.newgame import choices_message
    full = choices_message(["starter", "name", "rival"])
    assert "yours to make" in full and "bulbasaur" in full and "YOUR name" in full and "RIVAL's name" in full
    assert "quest('new_game <starter> name=<YOU> rival=<RIVAL>')" in full and "name your starter" in full
    only = choices_message(["starter"])
    assert "STARTER" in only and "YOUR name" not in only and "RIVAL's name" not in only
    assert "RED" not in full and "BLUE" not in full                                                    # no default is suggested: the model picks

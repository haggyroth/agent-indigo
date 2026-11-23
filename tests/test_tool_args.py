"""Tolerant tool arguments (agent.tool_args): repair the model's habits, explain the rest with the tool's own signature."""
import pytest

pytest.importorskip("openai")

from agent.tool_args import repair_args, signature  # noqa: E402
from agent.tools import tool_schema  # noqa: E402


def test_the_watched_run_call_is_repaired_use_hm_with_hm_instead_of_move():
    args, problem = repair_args("use_hm", {"hm": "Dig"}, tool_schema("use_hm"))
    assert problem == "" and args == {"move": "Dig"}


def test_synonyms_and_a_single_stray_name_map_onto_the_one_missing_argument():
    assert repair_args("go_to", {"location": "Pewter City"}, tool_schema("go_to"))[0]["destination"] == "Pewter City"
    assert repair_args("use_item", {"item_name": "Potion"}, tool_schema("use_item"))[0]["item"] == "Potion"
    assert repair_args("record_milestone", {"milestone": "got_fly"}, tool_schema("record_milestone"))[0]["name"] == "got_fly"       # one stray, one missing


def test_strings_are_coerced_to_the_schema_types():
    args, problem = repair_args("walk_to", {"x": "12", "y": 5.0}, tool_schema("walk_to"))
    assert problem == "" and args == {"x": 12, "y": 5}


def test_a_bare_value_goes_to_the_only_required_parameter():
    assert repair_args("use_move", "Thunder", tool_schema("use_move"))[0] == {"move": "Thunder"}
    assert repair_args("walk_to", [1, 2], tool_schema("walk_to"))[1].startswith("walk_to takes named arguments")


def test_a_really_missing_argument_is_explained_with_the_signature():
    args, problem = repair_args("walk_to", {"x": 3}, tool_schema("walk_to"))
    assert "walk_to needs y" in problem and "walk_to(x: integer, y: integer)" in problem and "x=3" in problem


def test_a_correct_call_and_unknown_tools_are_untouched():
    good = {"destination": "Pewter City", "force": True}
    assert repair_args("go_to", dict(good), tool_schema("go_to")) == (good, "")
    assert repair_args("no_such_tool", {"a": 1}, None) == ({"a": 1}, "")
    assert "go_to(" in signature("go_to", tool_schema("go_to"))


def test_the_client_names_the_signature_when_an_argument_is_missing():
    from agent.lm_studio_client import AgentClient
    out = AgentClient._failure_text("use_hm", '{"hm": 5}', KeyError("move"))
    assert out.startswith("Tool use_hm failed:") and "use_hm(" in out
    assert AgentClient._failure_text("heal", "{}", ValueError("boom")) == "Tool heal failed: boom"

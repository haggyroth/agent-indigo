"""Context-gated tool lists (#213): a battle offers battle tools, the overworld doesn't offer battle ones, anything
uncertain offers everything; the schemas stay consistent with the dispatcher; the token budget doesn't creep back."""
import json
import re
from pathlib import Path

from agent.tool_docs import END, START, render_markdown
from agent.tools import BATTLE_TOOLS, SAFARI_CONTEXT, SAFARI_TOOLS, TOOLS, tools_for
from game.state import GameContext

ROOT = Path(__file__).resolve().parent.parent


def names(ctx):
    return {t["function"]["name"] for t in tools_for(ctx)}


def tokens(ctx):
    return len(json.dumps(tools_for(ctx))) // 4


def test_a_battle_offers_only_battle_tools():
    n = names(GameContext.IN_BATTLE)
    assert n == set(BATTLE_TOOLS)
    assert {"use_move", "switch_pokemon", "catch", "flee_battle", "use_item"} <= n
    assert not n & {"go_to", "walk_to", "heal", "grind", "pc", "teach_move", "quest", "shop"}


def test_the_overworld_drops_battle_only_and_naming_tools_but_keeps_the_rest():
    n = names(GameContext.OVERWORLD)
    assert not n & {"use_move", "switch_pokemon", "catch", "flee_battle", "enter_name"}
    assert {"go_to", "walk_to", "heal", "grind", "pc", "use_item", "teach_move", "inspect_pokemon", "press_button",
            "advance_dialog", "close_menus", "answer_prompt", "save_state", "load_state"} <= n


def test_every_uncertain_context_offers_everything():
    everything = {t["function"]["name"] for t in TOOLS}
    for ctx in (GameContext.IN_MENU, GameContext.DIALOG_OPEN, GameContext.TRANSITIONING, GameContext.UNKNOWN, None):
        assert names(ctx) == everything, ctx
    assert names("IN_BATTLE") == set(BATTLE_TOOLS)                  # names work as well as enum members


def test_the_battle_use_item_text_is_the_battle_version():
    battle = next(t for t in tools_for(GameContext.IN_BATTLE) if t["function"]["name"] == "use_item")
    field = next(t for t in tools_for(GameContext.OVERWORLD) if t["function"]["name"] == "use_item")
    assert "ACTIVE" in battle["function"]["description"] and "Rare Candy" not in battle["function"]["description"]
    assert "Rare Candy" in field["function"]["description"]
    assert battle["function"]["parameters"] == field["function"]["parameters"]


def test_every_tool_is_offered_somewhere_and_gated_names_exist():
    all_names = [t["function"]["name"] for t in TOOLS]
    assert len(all_names) == len(set(all_names))
    assert set(BATTLE_TOOLS) <= set(all_names)
    assert set(all_names) == set().union(names(GameContext.IN_BATTLE), names(GameContext.OVERWORLD), names(None))


def test_every_schema_has_a_dispatcher_case():
    src = (ROOT / "agent" / "lm_studio_client.py").read_text()
    cases = set(re.findall(r'case "([a-z_]+)"', src))
    missing = [t["function"]["name"] for t in TOOLS if t["function"]["name"] not in cases]
    assert not missing, f"tools with a schema but no dispatcher case: {missing}"


def test_token_budget_has_not_crept_back():
    assert tokens(GameContext.IN_BATTLE) < 1500            # was ~5.6k with every tool on every call
    assert tokens(GameContext.OVERWORLD) < 4300
    assert tokens(None) < 5100                              # the "everything" fallback grew with save_game, give_item, safari, game_corner
    for t in TOOLS:
        assert len(t["function"]["description"]) < 650, t["function"]["name"]      # long guidance belongs in the prompt


def test_the_tool_context_falls_back_to_everything_when_the_screen_cannot_be_read():
    import pytest
    pytest.importorskip("openai")
    from types import SimpleNamespace
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(detect_context=lambda: (_ for _ in ()).throw(RuntimeError("no emulator")))
    assert c._tool_context() is None and len(tools_for(c._tool_context())) == len(TOOLS)
    c.reader = SimpleNamespace(detect_context=lambda: GameContext.IN_BATTLE)
    assert c._tool_context() == GameContext.IN_BATTLE


def test_claude_md_tool_table_is_current():
    text = (ROOT / "CLAUDE.md").read_text()
    block = text[text.index(START):text.index(END) + len(END)]
    assert block == render_markdown(), "CLAUDE.md's tool table is stale — run: python tools/gen_tool_docs.py"


def test_a_safari_battle_offers_its_own_menu_and_nothing_that_needs_a_bag_or_party():
    n = names(SAFARI_CONTEXT)
    assert n == set(SAFARI_TOOLS) and "safari" in n
    assert not n & {"use_move", "switch_pokemon", "use_item", "catch", "flee_battle", "go_to"}
    assert "safari" not in names(GameContext.IN_BATTLE) and "safari" not in names(GameContext.OVERWORLD)
    assert "safari" in names(GameContext.IN_MENU)                # uncertain screens still get everything

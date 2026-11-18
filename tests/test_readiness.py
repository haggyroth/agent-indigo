"""Readiness gates for the non-gym story beats (#271): pure table + the quest() warn-once behaviour (no emulator)."""
from types import SimpleNamespace as NS

import pytest

from knowledge import story_beats as sb
from knowledge.beat_readiness import NEEDS, readiness


def team(*levels):
    return [NS(level=lv) for lv in levels]


def test_every_need_names_a_real_driven_beat_and_floors_are_below_tops():
    for key, n in NEEDS.items():
        assert key in sb.BY_KEY and sb.BY_KEY[key].driver, key
        assert n.floor < n.top and n.depth >= 2


def test_a_lone_ace_is_not_ready_for_victory_road_but_a_deep_team_is():
    out = readiness("victory_road", team(44, 20, 20, 18, 15))
    assert "Not ready" in out and "only 1 of your team is L34+" in out and "grind" in out
    assert readiness("victory_road", team(44, 40, 38, 36, 30)) == ""


def test_a_low_ace_is_reported_with_the_recommended_level():
    out = readiness("silph_co", team(30, 29, 29, 28))
    assert "best Pokémon is L30 (L38 recommended)" in out and "only" not in out


def test_beats_without_a_requirement_and_empty_parties_never_warn():
    assert readiness("tea", team(5)) == "" and readiness("victory_road", []) == ""


def test_the_plan_lists_the_recommendation():
    assert "Recommended: best Pokémon L42+" in sb.plan(sb.BY_KEY["victory_road"], {"victory_road": "next"})


# ── quest(): warn once, then go ahead ────────────────────────────────────────────────────────────────
pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402


def test_quest_warns_once_for_an_underlevelled_party_then_runs_the_driver():
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_party=lambda: team(25, 12, 12))
    c._story = lambda: {b.key: "next" for b in sb.BEATS}
    ran = []
    c._get_silph_scope = lambda auto: (ran.append(1), "driver ran")[1]
    first = c._quest_tool("rocket_hideout")
    assert first.startswith("Not ready for quest('rocket_hideout')") and not ran
    assert c._quest_tool("rocket_hideout") == "driver ran" and ran == [1]

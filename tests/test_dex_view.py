"""The Kanto Pokédex as a view: caught / seen / missing, grouped by reachability, each with its best source (#362). Information; the model decides what to chase."""
from types import SimpleNamespace

import pytest

from knowledge import dex_plan as dp


def test_reach_classifies_wild_evolution_trade_and_event():
    owned = {1, 2, 4, 63, 64}
    assert dp.reach(10, owned)[0] == dp.REACH_NOW and dp.reach(10, owned)[1].startswith("wild:")          # Caterpie
    assert dp.reach(3, owned)[0] == dp.REACH_NOW                                                         # Venusaur: Ivysaur is owned (level 32)
    assert dp.reach(6, owned)[0] == dp.REACH_AFTER and "catch it first" in dp.reach(6, owned)[1]          # Charizard: needs Charmeleon first
    how, text, _q = dp.reach(65, owned)                                                                  # Alakazam: a trade evolution, nothing else
    assert how == dp.REACH_TRADE and text == "evolve Kadabra by trade"
    assert dp.reach(151, owned) == (dp.REACH_EVENT, "event only (Mew)", "")
    assert dp.reach(133, owned)[0] == dp.REACH_NOW and "gift" in dp.reach(133, owned)[1]                 # Eevee: a curated one-off source counts as reachable here


def test_a_version_exclusive_needs_a_partner():
    exclusive = [s for s in range(1, 152) if dp.sources(s, set())[0][0] == 6]
    assert exclusive, "the data lists no version exclusives"
    assert all(dp.reach(s, set())[0] == dp.REACH_TRADE for s in exclusive)


def test_the_view_counts_every_missing_species_exactly_once():
    owned, seen = {1, 2, 4, 16, 17, 63, 64}, 40
    text = dp.dex_view(owned, seen, per_group=1000)
    assert text.startswith(f"POKÉDEX (Kanto): {len(owned)}/151 caught, 40 seen, {151 - len(owned)} missing")
    listed = [ln for ln in text.splitlines() if ln.startswith("  ") and " — " in ln]
    assert len(listed) == 151 - len(owned)
    groups = {ln.split(" (")[0]: int(ln.split("(")[1].rstrip("):")) for ln in text.splitlines() if ln.endswith("):") and not ln.startswith(" ")}
    assert sum(groups.values()) == 151 - len(owned) and set(groups) <= {"REACHABLE NOW", "AFTER ANOTHER CATCH", "NEEDS A TRADE PARTNER", "EVENT ONLY"}
    assert "event-only." in text and "Mew" in text and "Alakazam — evolve Kadabra by trade" in text


def test_long_groups_are_trimmed_and_the_quest_keys_are_shown():
    text = dp.dex_view(set(), 0, per_group=3)
    assert "… and " in text and "more" in text
    full = dp.dex_view(set(), 0, per_group=1000)
    assert "[quest('zapdos')]" in full or "[quest('hitmon')]" in full


def test_a_full_dex_says_so():
    assert dp.dex_view(set(range(1, 152)), 151) == "POKÉDEX: all 151 Kanto species caught."


pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402


def test_quest_dex_serves_the_view_and_survives_a_failing_read():
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_dex_owned_ids=lambda: {1, 4, 7}, read_pokedex=lambda: (3, 20))
    for word in ("dex", "Pokedex", "DEX"):
        out = c._quest_tool(word)
        assert out.startswith("POKÉDEX (Kanto): 3/151 caught, 20 seen")
    c.reader = SimpleNamespace(read_dex_owned_ids=lambda: 1 / 0, read_pokedex=lambda: (0, 0))
    assert "could not be read" in c._quest_tool("dex")

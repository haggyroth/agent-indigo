"""The in-game NPC trades (#362): the table agrees with the dex plan's, names resolve, and the listing / refusals read right (a fake game)."""
from types import SimpleNamespace

import pytest

from game.constants import SPECIES_NAMES
from game.state import GameContext
from knowledge.dex_sources import TRADES
from knowledge.trades import NPC_TRADES, find

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402


def test_the_table_matches_the_dex_plans_wanted_species_and_places():
    assert set(TRADES) <= set(NPC_TRADES) and set(NPC_TRADES) - set(TRADES) == {32, 33}        # + LeafGreen's two Nidoran trades
    for got, (want, mp, npc, flag, where) in NPC_TRADES.items():
        if got in TRADES:
            assert TRADES[got] == (want, where), got
        assert len(mp) == 2 and len(npc) == 2 and 0x240 <= flag <= 0x280


def test_the_leafgreen_nidoran_trades_are_the_decomps():
    """ingame_trades.h LEAFGREEN: NINO is a Nidorino asked of a Nidorina (Route 11 gate, flag 0x251), MR. NIDO a Nidoran M asked of a Nidoran F (Underground Path, 0x24B)."""
    assert NPC_TRADES[33][:1] == (30,) and NPC_TRADES[33][3] == 0x251 and NPC_TRADES[32][:1] == (29,) and NPC_TRADES[32][3] == 0x24B
    assert find("nidorino", SPECIES_NAMES) == 33 and find("nidoran m", SPECIES_NAMES) == 32 and find("nidoran", SPECIES_NAMES) == 32      # (only the male is offered, so "nidoran" is unambiguous)


def test_names_resolve_loosely_and_ambiguity_is_refused():
    assert find("Farfetch'd", SPECIES_NAMES) == 83 and find("farfetchd", SPECIES_NAMES) == 83 and find("mr mime", SPECIES_NAMES) == 122
    assert find("jyn", SPECIES_NAMES) == 124 and find("", SPECIES_NAMES) is None and find("pikachu", SPECIES_NAMES) is None


def _client(party=(), flags=(), ctx=GameContext.OVERWORLD):
    c = AgentClient.__new__(AgentClient)
    mons = [SimpleNamespace(species_id=s, is_egg=False) for s in party]
    c.reader = SimpleNamespace(read_flag=lambda f: f in flags, read_party=lambda: mons, detect_context=lambda: ctx)
    return c


def test_the_listing_marks_done_trades_and_a_missing_species_is_said_plainly():
    out = _client(flags={0x24D})._trade_npc("")
    assert "FARFETCH'D for a SPEAROW" in out and "Vermilion City, house 2 (done)" in out and "MR. MIME for a ABRA" in out
    out = _client(party=[1, 4])._trade_npc("farfetchd")
    assert "your party has none" in out and "Spearow" in out
    assert "already made the trade" in _client(flags={0x24D}, party=[21])._trade_npc("farfetchd")
    assert "No in-game trade gives" in _client()._trade_npc("pikachu")
    assert "open field" in _client(party=[21], ctx=GameContext.IN_MENU)._trade_npc("farfetchd")

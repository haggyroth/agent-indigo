"""quest('fossil') (#362): which fossil it picks and what it says without one (a fake game)."""
from types import SimpleNamespace

import pytest

from game.state import GameContext

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402


def _client(flags=(), state=0, ctx=GameContext.OVERWORLD):
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_flag=lambda f: f in flags, read_var=lambda n: state, detect_context=lambda: ctx)
    return c


def test_it_picks_the_first_owned_unrevived_fossil_or_the_named_one():
    c = _client(flags={0x273, 0x25E})                                  # Helix and Old Amber owned
    assert c._fossil_pick("") == "helix" and c._fossil_pick("amber") == "amber" and c._fossil_pick("aerodactyl") == "amber"
    assert _client(flags={0x273, 0x2ED, 0x25E})._fossil_pick("") == "amber"          # the Helix is already revived
    assert _client()._fossil_pick("") is None and _client()._fossil_pick("pikachu") is None


def test_the_refusals_read_right():
    assert "No fossil to revive" in _client()._fossil("")
    assert "No fossil called" in _client()._fossil("pikachu")
    assert "already revived" in _client(flags={0x25E, 0x2EE})._fossil("amber")
    assert "do not have" in _client()._fossil("helix")
    assert "open field" in _client(flags={0x25E}, ctx=GameContext.IN_MENU)._fossil("amber")

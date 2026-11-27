"""quest('moltres') / quest('mewtwo') gates and the Surf re-entrancy guard (#361), against a fake game."""
from types import SimpleNamespace

import pytest

from game.state import GameContext

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402


def _client(flags=(), owned=(), ctx=GameContext.OVERWORLD, map_=(3, 5)):
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_flag=lambda f: f in flags, read_dex_owned=lambda s: s in owned, detect_context=lambda: ctx, read_current_map=lambda: map_)
    return c


def test_moltres_waits_for_the_islands_and_is_one_shot():
    assert "quest('sevii_one_island') first" in _client()._get_moltres()
    assert "already caught Moltres" in _client(owned={146})._get_moltres()
    assert "Moltres is gone" in _client(flags={0x2BD, 0x89B})._get_moltres()                  # fought: a legendary appears once


def test_mewtwo_waits_for_the_network_machine_and_is_one_shot():
    assert "link the Network Machine first" in _client()._get_mewtwo()
    assert "already caught Mewtwo" in _client(owned={150})._get_mewtwo()
    assert "Mewtwo is gone" in _client(flags={0x2BC, 0x844})._get_mewtwo()
    assert "in a battle" in _client(ctx=GameContext.IN_BATTLE)._get_mewtwo()


def test_a_surf_attempt_never_starts_another_inside_itself():
    """A shore walk with no path used to start Surf again, which walked to a shore again … until the stack ended (found on Kindle Road)."""
    c = _client()
    c._party_knows = lambda mv: True
    c._use_hm_blocked = lambda *a: ""
    calls = []

    def surf():
        calls.append(1)
        return c._use_hm("surf") if len(calls) < 5 else "deep"                               # what a walk from inside _surf did
    c._surf = surf
    c._flag_gate = lambda *a, **k: ""
    out = c._use_hm("surf")
    assert len(calls) == 1 and "Already looking for a shore" in out

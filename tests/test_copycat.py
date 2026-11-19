"""quest('copycat') refusals (#278, no emulator): the lesson is one-time, needs Tea, and the Rocket at her door must be gone — all answered before any travel."""
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402
from knowledge import story_beats as sb   # noqa: E402


def client(flags=(), items=()):
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_flag=lambda f: f in flags, detect_context=lambda: NS(name="OVERWORLD"), count_item=lambda i: 1 if i in items else 0,
                  read_key_items=lambda: [], read_money=lambda: 5000)
    c._has_tea = lambda: 0x2A6 in flags
    c._shop_for = lambda *a, **k: pytest.fail("should have refused before shopping")
    c._tutor = lambda *a, **k: pytest.fail("should have refused before the lesson")
    return c


def test_it_is_one_time_needs_tea_and_needs_the_saffron_rockets_gone():
    assert "already taught Mimic" in client(flags={0x2CD})._get_copycat()
    assert "Tea" in client()._get_copycat()
    assert "Silph Co." in client(flags={0x2A6})._get_copycat()


def test_the_beat_needs_silph_co_and_is_done_by_the_tutor_flag():
    b = sb.BY_KEY["copycat"]
    assert b.needs == ("silph_co",) and b.driver == "copycat" and b.optional and b.done == (("flag", 0x2CD),)

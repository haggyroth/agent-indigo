"""Reasoning never reaches history, whatever ENABLE_THINKING says (#374)."""
import types

import pytest

from agent.history import split_think

CASES = [
    ("<think>plan</think>\nGo north", "plan", "Go north"),
    ("no thinking here", "", "no thinking here"),
    ("<think>a</think>x<think>b</think>y", "a\nb", "xy"),
    ("<THINK>caps</THINK>ok", "caps", "ok"),
    ("<think>plan that got cut off by MAX_TOKENS", "plan that got cut off by MAX_TOKENS", ""),
    ("answer first <think>and then it started thinking and was cut", "and then it started thinking and was cut", "answer first"),
    ("implicit opening tag reasoning</think>the answer", "implicit opening tag reasoning", "the answer"),
    ("", "", ""),
]


@pytest.mark.parametrize("raw,thinking,answer", CASES)
def test_split_think(raw, thinking, answer):
    assert split_think(raw) == (thinking, answer)
    assert "<think" not in split_think(raw)[1].lower()


pytest.importorskip("openai")
import agent.lm_studio_client as lsc  # noqa: E402
from agent.lm_studio_client import AgentClient  # noqa: E402


def _msg(content, **extra):
    return types.SimpleNamespace(content=content, model_extra=extra, tool_calls=None)


@pytest.mark.parametrize("flag", [False, True])
@pytest.mark.parametrize("raw,thinking,answer", CASES)
def test_the_stored_content_never_contains_reasoning(monkeypatch, flag, raw, thinking, answer):
    monkeypatch.setattr(lsc, "ENABLE_THINKING", flag)
    shown, stored = AgentClient.__new__(AgentClient)._extract_response(_msg(raw))
    assert stored == answer and "<think" not in stored.lower()
    assert shown == (thinking if flag else "")                      # the flag decides display only


@pytest.mark.parametrize("field", ["reasoning_content", "reasoning"])
def test_separate_reasoning_fields_are_shown_but_not_stored(monkeypatch, field):
    monkeypatch.setattr(lsc, "ENABLE_THINKING", True)
    shown, stored = AgentClient.__new__(AgentClient)._extract_response(_msg("Go north", **{field: " deep thought "}))
    assert (shown, stored) == ("deep thought", "Go north")
    monkeypatch.setattr(lsc, "ENABLE_THINKING", False)
    assert AgentClient.__new__(AgentClient)._extract_response(_msg("Go north", **{field: "x"})) == ("", "Go north")


def test_a_reply_cut_off_inside_its_reasoning_leaves_a_well_formed_turn(monkeypatch):
    class Endpoint:
        chat = None

        def __init__(self):
            self.chat = types.SimpleNamespace(completions=self)

        def create(self, **kw):
            msg = types.SimpleNamespace(content="<think>and then I wondered about" , tool_calls=None, model_extra={})
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg, finish_reason="length")],
                                         usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=4096))
    c = AgentClient.__new__(AgentClient)
    c.llm, c.llm_calls = Endpoint(), 0
    c.total_prompt_tokens = c.total_completion_tokens = c.total_cached_tokens = 0
    c.messages = [{"role": "system", "content": "s"}]
    c.step("obs")
    last = c.messages[-1]
    assert last["role"] == "assistant" and "<think" not in last["content"] and "cut off" in last["content"]

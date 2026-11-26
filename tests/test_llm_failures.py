"""LLM failures are told apart (#372): fatal ones stop the run, a context overflow shrinks and resends, history is fitted to a token budget."""
import types

import pytest

from agent import history
from agent.llm_retry import call_with_retry, fatal_reason, is_context_overflow, is_transient, retry_after


class Err(Exception):
    def __init__(self, msg="", status=None, code=None, body=None, headers=None):
        super().__init__(msg)
        self.status_code, self.code, self.body = status, code, body
        if headers is not None:
            self.response = types.SimpleNamespace(headers=headers)


class RateLimitError(Err):                      # same class name as the SDK's: matching is by name
    pass


# ── classification (pure) ────────────────────────────────────────────────────────────────────────

def test_quota_429_is_fatal_not_transient_but_an_ordinary_429_still_backs_off():
    quota = RateLimitError("You exceeded your current quota", 429, code="insufficient_quota")
    assert fatal_reason(quota) and not is_transient(quota)
    plain = RateLimitError("slow down", 429)
    assert fatal_reason(plain) is None and is_transient(plain)


def test_credentials_missing_model_and_payment_are_fatal():
    for status in (401, 403, 404, 402):
        assert fatal_reason(Err("x", status)), status
    assert fatal_reason(Err("boom", 500)) is None and fatal_reason(ValueError("x")) is None


def test_context_overflow_detection():
    assert is_context_overflow(Err("Context size has been exceeded.", 400))
    assert is_context_overflow(Err("This model's maximum context length is 8192 tokens", 400, code="context_length_exceeded"))
    assert is_context_overflow(Err("Trying to keep the first 4121 tokens when context overflows. However, the model is loaded with context length of only 4096 tokens", 400))
    assert not is_context_overflow(Err("invalid tool schema", 400))
    assert not is_context_overflow(Err("context size", 500))                  # only a 400 is a request-size problem


def test_retry_after_header_stretches_the_wait():
    waits = []
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RateLimitError("slow", 429, headers={"retry-after": "30"})
        return "ok"
    assert call_with_retry(flaky, tries=3, sleep=waits.append) == "ok"
    assert waits == [30.0]                                                    # the server's ask beats the 2 s default
    assert retry_after(Err("x")) == 0


def test_a_fatal_error_is_not_retried():
    waits, calls = [], []

    def quota():
        calls.append(1)
        raise RateLimitError("x", 429, code="insufficient_quota")
    with pytest.raises(RateLimitError):
        call_with_retry(quota, tries=8, sleep=waits.append)
    assert len(calls) == 1 and waits == []


# ── history budget (pure) ────────────────────────────────────────────────────────────────────────

def _turns(n, size=700):
    ms = [{"role": "system", "content": "sys"}]
    for i in range(n):
        ms.append({"role": "user", "content": f"obs{i} " + "x" * size})
        ms.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": "go_to", "arguments": "{}"}}]})
        ms.append({"role": "tool", "tool_call_id": f"c{i}", "content": "ok " + "y" * size})
    return ms


def _valid(ms):
    """Every assistant tool_calls message is followed by its tool responses (the API's rule)."""
    for i, m in enumerate(ms):
        if m.get("tool_calls"):
            ids = {t["id"] for t in m["tool_calls"]}
            got = {x.get("tool_call_id") for x in ms[i + 1:i + 1 + len(ids)] if x["role"] == "tool"}
            if ids != got:
                return False
        if m["role"] == "tool" and not (ms[i - 1].get("tool_calls") or ms[i - 1]["role"] == "tool"):
            return False
    return True


def test_estimate_counts_text_and_flat_image_cost():
    assert history.estimate_tokens("a" * 350) == 101
    img = {"role": "user", "content": [{"type": "text", "text": "hi"}, {"type": "image_url", "image_url": {"url": "data:..."}}]}
    assert history.estimate_tokens(img) >= history.IMAGE_TOKENS


def test_fit_drops_oldest_whole_turns_and_never_splits_a_group():
    ms = _turns(10)
    fit, did = history.fit_to_budget(ms, budget=1500)
    assert did and fit[0]["role"] == "system" and _valid(fit)
    assert fit[-1] == ms[-1] and history.estimate_tokens(fit) <= 1500           # the newest turn survives
    assert len(fit) < len(ms)


def test_fit_is_a_no_op_when_it_already_fits_or_no_budget():
    ms = _turns(3)
    assert history.fit_to_budget(ms, budget=10 ** 6) == (ms, [])
    assert history.fit_to_budget(ms, budget=0) == (ms, [])


def test_fit_strips_images_when_one_turn_is_still_too_big():
    ms = [{"role": "system", "content": "s"},
          {"role": "user", "content": [{"type": "text", "text": "obs"}, {"type": "image_url", "image_url": {"url": "u"}}]}]
    fit, did = history.fit_to_budget(ms, budget=500)
    assert "dropped images" in did and fit[1]["content"] == "obs"


def test_scale_makes_the_estimate_more_pessimistic():
    ms = _turns(6)
    plain, _ = history.fit_to_budget(ms, budget=2500, scale=1.0)
    scaled, _ = history.fit_to_budget(ms, budget=2500, scale=2.0)
    assert len(scaled) < len(plain)


def test_last_user_group_is_api_valid():
    g = history.last_user_group(_turns(4))
    assert g[0]["role"] == "system" and g[1]["role"] == "user" and _valid(g) and len(g) == 4


# ── the client (fake endpoint) ───────────────────────────────────────────────────────────────────

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402
from agent.llm_retry import LLMFatalError  # noqa: E402
import agent.lm_studio_client as lsc  # noqa: E402


def _tc(i, name, args="{}"):
    fn = types.SimpleNamespace(name=name, arguments=args)
    return types.SimpleNamespace(id=i, function=fn, model_dump=lambda: {"id": i, "type": "function", "function": {"name": name, "arguments": args}})


class Endpoint:
    """Scripted chat endpoint: each entry is an exception to raise, a list of tool calls, or None (a plain answer). Records what it was sent."""
    def __init__(self, script, limit_tokens=0):
        self.script, self.sent, self.limit = list(script), [], limit_tokens
        self.chat = types.SimpleNamespace(completions=self)

    def create(self, **kw):
        self.sent.append(list(kw["messages"]))
        if self.limit and history.estimate_tokens(kw["messages"]) > self.limit:
            raise Err("Context size has been exceeded.", 400)
        step = self.script.pop(0) if self.script else None
        if isinstance(step, Exception):
            raise step
        msg = types.SimpleNamespace(content="", tool_calls=step, model_extra={})
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], usage=types.SimpleNamespace(prompt_tokens=100, completion_tokens=5))


def _client(endpoint, history_msgs=None):
    c = AgentClient.__new__(AgentClient)
    c.llm, c.llm_calls = endpoint, 0
    c.total_prompt_tokens = c.total_completion_tokens = c.total_cached_tokens = 0
    c.messages = history_msgs if history_msgs is not None else [{"role": "system", "content": "sys"}]
    c._current_opponent = ""
    c.mgba = types.SimpleNamespace(tick=lambda *a: None)
    return c


def test_a_context_overflow_shrinks_and_resends_instead_of_repeating():
    big = _turns(8, size=1500)
    before = history.estimate_tokens(big)
    ep = Endpoint([None], limit_tokens=before // 3)         # the loaded window is a third of what we would send
    c = _client(ep, big)
    c.step("now " + "z" * 300)
    assert len(ep.sent) >= 2 and ep.script == []             # failed, shrank, resent, answered
    assert history.estimate_tokens(ep.sent[-1]) <= before // 3 or len(ep.sent) <= 4
    assert c._learned_budget > 0                              # …and it learned a ceiling for the next request
    assert _valid(c.messages)


def test_the_learned_ceiling_fits_the_next_request_without_another_failure():
    big = _turns(8, size=1500)
    ep = Endpoint([None, None], limit_tokens=history.estimate_tokens(big) // 3)
    c = _client(ep, big)
    c.step("one")
    failures_after_first = len(ep.sent)
    c.step("two")
    assert len(ep.sent) == failures_after_first + 1          # the second step needed exactly one request


def test_an_overflow_that_nothing_can_fix_is_raised_after_the_ladder(monkeypatch):
    ep = Endpoint([Err("Context size has been exceeded.", 400)] * 6)
    c = _client(ep)
    with pytest.raises(Err):
        c.step("obs " + "w" * 6000)
    assert 2 <= len(ep.sent) <= 4                             # bounded: it tries what can be cut, then gives up — never an endless repeat
    assert ep.sent[-1][-1]["content"].endswith("fit the context window]")      # the last resort was tried (observation cut)
    assert c.messages == [{"role": "system", "content": "sys"}]


def test_a_quota_error_stops_at_once_and_leaves_history_clean():
    ep = Endpoint([RateLimitError("You exceeded your current quota", 429, code="insufficient_quota")])
    c = _client(ep)
    with pytest.raises(LLMFatalError) as e:
        c.step("obs")
    assert "quota" in e.value.reason and len(ep.sent) == 1
    assert c.messages == [{"role": "system", "content": "sys"}]


def test_a_failure_after_the_first_round_keeps_what_the_tools_already_did(monkeypatch):
    ep = Endpoint([[_tc("c1", "wait_frames", '{"frames": 5}')], Err("boom", 400)])
    c = _client(ep)
    monkeypatch.setattr(c, "_execute", lambda *a, **k: "Waited 5 frames.")
    monkeypatch.setattr(lsc.events, "observe", lambda *a, **k: None)
    monkeypatch.setattr(c, "_log_tool", lambda *a, **k: None)
    reasoning, actions = c.step("obs")                       # returns instead of raising: the game already moved
    assert actions == ["wait_frames"]
    roles = [m["role"] for m in c.messages]
    assert roles == ["system", "user", "assistant", "tool"] and _valid(c.messages)


def test_a_first_round_failure_still_rolls_the_user_turn_back():
    c = _client(Endpoint([Err("boom", 400)]))
    with pytest.raises(Err):
        c.step("obs")
    assert c.messages == [{"role": "system", "content": "sys"}]


def test_rollback_is_exact_even_when_older_turns_were_dropped_to_fit(monkeypatch):
    monkeypatch.setattr(lsc, "prompt_token_budget", lambda: 1200)
    ep = Endpoint([Err("boom", 400)])
    c = _client(ep, _turns(10))
    with pytest.raises(Err):
        c.step("obs")
    assert _valid(c.messages) and c.messages[0]["role"] == "system"      # older turns the budget dropped stay dropped; the failed turn is gone
    assert not any(m["role"] == "user" and m["content"] == "obs" for m in c.messages)
    assert len(c.messages) < len(_turns(10))


def test_the_estimator_calibrates_against_the_servers_count():
    ep = Endpoint([None])
    c = _client(ep)
    c.step("obs")                                            # the fake server reports 100 prompt tokens; the estimate (tool schemas included) is far higher
    assert c._tok_ratio < 1.0


def test_context_tokens_must_exceed_max_tokens(monkeypatch):
    import importlib
    import config
    monkeypatch.setenv("MAX_TOKENS", "4096")
    monkeypatch.setenv("CONTEXT_TOKENS", "4000")
    with pytest.raises(SystemExit):
        importlib.reload(config)
    monkeypatch.delenv("CONTEXT_TOKENS")
    monkeypatch.delenv("MAX_TOKENS")
    importlib.reload(config)
    assert config.prompt_token_budget() == 0


# ── run_episode ends with a named reason ─────────────────────────────────────────────────────────

def test_run_episode_stops_with_llm_error_instead_of_spending_the_error_budget(monkeypatch, tmp_path):
    import main
    from game.state import GameContext, GameState
    from memory.short_term import ShortTermMemory
    state = GameState(context=GameContext.OVERWORLD, badges=0, badge_bits=0, party=[], party_count=0, map_bank=3, map_id=0,
                      player_x=1, player_y=1, screen_fading=False)
    saved = []
    ltm = types.SimpleNamespace(data={"badges_earned": 0, "milestones": []}, save=lambda: saved.append(1), add_town=lambda n: False)

    def refuse(*a, **k):
        raise LLMFatalError("the account's quota / billing is exhausted — retrying cannot help")
    client = types.SimpleNamespace(
        _in_evolution_scene=lambda: False, llm_calls=3, total_tokens=10, total_prompt_tokens=8, total_completion_tokens=2,
        total_cached_tokens=0, run_log=None, _current_opponent="", step=refuse, set_system=lambda p: None,
        capture_screenshot=lambda: None, _maintain_exp_share=lambda: None)
    reader = types.SimpleNamespace(read_state=lambda: state, diff=lambda a, b: None, read_enemy_lead=lambda: None)
    rt = main.AgentRuntime(mgba=types.SimpleNamespace(tick=lambda *a: None, read32=lambda a: 0), reader=reader, client=client, ltm=ltm,
                           stm=ShortTermMemory(), journal=types.SimpleNamespace(), tilemap=types.SimpleNamespace(refresh=lambda: None))
    monkeypatch.setattr(main, "ERRORS_LOG", tmp_path / "errors.log")
    monkeypatch.setattr(main, "apply_battle_style", lambda *a: False)
    monkeypatch.setattr(main.events, "observe", lambda *a, **k: None)
    monkeypatch.setattr(main, "_apply_progress", lambda *a, **k: None)
    monkeypatch.setattr(main, "build_observation", lambda **k: "obs")
    monkeypatch.setattr(main, "build_system_prompt", lambda *a, **k: "sys")
    monkeypatch.setattr(main, "_handle_blackout", lambda *a, **k: False)
    monkeypatch.setattr(main, "USE_VISION", False)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)       # (a regression would burn the 30-error budget; don't make it slow too)
    res = main.run_episode(rt, verbose=False, max_wall_s=0)
    assert res.reason == "llm_error" and not res.passed and res.steps == 0
    assert saved                                                    # progress was written before stopping

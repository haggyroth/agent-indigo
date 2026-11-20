"""Cached prompt tokens (no emulator): read from whichever shape the endpoint reports, summed per run, logged per call and shown in the end-of-run tally."""
from types import SimpleNamespace as NS

from agent.usage import cached_prompt_tokens


def test_the_openai_and_ollama_shape_and_the_flat_variants_are_read():
    assert cached_prompt_tokens(NS(prompt_tokens=445, prompt_tokens_details=NS(cached_tokens=440))) == 440
    assert cached_prompt_tokens(NS(prompt_tokens=445, prompt_tokens_details={"cached_tokens": 12})) == 12                 # a dict, as some SDK versions return
    assert cached_prompt_tokens(NS(prompt_tokens=445, prompt_tokens_details=NS(cached_tokens=0))) == 0                    # "none cached" is a report, not a missing field
    assert cached_prompt_tokens(NS(prompt_cache_hit_tokens=300)) == 300                                                   # DeepSeek
    assert cached_prompt_tokens(NS(cache_read_input_tokens=7)) == 7                                                       # Anthropic-style


def test_an_endpoint_that_reports_nothing_gives_none():
    assert cached_prompt_tokens(None) is None
    assert cached_prompt_tokens(NS(prompt_tokens=10, completion_tokens=5)) is None
    assert cached_prompt_tokens(NS(prompt_tokens_details=None)) is None
    assert cached_prompt_tokens(NS(prompt_tokens_details=NS(cached_tokens=None))) is None
    assert cached_prompt_tokens(NS(prompt_tokens_details=NS(cached_tokens=True))) is None                                  # a bool is not a count


def test_the_client_sums_cached_tokens_and_logs_them_per_call():
    import pytest
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    events = []
    usages = [NS(prompt_tokens=100, completion_tokens=5, prompt_tokens_details=NS(cached_tokens=0)),
              NS(prompt_tokens=100, completion_tokens=5, prompt_tokens_details=NS(cached_tokens=90)),
              NS(prompt_tokens=100, completion_tokens=5)]                                                                 # no cache info: counted as 0, logged as None

    class Completions:
        def create(self, **kw):
            msg = NS(content="ok", tool_calls=None, model_extra={})
            return NS(choices=[NS(message=msg)], usage=usages.pop(0))

    c = AgentClient.__new__(AgentClient)
    c.llm = NS(chat=NS(completions=Completions()))
    c.messages = [{"role": "system", "content": "sys"}]
    c._current_opponent = ""
    c.llm_calls = c.total_prompt_tokens = c.total_completion_tokens = c.total_cached_tokens = 0
    c.run_log = NS(event=lambda kind, **f: events.append((kind, f)), dir=None, t0=0)
    for _ in range(3):
        c.step("obs")
    llm = [f for k, f in events if k == "llm"]
    assert [f["cached_tokens"] for f in llm] == [0, 90, None]
    assert c.total_cached_tokens == 90 and c.total_prompt_tokens == 300


def test_the_episode_result_and_the_tally_show_the_cached_share():
    import pytest
    pytest.importorskip("openai")                                 # main imports the client
    from main import EpisodeResult
    r = EpisodeResult(reason="goal", passed=True, steps=1, llm_calls=2, prompt_tokens=1000, completion_tokens=10, final_map=(3, 0), final_pos=(1, 1), badges=0, cached_tokens=900)
    assert "cached 90% of prompt" in r.summary() and r.to_dict()["cached_tokens"] == 900
    none = EpisodeResult(reason="goal", passed=True, steps=1, llm_calls=2, prompt_tokens=1000, completion_tokens=10, final_map=(3, 0), final_pos=(1, 1), badges=0)
    assert "cached" not in none.summary() and none.cached_tokens == 0

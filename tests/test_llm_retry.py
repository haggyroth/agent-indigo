"""Transient LLM failures are waited out with a backoff (agent.llm_retry)."""
from agent.llm_retry import call_with_retry, delays, is_transient


class APIConnectionError(Exception):          # same class name as the SDK's: matching is by name, so no SDK is needed
    pass


class RateLimitError(Exception):
    status_code = 429


class BadRequest(Exception):
    status_code = 400


def test_which_errors_are_transient():
    assert is_transient(APIConnectionError()) and is_transient(RateLimitError())
    assert not is_transient(BadRequest()) and not is_transient(ValueError("x"))
    e = Exception("boom")
    e.status_code = 503
    assert is_transient(e)


def test_the_backoff_doubles_and_is_capped():
    assert list(delays(8)) == [2, 4, 8, 16, 32, 60, 60, 60] and list(delays(0)) == []


def test_a_flaky_call_succeeds_after_waiting_and_a_real_error_fails_at_once():
    calls, waits = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise APIConnectionError("reset")
        return "ok"
    told = []
    assert call_with_retry(flaky, tries=5, sleep=waits.append, on_retry=lambda e, n, w: told.append((n, w))) == "ok"
    assert waits == [2, 4] and told == [(1, 2), (2, 4)]

    def bad():
        raise BadRequest("400")
    waits.clear()
    try:
        call_with_retry(bad, tries=5, sleep=waits.append)
        raise AssertionError("should have raised")
    except BadRequest:
        pass
    assert waits == []                                                    # no waiting for a 400


def test_the_last_transient_error_is_raised_when_the_retries_run_out():
    waits = []
    try:
        call_with_retry(lambda: (_ for _ in ()).throw(APIConnectionError("down")), tries=3, sleep=waits.append)
        raise AssertionError("should have raised")
    except APIConnectionError:
        pass
    assert waits == [2, 4, 8]

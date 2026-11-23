"""Retry a chat-completion call through transient failures (pure + an injectable sleep).

A cloud model (gemma4:31b-cloud) drops the connection now and then: logs/errors.log holds a dozen APIConnectionError tracebacks. Each used to cost the run one of its 30 consecutive-error
retries at one second apiece, so ~30 s of network trouble ended an hours-long run (`error_budget`). Connection resets, timeouts, rate limits and 5xx answers are waited out with an exponential
backoff instead (2, 4, 8 … capped at 60 s); anything else — a 400, a bad key — still fails at once."""
import time

_TRANSIENT = ("APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError")


def is_transient(exc: BaseException) -> bool:
    """A connection / timeout / rate-limit / server-side failure worth waiting out (matched by class name across the MRO: no hard dependency on the SDK)."""
    if any(c.__name__ in _TRANSIENT for c in type(exc).__mro__):
        return True
    code = getattr(exc, "status_code", None)
    return isinstance(code, int) and (code in (408, 409, 429) or code >= 500)


def delays(tries: int, base: float = 2.0, cap: float = 60.0):
    """The waits between attempts: base, 2·base, 4·base … capped."""
    for n in range(max(0, tries)):
        yield min(cap, base * (2 ** n))


def call_with_retry(fn, tries: int = 8, sleep=time.sleep, on_retry=None):
    """fn() with up to `tries` retries on transient errors (so tries + 1 attempts); the last error is re-raised. `on_retry(exc, attempt, wait)` is told about each wait."""
    waits = list(delays(tries))
    for attempt in range(len(waits) + 1):
        try:
            return fn()
        except Exception as e:
            if not is_transient(e) or attempt >= len(waits):
                raise
            if on_retry:
                on_retry(e, attempt + 1, waits[attempt])
            sleep(waits[attempt])

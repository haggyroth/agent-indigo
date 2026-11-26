"""Retry a chat-completion call through transient failures (pure + an injectable sleep).

A cloud model (gemma4:31b-cloud) drops the connection now and then: logs/errors.log holds a dozen APIConnectionError tracebacks. Each used to cost the run one of its 30 consecutive-error
retries at one second apiece, so ~30 s of network trouble ended an hours-long run (`error_budget`). Connection resets, timeouts, rate limits and 5xx answers are waited out with an exponential
backoff instead (2, 4, 8 … capped at 60 s); anything else — a 400, a bad key — still fails at once."""
import time

_TRANSIENT = ("APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError")


class LLMFatalError(Exception):
    """The endpoint refused in a way no retry or shrinking can fix (bad key, no access, unknown model, quota or billing exhausted).
    The run stops at once with a named reason instead of burning its error budget (or hours of backoff) on it."""

    def __init__(self, reason: str, cause: BaseException | None = None):
        super().__init__(reason)
        self.reason, self.cause = reason, cause


_QUOTA_WORDS = ("insufficient_quota", "exceeded your current quota", "billing", "out of credits", "insufficient credits", "payment required")
_CONTEXT_WORDS = ("context length", "context_length", "context size", "context window", "context overflow", "maximum context", "n_ctx",
                  "too many tokens", "prompt is too long", "input is too long", "exceeds the context", "reduce the length", "tokens to keep")


def _text(exc: BaseException) -> str:
    """The error's message plus any structured error code/body the SDK attached, lower-cased."""
    parts = [str(exc), str(getattr(exc, "code", "") or ""), str(getattr(exc, "body", "") or "")]
    return " ".join(parts).lower()


def is_context_overflow(exc: BaseException) -> bool:
    """The request was too big for the model's loaded context window (an HTTP 400 on LM Studio / OpenAI-compatible servers)."""
    code = getattr(exc, "status_code", None)
    if code is not None and code != 400:
        return False
    t = _text(exc)
    return any(w in t for w in _CONTEXT_WORDS)


def fatal_reason(exc: BaseException) -> str | None:
    """Why this error can never succeed on retry, or None. 401/403 (credentials), 402 and quota/billing 429s, and 404 (unknown model / wrong URL)."""
    code = getattr(exc, "status_code", None)
    t = _text(exc)
    if code in (401, 403):
        return f"the endpoint refused the credentials (HTTP {code}) — check LLM_API_KEY"
    if code == 402 or (code == 429 and any(w in t for w in _QUOTA_WORDS)) or (code is None and "insufficient_quota" in t):
        return "the account's quota / billing is exhausted — retrying cannot help"
    if code == 404:
        return "the endpoint says the model or URL does not exist (HTTP 404) — check MODEL_NAME and LLM_BASE_URL"
    return None


def retry_after(exc: BaseException) -> float:
    """Seconds the server asked us to wait (Retry-After header), or 0."""
    try:
        v = exc.response.headers.get("retry-after")          # type: ignore[attr-defined]
        return max(0.0, min(float(v), 300.0)) if v is not None else 0.0
    except Exception:
        return 0.0


def is_transient(exc: BaseException) -> bool:
    """A connection / timeout / rate-limit / server-side failure worth waiting out (matched by class name across the MRO: no hard dependency on the SDK).
    A quota / billing 429 is NOT transient (see fatal_reason)."""
    if fatal_reason(exc):
        return False
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
            wait = max(waits[attempt], retry_after(e))
            if on_retry:
                on_retry(e, attempt + 1, wait)
            sleep(wait)

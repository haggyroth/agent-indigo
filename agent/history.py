"""Conversation-history helpers (dependency-light so they're unit-testable).

Kept out of lm_studio_client.py so tests don't need the openai SDK.
"""
import re

# Harmony/gemma-style control tokens (<|channel|>, <|message|>, <|end|>, …) that
# some models leak into message content.
_CONTROL_TOKEN_RE = re.compile(r"<\|[^>]*?\|?>")


def strip_control_tokens(text: str) -> str:
    """Remove leaked harmony/gemma control tokens from model content so they
    aren't stored in history, replayed to the API, or shown in the console."""
    return _CONTROL_TOKEN_RE.sub("", text or "")


def trim_messages(messages: list[dict], max_history: int) -> list[dict]:
    """Trim history to ~max_history messages after the system prompt.

    The Chat Completions API requires every assistant `tool_calls` to be
    immediately followed by its matching `tool` responses. A naive tail slice
    can start on an orphaned `tool` message (its assistant was dropped) and get
    rejected with a 400. This cuts only at a `user` turn boundary, so a
    tool_calls/tool group is never split. If no boundary exists in the trim
    window, rather than returning oversized history unchanged (which could grow
    without bound in a pathological tool-heavy stretch, #69) it HARD-RESETS to the
    system prompt + the last user group — still API-valid (a user turn starts a
    fresh, self-contained group) and bounded to one step's worth of messages.
    """
    if len(messages) <= max_history + 1:
        return messages
    system = messages[:1] if messages and messages[0].get("role") == "system" else []
    target = len(messages) - max_history
    for i in range(max(target, len(system)), len(messages)):
        if messages[i].get("role") == "user":
            return system + messages[i:]
    # No user boundary within the window — fall back to the LAST user group so
    # history can't exceed the cap indefinitely.
    for i in range(len(messages) - 1, len(system) - 1, -1):
        if messages[i].get("role") == "user":
            return system + messages[i:]
    return system if system else messages


# ── token budget (#372) ──────────────────────────────────────────────────────────────────────────
# Without a tokenizer these are estimates; the client calibrates them against the server's reported prompt_tokens.
CHARS_PER_TOKEN = 3.5
IMAGE_TOKENS = 1500          # a ~240×160 screenshot / overhead map on typical vision models (a PNG is billed by size, not bytes)


def estimate_tokens(obj) -> int:
    """Rough token count of a message list, one message, a content value or a tool schema list (images cost a flat IMAGE_TOKENS)."""
    if obj is None:
        return 0
    if isinstance(obj, str):
        return int(len(obj) / CHARS_PER_TOKEN) + 1
    if isinstance(obj, list):
        return sum(estimate_tokens(x) for x in obj)
    if isinstance(obj, dict):
        if obj.get("type") == "image_url":
            return IMAGE_TOKENS
        return 4 + sum(estimate_tokens(v) for k, v in obj.items() if k != "role")
    return estimate_tokens(str(obj))


def strip_images(messages: list[dict]) -> list[dict]:
    """Messages with every image part replaced by its text parts (the model still gets the observation string)."""
    out = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            c = " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
            m = {**m, "content": c}
        out.append(m)
    return out


def _user_boundaries(messages: list[dict], start: int) -> list[int]:
    return [i for i in range(start, len(messages)) if messages[i].get("role") == "user"]


def last_user_group(messages: list[dict]) -> list[dict]:
    """System prompt + the most recent user turn with everything after it (the tool_calls/tool group it started). API-valid on its own."""
    system = messages[:1] if messages and messages[0].get("role") == "system" else []
    for i in range(len(messages) - 1, len(system) - 1, -1):
        if messages[i].get("role") == "user":
            return system + messages[i:]
    return messages


def fit_to_budget(messages: list[dict], budget: int, extra: int = 0, scale: float = 1.0) -> tuple[list[dict], list[str]]:
    """Shrink `messages` until (estimate × scale + extra) fits `budget` prompt tokens. Returns (messages, what was done).

    Cuts only at user-turn boundaries, so a tool_calls/tool group is never split. Order, cheapest loss first: drop the oldest whole
    turns (history is advisory — the observation carries the state), then the images of what is left. Whatever one turn alone costs
    (system prompt + the current observation) cannot be cut here: the caller's reactive ladder handles that case."""
    done: list[str] = []

    def cost(ms):
        return int(estimate_tokens(ms) * scale) + extra
    if budget <= 0 or cost(messages) <= budget:
        return messages, done
    system = 1 if messages and messages[0].get("role") == "system" else 0
    dropped = 0
    while cost(messages) > budget:
        bounds = _user_boundaries(messages, system)
        if len(bounds) < 2:
            break
        messages = messages[:system] + messages[bounds[1]:]
        dropped += 1
    if dropped:
        done.append(f"dropped {dropped} older turn(s)")
    if cost(messages) > budget and any(isinstance(m.get("content"), list) for m in messages):
        messages = strip_images(messages)
        done.append("dropped images")
    return messages, done

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


_THINK_BLOCK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>(.*)\Z", re.DOTALL | re.IGNORECASE)


def split_think(text: str) -> tuple[str, str]:
    """(thinking, answer) of a model reply: every closed <think>…</think> block, a trailing UNCLOSED <think>… (the reply was cut off by
    MAX_TOKENS inside its reasoning), and a bare leading `reasoning</think>answer` (templates that open the block for the model) are moved
    out of the answer. The answer is what may be stored in history and replayed to the API; the thinking never is (#374)."""
    text = text or ""
    thoughts: list[str] = []

    def take(m):
        thoughts.append(m.group(1).strip())
        return ""
    text = _THINK_BLOCK_RE.sub(take, text)
    if "</think>" in text.lower() and "<think>" not in text.lower():           # implicit opening tag
        i = text.lower().index("</think>")
        thoughts.append(text[:i].strip())
        text = text[i + len("</think>"):]
    text = _THINK_OPEN_RE.sub(take, text)
    return "\n".join(t for t in thoughts if t), text.strip()


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

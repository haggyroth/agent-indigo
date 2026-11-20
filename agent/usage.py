"""Token-usage helpers (dependency-free): how many prompt tokens the server served from its prompt cache.

OpenAI-compatible servers report it as usage.prompt_tokens_details.cached_tokens — OpenAI, OpenRouter and Ollama's /v1 endpoint (checked live: 0 on a first call, 440 of 445 on
a repeat of the same prefix). Some endpoints use a flat field instead (DeepSeek's prompt_cache_hit_tokens, Anthropic-style cache_read_input_tokens). None = the endpoint reports nothing."""


def _get(obj, name):
    if obj is None:
        return None
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def cached_prompt_tokens(usage) -> int | None:
    """Prompt tokens served from the server's cache for one call, or None when the endpoint doesn't say (0 means it said "none")."""
    for holder, name in ((_get(usage, "prompt_tokens_details"), "cached_tokens"), (usage, "prompt_cache_hit_tokens"), (usage, "cache_read_input_tokens")):
        v = _get(holder, name)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return int(v)
    return None

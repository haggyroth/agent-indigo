# Choosing and running a model

Agent Indigo talks to any **OpenAI-compatible chat-completions endpoint that supports tool (function) calling**. A pure chat model, or a server whose chat template drops tools, will reply in prose and never act.

## Endpoints

| Where | `LLM_BASE_URL` | Notes |
|---|---|---|
| **LM Studio** (local) | `http://localhost:1234/v1` (default) | Load the model, start the server, enable tool use. Keep it to **one concurrent generation** on consumer hardware. |
| **Ollama** (local or cloud models) | `http://localhost:11434/v1` | `LLM_API_KEY=ollama`; `ollama signin` for `:cloud` models. |
| **OpenAI / OpenRouter / others** | e.g. `https://api.openai.com/v1`, `https://openrouter.ai/api/v1` | Set `LLM_API_KEY` and `MODEL_NAME` to the provider's id. |

`MODEL_NAME` must match the model your endpoint serves exactly.

## Sizing the context

`prompt + MAX_TOKENS` must fit the model's **loaded** context window — not its maximum. Quantized local builds often load with 4–8k by default, which is too small for the system prompt plus a history; every call then fails with "Context size exceeded". Raise the loaded context, or lower `MAX_TOKENS` (it is a cap, not a target; the model stops when done). Reasoning models want headroom (`4096`–`8192`) because the tool call comes *after* the reasoning.

| Model family | `TEMPERATURE` | `MAX_TOKENS` | `ENABLE_THINKING` |
|---|---|---|---|
| Reasoning (thinking on) | `0.6` | `4096`–`8192` | `true` if the server exposes `reasoning_content` / `<think>` |
| Instruct / chat | `0.2`–`0.4` | `2048` | `false` |

## What works well

- **Tool-calling reliability matters most.** The skills do the fiddly work, so a mid-sized model that calls the right tool with the right arguments plays well; a stronger model mostly shows in judgement — team building, when to train, which battles to switch in.
- **Reasoning models work** and do not need vision: the text observation carries the key state.
- **Vision is optional and can be flaky.** Some quantized multimodal builds crash or blow their context on the screenshot. `USE_VISION=false` runs text-only; nothing important is lost.
- **Different models fail differently.** Models Agent Indigo has been run with include Gemma 4 and DeepSeek v4.1 Flash (via Ollama). They differ in how often they re-check state, how they handle refusals, and how they build a team — which is exactly what the run logs and the eval harness are for.

## Cost and spend controls

A decision step makes up to six model calls (the model may chain tool calls before the loop re-observes). As a guide from recorded runs, ~50 steps is about 300 calls and 3–6 million prompt tokens, most of them cache hits on endpoints that cache prompts. That is free against a local server and real money against a cloud one, so for any non-local endpoint set at least one cap:

| Variable | Stops the run after |
|---|---|
| `MAX_STEPS` | N decision steps |
| `MAX_LLM_CALLS` | N chat-completion calls |
| `TOKEN_BUDGET` | N prompt + completion tokens |
| `MAX_WALL_SECONDS` | N seconds of wall-clock time |

The agent warns at startup when `LLM_BASE_URL` is non-local and none of the first three is set. `LLM_TIMEOUT` bounds a single call, and `LLM_RETRIES` rides through transient failures (rate limits, resets, 5xx) with backoff before the error budget is charged.

## Comparing models

Runs from different models are comparable when they start from the same state with the same budget. Use the [eval harness](testing.md#evals-python--m-evals) (`python -m evals`) for pass/fail, steps, stuck-ratio and tokens, and `logs/runs/<ts>/run.jsonl` to see *why* two models diverged.

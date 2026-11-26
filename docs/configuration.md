# Configuration

All settings are environment variables, read from `.env` (copy [`.env.example`](../.env.example)) or the shell. They are parsed once in [`config.py`](../config.py); numeric values are validated at startup, so a typo (`MAX_STEPS=200a`) or an out-of-range value stops the run with a message naming the variable.

## Emulator and starting point

| Variable | Default | Description |
|---|---|---|
| `ROM_PATH` | `~/mgba-http/Pokemon_LeafGreen.gba` | Path to your LeafGreen `.gba` (US v1.0, `AGB-BPGE`). The default folder name is historical — set your own path. |
| `START_NEW_GAME` | off | Boot to the title screen with no save; the model starts the game itself with `quest('new_game')`. Takes precedence over the two below. |
| `START_FROM_SAVE` | — | A battery `.sav` to load and "Continue" into. |
| `START_FROM_STATE` | — | An emulator state (`.ss*`) to load directly: instant, no title screen, no quest-log recap. Takes precedence over `START_FROM_SAVE`. |
| `RESUME` | — | `latest` (the newest checkpoint under `logs/runs/*/checkpoints/`) or a checkpoint `.ss1` path. Loaded as `START_FROM_STATE`, with the journal snapshot saved beside it. |
| `STARTER`, `PLAYER_NAME`, `RIVAL_NAME` | — (**the model chooses**) | New game only. **Leave these blank and the model picks its own starter (`bulbasaur`, `charmander` or `squirtle`), its own name and its rival's name (up to 7 letters), and nicknames its starter and its Lapras.** Set any one and you decide for the model: the unset ones fall back to `bulbasaur` / `RED` / `BLUE` and no nicknames are asked for. |

## Run control

| Variable | Default | Description |
|---|---|---|
| `RUN_GOAL` | `hall_of_fame` | When a run is done. `hall_of_fame` = the Hall of Fame is recorded (bounded runs, evals). `completion` = keep playing past it until the completion target (the Kanto Pokédex, 151 caught, and every side quest) is reached — or a budget (`MAX_STEPS`, `TOKEN_BUDGET`, `MAX_WALL_SECONDS`, …) ends the run. After the Hall of Fame the observation carries a POST-GAME line (information only). The end record has `post_game_steps` and `dex_owned`. |
| `MAX_STEPS` | `0` | Stop after N decision steps (`0` = until interrupted). |
| `MAX_LLM_CALLS` | `0` | Stop after N chat-completion calls (`0` = unlimited). |
| `TOKEN_BUDGET` | `0` | Stop once cumulative prompt + completion tokens reach this (`0` = unlimited). |
| `MAX_WALL_SECONDS` | `0` | Hard wall-clock cap on the whole run, checked each step (`0` = unlimited). |
| `CHECKPOINT_EVERY` | `20` | Save an emulator checkpoint (and a journal snapshot) every N decision ticks and on every new badge; `0` = off. |
| `PER_SAVE_JOURNALS` | `true` | Give every save/state its own journal under `logs/journals/`. `false` = one global `logs/progress.json`. See [memory and logs](memory-and-logs.md). |
| `BATTLE_STYLE` | `shift` | The in-game *Battle Style* option, written every step. `shift` = after a trainer's Pokémon faints the game asks "Will you change POKéMON?" — a **free** switch; `set` = no prompt; blank = leave the save's value. |
| `LEAGUE_LOSS_RULE` | `advise` | Optional rule that raises the Elite Four's recommended levels after each loss in the League: `advise` (tell the model once per loss, then let it decide), `wall` (refuse until the raised levels are met), `off`. The base level shortfall is always a wall. |
| `LEAGUE_LOSS_BUMP` | `2` | Levels added to the recommended levels per League loss. |
| `USE_RUNNING_SHOES` | `true` | Hold B outdoors once the Running Shoes are owned (twice the speed); `false` = always walk. |
| `IV_PEEK_BEFORE_CATCH` | `false` | Show a wild Pokémon's IV quality before the catch. Off because a human player has no such readout in Gen III; turn on only for selective-catching experiments (runs are not comparable with it on). |

## Model and endpoint

| Variable | Default | Description |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:1234/v1` | Any OpenAI-compatible endpoint: LM Studio, Ollama (`http://localhost:11434/v1`), OpenAI, OpenRouter, … (`LM_STUDIO_BASE` is honoured as a fallback.) |
| `LLM_API_KEY` | `lm-studio` | Provider key for a cloud endpoint; a placeholder locally. `OPENAI_API_KEY` is only used as a fallback when the endpoint really is `api.openai.com` — one provider's key is never sent to another. |
| `MODEL_NAME` | `qwen/qwen2.5-14b-instruct` | The model id your endpoint serves. Must support tool calling. |
| `TEMPERATURE` | `0.6` | Sampling temperature. |
| `MAX_TOKENS` | `4096` | Cap on the response. `prompt + MAX_TOKENS` must fit the model's *loaded* context window. |
| `CONTEXT_TOKENS` | `0` | The model's *loaded* context window (LM Studio shows it). When set, the history is trimmed by estimated tokens so `prompt + MAX_TOKENS` fits (5 % margin; must be larger than `MAX_TOKENS`). `0` = unknown: the client learns a ceiling from the first context-overflow error instead. |
| `ENABLE_THINKING` | `false` | `true` for reasoning models that expose `reasoning_content` / `<think>` tokens. |
| `USE_VISION` | `true` | Attach the screenshot (and overhead area maps) to the model. `false` for text-only models or unstable vision; the text observation carries the key state either way. |
| `LLM_TIMEOUT` | `180` | Seconds allowed for one chat completion (`0` = none). A timed-out call counts against the consecutive-error budget. |
| `LLM_RETRIES` | `8` | Retries for a transient failure (connection reset, timeout, rate limit, 5xx) with 2 → 60 s exponential backoff (a `Retry-After` header is honoured), before the error budget is charged. `0` = none. A quota/billing 429, bad credentials (401/403/402) or an unknown model/URL (404) are never retried: the run ends at once with reason `llm_error`. A context-overflow 400 is answered by shrinking the request (images, then older turns, then the observation) and resending. |

See [models](models.md) for how to choose and size a model.

## Viewer and logging

| Variable | Default | Description |
|---|---|---|
| `SHOW_WINDOW` | `false` | Open a pygame window that renders the game (needs `pygame`). Close it or press `Esc` to stop cleanly. |
| `VIEWER_SCALE` | `3` | Window scale (240×160 × scale). |
| `VIEWER_FPS` | `120` | Playback pace cap (≈2× GBA speed); `0` = full emulator speed. |
| `LOG_LEVEL` | `events` | Terminal verbosity: `quiet` (milestones), `events` (+ every tool call), `debug` (+ observations and reasoning). |
| `STATUS_EVERY` | `25` | A one-line status (party, money, balls, tokens) every N ticks; `0` = off. |
| `SCREENSHOT_PATH` | per-process temp dir | Where the frame PNG is written each tick. The default is a private directory removed at exit (a predictable `/tmp` path would be a symlink hazard and clash between concurrent runs). |

## Build and test helpers

| Variable | Used by | Description |
|---|---|---|
| `MGBA_PREFIX` | `python -m game._mgba_build` | libmgba install prefix (default `/opt/homebrew`). |
| `LIVE_DIR` | live tests, `tools/live_suite.py` | Where the live-test fixtures live (default `saves/live/`). |
| `EVAL_START_SAVE` | `python -m evals` | The `.sav` the eval scenarios boot from. |
| `RUN_NAV_EVALS` | `tests/test_nav_scenarios.py` | `1` to enable the LLM-free navigation scenarios (they boot a real emulator). |

## Typical setups

```sh
# Local model in LM Studio, watch it play
MODEL_NAME=qwen/qwen3-14b ENABLE_THINKING=true SHOW_WINDOW=true python main.py

# Cloud model with a spend guard
LLM_BASE_URL=https://openrouter.ai/api/v1 LLM_API_KEY=sk-or-... MODEL_NAME=<provider id> \
  MAX_LLM_CALLS=2000 TOKEN_BUDGET=20000000 python main.py

# A fresh game — the model names itself, its rival, its starter and its Lapras
START_NEW_GAME=true python main.py

# …or you choose for it
START_NEW_GAME=true STARTER=squirtle PLAYER_NAME=ASH RIVAL_NAME=GARY python main.py

# Pick up a stopped run
RESUME=latest python main.py
```

## Exit status of `python main.py`

| code | meaning (`EpisodeResult.reason`) |
|---|---|
| `0` | the goal (`goal`), or a bound you asked for was reached: `max_steps`, `max_llm_calls`, `token_budget`, `max_wall` |
| `1` | the run broke: `stalled`, `error_budget`, `llm_error` (credentials / quota / unknown model) |
| `130` | interrupted (Ctrl-C) |

The stop reason is also in the run's `meta.json` and `run.jsonl` `end` record.

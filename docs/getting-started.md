# Getting started

This guide takes you from a fresh clone to a running agent, then covers the ways to start a run (new game, a cartridge save, a state, a checkpoint) and what to do when something goes wrong.

## 1. Requirements

| | |
|---|---|
| **Python** | 3.11 or newer |
| **libmgba** | `brew install mgba` (macOS) or your distribution's `libmgba` development package (Linux). The binding compiles against it. |
| **A C compiler** | Xcode Command Line Tools (macOS) or `build-essential` (Linux). cffi builds a small extension. |
| **A tool-calling LLM** | A local server ([LM Studio](https://lmstudio.ai/), [Ollama](https://ollama.com/)) or any OpenAI-compatible cloud endpoint. The model **must support function/tool calling** — see [models](models.md). |
| **The ROM** | Pokémon LeafGreen, US v1.0 (`.gba`, game code `AGB-BPGE`). Supply your own legally obtained copy; it is not part of this repository. |

Optional: `pygame` to watch the agent play in a window (`pip install pygame`).

## 2. Install

```sh
git clone https://github.com/haggyroth/agent-indigo.git
cd agent-indigo

python3 -m venv .venv
source .venv/bin/activate            # fish: source .venv/bin/activate.fish
pip install -r requirements.txt

brew install mgba                    # or your Linux libmgba package
python -m game._mgba_build           # compiles game/_mgba_native*.so
```

Rebuild the binding after upgrading libmgba. Verify it loads your ROM:

```sh
python -c "from game.mgba_core import NativeMGBAClient as C; m=C(); print(m.get_game_title(), m.get_game_code(), m.verify_connection())"
# POKEMON LEAF AGB-BPGE True
```

## 3. Configure

```sh
cp .env.example .env
```

At minimum set:

| Variable | What to put |
|---|---|
| `ROM_PATH` | Path to your LeafGreen `.gba` |
| `MODEL_NAME` | The model id your endpoint serves (the LM Studio / Ollama name, or the provider's id for a cloud model) |
| `LLM_BASE_URL` | The OpenAI-compatible endpoint. Default `http://localhost:1234/v1` (LM Studio). Ollama: `http://localhost:11434/v1`. |
| `LLM_API_KEY` | Your provider key for a cloud endpoint; a placeholder is fine locally |

Every other variable is optional — see [configuration](configuration.md). If you use a cloud endpoint, also set a spend guard (`MAX_STEPS`, `MAX_LLM_CALLS` or `TOKEN_BUDGET`) so an unattended run cannot spend without limit.

## 4. Run

```sh
source .venv/bin/activate
python main.py
```

By default the agent boots the ROM as-is. Choose how a run starts:

| You want | Set |
|---|---|
| **A brand-new game** (the model starts it with `quest('new_game')` — names, starter, Oak's parcel) | `START_NEW_GAME=true` (optionally `STARTER`, `PLAYER_NAME`, `RIVAL_NAME`) |
| **Continue a cartridge save** (`.sav`) | `START_FROM_SAVE=path/to/game.sav` |
| **Load an emulator state** (`.ss*`) straight into a scene | `START_FROM_STATE=path/to/state.ss1` |
| **Resume a stopped run** from its last checkpoint | `RESUME=latest` (or a `.ss1` path) |

Each save or state gets **its own journal** (see [memory and logs](memory-and-logs.md)), so continuing an old save never inherits another run's milestones.

Useful while experimenting:

```sh
# a bounded, text-only smoke run
USE_VISION=false MAX_STEPS=20 START_FROM_SAVE=path/to/game.sav python main.py

# watch it play (needs pygame)
SHOW_WINDOW=true python main.py
```

Stop a run with `Ctrl+C` (or close the viewer window / press `Esc`); the journal is saved and the last checkpoint is kept.

## 5. Watch what it is doing

- The terminal shows the live **event stream**: tool calls, catches, level-ups, badges, battle results, heals. `LOG_LEVEL=quiet|events|debug` sets how much; `STATUS_EVERY=<ticks>` adds a one-line status.
- Every run writes `logs/runs/<timestamp>/` with `run.jsonl` (each LLM call, tool call, event and observation), `meta.json`, and `checkpoints/`. This is the best place to look when a run misbehaves.
- With `SHOW_WINDOW=true` the viewer renders the game; it holds the last frame while the model thinks (the game only advances when the agent runs frames).

## 6. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `ERROR: emulator not ready or wrong ROM` | `ROM_PATH` is wrong, or the ROM is not US v1.0 LeafGreen (`AGB-BPGE`). Check the verify command above. |
| `ImportError` for `_mgba_native` | The binding is not built, or was built against an older libmgba: `python -m game._mgba_build`. |
| Build fails to find mgba headers | Point the builder at the prefix: `MGBA_PREFIX="$(brew --prefix)" python -m game._mgba_build`. |
| Every call fails with "Context size exceeded" | `prompt + MAX_TOKENS` must fit the model's **loaded** context. Lower `MAX_TOKENS` or raise the loaded context. |
| The model replies with text and never calls a tool | The model (or its chat template) does not support tool calling. Use one that does. |
| Vision crashes or blows the context | `USE_VISION=false` — the text observation carries the key state. |
| Calls hang | Set `LLM_TIMEOUT` (default 180 s) and `LLM_RETRIES`; keep a local server to one concurrent generation. |
| Window does not open | `SHOW_WINDOW=true` needs `pygame`; on a headless machine leave it off. |

If something looks wrong in the agent's play rather than the setup, read `logs/runs/<latest>/run.jsonl` — and see [testing](testing.md) for the eval harness, which scores runs against goals instead of requiring you to read logs.

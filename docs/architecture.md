# Architecture

Agent Indigo is a loop of **observe → decide → act**, with a strict split of responsibilities: the language model chooses *intent*, deterministic code performs it and reports back.

```text
 LeafGreen ROM
      │
 libmgba (Homebrew) ──cffi──► game/_mgba_native      in-process, headless, ~50× real time
      │                       game/mgba_core.py       NativeMGBAClient: read8/16/32, readrange, buttons, frames, states
      │
 game/memory_reader.py        decodes WRAM: party (XOR-decrypted), badges, map, position, battle structs, context
      │
 agent/observation.py         turns memory + knowledge into the text the model reads each tick
      │
 agent/lm_studio_client.py    OpenAI-compatible chat loop: up to 6 tool-call rounds per step, then re-observe
      │
 agent/skills/*               the tools: navigation, battle, party/PC, shopping, quests, HM moves, …
      │
 libmgba (buttons, frames)    ◄── skills press buttons, step frames, then VERIFY the result from memory
```

## The decision loop

`main.build_runtime()` loads the ROM and the requested start point (new game, `.sav`, state or checkpoint), selects the [journal](memory-and-logs.md) that belongs to it, and builds the runtime. `main.run_episode()` then repeats:

1. **Read state** — `LeafGreenReader.read_state()` decodes memory into a `GameState` (party, badges, map, position, context) and a `StateDiff` against the last tick.
2. **Build the observation** — one compact text block (plus an optional screenshot): context, location, the party, what changed, and — depending on the situation — a battle brief, shopping/readiness notes, area guidance, loop warnings.
3. **Ask the model** — the system prompt (rebuilt from long-term memory) plus recent history go to any OpenAI-compatible endpoint with the tool schemas that fit the screen. The model may chain up to six tool calls before control returns to the loop.
4. **Execute tools** — each tool is a skill (below). Results come back as short text the model can act on.
5. **Bookkeeping** — events, battle records, badge/milestone progress, blackout handling, checkpoints, the run log, goal and budget checks.

The loop is the same code the eval harness uses (`run_episode(goal=…)`), so scored runs and real runs cannot diverge.

### Context detection

`gMain.callback2` — the game's live "current screen" dispatcher — decides what the model is looking at: `OVERWORLD`, `IN_BATTLE`, `DIALOG_OPEN`, `IN_MENU`, `TRANSITIONING`. Flags that merely *look* like menu state (a menu flag that lingers after a menu closes) are paired with the screen-fade flag so the agent can never get stuck in a phantom menu. The addresses are authoritative in `game/constants.py`; the hard-won ones are listed in [CLAUDE.md](../CLAUDE.md#memory-addresses--context-detection).

## Skills, not button presses

Every tool is a **skill**: deterministic code that takes an intent, drives the emulator, and verifies the outcome in memory. Skills are mixins on the `AgentClient` in `agent/skills/`:

| Area | Examples |
|---|---|
| Navigation (`nav.py`, `overworld.py`) | `go_to`, `walk_to`, `go_to_map`, `grind`, `fly_to` — A* over the real tilemap, BFS over a generated map graph, ledges, NPCs, doors, caves, HM obstacles |
| Battle (`battle.py`, `items.py`, `movelearn.py`, `evolution.py`) | `use_move`, `switch_pokemon`, `use_item`, `catch`, `flee_battle`, level-up and evolution prompts |
| Party & PC (`party.py`, `pc.py`, `menu.py`) | `pc`, `reorder_party`, `team_report`, `inspect_pokemon`, `give_item` |
| Services (`services.py`, `selling.py`, `tutor.py`, `deleter.py`) | `heal`, `shop`, move tutors, the Move Deleter |
| Quests (`quests.py`, `gyms.py`, `hideout.py`, `silph.py`, `victory.py`, `league.py`, …) | `quest(name)` — the story chain, one resumable driver per beat |
| Field moves (`hm.py`, `fishing.py`, `bike.py`) | `use_hm` (Surf, Cut, Strength, Flash, Rock Smash), `fish`, the Bicycle |

Design rules every skill follows:

- **Self-verifying.** A skill reads memory after acting (position changed, HP changed, the menu opened) and never assumes a button press worked.
- **Resumable and clean-failing.** When something blocks it, the skill stops and says what and why, plus the exact call that resumes — it never mashes buttons.
- **The model plays the battles.** An encounter (wild or trainer) ends `go_to` / `grind` / the quest tools and hands control to the model; there is no fight auto-play.
- **Tools fit the screen.** `tools_for(context)` offers about 1.2k tokens of schema in battle and 3.9k on the overworld, and everything in ambiguous contexts.

The full list, generated from `agent/tools.py`, is in [tools.md](tools.md).

## The knowledge layer

`knowledge/` is pure data and string construction — no I/O. A large part is **generated from the [pokefirered](https://github.com/pret/pokefirered) decompilation** by the scripts in `tools/gen_*.py`, so it describes *this* game rather than a half-remembered version: the map graph with every warp, wild encounters, shop stock, learnsets, TM/HM compatibility, gym and trainer teams, puzzle tiles, boulder layouts, escape routes. The hand-written parts are the judgement calls: catch policy, team composition, readiness checks for each gym and the League, type matchups and immunities (including foe abilities such as Levitate), the system prompt.

The observation uses this layer to tell the model what matters *now*: the foe's types and ability, each of its moves annotated with effectiveness / STAB / "NO EFFECT", which teammate matches up best, the next gym's recommended level and what the team lacks, which Pokémon a trainer is about to send out, what to buy before the League.

## Module boundaries

These are intentional; do not cross them.

| Package | Does | Never does |
|---|---|---|
| `game/` | drives the emulator; decodes memory; tilemap, pathfinding, viewer | call the LLM; score anything |
| `agent/` | talks to the model; observation; skills (the only code that presses buttons) | touch the emulator except through skills / the client |
| `memory/` | journals, checkpoints, run log, short-term memory | network I/O |
| `knowledge/` | data and string building | any I/O |
| `evals/` | goals and scenarios are pure; only `runner.py` imports the heavy stack | — |

## What the agent writes to memory

The agent treats game RAM as read-only for observation: it does not touch save data, badges, stats, experience, RNG or battle outcomes. The only sanctioned writes are **menu cursor positions** (the FIGHT move cursor, the battle action cursor, the bag and party list cursors), which skills set to a target before pressing A — exactly equivalent to navigating a menu with the D-pad, but deterministic. It also writes the in-game *Battle Style* option each step (`BATTLE_STYLE`, default `shift`, which makes the game offer a free switch after a trainer's Pokémon faints). The ROM itself is never modified.

## Observability

- **Events** (`agent/events.py`): every catch, KO, level-up, badge, battle result, heal and tool call is one compact terminal line and one `run.jsonl` record. Counters by outcome feed the end-of-run statistics.
- **Run log** (`memory/run_log.py`): `logs/runs/<ts>/run.jsonl` holds every LLM call, tool call, event and tick observation; a watchdog records stalls.
- **Failure shots** (`agent/failure_shots.py`): when a skill fails, a screenshot of what was on screen is saved with the run.
- **Eval scorecards** (`evals/`): pass/fail, steps, event statistics, stuck-ratio, calls and tokens — see [testing](testing.md).

There is no shaped reward: what a run *did* is read from the event stream, not from a score nothing consumes.

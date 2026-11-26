# Memory, journals and logs

Agent Indigo keeps four kinds of state. Only the first two shape what the model knows; the rest exist so you can resume and analyse runs.

| | What | Where | Lives |
|---|---|---|---|
| **Short-term memory** | The last actions, position-visit counts, steps without movement — what the loop uses to notice it is going in circles | in-process (`memory/short_term.py`) | one run |
| **Long-term journal** | Session count, badges and gyms beaten, milestones, towns visited, battle counters (won / lost / fled / caught), League losses, what was last saved to the cartridge | `progress.json` (`memory/long_term.py`) | per save |
| **Battle journal** | One JSON line per battle — foe, level, lead, outcome, turns, moves, HP left — used to retrieve "loss lessons" against a foe that beat the team before | `battles.jsonl` (`memory/battle_journal.py`) | per save |
| **Run logs and checkpoints** | Everything a run did, plus emulator states to resume from | `logs/runs/<timestamp>/` | per run |

## One journal per save

Loading a save selects the journal that belongs to it, so testing an old fixture never inherits the milestones and "past losses" of a newer run.

| You start with | Journal used |
|---|---|
| `START_FROM_SAVE=a.sav` | `logs/journals/a-<hash>/{progress.json,battles.jsonl}` |
| `START_FROM_STATE=b.ss1` | `logs/journals/b-<hash>/…` |
| `RESUME=…/checkpoints/x.ss1` | `logs/journals/run-<timestamp>/…`, **restored from the snapshot written beside the checkpoint** — exactly what was true when that state was saved |
| `START_NEW_GAME=true`, or no save | the global `logs/progress.json` and `logs/battles.jsonl` |

The `<hash>` is a short hash of the file's absolute path, so two saves called `game.sav` in different folders stay apart. A journal that does not exist yet is **derived from the cartridge** rather than copied from another run: the starter and Oak's parcel once the save has a badge, every town whose Fly flag is set, and the gym badges the cartridge holds (the startup reconciliation adds those, and drops any badge a journal claims that the save does not).

Set `PER_SAVE_JOURNALS=false` for the single global journal. Reset one save's journal with:

```sh
python -m tools.reset_journal --source path/to/game.sav     # or no --source for the global one
python -m tools.reset_journal --bare                        # wipe everything, as if brand new
```

The reset backs the old files up next to them first.

## Checkpoints

Every `CHECKPOINT_EVERY` ticks (default 20), and on every new badge, the agent saves an emulator state under `logs/runs/<timestamp>/checkpoints/` — rolling (the newest few are kept) plus a permanent one per badge. Each state has its journal snapshot beside it (`<state>.ss1.ltm.json`, and the battle journal when it is small). `latest.json` records the newest one, which is what `RESUME=latest` loads.

This is not the cartridge save. A checkpoint is an emulator state (exact frame, RAM and all); the in-game save (`save_game`) writes the battery save the game itself would load. Both can be used to start a run.

## Run logs

Each run writes `logs/runs/<YYYYmmdd-HHMMSS>/`:

| File | Contents |
|---|---|
| `run.jsonl` | One JSON object per line with `t` (seconds since start) and a `kind`: `start`, `tick` (state + the observation the model saw), `llm` (one completion: tokens, reasoning, requested tool calls), `tool` (name, args, result, seconds), `ev` (a game event: catch, KO, badge, trip, …), `watchdog` (a stalled tool was stopped), `end` (reason, steps, calls, tokens, statistics) |
| `meta.json` | Config snapshot at the start, the result summary at the end |
| `checkpoints/` | The emulator states above |
| `shots/` | Screenshots saved when a skill failed, so the failure can be seen afterwards |

Writes are flushed per line, so a crash or `Ctrl+C` keeps everything. Logging is best-effort and can never break a run. `run.jsonl` is the first place to look when a run misbehaves — a few lines of Python over it answer questions like "how many tool calls were refused, and why?" or "what did the model see right before that blackout?".

## End-of-run statistics

There is no reward signal. What a run did is read from the event stream (`agent/events.py`): battles by outcome (won, lost, fled, caught, drawn), trainer wins, catches, level-ups, evolutions, faints, blackouts, badges, new towns, key items and heals. They print at the end of a run, go into the eval scorecard, and are stored in the `end` record of `run.jsonl`.

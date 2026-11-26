# Testing

There are three layers. Use the cheapest one that can catch the bug.

| Layer | Needs | What it proves | Run |
|---|---|---|---|
| **Unit tests** | nothing — no ROM, no emulator, no network | Decoders, rules, advice text, data tables, skill logic against fakes | `python -m pytest` |
| **Live tests** | the compiled binding, your ROM, fixtures in `saves/live/` | Skills and quests actually work on the real game — each test replays a real bug | `python tools/live_suite.py` |
| **Evals** | a model endpoint + the ROM | A *real agent run* makes progress toward a goal | `python -m evals` |

## Unit tests

More than a thousand hardware-free tests cover the Gen III decoder, the state machine, the type chart and matchup maths, the event stream, journals and checkpoints, tool gating, the generated data tables (maps, tutors, shops, boulder floors, gates — they catch data drift), and the advice the observation gives the model.

```sh
pip install -r requirements-test.txt
python -m pytest            # unit tests
ruff check .                # lint (real-error rules: pyflakes + syntax)
```

CI runs the suite on Python 3.11–3.13 and separately builds the native binding against libmgba on macOS ([`ci.yml`](../.github/workflows/ci.yml)). A test keeps the generated tool tables in `CLAUDE.md` and [tools.md](tools.md) current.

## Live tests (`tests/live/`)

Each live test replays a bug found in a watched run against the **real ROM** through the in-process binding: load a fixture state, call the skill, assert on the game's memory. They skip automatically when the binding, ROM or fixtures are missing, so CI (which has no ROM) skips them.

```sh
python tools/live_suite.py                                       # everything, with a preflight and a summary
python tools/live_suite.py -k articuno                           # a subset (never attested)
python tools/live_suite.py --changed origin/main --post-status   # only if the diff touches guarded code; then post the `live-suite` status for HEAD
```

The ROM and the ROM-derived fixtures can never be in the repository or in CI, so a pull request that touches *guarded* code (skills, `game/`, `main.py`, route and data modules) is attested by running the suite locally and posting a `live-suite` commit status; a gate workflow keeps that status honest (a new push resets it). The reasoning and the options considered are in [live-ci.md](live-ci.md); the fixtures are described in [`tests/live/README.md`](../tests/live/README.md).

## Evals (`python -m evals`)

Reading hundreds of log lines does not tell you whether a run made progress. The eval harness runs the **real agent loop** (`main.run_episode`) from a start state toward a goal with a step budget, in isolation (its own scratch journal, so a real save is never touched), and scores it: pass/fail, steps, event statistics (battles by outcome, level-ups), **stuck-ratio** (overworld ticks with no movement — the signature of a skill that cannot cross something), LLM calls and tokens.

```sh
python -m evals --list                # the scenarios
python -m evals                       # run all (needs a model endpoint + the ROM, like main.py)
python -m evals -s first_badge -v     # one scenario, streaming output
python -m evals first_badge -n 5      # one scenario, 5 trials -> a pass rate (the model samples at TEMPERATURE > 0)
python -m evals --strict              # exit 3 if any scenario was SKIPPED (fixture missing / start point would not load / goal already met at the start)
```

Results print as a table and are written to `logs/eval/<timestamp>.json`, each with a `meta` block (model, temperature, `MAX_TOKENS`, vision, git SHA, ROM and fixture SHA-1, Python) so two runs can be compared. Exit status: `0` nothing failed · `1` a scenario FAILED · `2` unknown scenario · `3` `--strict` and something was SKIPPED. `stuck` is the share of ticks after a movement tool where the player (map and tile) has not moved. Scenarios live in [`evals/scenarios.py`](../evals/scenarios.py) — from `reach_viridian` and `first_badge` up to `elite_four` and `full_chain` (the whole story to the Hall of Fame; days of wall time with a real model, run by hand) — and goals (reach a map, earn N badges, hit a milestone) in [`evals/goals.py`](../evals/goals.py). A scenario can be marked `xfail=<issue>` to document a known failure; it flips to a loud **XPASS** the day the bug is fixed.

There is also a **tier-1** deterministic check that drives the navigation skills with *no LLM*, so a failure is unambiguously a pathfinding or routing bug. It boots a real emulator, so it is opt-in: `RUN_NAV_EVALS=1 python -m pytest tests/test_nav_scenarios.py`.

## Mining a watched run

When you watch a run and something looks off, `logs/runs/<timestamp>/run.jsonl` has everything: the observation the model saw, its tool calls, and the results. The usual loop is: find the pattern in the log (refused calls, repeated results, contradictory advice), reproduce it in a unit test if it is logic, or a live test if it needs the real ROM, then fix it. Most of the live suite exists because of that loop.

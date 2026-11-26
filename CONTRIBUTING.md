# Contributing to Agent Indigo

Thanks for looking. This is a small project with a few strong conventions; following them keeps runs reproducible and the history readable.

## Set up

Follow [getting started](docs/getting-started.md), then:

```sh
pip install -r requirements-test.txt
python -m pytest        # unit tests — no ROM needed
ruff check .            # lint
```

## How changes are made

- **Branch** off `main` (`feat/…`, `fix/…`, `docs/…`, `chore/…`); never commit straight to `main`.
- **Commit messages** use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.
- **Pull requests** describe the change and the test plan, and are merged with a merge commit once CI is green.
- **Add a CHANGELOG entry** under *Unreleased* for anything a user or a watched run would notice: what was wrong, what changed, why.

## Tests

Every fix should come with the cheapest test that would have caught it:

1. A **unit test** if it is logic (advice text, a decoder, a rule, a data table).
2. A **live test** in `tests/live/` if it needs the real game — add the fixture it needs and describe it in `tests/live/README.md`.
3. An **eval scenario** if it is about whether a whole run makes progress.

If your change touches *guarded* code (skills, `game/`, `main.py`, route/data modules) the `live-suite` status must be green for the head commit; see [testing](docs/testing.md) and [live-ci](docs/live-ci.md). The ROM and ROM-derived fixtures are never committed.

## Ground rules

- **The model plays.** Do not add auto-play for fights or hard-code decisions the model should make; give it better information or a better tool instead. Prefer advice over forced walls so it keeps its autonomy.
- **Give the model the context a player would have.** If a watched run shows the model guessing at something the game already knows, surface it in the observation.
- **Respect the module boundaries** in [architecture](docs/architecture.md#module-boundaries): `game/` never calls the LLM, `knowledge/` does no I/O, only skills press buttons.
- **Generated data stays generated.** Edit the generator in `tools/gen_*.py` (and re-run it), not the output.
- **Skills verify.** A skill reads memory after acting and fails cleanly with a resumable message; it never mashes buttons.
- **Don't commit** a ROM, a save, a state, `.env`, or anything under `logs/` or `saves/`.

## Reporting problems

Open an issue with the model and endpoint you used, what you expected, and the relevant lines from `logs/runs/<timestamp>/run.jsonl` (the observation the model saw and the tool results around the problem are the most useful part).

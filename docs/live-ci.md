# Running the live suite without shipping the ROM (#279)

`tests/live/` drives the **real ROM** through the in-process libmgba binding. The ROM and the ROM-derived fixtures (`saves/live/*.ss1`: they contain VRAM / palettes / OAM) can never be in the
repository or in CI, so those tests are skipped there and a refactor can break a quest with every check green. This document records the options looked at, what was built, and what is
left for the owner to decide.

## What exists today (merged with this change)

| piece | where | what it does |
|---|---|---|
| One-command run + summary | `python tools/live_suite.py` | preflight (ROM, `work.sav`, every fixture a test loads, the compiled binding), runs `tests/live`, prints `N passed, M failed, K skipped in T min`, lists failures, **refuses to call an all-skipped run green** |
| Run only when it matters | `--changed origin/main` | exits 0 with "not needed" unless the diff touches *guarded* code (`agent/skills`, `game/`, `main.py`, `evals/`, route/data modules — `GUARDED` in the script) |
| Attestation | `--post-status` | publishes a `live-suite` **commit status** on HEAD (success only for a full, non-empty, all-green run; `-k` subsets are refused) |
| Keeping the status honest | `.github/workflows/live-gate.yml` | on every PR: no guarded code → `live-suite = success ("not needed")`; guarded code → `pending` until a local run posts success **for that exact commit** (a new push resets it) |

Workflow for a PR that touches guarded code:

```bash
python tools/live_suite.py --changed origin/main --post-status     # hours the first time; the status then covers the head commit
```

**Not done on purpose:** `live-suite` is *not yet* a required status check (that is a branch-protection setting, so it needs the owner's say-so). Until it is, it is advisory: a
pending `live-suite` on a PR means "run the live suite before merging". To make it enforce: Settings → Branches → `main` → add the `live-suite` context to required status checks
(it is always posted by the gate, so unguarded PRs are never blocked). The merge helper used in this repo (`merge_green.sh`) should then also wait for it.

## Options considered

| option | verdict | why |
|---|---|---|
| Commit the ROM, or an encrypted copy as a secret | **no** | it is distributing a copyrighted ROM to GitHub; "encrypted" does not change that |
| Self-hosted runner on a developer Mac | possible, **risky on a public repo** | full fidelity and automatic, but GitHub warns against self-hosted runners for public repos: a fork PR's workflow code runs on the Mac. Only safe with `pull_request` limited to same-repo branches (`github.event.pull_request.head.repo.full_name == github.repository`), "require approval for all outside collaborators", and the runner offline otherwise |
| **Local run + commit-status attestation** (built) | **recommended now** | no secrets, no infrastructure, no legal question; only users with write access can post statuses; stale attestations cannot cover new commits; trust is the developer's honesty (same as today's manual runs, now visible and enforceable) |
| Record/replay ("cassettes" of memory reads and button presses) | **no** | a replay only validates byte-identical call sequences, i.e. it fails exactly when the code under test changes — the case we want to catch |
| More decomp-derived unit tests | keep doing it | the generators already pin maps, tutors, shops, boulder floors, gates; they catch data drift, not driver bugs |
| **Build the ROM inside CI from the public decomp** | **viable, owner's call** | see below |

## Building the ROM in CI from pret/pokefirered (the only fully automatic ROM-free route)

Evidence gathered:

* The decomp's expected hash for the US LeafGreen build is `574fa542ffebb14be69902d1d36f1ec0a4afd71e` (`leafgreen.sha1`). The retail ROM this project is developed against
  (the maintainer's ROM) has **exactly that SHA-1**, so `make` with `GAME_VERSION=LEAFGREEN COMPARE=1` yields a byte-identical ROM: every address in `game/constants.py`
  (derived on that ROM) holds.
* pret's own CI does this on every push (`.github/workflows/build.yml`): checkout `pret/pokefirered` + `pret/agbcc`, `apt install binutils-arm-none-eabi libpng-dev`, build agbcc,
  `make -j all` with `COMPARE=1`. `COMPARE=1` fails the build unless the SHA-1 matches the retail ROM — i.e. a CI job could *prove* it is testing the real game.
* The ROM would exist only on the ephemeral runner: never committed, never uploaded as an artifact, never put in the Actions cache (cache the agbcc toolchain only).

Caveats, honestly:

1. **Legal comfort is the owner's decision.** pret does this publicly, but the decomp's assets are still Nintendo's; building a game ROM in your own Actions runs is the same activity at a
   different address. Nothing here should be switched on without that decision.
2. **Fixtures are the real blocker, not the ROM.** `*.ss1` states embed ROM-derived video memory, so they cannot be committed either. CI would have to *regenerate* them from a seed:
   `work.sav` (a battery save: player data, no ROM content) plus scripted staging with the harness helpers (`fly_to`, `set_badges`, `give_item`, `patch_mon`, `boost_party`…). Today's 14
   fixtures came from play-throughs and run checkpoints; a recipe-based generator needs one new primitive (`warp_to(map, x, y)` — write the warp destination and trigger the warp) and
   about a day to reproduce the 13 states `tests/live` loads. `post_hof.ss1` is already produced by a test (`test_the_credits_end_in_a_soft_reset…`) from `league_champion.ss1`.
3. **Cost.** The whole suite is long (see the measured baseline below); a per-PR run is unrealistic. A nightly or `workflow_dispatch` job on `main` is the realistic shape.
4. **libmgba on ubuntu.** The cffi binding is built against Homebrew's libmgba; Ubuntu's `libmgba-dev` is a different minor version. Unverified — needs one trial run.

Suggested phasing if the owner wants it: (1) `tools/make_live_fixtures.py` working locally from `work.sav` (started: it rebuilds three fixtures from recipes with Fly / `add_mon` / `go_to` — no `warp_to` was needed for those; dungeon-interior states still do) (useful on its own: fixes "contributors are blocked on missing
`.ss1` files"), (2) a manual `workflow_dispatch` job that builds the ROM, regenerates fixtures, builds the binding and runs a smoke subset, (3) nightly full run + status on `main`.

## The end-to-end regression (the fourth checkbox)

`evals` already has `full_chain` (goal: `hall_of_fame`), but with a real model it takes days. The LLM-free equivalent is `agent/scripted_policy.py` / `tools/scripted_run.py` (drives the real skills
with no model calls); extending its plan from four gyms to the whole `quest()` chain would give a deterministic overnight run. Not built here — it should come after the fixture generator, since it starts
from `work.sav` and needs nothing else.

## Measured baseline — and what the first full run found

The first full run of `tools/live_suite.py` on `main` (78 tests, ~37 minutes on an M-series Mac) was **75 passed, 3 failed** — three problems no CI check could have seen:

| failure | cause | fix |
|---|---|---|
| `victory_road_quest_reaches_indigo_plateau` | **a real regression**, shipped with the Articuno PR (#302): `use_hm('surf')` started walking to elevation-3 shores first and blocked `walk_to` from starting Surf itself, which Route 23's river crossing relied on. Bisected over three runs: green at `9c4e48d`/`5859df8`, red at `65e69ce` | the old nearest-shore search is restored byte for byte; the elevation-3 shores (needed for Seafoam B4F) are a *second pass*, only when the nearest six fail |
| `tea_quest_then_the_saffron_gate_guard_lets_you_in` | stale assertions: `silph_co` has a driver now ("no script" is never said), and the one-time readiness warning answers the first `quest()` call | tolerate both |
| `quest_brock_travels_to_the_gym…` | passed alone, failed in the full run: **state leaked between tests** — one shared runtime kept skill state and long-term memory (`gyms_beaten`), so quest('brock') headed for Misty's gym | `Live.load` resets every declared `SkillState` field and `ltm.data` |

A second full run then showed two tests that only passed by luck (`test_inspect_pokemon_and_the_catch_report…` threw its 3 Poké Balls at a foe whose first throw always breaks free and mis-used `give_item`, which only fills the Items pocket); both were made deterministic.
Final state: **78/78** (31 minutes). The value of the exercise is the point of this document: the regression above was sitting on `main` with every CI check green.

Rule of thumb that falls out of it: the live suite has to run before merging anything under the guarded paths, and a *full* run, because several bugs only show up through test interaction.

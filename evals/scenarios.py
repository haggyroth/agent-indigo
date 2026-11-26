"""Eval scenario registry.

A Scenario is a start point (battery save or mGBA save state) + a goal + a step
budget. The runner loads each in isolation and scores the episode. Add scenarios
here; keep them light (no heavy imports) so this stays CI-testable.

Start points default to the project's standard post-parcel save. Override per
scenario, or via env for local curated states (e.g. a Route-2 save that isolates
the #59 crossing without the whole Pallet→Route 2 journey).
"""
import os
from dataclasses import dataclass
from typing import Optional
from evals import goals

# The standard save the project boots from (post-parcel, Pokédex obtained). The stable fixture `saves/live/work.sav` (what the live suite boots from: Pallet /
# Viridian, Bulbasaur L8) is preferred: the maintainer's own play save in ~/mgba-http moves on with every run, and a scenario started from a late-game save
# measures nothing (first_badge would already be met). EVAL_START_SAVE overrides both.
_LIVE_WORK_SAV = os.path.join(os.environ.get("LIVE_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "saves", "live")), "work.sav")
DEFAULT_SAVE = os.path.expanduser(os.getenv("EVAL_START_SAVE") or (_LIVE_WORK_SAV if os.path.isfile(_LIVE_WORK_SAV) else "~/mgba-http/Pokemon_LeafGreen.sav"))


@dataclass
class Scenario:
    name:        str
    goal:        goals.Goal
    max_steps:   int
    start_save:  Optional[str] = None
    start_state: Optional[str] = None
    # Wall-clock safety cap (seconds) so an unattended eval can't run away — a local
    # model degraded to 3+ hour steps and burned 11 hours before. 0 = use the runner's
    # default ceiling. Set explicitly for legitimately long scenarios.
    max_wall_s:  float = 0.0
    notes:       str = ""
    # Known-failing today (documents an open bug); the run still executes and is
    # scored, but the runner reports it as an expected failure rather than a
    # regression. Set to an issue reference.
    xfail:       str = ""

    def fixtures(self) -> list[str]:
        """The local start files this scenario needs (a battery save and/or a save state)."""
        return [f for f in (self.start_state, self.start_save) if f]

    def missing_fixtures(self) -> list[str]:
        """The start files that are not on disk. `saves/*` is git-ignored, so a fresh checkout lacks the live fixtures."""
        return [f for f in self.fixtures() if not os.path.isfile(f)]


SCENARIOS: list[Scenario] = [
    Scenario(
        name="reach_viridian",
        goal=goals.reached_map(3, 1, "Viridian City"),
        max_steps=30,
        start_save=DEFAULT_SAVE,
        notes="From the post-parcel Pallet save, head north through Route 1 into "
              "Viridian City. Baseline overworld traversal + wild-battle handling.",
    ),
    Scenario(
        name="first_badge",
        goal=goals.badges_at_least(1),
        max_steps=400,
        start_save=DEFAULT_SAVE,
        notes="Earn the Boulder Badge from Brock. The save's lead is Bulbasaur L8 "
              "(Tackle/Growl/Leech Seed, no Vine Whip yet), so the agent must GRIND "
              "to ~L13 for Vine Whip before it can reliably beat Geodude L12 / Onix "
              "L14, then navigate the Pewter Gym and win. Long, exploratory run.",
    ),
    Scenario(
        name="second_badge",
        goal=goals.badges_at_least(2),
        max_steps=800,
        max_wall_s=5400,     # ~90 min ceiling; should finish well under this
        start_save=DEFAULT_SAVE,
        notes="Full mid-game pipeline: beat Brock, then cross Route 3 + Mt. Moon (a "
              "trainer-dense multi-floor maze) to Cerulean and beat Misty (Starmie L21, "
              "has Recover). Exercises everything post-first-badge — dungeon nav, trainer "
              "battles, healing/items — to surface the next capability gate.",
    ),
    Scenario(
        name="reach_pewter",
        goal=goals.reached_map(3, 2, "Pewter City"),
        max_steps=150,
        start_save=DEFAULT_SAVE,
        notes="The gauntlet: Route 2 is split by Viridian Forest's gate buildings, "
              "so go_to must WARP through the forest rather than walk to the sealed "
              "north edge. Solved end-to-end (#59 region routing + heal()/flee_battle "
              "to survive and skip wild encounters): a full LLM run reached Pewter "
              "(XPASS, steps=27, stuck=6%). Forest traversal is stochastic, so this "
              "is a probabilistic pass — go_to-through-forest autonomy (#81) would "
              "make it faster/more reliable.",
    ),
]


SCENARIOS += [
    Scenario(
        name="catch_a_pokemon",
        goal=goals.party_size_at_least(2),
        max_steps=60,
        start_save=DEFAULT_SAVE,
        notes="Catch a first wild Pokémon (go_to a grass route, weaken it, catch with a nickname). "
              "Exercises catch(), the nickname vetting/naming flow and the post-catch menus.",
    ),
    Scenario(
        name="balance_party",
        goal=goals.party_balanced(),
        max_steps=80,
        start_state=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "saves", "live", "threemon.ss1"),
        notes="Viridian City, party Bulbasaur L8 / Pikachu L5 / Caterpie L5 (local fixture, see "
              "tests/live/README.md). The agent should call grind() with no level so the laggards "
              "are brought within ~25% — covers train/grind, PP management and self-healing.",
    ),
]
SCENARIOS += [
    Scenario(
        name="elite_four",
        goal=goals.has_milestone("hall_of_fame"),
        max_steps=120,
        start_state=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "saves", "live", "league_door.ss1"),
        notes="Indigo Plateau, all eight badges, a level-60+ team (local fixture, see tests/live/README.md). quest('elite_four') preps, "
              "walks the five sealed rooms (Lorelei, Bruno, Agatha, Lance, the Champion) and the Hall of Fame; the model plays every battle. "
              "Passes when FLAG_SYS_GAME_CLEAR sets the hall_of_fame milestone.",
    ),
]
SCENARIOS += [
    Scenario(
        name="full_chain",
        goal=goals.has_milestone("hall_of_fame"),
        max_steps=40000,
        max_wall_s=3 * 86400,
        start_save=DEFAULT_SAVE,
        notes="The whole story from the standard post-parcel save: every gym beat is runnable (quest('brock') … quest('giovanni')), then quest('victory_road') and "
              "quest('elite_four'); the goal is the hall_of_fame milestone (FLAG_SYS_GAME_CLEAR). Days of wall time with a real model — run it by hand "
              "(python -m evals full_chain), never in CI; it exists so a regression anywhere in the chain shows up end to end.",
    ),
]


def by_name(name: str) -> Optional[Scenario]:
    return next((s for s in SCENARIOS if s.name == name), None)

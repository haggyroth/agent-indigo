"""Regenerate live-test fixtures (`saves/live/*.ss1`) from a starting save, with no model and no watched run (#279).

The live suite (tests/live) loads emulator states that contain ROM-derived video memory, so they can never be committed. This tool rebuilds the ones that are *recipes*: it boots the runtime
from `work.sav` (a battery save of an early game: Pallet / Viridian, a lone starter), stages the situation with the harness helpers (Fly, flags, badges, party edits) and writes the state.

    python tools/make_live_fixtures.py --list                      # what can be generated, and what exists
    python tools/make_live_fixtures.py                             # every recipe whose fixture is missing
    python tools/make_live_fixtures.py --only vermilion,league_door --force
    python tools/make_live_fixtures.py --out /tmp/fixtures         # elsewhere (LIVE_DIR is the default: saves/live)

A generated fixture matches its recipe's description, not necessarily a play-through's exact party or position: tests that need a specific one keep using the original. The recipes are plain
functions over `tests/live/harness.Live`; a new one is a few lines and a line in RECIPES. Needs the ROM, `work.sav` and the compiled binding (python -m game._mgba_build).
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SS_TICKET = 265


def go_to_town(live, town: str, want: tuple) -> None:
    """The boot state is indoors (Fly is refused there): walk out with the agent's own go_to skill — deterministic, no model — until the map is `want`."""
    import json
    for _ in range(6):
        if tuple(live.r.read_current_map()) == want:
            return
        live.c._execute("go_to", json.dumps({"destination": town}))
        if live.r.detect_context().name == "IN_BATTLE":
            raise AssertionError("a battle started on the way out (the starting save should be on a quiet route)")
    assert tuple(live.r.read_current_map()) == want, f"could not reach {town}: now at {live.r.read_current_map()}"


def recipe_threemon(live) -> None:
    """Viridian City, party Bulbasaur / Pikachu L5 / Caterpie L5 — the boot state plus two members."""
    go_to_town(live, "Viridian City", (3, 1))
    live.add_mon(25, 5, moves=(84, 45, 0, 0))                                  # Pikachu: Thunder Shock, Growl
    live.add_mon(10, 5, moves=(33, 81, 0, 0))                                  # Caterpie: Tackle, String Shot
    assert tuple(live.r.read_current_map()) == (3, 1), live.r.read_current_map()
    assert len(live.r.read_party()) == 3


def _stand_at_cable_club_counter(live, second_mon: tuple) -> None:
    """Viridian Pokémon Center 2F, across the counter from the Direct Corner attendant: the Cable Club tutorial done, the Pokédex in hand, and a second party member `second_mon` = (species, level, moves)."""
    import json
    live.set_flag(0x829)                                                       # FLAG_SYS_POKEDEX_GET
    species, level, moves = second_mon
    live.add_mon(species, level, moves=moves)                                  # the party needs two members to link
    live.set_var(0x407C, 2)                                                    # VAR_MAP_SCENE_POKEMON_CENTER_TEALA: the first-visit tutorial is over
    go_to_town(live, "Viridian City", (3, 1))
    for _ in range(6):                                                         # inside and up the stairs: map (5, 5)
        if tuple(live.r.read_current_map()) == (5, 5):
            break
        live.c._execute("go_to", json.dumps({"destination": "map:5,5"}))
    assert tuple(live.r.read_current_map()) == (5, 5), live.r.read_current_map()
    live.c._execute("walk_to", json.dumps({"x": 10, "y": 4}))
    assert tuple(live.r.read_player_pos()) == (10, 4), live.r.read_player_pos()
    live.m.tap("Up")                                                           # face the attendant (the walk may have ended facing another way)
    live.m.tick(20)


def recipe_cable_club_counter(live) -> None:
    """The player side of the link-cable tests (#363): Bulbasaur + a Kadabra L30 (Teleport, Confusion), which evolves by trade."""
    _stand_at_cable_club_counter(live, (64, 30, (100, 93, 0, 0)))


def recipe_partner_counter(live) -> None:
    """The partner side: Bulbasaur + a Rattata L5 (the throwaway it gives in a trade) at the same counter (#363)."""
    _stand_at_cable_club_counter(live, (19, 5, (33, 39, 0, 0)))


def recipe_vermilion(live) -> None:
    """Vermilion City, Ivysaur L30, the SS Ticket held, no Cut yet."""
    from knowledge.growth import exp_for_level
    from knowledge.growth_data import GROWTH_RATE
    go_to_town(live, "Pallet Town", (3, 0))
    live.fly_to("Vermilion City", badges=0b111)                                # Fly needs the Thunder Badge; the third badge is dropped again below
    live.set_badges(0b11)
    live.patch_mon(0, species=2, level=30, exp=exp_for_level(GROWTH_RATE.get(2, 0), 30), moves=[75, 22, 33, 73], pps=[25, 25, 35, 10])
    live.give_key_item(SS_TICKET)
    live.heal_hp()
    assert tuple(live.r.read_current_map()) == (3, 5), live.r.read_current_map()


def recipe_league_door(live) -> None:
    """Indigo Plateau Pokémon Center 1F, 8 badges, a six-strong boosted L70 team (the elite_four live test's staging)."""
    for species in (18, 65, 143, 130, 59):                                     # Pidgeot, Alakazam, Snorlax, Gyarados, Arcanine
        live.add_mon(species, 70, moves=(33, 0, 0, 0))
    go_to_town(live, "Pallet Town", (3, 0))
    live.fly_to("Indigo Plateau", badges=0xFF)
    live.league_ready(70)
    assert tuple(live.r.read_current_map()) == (3, 9), live.r.read_current_map()
    assert len(live.r.read_party()) == 6


# name -> (recipe, one-line description). A recipe stages from the boot state and asserts what it promises.
RECIPES = {
    "threemon": (recipe_threemon, "Viridian City with a three-member party"),
    "partner_counter": (recipe_partner_counter, "the trade partner's side: Bulbasaur + a Rattata at the same Cable Club counter"),
    "cable_club_counter": (recipe_cable_club_counter, "Viridian Pokémon Center 2F at the Direct Corner counter, a party of two (the link-cable tests)"),
    "vermilion": (recipe_vermilion, "Vermilion City, Ivysaur L30, the SS Ticket, no Cut"),
    "league_door": (recipe_league_door, "Indigo Plateau, 8 badges, a boosted L70 team of six"),
}


def build_live(live_dir: Path, work_sav: Path):
    """The runtime booted from work.sav and the harness around it (the same as tests/live/conftest.py)."""
    os.environ.pop("RESUME", None)
    os.environ["START_FROM_SAVE"] = str(work_sav)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests"))
    import game.mgba_core as mgba_core
    mgba_core.SHOW_WINDOW = False
    import main
    from live.harness import Live
    tmp = Path(tempfile.mkdtemp(prefix="fixtures-"))
    runtime = main.build_runtime(ltm_path=str(tmp / "ltm.json"), journal_path=str(tmp / "j.jsonl"), verbose=False)
    if runtime is None:
        raise SystemExit("the emulator runtime could not be built (ROM_PATH / the binding?)")
    return Live(runtime, live_dir), tmp


def main_cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", action="store_true", help="show the recipes and whether each fixture exists")
    ap.add_argument("--only", default="", help="comma-separated recipe names (default: every recipe whose fixture is missing)")
    ap.add_argument("--force", action="store_true", help="regenerate even when the fixture exists")
    ap.add_argument("--out", default="", help="output folder (default: LIVE_DIR or saves/live)")
    args = ap.parse_args(argv)
    live_dir = Path(os.environ.get("LIVE_DIR", ROOT / "saves" / "live"))
    out = Path(args.out) if args.out else live_dir
    if args.list:
        for name, (_fn, doc) in RECIPES.items():
            print(f"{name:12} {'exists ' if (out / f'{name}.ss1').exists() else 'missing'}  {doc}")
        return 0
    names = [n.strip() for n in args.only.split(",") if n.strip()] or list(RECIPES)
    unknown = [n for n in names if n not in RECIPES]
    if unknown:
        print(f"unknown recipe(s): {', '.join(unknown)} (see --list)")
        return 2
    todo = [n for n in names if args.force or not (out / f"{n}.ss1").exists()]
    if not todo:
        print("nothing to do: every selected fixture exists (use --force to regenerate)")
        return 0
    work_sav = Path(os.environ.get("WORK_SAV", live_dir / "work.sav"))
    rom = Path(os.path.expanduser(os.environ.get("ROM_PATH", "~/mgba-http/Pokemon_LeafGreen.gba")))
    for need, what in ((rom, "the ROM (ROM_PATH)"), (work_sav, "work.sav, the battery save the runtime boots from (WORK_SAV)")):
        if not need.exists():
            print(f"missing {what}: {need}")
            return 2
    out.mkdir(parents=True, exist_ok=True)
    live, tmp = build_live(out, work_sav)
    boot = tmp / "boot.ss1"
    assert live.m.save_state_file(str(boot)), "could not capture the boot state"
    failed = 0
    for name in todo:
        fn, _doc = RECIPES[name]
        assert live.m.load_state_file(str(boot)), "could not restore the boot state"
        live.m.tick(30)
        try:
            fn(live)
            assert live.m.save_state_file(str(out / f"{name}.ss1")), f"could not write {name}.ss1"
            print(f"made {out / f'{name}.ss1'}")
        except Exception as e:                                                  # one bad recipe does not stop the rest
            failed += 1
            print(f"FAILED {name}: {type(e).__name__}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main_cli())

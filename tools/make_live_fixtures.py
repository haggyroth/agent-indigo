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
import shutil
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


def _dungeon_recipe(name: str, dest: tuple, flags=(), badges: int = 0):
    """A recipe that stands the lead at the entrance of a dungeon interior (`Live.warp_to`: no walk, no Fly), with `flags` set and `badges` held."""
    def recipe(live) -> None:
        live.set_badges(badges)
        for f in flags:
            live.set_flag(f)
        live.warp_to(dest)
        assert tuple(live.r.read_current_map()) == dest, live.r.read_current_map()
        assert live.r.detect_context().name == "OVERWORLD"
    recipe.__doc__ = f"{name}: the entrance of {dest} on the free field."
    return recipe


# name -> (recipe, one-line description). A recipe stages from the boot state and asserts what it promises.
RECIPES = {
    "threemon": (recipe_threemon, "Viridian City with a three-member party"),
    "partner_counter": (recipe_partner_counter, "the trade partner's side: Bulbasaur + a Rattata at the same Cable Club counter"),
    "cable_club_counter": (recipe_cable_club_counter, "Viridian Pokémon Center 2F at the Direct Corner counter, a party of two (the link-cable tests)"),
    "mt_moon_1f": (_dungeon_recipe("mt_moon_1f", (1, 1)), "Mt. Moon 1F, at the entrance"),
    "rock_tunnel_1f": (_dungeon_recipe("rock_tunnel_1f", (1, 81)), "Rock Tunnel 1F, at the entrance (dark: no Flash)"),
    "silph_co_1f": (_dungeon_recipe("silph_co_1f", (1, 47)), "Silph Co. 1F, at the door"),
    "victory_road_1f": (_dungeon_recipe("victory_road_1f", (1, 39), badges=0xFF), "Victory Road 1F, at the Route 23 entrance, 8 badges"),
    "vermilion": (recipe_vermilion, "Vermilion City, Ivysaur L30, the SS Ticket, no Cut"),
    "league_door": (recipe_league_door, "Indigo Plateau, 8 badges, a boosted L70 team of six"),
}


def firered_partner_names() -> dict[str, int]:
    """partner_firered_<group> -> group: the FireRed partner states (a FireRed core at the Cable Club counter holding the exclusives, five to a state). Not part of RECIPES: they need the
    FireRed ROM and a FireRed counter state, which not every contributor has, so they are made only when named (or with --firered)."""
    sys.path.insert(0, str(ROOT))
    from agent.skills.linkpartner import partner_groups
    return {f"partner_firered_{g}": g for g in partner_groups()}


def make_firered_partner(group: int, out: Path) -> Path:
    """The FireRed partner state for `group`: FIRERED_STATE (a state of a FireRed game standing at a Pokémon Center 2F counter, e.g. ~/mgba-http/firered_trade_counter.ss0) with the group's
    exclusives added to the party (Tackle only, at the level they are first found at in FireRed). Written to `out`/partner_firered_<group>.ss1."""
    import functools
    import types
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests"))
    from agent.skills.linkpartner import FIRERED_ROM, partner_groups
    from game.memory_reader import LeafGreenReader
    from game.mgba_core import NativeMGBAClient
    from knowledge.exclusives import FIRERED_ONLY
    from live.harness import Live
    rom = Path(os.path.expanduser(os.environ.get("FIRERED_ROM_PATH", FIRERED_ROM)))
    state = Path(os.path.expanduser(os.environ.get("FIRERED_STATE", "~/mgba-http/firered_trade_counter.ss0")))
    for need, what in ((rom, "the FireRed ROM (FIRERED_ROM_PATH)"), (state, "a FireRed state at the Cable Club counter (FIRERED_STATE)")):
        if not need.exists():
            raise FileNotFoundError(f"missing {what}: {need}")
    fr = NativeMGBAClient(str(rom), show_window=False)
    try:
        fr.unrestricted_writes = True                                           # staging a partner, like the harness: this core is never the agent's game
        assert fr.load_state_file(str(state)), f"could not load {state}"
        fr.tick(30)
        reader = LeafGreenReader(fr)                                            # FireRed shares LeafGreen's RAM and callback addresses (verified for the link, #363)
        stage = types.SimpleNamespace(m=fr, r=reader)
        for name in ("patch_mon", "heal_hp"):
            setattr(stage, name, functools.partial(getattr(Live, name), stage))
        assert tuple(reader.read_current_map()) == (5, 5) and len(reader.read_party()) == 1, (reader.read_current_map(), reader.read_party())
        for sid in partner_groups()[group]:
            Live.add_mon(stage, sid, FIRERED_ONLY[sid][0], moves=(33, 0, 0, 0))
        fr.tick(30)
        assert [p.species_id for p in reader.read_party()][1:] == partner_groups()[group]
        target = out / f"partner_firered_{group}.ss1"
        assert fr.save_state_file(str(target)), f"could not write {target}"
        return target
    finally:
        fr.close()


def build_live(live_dir: Path, work_sav: Path):
    """The runtime booted from work.sav and the harness around it (the same as tests/live/conftest.py)."""
    os.environ.pop("RESUME", None)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests"))
    import game.mgba_core as mgba_core
    mgba_core.SHOW_WINDOW = False
    import main
    from live.harness import Live
    tmp = Path(tempfile.mkdtemp(prefix="fixtures-"))
    boot_sav = tmp / "work.sav"                                                 # a COPY: the cartridge save is file-backed, and an in-game save would overwrite the real work.sav
    shutil.copyfile(work_sav, boot_sav)
    os.environ["START_FROM_SAVE"] = str(boot_sav)
    runtime = main.build_runtime(start_save=str(boot_sav), ltm_path=str(tmp / "ltm.json"), journal_path=str(tmp / "j.jsonl"), verbose=False)
    if runtime is None:
        raise SystemExit("the emulator runtime could not be built (ROM_PATH / the binding?)")
    return Live(runtime, live_dir), tmp


def main_cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", action="store_true", help="show the recipes and whether each fixture exists")
    ap.add_argument("--only", default="", help="comma-separated recipe names (default: every recipe whose fixture is missing)")
    ap.add_argument("--firered", action="store_true", help="also make the FireRed partner states (partner_firered_<n>: needs the FireRed ROM and a FireRed counter state)")
    ap.add_argument("--force", action="store_true", help="regenerate even when the fixture exists")
    ap.add_argument("--out", default="", help="output folder (default: LIVE_DIR or saves/live)")
    args = ap.parse_args(argv)
    live_dir = Path(os.environ.get("LIVE_DIR", ROOT / "saves" / "live"))
    out = Path(args.out) if args.out else live_dir
    if args.list:
        for name, (_fn, doc) in RECIPES.items():
            print(f"{name:12} {'exists ' if (out / f'{name}.ss1').exists() else 'missing'}  {doc}")
        for name, group in firered_partner_names().items():
            print(f"{name:12} {'exists ' if (out / f'{name}.ss1').exists() else 'missing'}  the FireRed trade partner, group {group} (--firered or --only; needs the FireRed ROM)")
        return 0
    frs = firered_partner_names()
    names = [n.strip() for n in args.only.split(",") if n.strip()] or list(RECIPES) + (list(frs) if args.firered else [])
    unknown = [n for n in names if n not in RECIPES and n not in frs]
    if unknown:
        print(f"unknown recipe(s): {', '.join(unknown)} (see --list)")
        return 2
    todo = [n for n in names if args.force or not (out / f"{n}.ss1").exists()]
    if not todo:
        print("nothing to do: every selected fixture exists (use --force to regenerate)")
        return 0
    out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name in [n for n in todo if n in frs]:                                  # the FireRed partners need no LeafGreen runtime
        try:
            print(f"made {make_firered_partner(frs[name], out)}")
        except Exception as e:
            failed += 1
            print(f"FAILED {name}: {type(e).__name__}: {e}")
    todo = [n for n in todo if n in RECIPES]
    if not todo:
        return 1 if failed else 0
    work_sav = Path(os.environ.get("WORK_SAV", live_dir / "work.sav"))
    rom = Path(os.path.expanduser(os.environ.get("ROM_PATH", "~/mgba-http/Pokemon_LeafGreen.gba")))
    for need, what in ((rom, "the ROM (ROM_PATH)"), (work_sav, "work.sav, the battery save the runtime boots from (WORK_SAV)")):
        if not need.exists():
            print(f"missing {what}: {need}")
            return 2
    live, tmp = build_live(out, work_sav)
    boot = tmp / "boot.ss1"
    assert live.m.save_state_file(str(boot)), "could not capture the boot state"
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

#!/usr/bin/env python3
"""Regenerate knowledge/area_sweeps.py from a local pret/pokefirered checkout (#366).

Usage:
    python tools/gen_area_sweeps.py [path-to-pokefirered] > knowledge/area_sweeps.py

For every map it reads the decomp's own data: each trainer (the object event's script -> its `trainerbattle_*` -> the trainer constant -> the defeat flag
TRAINER_FLAGS_START + id), each overworld item ball (the object's FLAG_HIDE_* flag: set once it is taken) and each hidden item (its FLAG_HIDDEN_ITEM_* flag), then groups the
maps into the named areas a "complete this area" objective talks about (the RetroAchievements set names these). The game already stores the truth in flags, so progress
is READ from memory, never guessed.
"""
import glob
import json
import os
import re
import sys

PF_DEFAULT = os.path.expanduser("~/Projects/pokefirered")

# area name -> folder names (exact) or regexes (r"..." prefix means a regex over the folder name). Sevii Islands arrive with #360.
AREAS = {
    "Viridian Forest": ["ViridianForest"],
    "Mt. Moon": [r"re:^MtMoon_"],
    "Rock Tunnel": [r"re:^RockTunnel_"],
    "S.S. Anne": [r"re:^SSAnne_(?!Exterior)"],
    "Rocket Hideout": [r"re:^RocketHideout_"],
    "Pokémon Tower": [r"re:^PokemonTower_"],
    "Silph Co.": [r"re:^SilphCo_"],
    "Pokémon Mansion": [r"re:^PokemonMansion_"],
    "Power Plant": ["PowerPlant"],
    "Seafoam Islands": [r"re:^SeafoamIslands_"],
    "Safari Zone": [r"re:^SafariZone_"],
    "Victory Road": [r"re:^VictoryRoad_", "Route23"],
    "Cerulean Gym": ["CeruleanCity_Gym"],
    "Vermilion Gym": ["VermilionCity_Gym"],
    "Celadon Gym": ["CeladonCity_Gym"],
    "Fuchsia Gym": ["FuchsiaCity_Gym"],
    "Saffron Gym": ["SaffronCity_Gym"],
    "Cinnabar Gym": ["CinnabarIsland_Gym"],
    "Viridian Gym": ["ViridianCity_Gym"],
    "Routes 2-4, Viridian, Pewter, Cerulean": ["Route2", "Route3", "Route4", "ViridianCity", "PewterCity", "CeruleanCity"],
    "Routes 24-25": ["Route24", "Route25"],
    "Routes 9-10": ["Route9", "Route10"],
    "Routes 6-8, Saffron, Vermilion": ["Route6", "Route7", "Route8", "SaffronCity", "VermilionCity"],
    "Routes 11-15, Fuchsia": ["Route11", "Route12", "Route13", "Route14", "Route15", "FuchsiaCity"],
    "Routes 16-18, Celadon (Cycling Road)": ["Route16", "Route17", "Route18", "CeladonCity"],
    "Routes 19-21": ["Route19", "Route20", "Route21_North", "Route21_South"],
}


def parse_defines(path):
    """{NAME: int} for every `#define NAME <number | NAME | (NAME + n)>` that resolves."""
    raw = {}
    for m in re.finditer(r"^#define\s+(\w+)\s+(.+?)\s*(?://.*)?$", open(path).read(), re.M):
        raw[m.group(1)] = m.group(2).strip()
    cache = {}

    def val(name, seen=()):
        if name in cache:
            return cache[name]
        expr = raw.get(name)
        if expr is None or name in seen:
            return None
        e = expr.strip("() ")
        total = 0
        for tok in re.split(r"\s*\+\s*", e):
            tok = tok.strip("() ")
            if re.fullmatch(r"0[xX][0-9a-fA-F]+|\d+", tok):
                total += int(tok, 0)
            else:
                v = val(tok, seen + (name,))
                if v is None:
                    return None
                total += v
        cache[name] = total
        return total
    return {n: v for n in raw if (v := val(n)) is not None}


def trainer_index(pf: str) -> dict:
    """{script label: TRAINER_* constant} over EVERY script file: a map's own scripts.inc and the shared data/scripts/*.inc (the route trainers live there)."""
    out = {}
    files = glob.glob(f"{pf}/data/maps/*/scripts.inc") + glob.glob(f"{pf}/data/scripts/*.inc")
    for path in files:
        text = open(path).read()
        for m in re.finditer(r"^(\w+)::\s*\n(.*?)(?=^\w+::|\Z)", text, re.M | re.S):
            t = re.search(r"trainerbattle_\w+\s+(TRAINER_\w+)", m.group(2))
            if t:
                out[m.group(1)] = t.group(1)
    return out


def preset_hide_flags(pf: str, flags: dict) -> set:
    """Flags the game itself sets on a new game (EventScript_ResetAllMapFlags: objects that start hidden and appear later). An item ball whose hide flag starts SET is a
    story-conditional item (the Lift Key, the Silph Scope ...): 'flag set' would read as 'taken' before it ever appeared, so it is left out of the counts."""
    text = open(f"{pf}/data/event_scripts.s").read()
    m = re.search(r"^EventScript_ResetAllMapFlags::\s*\n(.*?)^\s*end\b", text, re.M | re.S)
    return {flags[n] for n in re.findall(r"setflag\s+(FLAG_\w+)", m.group(1) if m else "") if n in flags}


def renewable_hidden(pf: str) -> set:
    """Hidden items that RESPAWN (src/renewable_hidden_items.c re-rolls them daily): not one-time finds, so not part of a sweep."""
    return set(re.findall(r"HIDDEN_ID\((FLAG_HIDDEN_ITEM_\w+)\)", open(f"{pf}/src/renewable_hidden_items.c").read()))


def build(pf: str):
    flags = parse_defines(f"{pf}/include/constants/flags.h")
    trainers = parse_defines(f"{pf}/include/constants/opponents.h")
    trainer_start = flags["TRAINER_FLAGS_START"]
    groups = json.load(open(f"{pf}/data/maps/map_groups.json"))
    gn = {}
    for gi, gname in enumerate(groups["group_order"]):
        for ni, dname in enumerate(groups[gname]):
            gn[dname] = (gi, ni)
    tindex = trainer_index(pf)
    preset = preset_hide_flags(pf, flags)
    renewable = renewable_hidden(pf)
    per_map, unresolved = {}, []
    for mj in sorted(glob.glob(f"{pf}/data/maps/*/map.json")):
        folder = os.path.basename(os.path.dirname(mj))
        if folder not in gn:
            continue
        d = json.load(open(mj))
        tr, items, hidden = [], [], []
        for o in d.get("object_events", []):
            if o.get("trainer_type", "TRAINER_TYPE_NONE") not in ("TRAINER_TYPE_NONE",) and o.get("script") and o["trainer_type"].startswith("TRAINER_TYPE_"):
                const = tindex.get(o["script"])
                if const and const in trainers:
                    tr.append((trainer_start + trainers[const], const))
                else:
                    unresolved.append((folder, o["script"]))
            elif o.get("graphics_id") == "OBJ_EVENT_GFX_ITEM_BALL" and o.get("flag") in flags and flags[o["flag"]] not in preset:
                items.append((flags[o["flag"]], o["flag"]))
        for b in d.get("bg_events", []):
            if b.get("type") == "hidden_item" and b.get("flag") in flags and b["flag"] not in renewable:
                hidden.append((flags[b["flag"]], b["flag"]))
        if tr or items or hidden:
            per_map[folder] = {"map": gn[folder], "trainers": tr, "items": items, "hidden": hidden}
    return per_map, unresolved


def folders_for(patterns, per_map):
    out = []
    for f in per_map:
        if any((re.search(p[3:], f) if p.startswith("re:") else f == p) for p in patterns):
            out.append(f)
    return out


def main():
    pf = sys.argv[1] if len(sys.argv) > 1 else PF_DEFAULT
    per_map, unresolved = build(pf)
    out = ['"""GENERATED by tools/gen_area_sweeps.py from the pret/pokefirered decomp — do not edit. (#366)',
           "",
           "Every trainer / item ball / hidden item, per named area, with the game flag that says it is done: a trainer's defeat flag (TRAINER_FLAGS_START + id), an item ball's",
           'FLAG_HIDE_* (set once taken), a hidden item\'s FLAG_HIDDEN_ITEM_* (set once found). Progress is read from those flags — see knowledge/sweeps.py."""',
           "", "AREAS = {"]
    for area, pats in AREAS.items():
        fs = folders_for(pats, per_map)
        maps = [per_map[f]["map"] for f in fs]
        tr = sorted({(fl, c) for f in fs for fl, c in per_map[f]["trainers"]})
        it = sorted({(fl, c) for f in fs for fl, c in per_map[f]["items"]})
        hd = sorted({(fl, c) for f in fs for fl, c in per_map[f]["hidden"]})
        out.append(f"    {area!r}: {{")
        out.append(f"        'maps': {sorted(maps)!r},")
        out.append(f"        'trainers': {[fl for fl, _ in tr]!r},")
        out.append(f"        'items': {[fl for fl, _ in it]!r},")
        out.append(f"        'hidden': {[fl for fl, _ in hd]!r},")
        out.append("    },")
    out.append("}")
    sys.stdout.write("\n".join(out) + "\n")
    if unresolved:
        print(f"# unresolved trainer scripts ({len(unresolved)}): {unresolved[:6]}", file=sys.stderr)


if __name__ == "__main__":
    main()

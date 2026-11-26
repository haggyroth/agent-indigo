#!/usr/bin/env python3
"""Regenerate knowledge/fame_checker_data.py from a local pret/pokefirered checkout (#368).

Usage:
    python tools/gen_fame_checker.py [path-to-pokefirered] > knowledge/fame_checker_data.py

The Fame Checker holds 16 people x 6 "flavor texts" (gSaveBlock1.fameChecker[person].flavorTextFlags bit n); the game sets a bit with the `famechecker PERSON, n` script command. This reads
every such command, the script label it sits in, and where that script is placed: an NPC (object event) or a sign (bg event) on a map -> something to walk up to and talk to; anything
else (a battle's win script, a cutscene) -> an event that happens as the story goes by. Each entry is (person, index, map (group, num), kind, x, y, label, hide flag, need flag): the placed object's FLAG_HIDE_* (0 = always there): set while it is not out yet (the journals after a Gym, the gossipers after the Hall of Fame); need flag = a flag that must be SET before the script says it (game cleared).
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_rematches import parse_defines  # noqa: E402  (the same small #define resolver)

PF_DEFAULT = os.path.expanduser("~/Projects/pokefirered")


def build(pf: str):
    groups = json.load(open(f"{pf}/data/maps/map_groups.json"))
    gn = {}
    for gi, gname in enumerate(groups["group_order"]):
        for ni, dname in enumerate(groups[gname]):
            gn[dname] = (gi, ni)
    persons = {}
    for m in re.finditer(r"#define\s+FAMECHECKER_(\w+)\s+(\d+)", open(f"{pf}/include/constants/fame_checker.h").read()):
        if m.group(1) != "NUM_PERSONS":
            persons[f"FAMECHECKER_{m.group(1)}"] = int(m.group(2))
    flags = parse_defines(f"{pf}/include/constants/flags.h", seed={"SYS_FLAGS": 0x800})
    placed = {}                                                 # script label -> (folder, kind, x, y, hide flag number or 0)
    for mj in glob.glob(f"{pf}/data/maps/*/map.json"):
        folder = os.path.basename(os.path.dirname(mj))
        d = json.load(open(mj))
        for o in d.get("object_events", []):
            if o.get("script") and o["script"] != "0x0":
                placed.setdefault(o["script"], (folder, "npc", o["x"], o["y"], flags.get(o.get("flag"), 0)))
        for b in d.get("bg_events", []):
            if b.get("script"):
                placed.setdefault(b["script"], (folder, "sign", b["x"], b["y"], flags.get(b.get("flag"), 0)))
    folders = sorted(gn, key=len, reverse=True)
    refs = {}                                                   # script label -> the labels whose scripts goto / call it (so a win script is traced up to the NPC that runs it)
    for p in glob.glob(f"{pf}/data/**/*.inc", recursive=True):
        cur = None
        for line in open(p, errors="ignore"):
            m = re.match(r"^(\w+)::?", line)
            if m:
                cur = m.group(1)
                continue
            m = re.match(r"^\s*(?:goto|call|goto_if_\w+|call_if_\w+|trainerbattle_\w+|special\w*)\b(.*)", line)
            if m and cur:
                for tok in re.findall(r"[A-Za-z_]\w+", m.group(1)):
                    if tok != cur:
                        refs.setdefault(tok, set()).add(cur)

    def trace(label, depth=0, seen=()):
        """The nearest placed script that reaches `label` (itself first), or None."""
        if label in placed:
            return placed[label]
        if depth >= 5:
            return None
        for up in sorted(refs.get(label, ())):
            if up not in seen:
                r = trace(up, depth + 1, seen + (label,))
                if r:
                    return r
        return None

    entries = {}
    for p in sorted(glob.glob(f"{pf}/data/**/*.inc", recursive=True)):
        label = None
        folder_of_file = os.path.basename(os.path.dirname(p)) if "/data/maps/" in p else None
        for line in open(p, errors="ignore"):
            m = re.match(r"^(\w+)::?", line)
            if m:
                label = m.group(1)
            m = re.match(r"^\s*famechecker\s+(FAMECHECKER_\w+)\s*,\s*(\d+)\s*$", line)
            if not m or m.group(1) not in persons:
                continue
            person, idx = persons[m.group(1)], int(m.group(2))
            hit = trace(label) if label else None
            if hit:
                folder, kind, x, y, hide = hit
            else:
                folder = folder_of_file or next((f for f in folders if label and label.startswith(f + "_")), None)
                kind, x, y, hide = "event", -1, -1, 0
            if folder not in gn:
                print(f"# unresolved: {label} ({p})", file=sys.stderr)
                continue
            need = flags.get("FLAG_SYS_GAME_CLEAR", 0) if "GameClear" in label else 0       # the aides / the Fan Club worker only say it once the game is cleared
            entries.setdefault((person, idx), (person, idx, gn[folder], kind, x, y, label, hide, need))
    return persons, entries


def main():
    pf = sys.argv[1] if len(sys.argv) > 1 else PF_DEFAULT
    persons, entries = build(pf)
    names = {v: k.replace("FAMECHECKER_", "").title().replace("Ltsurge", "Lt. Surge").replace("Mrfuji", "Mr. Fuji") for k, v in persons.items()}
    out = ['"""GENERATED by tools/gen_fame_checker.py from the pret/pokefirered decomp — do not edit. (#368)',
           "",
           "PERSONS: the 16 Fame Checker people by index. ENTRIES: one (person, flavor index 0-5, map (group, num), kind, x, y, script label, hide flag, need flag) per flavor text; kind 'npc' / 'sign' = talk to it at",
           "(x, y) on that map, 'event' = set by a battle or scene as the story passes (x, y = -1); hide flag = the object's FLAG_HIDE_* (0 = always there; set = not out yet); need flag = must be SET first (0 = none).",
           '"""',
           "",
           f"PERSONS = {names!r}",
           "",
           "ENTRIES = ["]
    for k in sorted(entries):
        out.append(f"    {entries[k]!r},")
    out.append("]")
    print("\n".join(out))


if __name__ == "__main__":
    main()

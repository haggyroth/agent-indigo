#!/usr/bin/env python3
"""Read the user's REAL RetroAchievements unlocks for LeafGreen (game 788) and compare them with the agent's local evaluation (#358) — read-only: nothing is written to the account.

Usage:
    python tools/ra_sync.py                      # what the account has unlocked: counts, points, the ones still locked
    python tools/ra_sync.py --state saves/x.ss1  # also evaluate that emulator state locally and list where the two disagree
    python tools/ra_sync.py --user SOMEONE       # another public profile (default: the credentials' own username)

The credentials are those of tools/gen_ra_set.py (RA_USERNAME / RA_API_KEY, or the macOS Keychain item `retroachievements`). They go to retroachievements.org only; the key is never printed,
logged or written, and an HTTP failure is reported by status alone. The output stays on the screen: nothing of the account's progress is saved to a file.

Disagreements are information, not errors: the account may have been played on another save, and a 'probably' / 'unknown' check can never be proven right (knowledge/ra_map.py says which)."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.gen_ra_set import GAME_ID, credentials  # noqa: E402


def fetch_progress(user: str, key: str, target: str) -> dict:
    """API_GetGameInfoAndUserProgress for `target`'s progress on game 788. The API authenticates with query parameters only (z = username, y = web API key) over HTTPS; errors report the status
    alone, never the URL."""
    url = "https://retroachievements.org/API/API_GetGameInfoAndUserProgress.php?" + urllib.parse.urlencode({"z": user, "y": key, "u": target, "g": GAME_ID})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "agent-indigo-ra-sync"}), timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"RetroAchievements answered HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        sys.exit(f"could not read the progress ({type(e).__name__})")


def unlocked_ids(data: dict) -> dict:
    """{achievement id: 'hardcore' | 'softcore'} for what the account has earned (a DateEarnedHardcore / DateEarned on the achievement)."""
    out = {}
    for a in (data.get("Achievements") or {}).values():
        if a.get("DateEarnedHardcore"):
            out[int(a["ID"])] = "hardcore"
        elif a.get("DateEarned"):
            out[int(a["ID"])] = "softcore"
    return out


def consistency(data: dict, unlocked: dict) -> str:
    """'' when the response's own award counts match what unlocked_ids parsed; else a warning (the per-achievement date fields are only present once earned, so a mismatch means the parsing
    does not know this response's field names — never trust an empty list then)."""
    said = int(data.get("NumAwardedToUser") or 0)
    if said != len(unlocked):
        return f"WARNING: the response says {said} earned but {len(unlocked)} were read from the achievements' dates — the field names may have changed; the lists below are not reliable."
    return ""


def compare(unlocked: dict, states: dict) -> dict:
    """Where the account and the local evaluation differ. `unlocked` as from unlocked_ids, `states` as from knowledge.ra_progress.evaluate.
    - 'agree': earned on the account and 'yes' here, or locked there and not 'yes' here (a 'probably' counts as not yes)
    - 'account_only': earned on the account, but the local check says 'no' — a wrong mapping, a different save, or a check that reads something else
    - 'local_only': 'yes' here but locked on the account (the agent got it; the account is somewhere else)
    - 'untracked': earned on the account, but there is no check ('unknown')
    - 'probably_hit': earned on the account and 'probably' here (the partial check held and was right)"""
    out = {"agree": [], "account_only": [], "local_only": [], "untracked": [], "probably_hit": []}
    for aid, st in states.items():
        mine = aid in unlocked
        if mine and st == "unknown":
            out["untracked"].append(aid)
        elif mine and st == "probably":
            out["probably_hit"].append(aid)
        elif mine and st == "no":
            out["account_only"].append(aid)
        elif not mine and st == "yes":
            out["local_only"].append(aid)
        else:
            out["agree"].append(aid)
    return out


def summary(unlocked: dict) -> str:
    from knowledge.ra_set import ACHIEVEMENTS
    pts = {a[0]: a[3] for a in ACHIEVEMENTS}
    got = [aid for aid in unlocked if aid in pts]
    return f"{len(got)}/{len(ACHIEVEMENTS)} earned ({sum(pts[a] for a in got)}/{sum(pts.values())} pts), {sum(1 for v in unlocked.values() if v == 'hardcore')} in hardcore"


def local_states(state_path: str) -> dict:
    """The agent's own evaluation of an emulator state: LeafGreen booted from ROM_PATH with the state loaded (the same reader the live tests use)."""
    from types import SimpleNamespace

    from agent import ra
    from game.memory_reader import LeafGreenReader
    from game.mgba_core import NativeMGBAClient
    from knowledge import ra_progress
    rom = os.path.expanduser(os.environ.get("ROM_PATH", "~/mgba-http/Pokemon_LeafGreen.gba"))
    client = NativeMGBAClient(rom, show_window=False)
    try:
        if not client.load_state_file(state_path):
            sys.exit(f"could not load the state {state_path}")
        client.tick(30)
        return ra_progress.evaluate(ra.make_check(LeafGreenReader(client), SimpleNamespace(data={"milestones": []})))
    finally:
        client.close()


def report(unlocked: dict, states: dict | None) -> str:
    from knowledge.ra_set import ACHIEVEMENTS
    title = {a[0]: a[1] for a in ACHIEVEMENTS}
    lines = [f"Account: {summary(unlocked)}"]
    if states is None:
        locked = [a for a in ACHIEVEMENTS if a[0] not in unlocked]
        lines.append(f"Still locked ({len(locked)}): " + "; ".join(a[1] for a in locked[:15]) + (" …" if len(locked) > 15 else ""))
        return "\n".join(lines)
    diff = compare(unlocked, states)
    lines.append(f"Local: {sum(1 for s in states.values() if s == 'yes')} yes, {sum(1 for s in states.values() if s == 'probably')} probably, {sum(1 for s in states.values() if s == 'unknown')} untracked")
    lines.append(f"Agree: {len(diff['agree'])}; the partial checks that held on the account: {len(diff['probably_hit'])}")
    for key, what in (("account_only", "On the account but NOT here (a different save, or a wrong check)"), ("local_only", "Here but locked on the account"),
                      ("untracked", "On the account, no check here")):
        if diff[key]:
            lines.append(f"{what} ({len(diff[key])}): " + "; ".join(title.get(a, str(a)) for a in diff[key]))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--state", help="an emulator state (.ss1) to evaluate locally and compare")
    ap.add_argument("--user", help="another user's public progress (default: the credentials' own)")
    args = ap.parse_args()
    user, key = credentials()
    data = fetch_progress(user, key, args.user or user)
    unlocked = unlocked_ids(data)
    if warning := consistency(data, unlocked):
        print(warning)
    print(report(unlocked, local_states(args.state) if args.state else None))


if __name__ == "__main__":
    main()

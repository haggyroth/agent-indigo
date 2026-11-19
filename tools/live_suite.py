"""One-command local run of the live (real-ROM) suite, with a summary and an optional GitHub commit status (#279).

    python tools/live_suite.py                         # run everything, print a summary
    python tools/live_suite.py -k articuno             # a subset (pytest -k)
    python tools/live_suite.py --changed origin/main   # run only if the diff touches guarded code (else exit 0, "not needed")
    python tools/live_suite.py --changed origin/main --post-status   # ...and publish the `live-suite` commit status for HEAD
    python tools/live_suite.py --guard-needed origin/main            # no emulator needed: prints yes/no (what the CI gate runs)

Why a script instead of a CI job: the live tests drive the real ROM through the in-process libmgba binding, and the ROM (plus the ROM-derived fixtures in saves/live) can never be in CI.
So the suite runs on a developer machine and *attests* to the result with a commit status named `live-suite`; .github/workflows/live-gate.yml keeps that status `pending` on pull
requests that touch GUARDED code until a local run flips it. See docs/live-ci.md for the options considered (self-hosted runner, decomp-built ROM) and the recommendation.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = "live-suite"
# Code whose behaviour only the real ROM can vouch for. A PR that changes none of these cannot break a live test (data-only generators and docs included).
GUARDED = (
    "agent/skills/*", "agent/tools.py", "agent/lm_studio_client.py", "agent/observation.py",
    "game/*", "main.py", "evals/*",
    "knowledge/*_route.py", "knowledge/*_data.py", "knowledge/map_graph.py", "knowledge/map_regions.py", "knowledge/gates.py", "knowledge/boulder_puzzle.py",
    "knowledge/story_beats.py", "knowledge/navigation.py", "knowledge/tutors.py", "knowledge/puzzle_tiles.py",
    "tests/live/*.py",
)


def changed_files(base: str) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def guarded(paths) -> list[str]:
    return [p for p in paths if any(fnmatch.fnmatch(p, g) for g in GUARDED)]


def required_fixtures() -> list[str]:
    """Fixture names the live tests load (`live.load("name")`), plus work.sav which the runtime boots from."""
    text = (ROOT / "tests" / "live" / "test_live_regressions.py").read_text()
    return sorted({m.group(1) for m in re.finditer(r'live\.load\("([a-z_0-9]+)"\)', text)})


def preflight() -> list[str]:
    """Problems that would make every live test skip (so a green run would mean nothing). Empty = ready."""
    problems = []
    rom = Path(os.path.expanduser(os.environ.get("ROM_PATH", "~/mgba-http/Pokemon_LeafGreen.gba")))
    if not rom.exists():
        problems.append(f"ROM not found at {rom} (set ROM_PATH)")
    live_dir = Path(os.environ.get("LIVE_DIR", ROOT / "saves" / "live"))
    if not (live_dir / "work.sav").exists():
        problems.append(f"{live_dir / 'work.sav'} missing (the battery save the runtime boots from)")
    missing = [f for f in required_fixtures() if not (live_dir / f"{f}.ss1").exists()]
    if missing:
        problems.append("fixtures missing in " + str(live_dir) + ": " + ", ".join(missing) + " — see tests/live/README.md")
    sys.path.insert(0, str(ROOT))
    try:
        import game.mgba_core  # noqa: F401
    except Exception as e:
        problems.append(f"native binding unavailable ({e}) — python -m game._mgba_build")
    return problems


def summarize(junit_xml: Path) -> dict:
    root = ET.parse(junit_xml).getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    res = {"passed": 0, "failed": 0, "skipped": 0, "seconds": 0.0, "failures": [], "skips": []}
    for suite in suites:
        for case in suite.iter("testcase"):
            res["seconds"] += float(case.get("time") or 0)
            name = f"{case.get('classname', '').split('.')[-1]}::{case.get('name')}"
            if case.find("failure") is not None or case.find("error") is not None:
                res["failed"] += 1
                res["failures"].append(name)
            elif case.find("skipped") is not None:
                res["skipped"] += 1
                res["skips"].append(name)
            else:
                res["passed"] += 1
    return res


def head_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def post_status(sha: str, state: str, description: str) -> None:
    """Publish the `live-suite` commit status with gh (needs `gh auth login` and write access to the repo)."""
    repo = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["gh", "api", f"repos/{repo}/statuses/{sha}", "-f", f"state={state}", "-f", f"context={CONTEXT}", "-f", f"description={description[:140]}"],
                   cwd=ROOT, check=True, capture_output=True)
    print(f"posted {CONTEXT}={state} on {sha[:8]}: {description}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-k", dest="keyword", default="", help="pytest -k expression")
    ap.add_argument("--changed", metavar="BASE", help="run only if `git diff BASE...HEAD` touches guarded code")
    ap.add_argument("--guard-needed", metavar="BASE", help="print yes/no (does the diff touch guarded code?) and exit; needs no ROM")
    ap.add_argument("--post-status", action="store_true", help=f"publish the `{CONTEXT}` commit status for HEAD (success / failure)")
    args = ap.parse_args(argv)
    if args.post_status and args.keyword:
        print("refusing --post-status with -k: the status attests the WHOLE suite, not a subset.")
        return 2

    if args.guard_needed:
        hit = guarded(changed_files(args.guard_needed))
        print("yes" if hit else "no")
        if hit:
            print("guarded files:", ", ".join(hit[:10]) + (" …" if len(hit) > 10 else ""), file=sys.stderr)
        return 0
    if args.changed:
        hit = guarded(changed_files(args.changed))
        if not hit:
            print(f"live suite not needed: no guarded files changed vs {args.changed}")
            if args.post_status:
                post_status(head_sha(), "success", "not needed: no guarded code changed")
            return 0
        print(f"guarded files changed ({len(hit)}): " + ", ".join(hit[:8]) + (" …" if len(hit) > 8 else ""))

    problems = preflight()
    if problems:
        print("The live suite cannot run here:\n  - " + "\n  - ".join(problems))
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "live.xml"
        cmd = [sys.executable, "-m", "pytest", "tests/live", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}"]
        if args.keyword:
            cmd += ["-k", args.keyword]
        print("running:", " ".join(cmd))
        code = subprocess.run(cmd, cwd=ROOT).returncode
        res = summarize(xml) if xml.exists() else {"passed": 0, "failed": 0, "skipped": 0, "seconds": 0.0, "failures": [], "skips": []}

    total = res["passed"] + res["failed"] + res["skipped"]
    line = f"{res['passed']} passed, {res['failed']} failed, {res['skipped']} skipped of {total} in {res['seconds'] / 60:.1f} min"
    print("\n" + line)
    if res["failures"]:
        print("FAILED:\n  " + "\n  ".join(res["failures"]))
    if res["skipped"] == total and total:
        print("everything skipped — a green run here would mean nothing (ROM/fixtures/binding?).")
        code = code or 3
    if args.post_status:
        ok = code == 0 and not res["failed"] and res["passed"] > 0
        post_status(head_sha(), "success" if ok else "failure", line)
    print(json.dumps({k: res[k] for k in ("passed", "failed", "skipped")}))
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""CLI for the eval harness:  python -m evals [NAME | --scenario NAME] [--trials N] [--strict] [--verbose] [--list]

Runs Tier-2 scenarios (real agent loop toward a goal) and prints a scorecard.
Needs the LLM endpoint + native binding + ROM up, same as `python main.py`.

Exit status: 0 nothing failed · 1 a scenario FAILED · 2 usage error (unknown scenario) · 3 `--strict` and a scenario was SKIPPED (missing fixture, start point
that would not load, emulator unavailable, goal already met at the start) or nothing ran.
"""
import argparse
import sys

from evals.scenarios import SCENARIOS, by_name


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m evals",
                                 description="Run agent eval scenarios.")
    ap.add_argument("name", nargs="?", help="run only this scenario (same as --scenario)")
    ap.add_argument("--scenario", "-s", help="run only this scenario by name")
    ap.add_argument("--trials", "-n", type=int, default=1, help="run each scenario N times and report a pass rate (the model samples, so one run is one noisy sample)")
    ap.add_argument("--list", "-l", action="store_true", help="list scenarios and exit")
    ap.add_argument("--strict", action="store_true",
                    help="exit 3 if any scenario was SKIPPED (a missing fixture or a start point that would not load) or nothing ran")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="stream the per-tick agent output (default: quiet)")
    args = ap.parse_args()

    if args.list:
        for sc in SCENARIOS:
            tag = f" [xfail {sc.xfail}]" if sc.xfail else ""
            if sc.missing_fixtures():
                tag += f" [MISSING: {', '.join(sc.missing_fixtures())}]"
            print(f"{sc.name:16} ≤{sc.max_steps:<4} {sc.goal.desc}{tag}")
            if sc.notes:
                print(f"{'':16} {sc.notes}")
        return

    from evals.runner import exit_code, run_all

    wanted = args.scenario or args.name
    if wanted:
        sc = by_name(wanted)
        if sc is None:
            print(f"Unknown scenario '{wanted}'. "
                  f"Known: {', '.join(s.name for s in SCENARIOS)}", file=sys.stderr)
            sys.exit(2)
        results = run_all([sc], verbose=args.verbose, trials=args.trials)
    else:
        results = run_all(verbose=args.verbose, trials=args.trials)
    code = exit_code(results, strict=args.strict)
    if code:
        sys.exit(code)


if __name__ == "__main__":
    main()

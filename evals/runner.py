"""Tier-2 eval runner: drive the real agent loop through scenarios and score them.

Each scenario builds an isolated AgentRuntime (its own scratch progress.json /
battles.jsonl so the real logs are never touched), runs `main.run_episode` with
the scenario's goal + step budget, and collects the EpisodeResult. Results print
as a table and write to logs/eval/<timestamp>.json.

This imports the heavy agent stack (via `main`), so it only runs where the LLM
endpoint + native binding + ROM are available — not in the dependency-light CI.
"""
import json
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from config import PROGRESS_PATH
from evals.scenarios import Scenario, SCENARIOS

console = Console()
EVAL_DIR = Path(PROGRESS_PATH).parent / "eval"
DEFAULT_EVAL_WALL_S = 7200.0   # 2h hard ceiling for any scenario without its own cap


def run_scenario(sc: Scenario, *, verbose: bool = False, trial: int = 1) -> dict:
    """Run one scenario end-to-end. Returns a result dict (EpisodeResult + meta + provenance). A scenario that cannot start where it says
    (fixture missing, start point unloadable, emulator down, goal already met at the start) is returned as status SKIPPED — never run, never FAIL."""
    import main as agent  # heavy import kept local so `evals` stays importable

    missing = sc.missing_fixtures()
    if missing:                                   # never boot (and spend a step budget on) a scenario that cannot start where it says
        return _skipped(sc, f"fixture_missing: {', '.join(missing)}")

    scratch = EVAL_DIR / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    ltm_path     = scratch / f"{sc.name}_progress.json"
    journal_path = scratch / f"{sc.name}_battles.jsonl"
    for p in (ltm_path, journal_path):     # start clean every run
        p.unlink(missing_ok=True)

    console.print(f"[bold]▶ {sc.name}[/] — goal: {sc.goal.desc} (≤{sc.max_steps} steps)")
    try:
        rt = agent.build_runtime(
            start_save=sc.start_save or "", start_state=sc.start_state or "",
            ltm_path=str(ltm_path), journal_path=str(journal_path), verbose=verbose,
        )
    except agent.StartPointError as e:
        return _skipped(sc, f"start_point_failed: {e}")
    if rt is None:
        return _skipped(sc, "emulator_unavailable")
    try:
        if sc.goal(rt.reader.read_state(), rt.ltm):          # a goal that is already true at the start would "pass" at step 0 and measure nothing
            return _skipped(sc, "goal_met_at_start")
        return _run(sc, rt, agent, verbose, trial)
    finally:
        rt.mgba.close()                                      # one core per scenario: free it now, not whenever the GC gets to it


def _run(sc: Scenario, rt, agent, verbose: bool, trial: int) -> dict:

    # Always bound the wall-clock so an unattended eval can't run away (an 11-hour
    # run happened when a local model degraded). Scenarios may set a tighter cap.
    wall = sc.max_wall_s or DEFAULT_EVAL_WALL_S
    t0 = time.time()
    result = agent.run_episode(rt, goal=sc.goal, goal_desc=sc.goal.desc,
                               max_steps=sc.max_steps, max_wall_s=wall, verbose=verbose)
    elapsed = round(time.time() - t0, 1)

    out = result.to_dict()
    from evals.provenance import provenance
    out.update(scenario=sc.name, elapsed_s=elapsed, xfail=sc.xfail, trial=trial, meta=provenance(sc))
    # An xfail scenario that fails is "expected"; if it unexpectedly passes, flag it.
    out["status"] = _status(result.passed, sc.xfail)
    console.print(f"  {result.summary()}  [{out['status']}]  ({elapsed}s)")
    return out


def _skipped(sc: Scenario, why: str) -> dict:
    """A scenario that could not start where it says is SKIPPED — never run, never scored FAIL."""
    console.print(f"[yellow]  SKIPPED {sc.name}: {why}[/]")
    return dict(scenario=sc.name, status="SKIPPED", reason=why, passed=False, steps=0, llm_calls=0, total_tokens=0,
                prompt_tokens=0, completion_tokens=0, final_map=(0, 0), final_pos=(0, 0), badges=0, stats={}, milestones=[],
                stuck_ratio=0.0, goal_desc=sc.goal.desc, cached_tokens=0, elapsed_s=0.0, xfail=sc.xfail)


def _status(passed: bool, xfail: str) -> str:
    if xfail:
        return "XPASS" if passed else "xfail"   # XPASS = bug may be fixed!
    return "PASS" if passed else "FAIL"


def run_all(scenarios: list[Scenario] | None = None, *, verbose: bool = False, trials: int = 1) -> list[dict]:
    """Every scenario, `trials` times each (the model samples at TEMPERATURE > 0, so one run is one noisy sample)."""
    scenarios = scenarios if scenarios is not None else SCENARIOS
    results = [run_scenario(sc, verbose=verbose, trial=t) for sc in scenarios for t in range(1, max(1, trials) + 1)]
    _report(results)
    return results


def exit_code(results: list[dict], strict: bool = False) -> int:
    """Process exit status of an eval run: 1 any FAIL (an xfail that fails is expected, an XPASS is not an error); 3 under `strict` when anything was SKIPPED
    or nothing ran; else 0. (2 = usage error, decided by the CLI.)"""
    if any(r["status"] == "FAIL" for r in results):
        return 1
    if strict and (not results or any(r["status"] == "SKIPPED" for r in results)):
        return 3
    return 0


def pass_rates(results: list[dict]) -> dict[str, tuple[int, int]]:
    """{scenario: (trials that met the goal, trials that ran)} — SKIPPED trials did not run, so they do not count."""
    out: dict[str, list[int]] = {}
    for r in results:
        if r["status"] == "SKIPPED":
            continue
        k, n = out.setdefault(r["scenario"], [0, 0])
        out[r["scenario"]] = [k + (r["status"] in ("PASS", "XPASS")), n + 1]
    return {name: (k, n) for name, (k, n) in out.items()}


def _event_cell(stats: dict) -> str:
    """'3W 1F 2C · 5↑' = battles won / fled / caught, level-ups (the event-stream statistics; was a reward number)."""
    b = stats.get("battles", {})
    return (f"{b.get('won', 0)}W {b.get('fled', 0)}F {b.get('caught', 0)}C · {stats.get('level_ups', 0)}↑"
            if stats else "—")


def _report(results: list[dict]) -> None:
    if not results:
        console.print("[yellow]No scenarios ran.[/]")
        return
    table = Table(title="Eval results", show_lines=False)
    for col in ("scenario", "status", "reason", "steps", "events", "achv",
                "final_map", "stuck", "llm_calls", "tokens", "time"):
        table.add_column(col)
    for r in results:
        style = {"PASS": "green", "XPASS": "yellow bold",
                 "FAIL": "red", "xfail": "dim", "SKIPPED": "yellow"}.get(r["status"], "")
        table.add_row(
            r["scenario"], f"[{style}]{r['status']}[/]" if style else r["status"],
            r["reason"], str(r["steps"]), _event_cell(r.get("stats") or {}), f"{r.get('achievements', 0)} ({r.get('achievement_points', 0)}p)",
            str(tuple(r["final_map"])), f"{r['stuck_ratio']:.0%}",
            str(r["llm_calls"]), str(r["total_tokens"]), f"{r['elapsed_s']}s",
        )
    console.print(table)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = EVAL_DIR / f"{stamp}.json"
    path.write_text(json.dumps({"timestamp": stamp, "results": results}, indent=2))
    console.print(f"[dim]Wrote {path}[/]")

    rates = pass_rates(results)
    if any(n > 1 for _k, n in rates.values()):
        for name, (k, n) in rates.items():
            console.print(f"  {name}: {k}/{n} trials met the goal ({k / n:.0%})")
    passed = sum(r["status"] in ("PASS", "XPASS") for r in results)
    skipped = sum(r["status"] == "SKIPPED" for r in results)
    console.print(f"\n[bold]{passed}/{len(results) - skipped} scenarios met their goal.[/]"
                  + (f" [yellow]{skipped} skipped (could not start).[/]" if skipped else ""))

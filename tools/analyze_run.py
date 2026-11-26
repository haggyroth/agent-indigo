"""Mine a run's trace (`logs/runs/<ts>/run.jsonl`) for the things every watched run gets asked (#364).

    python -m tools.analyze_run [PATH|latest] [--diff OTHER] [--json] [--top N]

PATH is a run directory, a `run.jsonl`, or `latest` (the newest run under logs/runs). The report covers: the timeline (steps, battles by outcome, badges,
blackouts, watchdog stops), tool usage (counts, seconds, the slowest calls), refusals (tool results that read like errors, grouped by text with the call that
caused them), loops (identical tool/args/result runs, `read_game_state` density) and model behaviour (LLM calls per step, tokens, cache hits, empty rounds).
`--diff` puts two runs side by side (two models from the same fixture); `--json` prints the numbers instead.

Everything below `main()` is a pure function over parsed records, so it is unit-tested on a small inline log (tests/test_analyze_run.py).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "logs" / "runs"

# A tool result that reads like the tool refusing or failing (the "unknown move", "can't switch", "trainer battle started" classes of a watched run).
REFUSAL_RE = re.compile(
    r"\b(failed|fail(s|ed)? to|can't|cannot|can not|refus|not recorded|unknown|invalid|not a known|no such|not found|isn't|is not|won't|doesn't|"
    r"does not|trainer battle started|stopped|time limit|no progress|disabled|blocked|don't have|haven't|nothing to)\b", re.I)
# ...but these are ordinary, successful answers that merely contain such words.
_BENIGN_RE = re.compile(r"^(arrived|used |healed|pressed|waited|state saved|state loaded|milestone '.*' recorded|\{)", re.I)


# ── loading ──────────────────────────────────────────────────────────────────────────────────────

def resolve(target: str | None, runs_dir: Path = RUNS) -> Path:
    """The run.jsonl a path / run directory / 'latest' names."""
    if not target or target == "latest":
        dirs = sorted((d for d in runs_dir.glob("*") if (d / "run.jsonl").exists()), key=lambda d: d.name)
        if not dirs:
            raise FileNotFoundError(f"no runs under {runs_dir}")
        return dirs[-1] / "run.jsonl"
    p = Path(target).expanduser()
    if p.is_dir():
        p = p / "run.jsonl"
    if not p.exists() and (runs_dir / target / "run.jsonl").exists():
        p = runs_dir / target / "run.jsonl"
    if not p.exists():
        raise FileNotFoundError(f"no run.jsonl at {target}")
    return p


def load(path: Path) -> list[dict]:
    """Every parseable record, in order (a crashed run may end on a torn line: skipped, not fatal)."""
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


# ── analysis (pure) ──────────────────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """A result with its numbers / coordinates blanked, so 'blocked at (4,7)' and 'blocked at (5,7)' group together."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", text or "")).strip()[:160]


def is_refusal(result: str) -> bool:
    text = (result or "").strip()
    return bool(text) and not _BENIGN_RE.match(text) and bool(REFUSAL_RE.search(text[:400]))


def timeline(recs: list[dict]) -> dict:
    ticks = [r for r in recs if r.get("kind") == "tick"]
    evs = Counter(r.get("ev") for r in recs if r.get("kind") == "ev")
    outcomes = Counter()
    for r in recs:
        if r.get("kind") == "ev" and r.get("ev") == "battle_end":
            m = re.search(r"\b(won|lost|fled|caught|drew|foe fled|teleported)\b", r.get("text", ""))
            outcomes[m.group(1) if m else "other"] += 1
    start = next((r for r in recs if r.get("kind") == "start"), {})
    end = next((r for r in reversed(recs) if r.get("kind") == "end"), {})
    return {
        "steps": ticks[-1].get("step") if ticks else 0, "seconds": round(max((r.get("t", 0) for r in recs), default=0), 1),
        "start_badges": start.get("badges"), "end_badges": end.get("badges", ticks[-1].get("badges") if ticks else None),
        "battles": dict(outcomes), "battle_starts": evs.get("battle_start", 0), "badges_earned": evs.get("badge", 0), "new_towns": evs.get("town", 0),
        "blackouts": evs.get("blackout", 0), "checkpoints": evs.get("checkpoint", 0), "catches": evs.get("catch", 0), "level_ups": evs.get("level_up", 0),
        "watchdog_stops": sum(1 for r in recs if r.get("kind") == "watchdog"),
        "end_reason": end.get("reason"), "stuck_ratio": end.get("stuck_ratio"),
    }


def tool_usage(recs: list[dict], top: int = 5) -> dict:
    tools = [r for r in recs if r.get("kind") == "tool"]
    per: dict[str, list[float]] = defaultdict(list)
    for r in tools:
        per[r.get("name", "?")].append(float(r.get("secs") or 0))
    rows = sorted(({"tool": n, "calls": len(s), "seconds": round(sum(s), 1), "mean": round(sum(s) / len(s), 2)} for n, s in per.items()),
                  key=lambda x: -x["seconds"])
    slow = sorted(tools, key=lambda r: -float(r.get("secs") or 0))[:top]
    return {"total_calls": len(tools), "per_tool": rows,
            "slowest": [{"tool": r.get("name"), "args": (r.get("args") or "")[:80], "secs": round(float(r.get("secs") or 0), 1), "t": r.get("t"),
                         "result": (r.get("result") or "")[:100]} for r in slow]}


def refusals(recs: list[dict], top: int = 10) -> dict:
    """Tool results that look like errors / refusals, grouped by text; each group names the tools that caused it."""
    groups: dict[str, dict] = {}
    n_tools = 0
    for r in recs:
        if r.get("kind") != "tool":
            continue
        n_tools += 1
        res = r.get("result") or ""
        if not is_refusal(res):
            continue
        g = groups.setdefault(_norm(res), {"text": _norm(res), "count": 0, "tools": Counter(), "example": res[:200]})
        g["count"] += 1
        g["tools"][r.get("name", "?")] += 1
    rows = sorted(groups.values(), key=lambda g: -g["count"])
    total = sum(g["count"] for g in rows)
    return {"total": total, "share_of_calls": round(total / n_tools, 3) if n_tools else 0.0,
            "groups": [{**g, "tools": dict(g["tools"])} for g in rows[:top]]}


def loops(recs: list[dict], min_run: int = 3) -> dict:
    """Runs of >= min_run consecutive identical (tool, args, result), and how much of the call stream is read_game_state."""
    tools = [r for r in recs if r.get("kind") == "tool"]
    runs, i = [], 0
    while i < len(tools):
        key = (tools[i].get("name"), tools[i].get("args"), tools[i].get("result"))
        j = i
        while j + 1 < len(tools) and (tools[j + 1].get("name"), tools[j + 1].get("args"), tools[j + 1].get("result")) == key:
            j += 1
        if j - i + 1 >= min_run:
            runs.append({"tool": key[0], "args": (key[1] or "")[:60], "result": (key[2] or "")[:100], "length": j - i + 1, "at_t": tools[i].get("t")})
        i = j + 1
    reads = sum(1 for r in tools if r.get("name") == "read_game_state")
    return {"repeats": sorted(runs, key=lambda x: -x["length"]), "read_game_state_calls": reads,
            "read_game_state_per_100_calls": round(100 * reads / len(tools), 1) if tools else 0.0}


def model_behaviour(recs: list[dict]) -> dict:
    llm = [r for r in recs if r.get("kind") == "llm"]
    ticks = [r for r in recs if r.get("kind") == "tick"]
    prompt = sum(r.get("prompt_tokens") or 0 for r in llm)
    completion = sum(r.get("completion_tokens") or 0 for r in llm)
    cached = sum(r.get("cached_tokens") or 0 for r in llm)
    empty = sum(1 for r in llm if not (r.get("content") or "").strip() and not r.get("tool_calls"))
    return {"llm_calls": len(llm), "calls_per_step": round(len(llm) / len(ticks), 2) if ticks else None, "prompt_tokens": prompt, "completion_tokens": completion,
            "cache_hit_rate": round(cached / prompt, 3) if prompt else 0.0, "empty_rounds": empty,
            "max_round": max((r.get("round") or 0 for r in llm), default=0)}


def analyze(recs: list[dict], top: int = 5) -> dict:
    return {"timeline": timeline(recs), "tools": tool_usage(recs, top), "refusals": refusals(recs, top * 2), "loops": loops(recs),
            "model": model_behaviour(recs)}


# the metrics a diff puts side by side: (label, getter)
_DIFF_ROWS = [
    ("steps", lambda a: a["timeline"]["steps"]), ("seconds", lambda a: a["timeline"]["seconds"]), ("end reason", lambda a: a["timeline"]["end_reason"]),
    ("badges at end", lambda a: a["timeline"]["end_badges"]), ("battles", lambda a: sum(a["timeline"]["battles"].values())),
    ("battles lost", lambda a: a["timeline"]["battles"].get("lost", 0)), ("blackouts", lambda a: a["timeline"]["blackouts"]),
    ("watchdog stops", lambda a: a["timeline"]["watchdog_stops"]), ("stuck ratio", lambda a: a["timeline"]["stuck_ratio"]),
    ("tool calls", lambda a: a["tools"]["total_calls"]), ("refusals", lambda a: a["refusals"]["total"]),
    ("refusal share of calls", lambda a: a["refusals"]["share_of_calls"]), ("identical-call runs", lambda a: len(a["loops"]["repeats"])),
    ("read_game_state / 100 calls", lambda a: a["loops"]["read_game_state_per_100_calls"]), ("LLM calls", lambda a: a["model"]["llm_calls"]),
    ("LLM calls / step", lambda a: a["model"]["calls_per_step"]), ("prompt tokens", lambda a: a["model"]["prompt_tokens"]),
    ("completion tokens", lambda a: a["model"]["completion_tokens"]), ("cache hit rate", lambda a: a["model"]["cache_hit_rate"]),
    ("empty rounds", lambda a: a["model"]["empty_rounds"]),
]


def diff(a: dict, b: dict) -> list[tuple[str, object, object]]:
    return [(label, get(a), get(b)) for label, get in _DIFF_ROWS]


# ── rendering ────────────────────────────────────────────────────────────────────────────────────

def render(report: dict, title: str = "") -> str:
    t, tools, ref, lp, m = report["timeline"], report["tools"], report["refusals"], report["loops"], report["model"]
    out = [f"== {title or 'run'} =="]
    out.append(f"Timeline: {t['steps']} steps in {t['seconds']} s · ended: {t['end_reason'] or 'no end record (crashed / still running)'} · badges {t['start_badges']} -> {t['end_badges']}")
    out.append(f"  battles {t['battle_starts']} started, outcomes {t['battles'] or '—'} · catches {t['catches']} · level-ups {t['level_ups']} · new towns {t['new_towns']}"
               f" · blackouts {t['blackouts']} · checkpoints {t['checkpoints']} · watchdog stops {t['watchdog_stops']} · stuck ratio {t['stuck_ratio']}")
    out.append(f"\nTools: {tools['total_calls']} calls")
    for r in tools["per_tool"][:12]:
        out.append(f"  {r['tool']:<20} {r['calls']:>5} calls  {r['seconds']:>8} s  (mean {r['mean']} s)")
    if tools["slowest"]:
        out.append("  slowest:")
        for s in tools["slowest"]:
            out.append(f"    {s['secs']:>7} s  {s['tool']}({s['args']}) at t={s['t']}  -> {s['result']}")
    out.append(f"\nRefusals: {ref['total']} ({ref['share_of_calls']:.1%} of calls)")
    for g in ref["groups"]:
        out.append(f"  {g['count']:>4}×  {g['text']}   [{', '.join(f'{k}×{v}' for k, v in g['tools'].items())}]")
    out.append(f"\nLoops: {len(lp['repeats'])} runs of identical calls · read_game_state {lp['read_game_state_calls']} calls ({lp['read_game_state_per_100_calls']}/100)")
    for r in lp["repeats"][:8]:
        out.append(f"  {r['length']:>4}×  {r['tool']}({r['args']}) -> {r['result']}   (from t={r['at_t']})")
    out.append(f"\nModel: {m['llm_calls']} LLM calls ({m['calls_per_step']} per step, deepest round {m['max_round']}) · {m['prompt_tokens']} prompt + {m['completion_tokens']} completion tokens"
               f" · cache hit {m['cache_hit_rate']:.0%} · {m['empty_rounds']} empty rounds")
    return "\n".join(out)


def render_diff(rows, name_a: str, name_b: str) -> str:
    w = max(len(r[0]) for r in rows)
    lines = [f"{'':<{w}}  {name_a:>20}  {name_b:>20}"]
    lines += [f"{label:<{w}}  {str(x):>20}  {str(y):>20}" for label, x, y in rows]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.analyze_run", description="Analyze a run's run.jsonl.")
    ap.add_argument("run", nargs="?", default="latest", help="a run directory, a run.jsonl, a run name under logs/runs, or 'latest' (default)")
    ap.add_argument("--diff", metavar="OTHER", help="compare with another run")
    ap.add_argument("--json", action="store_true", help="print the numbers as JSON")
    ap.add_argument("--top", type=int, default=5, help="how many slowest calls / refusal groups to list")
    args = ap.parse_args(argv)
    try:
        path = resolve(args.run)
        report = analyze(load(path), args.top)
        other = analyze(load(resolve(args.diff)), args.top) if args.diff else None
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"run": str(path), "report": report, **({"diff_against": str(resolve(args.diff)), "other": other, "diff": diff(report, other)} if other else {})},
                         indent=2, default=str))
    elif other:
        print(render_diff(diff(report, other), path.parent.name, resolve(args.diff).parent.name))
    else:
        print(render(report, str(path.parent.name)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

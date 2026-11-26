"""tools/analyze_run: the questions every watched run gets asked, as pure functions over a small inline log (#364)."""
import json

import pytest

from tools import analyze_run as ar


def _tool(t, name, args="{}", result="ok", secs=1.0):
    return {"t": t, "kind": "tool", "name": name, "args": args, "result": result, "secs": secs}


def _llm(n, content="", tool_calls=None, prompt=1000, completion=50, cached=800, rnd=0):
    return {"t": n, "kind": "llm", "n": n, "round": rnd, "prompt_tokens": prompt, "completion_tokens": completion, "cached_tokens": cached,
            "content": content, "tool_calls": tool_calls or []}


LOG = [
    {"t": 0, "kind": "start", "badges": 1, "map": [3, 0]},
    {"t": 1, "kind": "ev", "ev": "battle_start", "text": "wild Rattata L3"},
    {"t": 3, "kind": "ev", "ev": "battle_end", "text": "battle over: won (Rattata)"},
    {"t": 4, "kind": "ev", "ev": "battle_end", "text": "battle over: fled"},
    {"t": 5, "kind": "ev", "ev": "badge", "text": "badge"},
    {"t": 6, "kind": "ev", "ev": "blackout", "text": "BLACKOUT"},
    _llm(1, tool_calls=[["go_to", "{}"]]), _llm(2, content="", tool_calls=[]), _llm(3, content="done", tool_calls=[]),
    _tool(10, "go_to", '{"destination":"Pewter City"}', "Arrived at Pewter City.", 8.0),
    _tool(11, "use_move", '{"move":"Vine Whip"}', "'Vine Whip' is not a known move for the active Pokémon right now. Its moves: Tackle (PP 35)", 2.0),
    _tool(12, "use_move", '{"move":"Vine Whip"}', "'Vine Whip' is not a known move for the active Pokémon right now. Its moves: Tackle (PP 34)", 2.0),
    _tool(13, "go_to", '{"destination":"Gym"}', "A TRAINER battle started at Route 3 on the way to Gym (you can't flee it).", 30.0),
    _tool(14, "read_game_state"), _tool(15, "read_game_state"), _tool(16, "read_game_state"),
    _tool(17, "press_button", '{"button":"A"}', "Pressed A × 1", 0.1),
    {"t": 18, "kind": "watchdog", "tool": "grind", "reason": "no progress"},
    {"t": 19, "kind": "tick", "step": 1, "badges": 1},
    {"t": 20, "kind": "tick", "step": 2, "badges": 2},
    {"t": 21, "kind": "end", "reason": "max_steps", "badges": 2, "stuck_ratio": 0.25},
]


def test_timeline():
    t = ar.timeline(LOG)
    assert t["steps"] == 2 and t["battles"] == {"won": 1, "fled": 1} and t["blackouts"] == 1 and t["watchdog_stops"] == 1
    assert t["start_badges"] == 1 and t["end_badges"] == 2 and t["end_reason"] == "max_steps" and t["stuck_ratio"] == 0.25 and t["badges_earned"] == 1


def test_tool_usage_counts_seconds_and_the_slowest():
    u = ar.tool_usage(LOG, top=2)
    assert u["total_calls"] == 8
    top = u["per_tool"][0]
    assert top["tool"] == "go_to" and top["calls"] == 2 and top["seconds"] == 38.0
    assert [s["secs"] for s in u["slowest"]] == [30.0, 8.0] and u["slowest"][0]["tool"] == "go_to"


def test_refusals_group_by_text_with_numbers_blanked_and_name_the_tool():
    r = ar.refusals(LOG)
    assert r["total"] == 3
    top = r["groups"][0]
    assert top["count"] == 2 and top["tools"] == {"use_move": 2} and "PP #" in top["text"]          # (PP 35) and (PP 34) are one group
    assert any("TRAINER battle started" in g["text"] for g in r["groups"])
    assert r["share_of_calls"] == round(3 / 8, 3)


def test_ordinary_answers_are_not_refusals():
    for ok in ("Arrived at Pewter City.", "Used Tackle. [foe 3/20]", "Pressed A × 1", "Healed the party.", '{"context": "OVERWORLD"}', ""):
        assert not ar.is_refusal(ok), ok
    for bad in ("You can't switch — you're trapped", "Tool walk_to failed: boom", "A TRAINER battle started at Route 3", "Not recorded: the game does not confirm"):
        assert ar.is_refusal(bad), bad


def test_loops_find_identical_runs_and_read_state_density():
    recs = [_tool(i, "use_move", '{"move":"Growl"}', "Used Growl.") for i in range(4)] + [_tool(9, "go_to"), _tool(10, "read_game_state")]
    lp = ar.loops(recs)
    assert lp["repeats"][0]["length"] == 4 and lp["repeats"][0]["tool"] == "use_move"
    assert lp["read_game_state_calls"] == 1 and lp["read_game_state_per_100_calls"] == round(100 / 6, 1)
    assert ar.loops([_tool(1, "a"), _tool(2, "a")])["repeats"] == []                           # two is not a loop


def test_model_behaviour():
    m = ar.model_behaviour(LOG)
    assert m["llm_calls"] == 3 and m["calls_per_step"] == 1.5 and m["prompt_tokens"] == 3000 and m["cache_hit_rate"] == 0.8
    assert m["empty_rounds"] == 1                                                                # round 2: no content and no tool call


def test_analyze_render_and_diff_work_together():
    a = ar.analyze(LOG)
    text = ar.render(a, "run A")
    for needle in ("Timeline: 2 steps", "Tools: 8 calls", "Refusals: 3", "Loops:", "Model: 3 LLM calls"):
        assert needle in text
    b = ar.analyze(LOG[:10])
    rows = dict((label, (x, y)) for label, x, y in ar.diff(a, b))
    assert rows["tool calls"] == (8, 1) and rows["steps"][0] == 2
    assert "tool calls" in ar.render_diff(ar.diff(a, b), "A", "B")


def test_an_empty_or_torn_log_does_not_crash(tmp_path):
    p = tmp_path / "run.jsonl"
    p.write_text('{"kind": "start"}\n{"kind": "tool", "name": "go_to", "secs": 1\n')             # the second line is torn (crashed mid-write)
    recs = ar.load(p)
    assert len(recs) == 1
    assert ar.analyze(recs)["tools"]["total_calls"] == 0
    assert ar.analyze([])["timeline"]["steps"] == 0


def test_resolve_latest_dir_and_name(tmp_path):
    for name in ("20261101-000000", "20261102-000000"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "run.jsonl").write_text("{}\n")
    assert ar.resolve("latest", tmp_path).parent.name == "20261102-000000"
    assert ar.resolve(str(tmp_path / "20261101-000000")).name == "run.jsonl"
    assert ar.resolve("20261101-000000", tmp_path).parent.name == "20261101-000000"
    with pytest.raises(FileNotFoundError):
        ar.resolve("nope", tmp_path)


def test_cli_text_json_and_diff(tmp_path, capsys):
    for name in ("a", "b"):
        d = tmp_path / name
        d.mkdir()
        (d / "run.jsonl").write_text("\n".join(json.dumps(r) for r in LOG))
    assert ar.main([str(tmp_path / "a")]) == 0
    assert "Timeline" in capsys.readouterr().out
    assert ar.main([str(tmp_path / "a"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["tools"]["total_calls"] == 8
    assert ar.main([str(tmp_path / "a"), "--diff", str(tmp_path / "b")]) == 0
    assert "tool calls" in capsys.readouterr().out
    assert ar.main([str(tmp_path / "missing")]) == 2

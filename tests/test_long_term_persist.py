"""Persistence robustness for LongTermMemory (#62).

progress.json is the only cross-session memory. save() must be atomic (a crash
mid-write must not truncate it) and _load() must tolerate a corrupt file instead
of crashing startup.
"""
import json
import memory.long_term as lt


def make_ltm(monkeypatch, tmp_path):
    monkeypatch.setattr(lt, "PROGRESS_PATH", tmp_path / "progress.json")
    return lt.LongTermMemory()


def test_save_then_reload_roundtrips(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    ltm.data["badges_earned"] = 3
    ltm.data["starter"] = "Bulbasaur"
    ltm.save()
    reloaded = lt.LongTermMemory()
    assert reloaded.data["badges_earned"] == 3
    assert reloaded.data["starter"] == "Bulbasaur"


def test_save_leaves_no_temp_file(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    ltm.save()
    # The atomic write renames the temp into place — nothing left behind.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_save_is_valid_json_on_disk(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    ltm.data["towns_visited"] = ["Pallet Town"]
    ltm.save()
    on_disk = json.loads((tmp_path / "progress.json").read_text())
    assert on_disk["towns_visited"] == ["Pallet Town"]


def test_corrupt_file_recovers_to_defaults(monkeypatch, tmp_path):
    path = tmp_path / "progress.json"
    path.write_text('{"badges_earned": 3, TRUNCATED')  # invalid JSON
    monkeypatch.setattr(lt, "PROGRESS_PATH", path)
    ltm = lt.LongTermMemory()          # must not raise
    assert ltm.data["badges_earned"] == 0        # fell back to DEFAULTS
    assert ltm.data["milestones"] == []


def test_corrupt_file_is_renamed_aside(monkeypatch, tmp_path):
    path = tmp_path / "progress.json"
    path.write_text("not json at all")
    monkeypatch.setattr(lt, "PROGRESS_PATH", path)
    lt.LongTermMemory()
    # The bad file is moved to a .corrupt-*.bak sibling, not silently deleted.
    baks = list(tmp_path.glob("progress.json.corrupt-*.bak"))
    assert len(baks) == 1
    assert baks[0].read_text() == "not json at all"


def test_recovered_instance_can_save_again(monkeypatch, tmp_path):
    path = tmp_path / "progress.json"
    path.write_text("}{ broken")
    monkeypatch.setattr(lt, "PROGRESS_PATH", path)
    ltm = lt.LongTermMemory()
    ltm.data["badges_earned"] = 1
    ltm.save()                          # writing over the (renamed-away) path works
    assert json.loads(path.read_text())["badges_earned"] == 1


# ── every key the code writes survives a reload (#371) ──────────────────────────────────────────

def test_feature_keys_round_trip(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    ltm.data["gym_losses"] = {"10/16": 88}
    ltm.data["hidden_taken"] = ["3/27/15/7"]
    ltm.data["pc_visited"] = ["3,3"]
    ltm.data["shop_broke_at"] = 500
    ltm.save()
    r = lt.LongTermMemory()
    assert r.data["gym_losses"] == {"10/16": 88}
    assert r.data["hidden_taken"] == ["3/27/15/7"]
    assert r.data["pc_visited"] == ["3,3"]
    assert r.data["shop_broke_at"] == 500


def test_undeclared_key_is_kept_and_retired_key_is_dropped(monkeypatch, tmp_path):
    path = tmp_path / "progress.json"
    path.write_text(json.dumps({"badges_earned": 2, "some_new_feature": [1], "key_items_obtained": 3}))
    monkeypatch.setattr(lt, "PROGRESS_PATH", path)
    ltm = lt.LongTermMemory()
    assert ltm.data["some_new_feature"] == [1]
    assert "key_items_obtained" not in ltm.data


def test_defaults_do_not_alias_between_instances(monkeypatch, tmp_path):
    a = make_ltm(monkeypatch, tmp_path)
    a.data["gym_losses"]["x"] = 1
    a.data["hidden_taken"].append("t")
    assert lt.DEFAULTS["gym_losses"] == {} and lt.DEFAULTS["hidden_taken"] == []


def _ltm_keys_used_in_source():
    """String keys the non-test code reads/writes on `ltm.data` (directly or via a local alias `d = ….ltm.data`)."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    found: dict[str, str] = {}
    for py in root.rglob("*.py"):
        rel = py.relative_to(root)
        if rel.parts[0] in ("tests", ".venv", "venv", "logs", "saves") or any(p.startswith(".") for p in rel.parts):
            continue
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue

        def is_ltm_data(n):
            return (isinstance(n, ast.Attribute) and n.attr == "data" and
                    ((isinstance(n.value, ast.Attribute) and n.value.attr == "ltm") or (isinstance(n.value, ast.Name) and n.value.id in ("ltm", "l"))))
        def is_data_in(n, aliases):
            return is_ltm_data(n) or (isinstance(n, ast.Name) and n.id in aliases)
        # Aliases (`d = t.ltm.data`) are scoped to their own function: another function's `d` is unrelated.
        def walk_scope(scope):
            """ast.walk limited to this scope's own statements (nested functions are scanned as scopes of their own)."""
            todo = list(ast.iter_child_nodes(scope))
            while todo:
                n = todo.pop()
                yield n
                if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                    todo.extend(ast.iter_child_nodes(n))
        scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for scope in scopes:
            aliases = {t.id for a in walk_scope(scope) if isinstance(a, ast.Assign) and is_ltm_data(a.value)
                       for t in a.targets if isinstance(t, ast.Name)}
            for n in walk_scope(scope):
                if isinstance(n, ast.Subscript) and is_data_in(n.value, aliases) and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
                    found.setdefault(n.slice.value, f"{rel}:{n.lineno}")
                elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("get", "setdefault", "pop")
                      and is_data_in(n.func.value, aliases) and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                    found.setdefault(n.args[0].value, f"{rel}:{n.lineno}")
    return found


def test_every_ltm_key_the_code_uses_is_declared_in_defaults():
    used = _ltm_keys_used_in_source()
    assert used, "the scan found no ltm.data keys — it is broken"
    missing = {k: where for k, where in used.items() if k not in lt.DEFAULTS}
    assert not missing, f"keys used on ltm.data but absent from memory.long_term.DEFAULTS: {missing}"

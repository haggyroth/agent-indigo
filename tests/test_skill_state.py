"""Skill state is declared in one place (agent/skills/state.py), never created by a stray assignment or read with a getattr fallback."""
import ast
from pathlib import Path

from agent.skills.state import SkillState, lazy

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted((ROOT / "agent" / "skills").glob("*.py")) + [ROOT / "agent" / "lm_studio_client.py"]
DECLARED = {n for n in vars(SkillState) if not n.startswith("__")}
# Set in AgentClient.__init__ (not skill state): connections, the message list, spend counters.
INIT_OWNED = {"llm", "mgba", "reader", "ltm", "tilemap", "messages", "llm_calls", "total_prompt_tokens", "total_completion_tokens",
              "run_log"}


def _tree(path):
    return ast.parse(path.read_text())


def test_no_skill_reaches_into_dict_or_getattr_fallbacks_for_declared_state():
    bad = []
    for p in FILES:
        if p.name == "state.py":
            continue
        for n in ast.walk(_tree(p)):
            if isinstance(n, ast.Attribute) and n.attr == "__dict__" and isinstance(n.value, ast.Name) and n.value.id == "self":
                bad.append(f"{p.name}:{n.lineno} self.__dict__")
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("getattr", "hasattr")
                    and n.args and isinstance(n.args[0], ast.Name) and n.args[0].id == "self"
                    and len(n.args) > 1 and isinstance(n.args[1], ast.Constant) and n.args[1].value in DECLARED):
                bad.append(f"{p.name}:{n.lineno} {n.func.id}(self, {n.args[1].value!r})")
    assert not bad, "read declared skill state as a plain attribute:\n  " + "\n  ".join(bad)


def test_every_attribute_a_skill_assigns_on_self_is_declared():
    methods, stores = set(), {}
    for p in FILES:
        if p.name == "state.py":
            continue
        t = _tree(p)
        funcs = [n for n in ast.walk(t) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        methods.update(f.name for f in funcs)
        for fn in funcs:
            if fn.name == "__init__":
                continue
            for n in ast.walk(fn):
                if (isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store) and isinstance(n.value, ast.Name)
                        and n.value.id == "self"):
                    stores.setdefault(n.attr, f"{p.name}:{n.lineno}")
    undeclared = {a: w for a, w in stores.items() if a not in DECLARED | INIT_OWNED and a not in methods}
    assert not undeclared, f"declare these in agent/skills/state.py: {undeclared}"


def test_per_instance_dicts_are_not_shared_between_clients():
    class A(SkillState):
        pass
    a, b = A(), A()
    a._trainer_losses[(3, 0)] = 2
    assert b._trainer_losses == {} and a._trainer_losses == {(3, 0): 2} and isinstance(vars(SkillState)["_edge_fail"], lazy)

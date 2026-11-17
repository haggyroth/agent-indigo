"""No new dead code (#214): every function / method / class in the hand-written runtime packages must be referenced
somewhere outside its own definition (other runtime code, a tool script, or the eval harness). Tests don't count —
code that only a test calls is dead code with a test. Generated tables (tools/gen_*.py output) are exempt."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ("agent", "game", "knowledge", "memory", "evals")
GENERATED = {"map_regions.py", "map_graph.py", "species_data.py", "move_data.py", "move_effects.py", "base_stats.py",
             "growth_data.py", "gym_teams.py", "wild_locations.py", "encounters.py", "evolutions.py",
             "tmhm_learnsets.py", "puzzle_tiles.py", "_mgba_native.py"}
# Deliberate small public APIs kept for symmetry / the eval DSL / tests of documented behaviour.
ALLOW = {
    "has_milestone", "all_of", "any_of",            # evals.goals combinators
    "write16", "write32",                           # low-level memory writes (write16 is used by the live harness)
    "decode_gen3_string",                           # charset helper with tests
    "is_fainted", "anything_changed",               # small dataclass conveniences
}


def _sources(dirs, skip_generated):
    for d in dirs:
        for p in (ROOT / d).rglob("*.py"):
            if "__pycache__" in p.parts or (skip_generated and p.name in GENERATED):
                continue
            yield p


def test_no_unreferenced_functions_methods_or_classes():
    corpus = "\n".join(p.read_text() for p in [*_sources(SCAN + ("tools",), False), ROOT / "main.py", ROOT / "config.py"])
    dead = []
    for p in _sources(SCAN, True):
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
                if name.startswith("__") or name == "main" or name in ALLOW:
                    continue
                if len(re.findall(rf"\b{re.escape(name)}\b", corpus)) <= 1:
                    dead.append(f"{p.relative_to(ROOT)}:{node.lineno} {name}")
    assert not dead, "unreferenced (delete, or add to ALLOW with a reason):\n  " + "\n  ".join(dead)

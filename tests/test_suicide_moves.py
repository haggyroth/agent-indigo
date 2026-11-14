"""Self-Destruct / Explosion faint their user (no XP) — they must never beat a weaker attack."""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from knowledge.battle import battle_summary      # noqa: E402
from knowledge.leafgreen_data import SUICIDE_MOVES   # noqa: E402


def test_suicide_moves_set():
    assert SUICIDE_MOVES == {"Self-Destruct", "Explosion"}


def test_best_move_never_picks_selfdestruct_over_a_weaker_attack():
    # Geodude: Self-Destruct (200) out-powers Tackle (35) / Rock Throw (50) — the 2026-11-14 loop.
    names = ["Tackle", "Self-Destruct", "Rock Throw", "Defense Curl"]
    pp = [35, 5, 15, 40]
    assert AgentClient._best_damaging_move(names, pp, ("ROC", "GRO"), ("NOR",)) == "Rock Throw"


def test_best_move_skips_explosion_even_with_no_type_info():
    assert AgentClient._best_damaging_move(["Explosion", "Tackle", "", ""], [5, 35, 0, 0]) == "Tackle"


def test_best_move_none_when_only_a_suicide_move_attacks():
    # None routes the caller to _no_attack_turn (switch / flee), never to blowing the mon up.
    assert AgentClient._best_damaging_move(["Self-Destruct", "Defense Curl", "", ""], [5, 40, 0, 0]) is None


def test_battle_summary_never_suggests_a_suicide_move():
    out = battle_summary(["Self-Destruct", "Tackle", "", ""], "Rattata", 1.0, [5, 35, 0, 0], ("ROC",))
    assert "Best move: Tackle" in out
    assert "Best move: Self-Destruct" not in out
    assert "FAINT YOUR OWN" in out


def test_use_move_refuses_selfdestruct_when_another_attack_exists(monkeypatch):
    from types import SimpleNamespace
    import game.menu
    from game.state import GameContext
    monkeypatch.setattr(game.menu, "forced_party_screen", lambda *a: False)
    c = AgentClient.__new__(AgentClient)
    c.mgba = SimpleNamespace()
    c.reader = SimpleNamespace(read_party=lambda: [SimpleNamespace(move_names=[], pp=[], species_id=74)],
                               detect_context=lambda: GameContext.IN_BATTLE)
    c._active_moves_view = lambda: ([1, 2], ["Self-Destruct", "Tackle"], [5, 35], None, 0)
    out = c._use_move("Self-Destruct")
    assert out.startswith("Refused") and "Tackle" in out

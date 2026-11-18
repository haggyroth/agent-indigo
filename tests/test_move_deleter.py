"""forget_move's refusals (#273, no emulator): the party's last HM copy is protected, unknown moves and one-move Pokémon are reported, and the HM block
in teach_move points at the Move Deleter."""
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402


def mon(name, moves):
    return NS(species_name=name, nickname="", move_names=moves, species_id=1, level=20, current_hp=20, max_hp=20)


def client(party):
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_party=lambda: party, detect_context=lambda: NS(name="OVERWORLD"))
    c._go_to = lambda *a, **k: pytest.fail("should have refused before travelling")
    return c


def test_the_last_copy_of_an_hm_is_protected_unless_forced():
    party = [mon("Venusaur", ["Razor Leaf", "Tackle", "", ""]), mon("Pidgeotto", ["Cut", "Surf", "Gust", "Tackle"])]
    out = client(party)._forget_move("Pidgeotto", "Cut")
    assert "only one who knows Cut" in out and "force=true" in out


def test_an_hm_known_by_someone_else_is_not_protected():
    party = [mon("Venusaur", ["Cut", "Tackle", "", ""]), mon("Pidgeotto", ["Cut", "Surf", "Gust", "Tackle"])]
    c = client(party)
    c._go_to = lambda *a, **k: "Blocked reaching Move Deleter's House: gated"        # got past the checks: it tried to travel
    c.reader.read_current_map = lambda: (3, 7)
    assert "Can't reach the Move Deleter" in c._forget_move("Pidgeotto", "Cut")


def test_unknown_move_and_only_move_are_reported_before_any_travel():
    party = [mon("Pidgeotto", ["Cut", "Surf", "Gust", "Tackle"]), mon("Magikarp", ["Splash", "", "", ""])]
    c = client(party)
    assert "doesn't know" in c._forget_move("Pidgeotto", "Fly")
    assert "last move" in c._forget_move("Magikarp", "Splash")


def test_the_hm_block_in_teach_move_points_at_the_deleter():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "agent" / "skills" / "tmhm.py").read_text()
    assert "forget_move('{who}', '{forget}')" in src

"""Readiness: the fundamentals (heal/PP, restock, catch, train, level) that go_to must not quietly replace."""
from types import SimpleNamespace

import pytest

from game.state import GameContext, PokemonStatus
from knowledge.readiness import assess, blocking, next_gym_target, render


def mon(level, hp=40, mx=40, moves=("Tackle",), pp=(20,), name="Bulbasaur", nick=""):
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=mx, status="healthy", species_id=1,
                         species_name=name, nickname=nick, move_names=list(moves), pp=list(pp))


def codes(needs):
    return [n.code for n in needs]


def test_a_hurt_lead_or_a_faint_is_a_must_heal():
    assert codes(blocking(assess([mon(14, hp=10), mon(14)], 9, 5, 0, ["Brock"]))) == ["heal"]
    assert codes(blocking(assess([mon(14), mon(14, hp=0)], 9, 5, 0, ["Brock"]))) == ["heal"]


def test_attack_pp_nearly_gone_is_a_must_heal_status_moves_dont_count():
    needs = assess([mon(14, moves=("Tackle", "Growl"), pp=(1, 40))], 9, 5, 0, ["Brock"])
    assert codes(blocking(needs)) == ["heal"] and "PP" in blocking(needs)[0].text
    needs = assess([mon(14, moves=("Tackle", "Growl"), pp=(0, 40))], 9, 5, 0, ["Brock"])
    assert "no Pokémon has attacking PP left" in blocking(needs)[0].text


def test_shop_catch_train_and_level_are_advice_not_blockers():
    needs = assess([mon(10), mon(2)], balls=1, potions=0, money=2000, gyms_beaten=[])
    assert set(codes(needs)) == {"shop", "catch", "train", "level", "hunt"} and not blocking(needs)   # hunt: Brock's gym


def test_shop_advice_needs_money_and_a_healthy_ready_team_is_quiet(monkeypatch):
    import knowledge.team as team_mod
    monkeypatch.setattr(team_mod, "gaps", lambda *a, **k: [])        # team composition is covered in test_team.py
    assert "shop" not in codes(assess([mon(14)] * 4, 0, 0, 100, ["Brock"]))
    team = [mon(24), mon(22), mon(21), mon(21)]
    assert assess(team, 9, 5, 800, ["Brock", "Misty"]) == []
    assert render([]) == ""


def test_next_gym_target_is_one_under_the_ace():
    assert next_gym_target([]) == ("Brock", 13)
    assert next_gym_target(["Brock"]) == ("Misty", 20)


def test_render_marks_must_items():
    text = render(assess([mon(14, hp=5)], 9, 5, 0, ["Brock"]))
    assert text.startswith("READINESS") and "⛔ heal()" in text


# ── the model-facing go_to ───────────────────────────────────────────────────────
def _client(needs, ctx=GameContext.OVERWORLD):
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(detect_context=lambda: ctx)
    c._readiness = lambda: needs
    c.calls = []
    c._go_to = lambda d, **kw: c.calls.append(d) or "Arrived at X."
    return c


def test_go_to_refuses_to_start_when_the_party_must_heal():
    from knowledge.readiness import Need
    c = _client([Need("must", "heal", "heal() — Bulbasaur is at 4/40 HP")])
    out = c._go_to_tool("Route 2")
    assert "Not travelling yet" in out and "heal()" in out and c.calls == []
    assert c._go_to_tool("Route 2", force=True).startswith("Arrived") and c.calls == ["Route 2"]


def test_go_to_still_goes_to_a_center_or_mart_when_hurt_and_appends_reminders():
    from knowledge.readiness import Need
    c = _client([Need("must", "heal", "x"), Need("should", "catch", "only 1 Pokémon — catch more")])
    out = c._go_to_tool("Pokemon Center")
    assert out.startswith("Arrived") and "catch more" in out and c.calls == ["Pokemon Center"]

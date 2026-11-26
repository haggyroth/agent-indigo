"""quest('sweep <area>') against a fake game (#366): what it picks next, what it hands back, where it stops."""
from types import SimpleNamespace

import pytest

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402
from game.state import GameContext  # noqa: E402
from knowledge.area_sweeps import AREAS  # noqa: E402

FOREST = AREAS["Viridian Forest"]
MAP = FOREST["maps"][0]


class Game:
    """A tiny world for one area: flags set as the driver 'picks up' or 'beats' things."""
    def __init__(self, beaten=(), taken=(), hp=1.0):
        self.flags = set(beaten) | set(taken)
        self.ctx = GameContext.OVERWORLD
        self.map = MAP
        self.pos = (10, 10)
        self.hp = hp
        self.log = []


def _client(g: Game, battle_on_trainer=True):
    c = AgentClient.__new__(AgentClient)
    mon = SimpleNamespace(max_hp=40, hp_percent=g.hp, nickname="Sparky", species_name="PIKACHU")
    c.reader = SimpleNamespace(read_flag=lambda f: f in g.flags, detect_context=lambda: g.ctx, read_party=lambda: [mon],
                               read_current_map=lambda: g.map, read_player_pos=lambda: g.pos)
    c.mgba = SimpleNamespace(tap=lambda b: None, tick=lambda n=1: None)
    pos = {f: (x, y) for f, _m, x, y in FOREST["item_pos"] + FOREST["trainer_pos"]}
    flag_at = {v: k for k, v in pos.items()}

    def pick_ball(x, y):
        g.log.append(("ball", x, y))
        g.flags.add(flag_at[(x, y)])
        return "an item", ""
    c._pick_ball = pick_ball
    c._approach_adjacent = lambda x, y: (g.log.append(("approach", x, y)), True)[1]
    c._facing_dir = lambda *a: "Up"

    def after_talk():
        pass
    c._advance_to_control = after_talk

    def tap(b):
        if b == "A" and battle_on_trainer and g.log and g.log[-1][0] == "approach":
            g.ctx = GameContext.IN_BATTLE                  # the trainer starts a fight
    c.mgba = SimpleNamespace(tap=tap, tick=lambda n=1: None)
    c._go_to_map_tuple = lambda target, name, call: (g.log.append(("travel", target)), setattr(g, "map", tuple(target)), None)[2]
    return c


def test_area_names_match_loosely_and_ambiguity_is_reported():
    c = _client(Game())
    assert c._sweep_area("viridian forest")[0] == "Viridian Forest" and c._sweep_area("Mt. Moon")[0] == "Mt. Moon"
    area, hits = c._sweep_area("gym")
    assert area is None and len(hits) > 1
    assert "No area called" in c._sweep("atlantis") and "Which area?" in c._sweep("gym")


def test_it_collects_every_item_ball_then_reports_the_area_done():
    g = Game(beaten=FOREST["trainers"])
    out = _client(g)._sweep("Viridian Forest")
    assert [e[0] for e in g.log].count("ball") == 4 and all(f in g.flags for f in FOREST["items"])
    assert "every trainer and item ball is done" in out and "Picked up: an item, an item, an item, an item." in out


def test_a_trainer_battle_ends_the_call_and_the_flags_say_where_it_resumes():
    g = Game(taken=FOREST["items"])
    out = _client(g)._sweep("Viridian Forest")
    assert g.ctx == GameContext.IN_BATTLE and "battle started — play it" in out and "quest('sweep Viridian Forest') again" in out
    assert [e[0] for e in g.log] == ["approach"]            # one trainer approached, then the battle was handed back
    g.ctx = GameContext.OVERWORLD                                                          # (the model played it)
    g.flags.add(g.log[0] and next(f for f, _m, x, y in FOREST["trainer_pos"] if (x, y) == g.log[0][1:]))
    _client(g)._sweep("Viridian Forest")
    assert [e[0] for e in g.log].count("approach") == 2                                    # the second call picked the NEXT trainer, not the beaten one


def test_a_hurt_lead_stops_before_the_next_trainer_but_not_before_an_item():
    g = Game(hp=0.3)
    out = _client(g)._sweep("Viridian Forest")
    assert "Sparky is at 30% — heal() before the next trainer" in out
    assert [e[0] for e in g.log].count("ball") == 4 and "approach" not in [e[0] for e in g.log]   # the balls are safe to collect; the trainers wait


def test_it_travels_to_the_map_that_holds_the_next_target():
    g = Game(beaten=FOREST["trainers"])
    g.map = (3, 1)                                                                          # Viridian City
    _client(g)._sweep("Viridian Forest")
    assert g.log[0] == ("travel", tuple(MAP))


def test_what_it_cannot_reach_is_skipped_with_a_note_and_never_looped_on():
    g = Game(beaten=FOREST["trainers"])
    c = _client(g)
    c._pick_ball = lambda x, y: ("", f"couldn't reach the item at ({x},{y})")
    out = c._sweep("Viridian Forest")
    assert out.count("couldn't reach the item") == 4 and "4 left" in out


def test_a_trainer_who_does_not_fight_is_skipped_with_a_note():
    g = Game(taken=FOREST["items"])
    out = _client(g, battle_on_trainer=False)._sweep("Viridian Forest")
    assert "did not start a battle" in out and g.ctx == GameContext.OVERWORLD


def test_it_refuses_outside_the_open_field():
    g = Game()
    g.ctx = GameContext.IN_MENU
    assert "open field" in _client(g)._sweep("Viridian Forest")


def test_quest_routes_sweep_to_the_driver(monkeypatch):
    c = _client(Game())
    monkeypatch.setattr(c, "_sweep", lambda q: f"swept {q!r}")
    assert c._quest_tool("sweep Mt. Moon") == "swept 'Mt. Moon'"

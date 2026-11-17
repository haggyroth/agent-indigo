"""Bill / S.S. Anne quests hand encounters to the model and resume themselves (#203 follow-up, no emulator)."""
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.constants import Addr                    # noqa: E402
from game.state import GameContext                 # noqa: E402


class World:
    def __init__(self, ctx=GameContext.OVERWORLD, trainer=False, map_=(3, 24), pos=(5, 5)):
        self.ctx, self.trainer, self.map, self.pos = ctx, trainer, map_, pos

    def detect_context(self): return self.ctx
    def read32(self, a): return Addr.BATTLE_TYPE_TRAINER if (a == Addr.BATTLE_TYPE_FLAGS and self.trainer) else 0
    def read_current_map(self): return self.map
    def read_player_pos(self): return self.pos
    def read_key_items(self): return []
    def read_flag(self, n): return False
    def read_enemy_lead(self): return NS(species_id=19, species_name="RATTATA", level=7, current_hp=18, max_hp=18)
    def read_party(self): return []


def client(world):
    c = AgentClient.__new__(AgentClient)
    c.reader = c.mgba = world
    c._ball_count = lambda: 0
    c._trip = None
    return c


def test_ss_ticket_travel_hands_an_encounter_over_and_names_itself_as_the_resume_call():
    w = World()
    c = client(w)
    seen = {}

    def go(dest, mode="yield", auto_trainers=False, resume_call=None):
        seen.update(dest=dest, mode=mode, auto=auto_trainers, call=resume_call)
        w.ctx = GameContext.IN_BATTLE
        return c._yield_encounter(dest, False, None, resume_call)
    c._go_to = go
    out = c._get_ss_ticket()
    assert "wild RATTATA L7" in out and "get_ss_ticket()" in out and "go_to(" not in out
    assert seen == {"dest": "Bill's Sea Cottage", "mode": "yield", "auto": False, "call": "get_ss_ticket()"}
    assert c._trip["call"] == "get_ss_ticket()"


def test_auto_trainers_is_passed_through_to_the_trip():
    w = World()
    c = client(w)
    got = []

    def go(dest, mode="yield", auto_trainers=False, resume_call=None):
        got.append(auto_trainers)
        w.ctx = GameContext.IN_BATTLE
        return "stopped"
    c._go_to = go
    c._has_ss_ticket = lambda: True
    c._knows_cut = lambda: False
    c._get_ss_ticket(auto_trainers=True) if False else None
    c._get_cut(auto_trainers=True)
    assert got == [True]


def test_quest_battle_is_none_outside_a_battle_and_a_trainer_brief_inside_one():
    assert client(World())._quest_battle("get_cut()", "the Captain") is None
    out = client(World(ctx=GameContext.IN_BATTLE, trainer=True))._quest_battle("get_cut()", "the Captain")
    assert "TRAINER" in out and "get_cut()" in out


def test_press_on_tile_clears_a_battle_as_plain_transport_and_hands_back_what_it_cannot():
    w = World(ctx=GameContext.IN_BATTLE)
    c = client(w)
    c._walk_to = lambda x, y: None
    seen = []
    c._handle_travel_battle = lambda name, mode="yield", **k: seen.append(mode) or "could not clear it"
    assert c._press_on_tile((4, 6), "Up") is False          # never reached the tile
    assert seen == ["flee"]                                  # fought as transport, then stopped (no retry loop)

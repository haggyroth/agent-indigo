"""Unit tests for flee_battle + travel-battle guard logic (no emulator)."""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import GameContext, PokemonStatus  # noqa: E402
from game.constants import Addr                    # noqa: E402


class _Fake:
    def __init__(self, ctx, flags=0, outcome=0, party=None):
        self.ctx = ctx
        self.flags = flags
        self.outcome = outcome
        self._party = party if party is not None else []

    def detect_context(self):
        return self.ctx

    def read32(self, addr):
        return self.flags if addr == Addr.BATTLE_TYPE_FLAGS else 0

    def read8(self, addr):
        return self.outcome if addr == Addr.BATTLE_OUTCOME else 0

    def read_party(self):
        return self._party


def _client(ctx, flags=0, outcome=0, party=None):
    f = _Fake(ctx, flags, outcome, party)
    c = AgentClient.__new__(AgentClient)
    c.reader = f
    c.mgba = f
    return c


def _mon(cur, mx=50):
    return PokemonStatus(slot=0, level=18, current_hp=cur, max_hp=mx, status="healthy")


def test_flee_refuses_when_not_in_battle():
    assert "Not in a battle" in _client(GameContext.OVERWORLD)._flee_battle()


def test_flee_refuses_trainer_battle():
    msg = _client(GameContext.IN_BATTLE, flags=Addr.BATTLE_TYPE_TRAINER)._flee_battle()
    assert "trainer battle" in msg.lower()


# ── Travel trainer battles are now AUTO-FOUGHT; _auto_fight is stubbed so the tests
#    drive the post-fight state the decision logic reads (outcome / context / party HP).

def _trainer_client(*, outcome, ctx_after, party):
    c = _client(ctx_after, flags=Addr.BATTLE_TYPE_TRAINER, outcome=outcome, party=party)
    c._auto_fight = lambda: None      # don't drive a real battle in a unit test
    return c


def test_travel_trainer_win_continues_travel():
    # Clean win (outcome WON, back in overworld, lead healthy) → keep travelling (None).
    c = _trainer_client(outcome=Addr.B_OUTCOME_WON, ctx_after=GameContext.OVERWORLD,
                        party=[_mon(45)])
    assert c._handle_travel_battle("Cerulean City", mode="yield", auto_trainers=True) is None


def test_travel_trainer_loss_bails():
    c = _trainer_client(outcome=Addr.B_OUTCOME_LOST, ctx_after=GameContext.TRANSITIONING,
                        party=[_mon(0), _mon(0)])
    msg = c._handle_travel_battle("Cerulean City", mode="yield", auto_trainers=True)
    assert msg is not None and "lost" in msg.lower() and "heal" in msg.lower()


def test_second_loss_near_the_same_map_says_stop_retrying():
    c = _trainer_client(outcome=Addr.B_OUTCOME_LOST, ctx_after=GameContext.TRANSITIONING,
                        party=[_mon(0), _mon(0)])
    c.reader.read_current_map = lambda: (3, 3)
    first = c._handle_travel_battle("Pewter City", mode="yield", auto_trainers=True)
    second = c._handle_travel_battle("Pewter City", mode="yield", auto_trainers=True)
    assert "Do NOT retry" not in first and "heal" in first.lower()
    assert "Do NOT retry" in second and "grind" in second.lower()


def test_travel_trainer_all_fainted_bails_even_without_outcome():
    # Blackout race: outcome not yet set but the whole party is down → still a loss.
    c = _trainer_client(outcome=0, ctx_after=GameContext.TRANSITIONING,
                        party=[_mon(0), _mon(0)])
    assert "lost" in c._handle_travel_battle("Cerulean City", mode="yield", auto_trainers=True).lower()


def test_travel_trainer_unfinished_hands_back():
    # Still IN_BATTLE after a full auto pass (tough trainer / forced switch) → take over.
    c = _trainer_client(outcome=0, ctx_after=GameContext.IN_BATTLE, party=[_mon(20)])
    msg = c._handle_travel_battle("Cerulean City", mode="yield", auto_trainers=True)
    assert msg is not None and "autopilot" in msg.lower()


def test_travel_trainer_win_but_low_hp_bails_to_heal():
    c = _trainer_client(outcome=Addr.B_OUTCOME_WON, ctx_after=GameContext.OVERWORLD,
                        party=[_mon(5)])          # 5/50 = 10% < TRAVEL_HP_FLOOR
    msg = c._handle_travel_battle("Cerulean City", mode="yield", auto_trainers=True)
    assert msg is not None and "low" in msg.lower() and "heal" in msg.lower()


def test_action_cursor_constants():
    # RUN is index 3 in the FIGHT/BAG/POKEMON/RUN grid; cursor is the u8 adjacent
    # to the move cursor.
    assert Addr.ACTION_RUN == 3
    assert Addr.ACTION_CURSOR == 0x02023FF8
    assert Addr.CTRL_CHOOSE_ACTION == 0x08030611


# ── go_to encounter hand-off (#202) ──────────────────────────────────────────────────
def _wild_client(party=None, balls=3):
    from types import SimpleNamespace as NS
    c = _client(GameContext.IN_BATTLE, flags=0, party=party or [_mon(50)])
    foe = NS(species_id=19, species_name="RATTATA", level=4, current_hp=14, max_hp=14)
    c.reader.read_enemy_lead = lambda: foe
    c.reader.read_current_map = lambda: (3, 19)          # Route 1
    c.reader.read_dex_owned = lambda _s: True
    c._ball_count = lambda: balls
    c._flee_battle = lambda: "Got away safely!"
    c._auto_fight = lambda: None
    return c


def test_yield_mode_hands_a_wild_battle_to_the_model_and_records_the_trip():
    c = _wild_client()
    msg = c._handle_travel_battle("Viridian City", mode="yield", resume="Viridian City")
    assert "wild RATTATA L4" in msg and "go_to('Viridian City')" in msg
    assert "use_move" in msg and "catch()" in msg and "flee_battle()" in msg
    assert c._trip == {"dest": "Viridian City", "target": "Viridian City", "call": None}


def test_yield_mode_never_fights_flees_or_throws_a_ball_itself():
    c = _wild_client()
    called = []
    c._flee_battle = lambda: called.append("flee") or "Got away safely!"
    c._auto_fight = lambda: called.append("fight")
    c._grind_try_catch = lambda: called.append("catch")
    assert c._handle_travel_battle("Pewter City", mode="yield") is not None
    assert called == []


def test_yield_mode_resume_uses_the_original_waypoint_not_the_resolved_name():
    c = _wild_client()
    msg = c._handle_travel_battle("Pewter Gym (Brock)", mode="yield", resume="Gym")
    assert "go_to('Gym')" in msg and c._trip["dest"] == "Gym"


def test_yield_mode_trainer_battle_is_handed_over_too():
    c = _trainer_client(outcome=0, ctx_after=GameContext.IN_BATTLE, party=[_mon(50)])
    c.reader.read_current_map = lambda: (3, 2)
    msg = c._handle_travel_battle("Cerulean City", mode="yield")
    assert "TRAINER" in msg and "can't flee" in msg and "go_to('Cerulean City')" in msg


def test_auto_trainers_still_autofights_trainers_but_wild_is_yielded():
    c = _trainer_client(outcome=Addr.B_OUTCOME_WON, ctx_after=GameContext.OVERWORLD, party=[_mon(45)])
    assert c._handle_travel_battle("Cerulean City", mode="yield", auto_trainers=True) is None
    w = _wild_client()
    assert w._handle_travel_battle("Cerulean City", mode="yield", auto_trainers=True) is not None


def test_flee_mode_runs_from_wild_and_does_not_stop_for_low_hp():
    c = _wild_client(party=[_mon(5)])                    # 10% HP, on its way to a Center
    assert c._handle_travel_battle("Pokemon Center", mode="flee") is None


def test_flee_mode_falls_back_to_fighting_when_the_escape_fails():
    c = _wild_client()
    c._flee_battle = lambda: "Couldn't escape!"
    fought = []

    def fight():
        fought.append(1)
        c.reader.ctx = GameContext.OVERWORLD
    c._auto_fight = fight
    assert c._handle_travel_battle("Pokemon Center", mode="flee") is None and fought == [1]
    c2 = _wild_client()
    c2._flee_battle = lambda: "Couldn't escape!"
    msg = c2._handle_travel_battle("Pokemon Center", mode="flee")          # still in battle after the fight
    assert msg is not None and "escape failed" in msg


def test_go_to_tool_without_a_destination_resumes_the_trip():
    c = _wild_client()
    c._readiness = lambda: []
    seen = []
    c._go_to = lambda d, mode="yield", auto_trainers=False: seen.append((d, mode, auto_trainers)) or "Arrived at X."
    assert "No trip in progress" in c._go_to_tool("")
    c._trip = {"dest": "Viridian City", "target": "Viridian City"}
    c.reader.detect_context = lambda: GameContext.OVERWORLD
    assert c._go_to_tool("").startswith("Arrived")
    assert seen == [("Viridian City", "yield", False)]
    c._go_to_tool("Route 2", auto_trainers=True)
    assert seen[-1] == ("Route 2", "yield", True)


def test_heal_travels_in_flee_mode():
    c = _wild_client()
    modes = []
    c._party_needs_heal = lambda: True
    c.reader.read_current_map = lambda: (3, 1)
    c._go_to = lambda d, mode="yield", **kw: modes.append(mode) or "Stopped"
    c._heal()
    assert modes == ["flee"]

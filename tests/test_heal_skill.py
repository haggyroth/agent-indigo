"""Unit tests for the parts of heal() that don't need the emulator."""
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import PokemonStatus, GameContext  # noqa: E402


def _mon(cur, mx):
    return PokemonStatus(slot=0, level=10, current_hp=cur, max_hp=mx, status="healthy")


class _Reader:
    def __init__(self, party):
        self._party = party

    def read_party(self):
        return self._party


def _client(party):
    c = AgentClient.__new__(AgentClient)
    c.reader = _Reader(party)
    return c


class _CtxReader:
    """detect_context() returns `menu_ctx` for the first `menu_steps` calls (the
    lingering post-heal state), then OVERWORLD."""
    def __init__(self, menu_steps, menu_ctx=GameContext.IN_MENU):
        self.menu_steps = menu_steps
        self.menu_ctx = menu_ctx
        self.calls = 0

    def detect_context(self):
        self.calls += 1
        return self.menu_ctx if self.calls <= self.menu_steps else GameContext.OVERWORLD


class _Mgba:
    def __init__(self):
        self.taps = []

    def read32(self, _addr):
        return 0

    def tap(self, b):
        self.taps.append(b)

    def tick(self, n=1):
        pass


def _ctrl_client(reader, mgba):
    c = AgentClient.__new__(AgentClient)
    c.reader = reader
    c.mgba = mgba
    return c


def test_heal_noops_when_already_full():
    # Full party → heal() returns immediately without any navigation.
    msg = _client([_mon(27, 27)])._heal()
    assert "already at full HP" in msg


def test_nurse_tile_is_below_the_counter():
    # Regression for the counter geometry: talk from (7,4), not the counter (7,3).
    assert AgentClient._NURSE_TILE == (7, 4)


def test_advance_to_control_presses_A_until_overworld():
    # heal() ends by calling this so it returns in real OVERWORLD control (the fix for
    # the Poké Center exit stall). It must keep tapping A through the lingering IN_MENU
    # state and stop the moment control returns.
    r = _CtxReader(menu_steps=6)
    mg = _Mgba()
    ctx = _ctrl_client(r, mg)._advance_to_control(tries=24)
    assert ctx == GameContext.OVERWORLD
    assert mg.taps == ["A"] * 6          # pressed exactly until control returned, no more


def test_advance_to_control_stops_on_battle():
    # If a battle starts while advancing, bail immediately (don't mash A into it).
    r = _CtxReader(menu_steps=2, menu_ctx=GameContext.IN_BATTLE)
    mg = _Mgba()
    ctx = _ctrl_client(r, mg)._advance_to_control(tries=24)
    assert ctx == GameContext.IN_BATTLE
    assert mg.taps == []                 # IN_BATTLE on the first check → no presses


def test_advance_to_control_bounded():
    # Never loops forever if control never returns — capped by `tries`.
    r = _CtxReader(menu_steps=999)
    mg = _Mgba()
    ctx = _ctrl_client(r, mg)._advance_to_control(tries=5)
    assert ctx == GameContext.IN_MENU
    assert len(mg.taps) == 5


def test_field_heal_uses_a_revive_then_the_smallest_potion_that_fills_the_gap():
    """Deep in Victory Road no Center is reachable (chain run 7 looped heal() 2,800x): the Bag heals instead."""
    from types import SimpleNamespace as NS
    from agent.skills.items import FieldItemMixin

    party = [NS(current_hp=0, max_hp=100), NS(current_hp=20, max_hp=100), NS(current_hp=100, max_hp=100)]
    bag = {24: 1, 13: 5, 21: 3}
    used = []

    class Host(FieldItemMixin):
        reader = NS(read_party=lambda: party, read_items_pocket=lambda: list(bag.items()))

        def _field_use_item(self, item, target=""):
            used.append(item)
            if item == "Revive":
                bag[24] -= 1
                party[0].current_hp = 50
            elif item == "Hyper Potion":
                bag[21] -= 1
                party[1].current_hp = 100
            return "Used it"

    assert Host()._field_heal() == ["Revive", "Hyper Potion"]          # Revive first; the 80-HP gap needs more than a Potion's 20
    assert Host()._field_heal() == []                                   # nobody is left under half


class _Where:
    def __init__(self, mp, pos, party):
        self.mp, self.pos, self._party = mp, pos, party

    def read_current_map(self):
        return self.mp

    def read_player_pos(self):
        return self.pos

    def read_party(self):
        return self._party

    def read_objects_by_gfx(self, ids):
        return []


def test_heal_falls_back_to_the_next_center_when_the_nearest_is_unreachable():
    """Route 23 with a fainted party: the graph's nearest Center (the Indigo Plateau's) is not reachable, so heal() must try the next one (Viridian's) instead of giving up —
    the chain stalled on this for 2,000+ calls."""
    c = AgentClient.__new__(AgentClient)
    c.reader = _Where((3, 42), (10, 5), [_mon(0, 100)])         # Route 23's NORTH half: the Plateau's Center is the nearest on paper (from the south it is not even tried)
    c.mgba = c.reader
    trips = []

    def go_to(dest, mode="yield", auto_trainers=False, resume_call=None):
        trips.append(dest)
        return ("Heading to Pokemon Center: stuck at Route 23 (Couldn't get to the North edge)." if len(trips) == 1
                else "Arrived at the Pokémon Center (5, 4).")
    c._go_to = go_to
    c._field_heal = lambda: ["never"]
    out = c._heal()
    assert trips == ["Pokemon Center", "map:5,4"], trips            # first the nearest, then Viridian's by exact map
    assert "healed from the Bag" not in out


def test_a_map_destination_resolves_to_that_exact_map():
    c = AgentClient.__new__(AgentClient)
    assert c._resolve_destination("map:5,4")[0] == (5, 4)
    assert c._resolve_destination("map:oops")[0] is None

"""quest('rematch') against a fake game (#367): the VS Seeker state reader, and what the driver picks, hands back and refuses."""
from types import SimpleNamespace

import pytest

from game.constants import Addr
from game.memory_reader import LeafGreenReader
from game.state import GameContext

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402

SB1 = 0x02025000


class Mem:
    """Just enough client for read_vs_seeker / read_objects_by_local."""
    def __init__(self, steps=0, table=None, objs=()):
        self.steps, self.table, self.objs = steps, dict(table or {}), list(objs)

    def read32(self, a):
        return SB1 if a == Addr.SAVEBLOCK1_PTR else 0

    def read16(self, a):
        return self.steps if a == SB1 + Addr.VSSEEKER_STEPS_OFFSET else 0

    def read_range(self, a, n):
        if a == SB1 + Addr.VSSEEKER_TABLE_OFFSET:
            raw = bytearray(n)
            for k, v in self.table.items():
                raw[k] = v
            return bytes(raw)
        raw = bytearray(n)
        for i, (loc, x, y, player) in enumerate(self.objs):
            o = i * Addr.OBJECT_EVENT_STRIDE
            raw[o] = 1
            raw[o + 2] = 1 if player else 0
            raw[o + 0x10:o + 0x12] = (x + Addr.OBJECT_COORD_OFFSET).to_bytes(2, "little")
            raw[o + 0x12:o + 0x14] = (y + Addr.OBJECT_COORD_OFFSET).to_bytes(2, "little")
            raw[o + Addr.OBJECT_LOCALID_OFFSET] = loc
        return bytes(raw)


def _reader(mem):
    r = LeafGreenReader.__new__(LeafGreenReader)
    r.client = mem
    r._valid_ewram_ptr = lambda p: p == SB1
    return r


def test_the_state_reader_splits_the_counter_and_lists_the_table():
    st = _reader(Mem(steps=37 | (12 << 8), table={5: 2, 9: 1})).read_vs_seeker()
    assert st == {"bag_steps": 37, "charge_steps": 12, "ready": {5: 2, 9: 1}}


def test_the_object_reader_keys_npcs_by_local_id_and_leaves_the_player_out():
    got = _reader(Mem(objs=[(3, 20, 9, False), (0xFF, 22, 10, True)])).read_objects_by_local()
    assert got == {3: (20, 9)}


def _client(have_item=True, ctx=GameContext.OVERWORLD, state=None):
    c = AgentClient.__new__(AgentClient)
    st = state or {"bag_steps": 100, "charge_steps": 0, "ready": {}}
    c.reader = SimpleNamespace(read_flag=lambda f: False, read_key_items=lambda: [362] if have_item else [], detect_context=lambda: ctx,
                               read_vs_seeker=lambda: st, read_objects_by_local=lambda: {}, read_party=lambda: [])
    c.mgba = SimpleNamespace(tap=lambda b: None, tick=lambda n=1: None)
    return c


def test_without_the_item_it_says_where_to_get_it():
    out = _client(have_item=False)._rematch("")
    assert "no VS Seeker" in out and "Vermilion" in out and "REMATCHES:" in out


def test_status_reports_charge_and_flagged_trainers_without_acting():
    out = _client(state={"bag_steps": 60, "charge_steps": 30, "ready": {4: 1}})._rematch("status")
    assert "40 more steps" in out and "1 trainer(s) are flagged" in out and "70 steps" in out


def test_it_refuses_off_the_open_field():
    assert "open field" in _client(ctx=GameContext.IN_MENU)._rematch("")


def test_quest_routes_rematch_to_the_driver():
    c = _client()
    c._rematch = lambda arg="": f"driver:{arg}"
    assert c._quest_tool("rematch status") == "driver:status"

"""'Unreadable' must not read as 'zero' (#376): while the SaveBlock pointers are invalid the SaveBlock readers return their last good value."""
from game.constants import Addr
from game.memory_reader import LeafGreenReader

SB1, SB2, KEY = 0x02030000, 0x02031000, 0x9ABCDEF1
K16 = KEY & 0xFFFF


class Mem:
    """A tiny sparse memory with a switch that makes the SaveBlock pointers invalid (title screen / transition frame)."""
    def __init__(self):
        self.b = {}
        self.valid = True

    def put(self, addr, data):
        for i, x in enumerate(data):
            self.b[addr + i] = x

    def put16(self, addr, v):
        self.put(addr, v.to_bytes(2, "little"))

    def put32(self, addr, v):
        self.put(addr, v.to_bytes(4, "little"))

    def read32(self, a):
        if a == Addr.SAVEBLOCK1_PTR:
            return SB1 if self.valid else 0
        if a == Addr.SAVEBLOCK2_PTR:
            return SB2 if self.valid else 0
        return int.from_bytes(bytes(self.b.get(a + i, 0) for i in range(4)), "little")

    def read16(self, a):
        return int.from_bytes(bytes(self.b.get(a + i, 0) for i in range(2)), "little")

    def read8(self, a):
        return self.b.get(a, 0)

    def read_range(self, a, n):
        return bytes(self.b.get(a + i, 0) for i in range(n))


def _world():
    m = Mem()
    m.put32(SB2 + Addr.ENCRYPTION_KEY_OFFSET, KEY)
    m.put32(SB1 + Addr.MONEY_OFFSET, 4300 ^ KEY)
    m.put16(SB1 + Addr.COINS_OFFSET, 120 ^ K16)
    slot = lambda iid, q: iid.to_bytes(2, "little") + (q ^ K16).to_bytes(2, "little")      # noqa: E731
    m.put(SB1 + Addr.ITEMS_OFFSET, slot(13, 5) + slot(14, 2))
    m.put(SB1 + Addr.TMHM_OFFSET, slot(289, 1))
    m.put(SB1 + Addr.KEY_ITEMS_OFFSET, (1).to_bytes(2, "little") + bytes(2) + (2).to_bytes(2, "little") + bytes(2) + (3).to_bytes(2, "little") + bytes(2))
    m.put(SB1 + Addr.FLAGS_OFFSET + (0x829 >> 3), bytes([1 << (0x829 & 7)]))
    m.put16(SB1 + Addr.VARS_OFFSET, 14)
    m.put(SB2 + Addr.DEX_OWNED_OFFSET, bytes([0b00000111]))
    m.put(SB2 + Addr.DEX_SEEN_OFFSET, bytes([0b00001111]))
    r = LeafGreenReader.__new__(LeafGreenReader)         # (several tests build readers this way: the cache must not need __init__)
    r.client = m
    r.map_epoch = 0
    return r, m


def _snapshot(r):
    return dict(money=r.read_money(), coins=r.read_coins(), bag=r.read_bag(), items=r.read_items_pocket(), tms=r.read_tmhm_pocket(),
                key_count=r.read_key_item_count(), key_items=r.read_key_items(), flag=r.read_flag(0x829), var=r.read_var(0x4000),
                dex=r.read_pokedex(), owned=r.read_dex_owned_ids())


def test_every_saveblock_reader_keeps_its_last_good_value_while_the_pointers_are_invalid():
    r, m = _world()
    good = _snapshot(r)
    assert good["money"] == 4300 and good["key_count"] == 3 and good["flag"] is True and good["bag"] == {13: 5, 14: 2}
    m.valid = False                                        # a transition frame
    assert _snapshot(r) == good                            # not 0 / False / {} / []
    m.valid = True
    assert _snapshot(r) == good


def test_a_value_that_really_changed_is_picked_up_once_the_pointers_are_valid_again():
    r, m = _world()
    r.read_money()
    m.put32(SB1 + Addr.MONEY_OFFSET, 900 ^ KEY)
    m.valid = False
    assert r.read_money() == 4300                          # still the last good one while unreadable
    m.valid = True
    assert r.read_money() == 900


def test_a_failed_money_decrypt_is_not_zero_money():
    r, m = _world()
    assert r.read_money() == 4300
    m.put32(SB1 + Addr.MONEY_OFFSET, 0xFFFFFFFF)           # decrypts to garbage (wrong key mid-transition)
    assert r.read_money() == 4300


def test_never_read_still_falls_back_to_the_empty_defaults():
    r, m = _world()
    m.valid = False
    assert (r.read_money(), r.read_bag(), r.read_items_pocket(), r.read_key_item_count(), r.read_flag(1), r.read_pokedex()) == (0, {}, [], 0, False, (0, 0))


def test_a_five_zero_five_key_item_count_has_no_phantom_gain():
    r, m = _world()
    seen = [r.read_key_item_count()]
    m.valid = False
    seen.append(r.read_key_item_count())
    m.valid = True
    seen.append(r.read_key_item_count())
    assert seen == [3, 3, 3]                               # main._apply_progress compares against the previous value: no 'key item obtained'


def test_callers_cannot_corrupt_the_cache_through_what_they_were_handed():
    r, m = _world()
    bag = r.read_bag()
    bag[13] = 999
    items = r.read_items_pocket()
    items.clear()
    m.valid = False
    assert r.read_bag() == {13: 5, 14: 2} and r.read_items_pocket() == [(13, 5), (14, 2)]


def test_reset_caches_forgets_the_old_timeline_and_counts_as_a_reload():
    r, m = _world()
    _snapshot(r)
    before = r.map_epoch
    r.reset_caches()
    m.valid = False
    assert r.read_money() == 0 and r.read_flag(0x829) is False and r.read_bag() == {}      # nothing from before the load answers now
    assert r.map_epoch == before + 1


def test_the_load_state_tool_resets_the_readers_caches():
    import types
    import pytest
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    calls = []
    c.mgba = types.SimpleNamespace(saved_this_session=lambda s: True, load_state=lambda s=0: True)
    c.reader = types.SimpleNamespace(reset_caches=lambda: calls.append(1))
    c._grind_run = None
    assert "loaded" in c._execute_inner("load_state", '{"slot": 3}')
    assert calls == [1]

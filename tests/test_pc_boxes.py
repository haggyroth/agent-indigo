"""PC boxes: memory decoding, growth levels, skill guards (the UI itself is covered by the live tests)."""
from types import SimpleNamespace

import pytest

from game.constants import Addr
from game.memory_reader import SUBSTRUCT_ORDER, LeafGreenReader
from knowledge.growth import exp_for_level, level_from_exp


def test_growth_levels_match_the_decomp_formulas():
    assert level_from_exp(1, 4575) == 19 and level_from_exp(1, 555) == 9       # Bulbasaur: medium slow
    assert level_from_exp(25, 135) == 5                                           # Pikachu: medium fast
    assert exp_for_level(0, 10) == 1000 and exp_for_level(4, 10) == 800 and exp_for_level(5, 10) == 1250
    assert level_from_exp(1, 0) == 1 and level_from_exp(1, 10**9) == 100


def _boxmon(species, exp, nick=b"\xc3\xcc\xff"):
    """An 80-byte BoxPokemon: personality/OT, nickname, encrypted substructs (G = species+exp)."""
    pid, ot = 0x11223344, 0x55667788
    key = pid ^ ot
    sub = {k: bytearray(12) for k in "GAEM"}
    sub["G"][0:2] = species.to_bytes(2, "little")
    sub["G"][4:8] = exp.to_bytes(4, "little")
    sub["A"][0:2] = (33).to_bytes(2, "little")                                    # Tackle
    order = SUBSTRUCT_ORDER[pid % 24]
    blob = bytearray()
    for letter in order:
        blob += sub[letter]
    for i in range(0, 48, 4):
        w = int.from_bytes(blob[i:i + 4], "little") ^ key
        blob[i:i + 4] = w.to_bytes(4, "little")
    raw = bytearray(80)
    raw[0:4], raw[4:8] = pid.to_bytes(4, "little"), ot.to_bytes(4, "little")
    raw[8:8 + len(nick)] = nick
    raw[32:80] = blob
    return bytes(raw)


def _reader(boxes):
    base = 0x02029000
    mem = {Addr.POKEMON_STORAGE_PTR: base, base: 1}
    ram = bytearray(14 * 30 * 80)
    for (b, s), data in boxes.items():
        off = (b * 30 + s) * 80
        ram[off:off + 80] = data

    class _C:
        def read32(self, a): return mem.get(a, 0)
        def read8(self, a): return mem.get(a, 0)
        def read_range(self, a, n):
            off = a - (base + 4)
            return bytes(ram[off:off + n])
    r = LeafGreenReader.__new__(LeafGreenReader)
    r.client = _C()
    return r


def test_box_mons_decode_species_level_and_skip_empty_slots():
    r = _reader({(0, 0): _boxmon(25, 135), (1, 14): _boxmon(1, 4575)})
    boxes = r.read_boxes()
    assert [(m["box"], m["slot"], m["species_name"], m["level"]) for m in boxes] == \
        [(0, 0, "Pikachu", 5), (1, 14, "Bulbasaur", 19)]
    assert boxes[0]["move_names"] == ["Tackle"]
    assert r.read_current_box() == 1
    assert r._decode_box_mon(bytes(80), 3, 3) is None                      # an empty slot


def _client(party, boxes=()):
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_party=lambda: party, read_boxes=lambda: list(boxes), read_current_box=lambda: None)
    c._open_pc = lambda mode=1: "SHOULD NOT OPEN"
    return c


def mon(name, hp=20, nick=""):
    return SimpleNamespace(species_name=name, nickname=nick, current_hp=hp, max_hp=20, move_names=[])


def test_deposit_refuses_the_last_pokemon_and_the_last_able_one():
    assert "only Pokémon" in _client([mon("A")])._pc_deposit("1")
    out = _client([mon("A"), mon("B", hp=0)])._pc_deposit("A")
    assert "only Pokémon able to battle" in out
    assert "Couldn't find" in _client([mon("A"), mon("B")])._pc_deposit("Mew")


def test_withdraw_needs_a_match_and_a_free_slot():
    assert "No Pokémon matching" in _client([mon("A")], [])._pc_withdraw("pikachu")
    box = [{"box": 0, "slot": 3, "species_name": "Pikachu", "nickname": "Zap", "level": 9, "species_id": 25,
            "move_names": []}]
    assert "party is full" in _client([mon(str(i)) for i in range(6)], box)._pc_withdraw("zap")


def test_swap_validates_the_boxed_pokemon_before_depositing_anything():
    c = _client([mon("A"), mon("B")], [])
    c._pc_deposit = lambda who, force=False: (_ for _ in ()).throw(AssertionError("must not deposit"))
    assert "Nothing was deposited" in c._pc_swap("A", "nobody")


def test_pc_listing_reads_nicely():
    box = [{"box": 0, "slot": 3, "species_name": "Pikachu", "nickname": "Zap", "level": 9, "species_id": 25,
            "move_names": ["Thunder Shock"]},
           {"box": 1, "slot": 0, "species_name": "Geodude", "nickname": "", "level": 12, "species_id": 74,
            "move_names": ["Tackle"]}]
    out = _client([mon("A")], box)._pc_boxes()
    assert "2 Pokémon stored" in out
    assert "Box 1 (1/30): Zap (Pikachu L9)" in out and "Box 2 (1/30): Geodude L12" in out
    detail = _client([mon("A")], box)._pc_boxes(detail=True)
    assert "1:3 Zap (Pikachu L9, ELE) — Thunder Shock" in detail and "2:0 Geodude" in detail


# ── #206: full boxes, ambiguity, swap order, HM guard ───────────────────────────────────
def bm(box, slot, species, level, nick="", sid=1):
    return {"box": box, "slot": slot, "species_name": species, "nickname": nick, "level": level,
            "species_id": sid, "move_names": []}


def test_deposit_box_choice_skips_full_boxes_and_wraps():
    from agent.skills.pc import pick_deposit_box
    assert pick_deposit_box({}, 0) == 0
    assert pick_deposit_box({0: 30}, 0) == 1
    assert pick_deposit_box({0: 30, 1: 30}, 0) == 2
    assert pick_deposit_box({13: 30}, 13) == 0                  # wraps around
    assert pick_deposit_box({b: 30 for b in range(14)}, 3) is None


def test_boxed_lookup_lists_ambiguous_matches_instead_of_guessing():
    from agent.skills.pc import resolve_boxed
    boxes = [bm(0, 4, "Pidgey", 8), bm(1, 11, "Pidgey", 14), bm(0, 9, "Rattata", 5, nick="Nibbles")]
    mon, why = resolve_boxed("nibbles", boxes)
    assert mon["slot"] == 9 and why == ""                       # exact nickname wins
    mon, why = resolve_boxed("pidgey", boxes)
    assert mon is None and "2 Pokémon match" in why and "2:11" in why and "1:4" in why
    mon, why = resolve_boxed("2:11", boxes)
    assert mon["level"] == 14
    assert resolve_boxed("9:9", boxes)[0] is None
    assert "No Pokémon matching" in resolve_boxed("mew", boxes)[1]


def test_deposit_target_is_the_first_box_with_room_because_the_chooser_starts_on_box_1():
    from agent.skills.pc import pick_deposit_box
    full = {0: 30, 1: 30}
    assert pick_deposit_box(full, 0) == 2


def test_deposit_reports_when_every_box_is_full():
    full = [bm(b, s, "Pidgey", 5) for b in range(14) for s in range(30)]
    c = _client([mon("A"), mon("B")], full)
    c.reader.read_current_box = lambda: 0
    assert "All 14 PC boxes are full" in c._pc_deposit("A")


def hm_mon(name, moves, hp=20):
    m = mon(name, hp)
    m.move_names = moves
    return m


def test_deposit_refuses_the_only_hm_carrier_unless_forced():
    party = [hm_mon("Bulbasaur", ["Tackle", "Cut"]), hm_mon("Pidgey", ["Gust"])]
    out = _client(party)._pc_deposit("Bulbasaur")
    assert "only Pokémon that knows Cut" in out and "force=true" in out
    party[1].move_names = ["Cut"]                              # someone else knows it too
    c = _client(party)
    assert c._deposit_problem(party, 0) is None
    party[1].move_names = ["Gust"]
    assert c._deposit_problem(party, 0, force=True) is None


def test_swap_resolves_both_sides_first_and_withdraws_by_exact_slot():
    boxes = [bm(0, 4, "Pidgey", 8), bm(1, 11, "Pidgey", 14)]
    party = [hm_mon("A", ["Tackle"]), hm_mon("Pidgey", ["Gust"])]
    c = _client(party, boxes)
    calls = []
    c._pc_deposit = lambda who, force=False: calls.append(("dep", who)) or "Deposited Pidgey into Box 1."
    c._pc_withdraw = lambda who: calls.append(("wd", who)) or "Withdrew Pidgey (L14) from Box 2."
    out = c._pc_swap("2", "2:11")
    assert calls == [("dep", "2"), ("wd", "2:11")] and out.startswith("Deposited")
    calls.clear()
    amb = c._pc_swap("A", "pidgey")                            # ambiguous boxed name: nothing happens
    assert calls == [] and "Nothing was deposited" in amb and "2 Pokémon match" in amb
    assert "Nothing was deposited" in c._pc_swap("Mew", "2:11")


def test_swap_warns_when_the_withdrawal_fails_after_the_deposit():
    c = _client([hm_mon("A", ["Tackle"]), hm_mon("B", ["Gust"])], [bm(0, 4, "Pidgey", 8)])
    c._pc_deposit = lambda who, force=False: "Deposited B into Box 1."
    c._pc_withdraw = lambda who: "The withdrawal of Pidgey didn't go through — try pc_withdraw again."
    assert "party is one short" in c._pc_swap("B", "1:4")

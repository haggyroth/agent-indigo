"""The Fame Checker data + progress logic (#368): 16 people x 6 entries, gates from the decomp's hide flags, what is open, and where the driver goes next."""
from types import SimpleNamespace

import pytest

from game.constants import Addr
from game.memory_reader import LeafGreenReader
from knowledge import fame_checker as fc
from knowledge.fame_checker_data import ENTRIES, PERSONS


def test_every_person_has_all_six_entries_exactly_once():
    assert len(PERSONS) == 16 and len(ENTRIES) == 96
    assert {(e[0], e[1]) for e in ENTRIES} == {(p, i) for p in range(16) for i in range(6)}
    assert {e[3] for e in ENTRIES} <= {"npc", "sign", "event"}
    assert all((e[4] >= 0) == (e[3] != "event") for e in ENTRIES)                  # only a scene has no tile


def test_status_counts_what_is_owned_and_splits_open_from_waiting():
    flags = {157, 115}                                                            # gossipers hidden, Erika's journals hidden (set = not out yet)
    s = fc.status({0: {0, 1}}, lambda n: n in flags)
    assert s["have"] == 2 and len(s["missing"]) == 94
    assert len(s["now"]) + sum(s["waiting"].values()) == 94
    assert any("Hall of Fame" in why for why in s["waiting"]) and any("Erika" in why for why in s["waiting"])
    assert not any(e[7] in flags for e in s["now"])                               # nothing open is behind a set hide flag


def test_the_game_clear_entries_wait_for_the_hall_of_fame():
    e = next(e for e in ENTRIES if e[8])
    assert "Hall of Fame" in fc.gate(e, lambda n: False)
    assert fc.gate(e, lambda n: n == e[8]) == ""


def test_a_finished_checker_says_so():
    owned = {p: set(range(6)) for p in range(16)}
    assert "complete" in fc.line(owned, lambda n: False) and fc.view(owned, lambda n: False) == fc.line(owned, lambda n: False)


def test_next_target_prefers_this_map_then_the_nearest_and_skips_the_unreachable_and_given_up():
    here = (3, 0)
    sign = next(e for e in ENTRIES if tuple(e[2]) == here and e[3] == "sign")
    got = fc.next_target({}, lambda n: False, here)
    assert got == sign or tuple(got[2]) == here                                  # this map first
    owned = {sign[0]: {sign[1]}}
    near = (4, 3)
    d = {near: 1}
    pick = fc.next_target(owned, lambda n: False, here, dist=lambda mp: d.get(mp, 50 if mp != (9, 9) else None))
    assert tuple(pick[2]) == near                                                # the closer map beats data order
    skipped = fc.next_target(owned, lambda n: False, here, skip={(pick[0], pick[1])}, dist=lambda mp: d.get(mp, 50))
    assert (skipped[0], skipped[1]) != (pick[0], pick[1])
    assert fc.next_target(owned, lambda n: False, here, dist=lambda mp: None) is None        # nothing reachable


SB1 = 0x02025000


def _reader(words):
    r = LeafGreenReader.__new__(LeafGreenReader)
    raw = b"".join(w.to_bytes(2, "little") for w in words)
    r.client = SimpleNamespace(read32=lambda a: SB1, read_range=lambda a, n: raw if a == SB1 + Addr.FAMECHECKER_OFFSET else bytes(n))
    r._valid_ewram_ptr = lambda p: p == SB1
    return r


def test_the_reader_decodes_flavor_bits_above_the_pick_state():
    words = [0] * 16
    words[0] = 0b10 | (1 << 3) | (1 << 6)                                         # pickState 2 (coloured), flavor 1 and 4
    words[15] = 0x3F << 2
    got = _reader(words).read_fame_checker()
    assert got[0] == {1, 4} and got[15] == {0, 1, 2, 3, 4, 5} and got[3] == set()


@pytest.mark.parametrize("arg,fragment", [("", "Missing, by person")])
def test_quest_fame_lists_by_person(arg, fragment):
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_flag=lambda n: False, read_fame_checker=lambda: {0: {0}})
    assert fragment in c._quest_tool("fame")

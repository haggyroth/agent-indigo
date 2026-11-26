"""#377 gate: the game keeps every party struct's checksum valid in RAM, in every saved scene — so the checksum can be trusted as the validity test."""
import pytest

from game.constants import Addr
from game.memory_reader import checksum_ok

from live.conftest import LIVE_DIR


def _fixtures():
    return sorted(p.stem for p in LIVE_DIR.glob("*.ss1"))


@pytest.mark.parametrize("name", _fixtures())
def test_every_occupied_party_slot_passes_the_checksum(live, name):
    live.load(name)
    for _ in range(3):                                   # a few frames in: not on the load frame itself
        live.m.tick(10)
    bad = []
    for slot in range(6):
        raw = live.m.read_range(Addr.PARTY_DATA + 100 * slot, 100)
        if raw[0x54] and not checksum_ok(raw):
            bad.append(slot)
    assert not bad, f"{name}: party slot(s) {bad} fail the checksum"
    foe = live.m.read_range(Addr.ENEMY_PARTY, 100)
    if live.r.detect_context().name == "IN_BATTLE" and foe[0x54]:
        assert checksum_ok(foe), f"{name}: the enemy lead fails the checksum"

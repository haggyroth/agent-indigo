"""A party slot is judged by the game's own checksum, and one bad slot degrades only itself (#377)."""
from dataclasses import replace

import pytest

from conftest import FakeClient, build_party_mon
from game.constants import Addr
from game.memory_reader import LeafGreenReader, checksum_ok


def _mon(pid=0x12345678, **kw):
    kw.setdefault("level", 10)
    kw.setdefault("cur_hp", 20)
    kw.setdefault("max_hp", 30)
    return build_party_mon(pid, 0x0000BEEF, **kw)


@pytest.mark.parametrize("residue", range(24))
def test_every_substructure_order_checksums(residue):
    pid = 24 * 1000 + residue                                 # pid % 24 == residue: all 24 orderings
    assert pid % 24 == residue and checksum_ok(_mon(pid=pid, species=25 + residue))


def test_a_flipped_data_byte_or_checksum_fails():
    raw = bytearray(_mon())
    assert checksum_ok(bytes(raw))
    for off in (32, 47, 60, 79):                              # inside the encrypted block
        bad = bytearray(raw)
        bad[off] ^= 0x40
        assert not checksum_ok(bytes(bad)), off
    bad = bytearray(raw)
    bad[0x1C] ^= 1                                            # the stored checksum itself
    assert not checksum_ok(bytes(bad))
    assert not checksum_ok(bytes(raw[:50]))                   # a short read is never valid


def _decode(raw):
    r = LeafGreenReader.__new__(LeafGreenReader)
    r.decrypt = True
    return r._decode_mon(bytes(raw), 0)


def test_decode_reports_validity_and_the_egg_flags():
    assert _decode(_mon()).valid and not _decode(_mon()).is_egg
    bad_egg = bytearray(_mon())
    bad_egg[0x13] |= 0x01                                     # the game marks a mon whose checksum failed as a Bad Egg
    assert not _decode(bad_egg).valid
    egg = bytearray(_mon())
    egg[0x13] |= 0x04
    assert _decode(egg).is_egg and _decode(egg).valid
    damaged = bytearray(_mon())
    damaged[40] ^= 0xFF
    assert not _decode(damaged).valid


def _party(*mons):
    fc = FakeClient()
    for slot, raw in enumerate(mons):
        fc.set_bytes(Addr.PARTY_DATA + 100 * slot, raw)
    return fc, LeafGreenReader(fc, decrypt=True)


def test_one_corrupt_slot_does_not_freeze_the_rest_of_the_party():
    a, b = _mon(pid=0x11111111, species=1), _mon(pid=0x22222222, species=4)
    fc, r = _party(a, b)
    assert [m.species_id for m in r.read_party()] == [1, 4]
    # slot 0 takes damage while slot 1 is caught mid-write
    fc.set_bytes(Addr.PARTY_DATA, _mon(pid=0x11111111, species=1, cur_hp=7))
    broken = bytearray(b)
    broken[45] ^= 0xFF
    fc.set_bytes(Addr.PARTY_DATA + 100, bytes(broken))
    p = r.read_party()
    assert p[0].current_hp == 7 and not p[0].stale          # the healthy slot is current, not frozen
    assert p[1].species_id == 4 and p[1].stale and p[1].valid  # the broken slot is its last good read, flagged


def test_a_slot_that_stays_invalid_stops_being_masked_after_the_stale_limit():
    a = _mon(pid=0x11111111, species=1)
    fc, r = _party(a)
    r.read_party()
    broken = bytearray(a)
    broken[45] ^= 0xFF
    fc.set_bytes(Addr.PARTY_DATA, bytes(broken))
    seen = [r.read_party()[0] for _ in range(LeafGreenReader.STALE_READS + 2)]
    assert all(m.stale for m in seen[:LeafGreenReader.STALE_READS])
    assert not seen[-1].stale and not seen[-1].valid          # then the truth is shown, flagged — not a party frozen forever


def test_a_valid_party_is_untouched():
    fc, r = _party(_mon(pid=1, species=1), _mon(pid=2, species=7))
    p = r.read_party()
    assert all(m.valid and not m.stale for m in p) and replace(p[0], slot=0) == p[0]

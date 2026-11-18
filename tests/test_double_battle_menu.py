"""game.menu.forced_party_screen in a DOUBLE battle: the forced choice also appears when the SECOND of our battlers (gBattleMons[2]) is the one down."""
from game.constants import Addr
from game.menu import forced_party_screen


class Mem:
    def __init__(self, cb2, outcome, flags, hp0, hp2, sp0=3, sp2=9):
        self.v32 = {Addr.GMAIN_CALLBACK2: cb2, Addr.BATTLE_TYPE_FLAGS: flags}
        self.v8 = {Addr.BATTLE_OUTCOME: outcome}
        self.v16 = {Addr.BATTLE_MON0_SPECIES: sp0, Addr.BATTLE_MON0_SPECIES + 0x28: hp0,
                    Addr.BATTLE_MON0_SPECIES + 0xB0: sp2, Addr.BATTLE_MON0_SPECIES + 0xB0 + 0x28: hp2}

    def read32(self, a): return self.v32.get(a, 0)
    def read8(self, a): return self.v8.get(a, 0)
    def read16(self, a): return self.v16.get(a, 0)


class Reader:
    def __init__(self, mem): self.m = mem
    def read_active_battle_species(self): return self.m.read16(Addr.BATTLE_MON0_SPECIES)
    def read_active_battle_hp(self): return self.m.read16(Addr.BATTLE_MON0_SPECIES + 0x28)


def _forced(**kw):
    m = Mem(**kw)
    return forced_party_screen(m, Reader(m))


def test_single_battle_forced_screen_is_unchanged():
    assert _forced(cb2=Addr.CB2_PARTY_MENU, outcome=0, flags=Addr.BATTLE_TYPE_TRAINER, hp0=0, hp2=0)
    assert not _forced(cb2=Addr.CB2_PARTY_MENU, outcome=0, flags=Addr.BATTLE_TYPE_TRAINER, hp0=40, hp2=0)


def test_double_battle_second_battler_down_is_a_forced_screen():
    flags = Addr.BATTLE_TYPE_TRAINER | Addr.BATTLE_TYPE_DOUBLE
    assert _forced(cb2=Addr.CB2_PARTY_MENU, outcome=0, flags=flags, hp0=40, hp2=0)
    assert not _forced(cb2=Addr.CB2_PARTY_MENU, outcome=0, flags=flags, hp0=40, hp2=25)       # both up: the field/switch menu, not forced
    assert not _forced(cb2=Addr.CB2_PARTY_MENU, outcome=1, flags=flags, hp0=40, hp2=0)        # a finished battle: stale struct

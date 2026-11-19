"""Helpers for staging live scenarios (party patching, forcing a wild battle, ...)."""
import pytest

from game.constants import Addr
from game.memory_reader import SUBSTRUCT_ORDER
from game.state import GameContext

B1 = Addr.BATTLE_MON0_SPECIES + 0x58          # gBattleMons[1]: the live foe


class Live:
    def __init__(self, rt, live_dir):
        self.rt, self.dir = rt, live_dir
        self.c, self.r, self.m = rt.client, rt.reader, rt.mgba

    def load(self, name: str) -> None:
        path = self.dir / f"{name}.ss1"
        if not path.exists():
            pytest.skip(f"fixture {path} missing — see tests/live/README.md")
        assert self.m.load_state_file(str(path)), f"could not load {path}"
        self.m.tick(30)
        self.heal_hp()
        self.c._grind_run = None            # a grind session from an earlier test must not leak its floor/level
        self.c._training_swapped = False
        self.c._trip = None

    def give_item(self, item_id: int, qty: int = 1) -> None:
        """Put `qty` of `item_id` in the first free Items-pocket slot (quantities are XOR'd with the save key)."""
        sb1 = self.m.read32(Addr.SAVEBLOCK1_PTR)
        k16 = self.r._encryption_key() & 0xFFFF
        for i in range(Addr.ITEMS_SLOTS):
            base = sb1 + Addr.ITEMS_OFFSET + 4 * i
            if self.m.read16(base) == 0:
                self.m.write16(base, item_id)
                self.m.write16(base + 2, qty ^ k16)
                return
        raise AssertionError("Items pocket is full")

    def give_key_item(self, item_id: int) -> None:
        """Put a key item (Silph Scope, Poké Flute, Secret Key, …) in the first free Key Items slot. Quantities are XOR'd like the Items pocket."""
        sb1 = self.m.read32(Addr.SAVEBLOCK1_PTR)
        k16 = self.r._encryption_key() & 0xFFFF
        for i in range(Addr.KEY_ITEMS_SLOTS):
            base = sb1 + Addr.KEY_ITEMS_OFFSET + 4 * i
            if self.m.read16(base) == item_id:
                return
            if self.m.read16(base) == 0:
                self.m.write16(base, item_id)
                self.m.write16(base + 2, 1 ^ k16)
                return
        raise AssertionError("Key Items pocket is full")

    def fly_to(self, town: str, badges: int = 0b1111111, flags=(), key_items=()) -> None:
        """Stage: give the lead Fly, the badges, the visited flag of `town` (and any extra flags / key items), then fly there."""
        import json
        from agent.skills.hm import FLY_SPOTS
        self.patch_mon(0, moves=[33, 19, 0, 0], pps=[35, 15, 0, 0])
        self.set_badges(badges)
        self.set_flag(FLY_SPOTS[town.lower()][2])
        for f in flags:
            self.set_flag(f)
        for k in key_items:
            self.give_key_item(k)
        out = self.c._execute("fly_to", json.dumps({"town": town.split()[0]}))
        assert tuple(self.r.read_current_map()) == FLY_SPOTS[town.lower()][0], out
        self.patch_mon(0, moves=[75, 22, 33, 0], pps=[25, 25, 35, 0])        # back to real attacks (Razor Leaf / Vine Whip / Tackle)
        self.heal_hp()

    def defeat_all_trainers(self) -> None:
        """Stage: mark every trainer (flags 0x500..0x7E6) as already beaten — for tests about NAVIGATION, where a fight on the way is noise
        (a defeated trainer just repeats his post-battle line; line-of-sight trainers no longer start fights)."""
        sb1 = self.m.read32(Addr.SAVEBLOCK1_PTR)
        for n in range(0x500, 0x7E7):
            a = sb1 + Addr.FLAGS_OFFSET + (n >> 3)
            self.m.write8(a, self.m.read8(a) | (1 << (n & 7)))

    def set_dex(self, caught: int, seen: int | None = None) -> None:
        """Stage: make the Pokédex hold species 1..`caught` as CAUGHT and 1..`seen` (default: the same) as seen. The game counts a species as caught only when its
        owned bit AND all three seen arrays agree (SaveBlock2 owned + seen, SaveBlock1 seen1 + seen2), so all four are written."""
        seen = caught if seen is None else max(seen, caught)
        sb1, sb2 = self.m.read32(Addr.SAVEBLOCK1_PTR), self.m.read32(Addr.SAVEBLOCK2_PTR)

        def fill(base, n):
            for i in range(52):
                bits = sum(1 << b for b in range(8) if i * 8 + b < n)
                self.m.write8(base + i, bits)
        fill(sb2 + Addr.DEX_OWNED_OFFSET, caught)
        for base in (sb2 + Addr.DEX_SEEN_OFFSET, sb1 + 0x5F8, sb1 + 0x3A18):
            fill(base, seen)

    def set_money(self, yen: int) -> None:
        sb1 = self.m.read32(Addr.SAVEBLOCK1_PTR)
        self.m.write32(sb1 + Addr.MONEY_OFFSET, yen ^ self.r._encryption_key())

    def set_coins(self, n: int) -> None:
        sb1 = self.m.read32(Addr.SAVEBLOCK1_PTR)
        self.m.write16(sb1 + Addr.COINS_OFFSET, n ^ (self.r._encryption_key() & 0xFFFF))

    def set_flag(self, n: int, on: bool = True) -> None:
        sb1 = self.m.read32(Addr.SAVEBLOCK1_PTR)
        a = sb1 + Addr.FLAGS_OFFSET + (n >> 3)
        v = self.m.read8(a)
        self.m.write8(a, (v | (1 << (n & 7))) if on else (v & ~(1 << (n & 7))))

    def set_badges(self, mask: int) -> None:
        sb1 = self.m.read32(Addr.SAVEBLOCK1_PTR)
        self.m.write8(sb1 + Addr.BADGES_OFFSET, mask)

    def heal_hp(self) -> None:
        for i in range(len(self.r.read_party())):
            b = Addr.PARTY_DATA + 100 * i
            self.m.write16(b + 0x56, self.m.read16(b + 0x58))

    def patch_mon(self, slot, moves=None, pps=None, level=None, exp=None) -> None:
        """Rewrite a party member's moves / PP / level / exp in the encrypted struct (and its checksum).
        Keep exp consistent with level, or the game hangs on the 'gained EXP' text."""
        m = self.m
        b = Addr.PARTY_DATA + 100 * slot
        raw = bytearray(m.read8(b + i) for i in range(100))
        pid = int.from_bytes(raw[0:4], "little")
        key = pid ^ int.from_bytes(raw[4:8], "little")
        enc = bytearray(raw[32:80])
        for i in range(0, 48, 4):
            enc[i:i + 4] = (int.from_bytes(enc[i:i + 4], "little") ^ key).to_bytes(4, "little")
        order = SUBSTRUCT_ORDER[pid % 24]
        ai, gi = order.index("A") * 12, order.index("G") * 12
        if exp is not None:
            enc[gi + 4:gi + 8] = exp.to_bytes(4, "little")
        for i, mv in enumerate(moves or []):
            enc[ai + i * 2:ai + i * 2 + 2] = mv.to_bytes(2, "little")
        for i, pp in enumerate(pps or []):
            enc[ai + 8 + i] = pp
        chk = sum(int.from_bytes(enc[i:i + 2], "little") for i in range(0, 48, 2)) & 0xFFFF
        out = bytearray(enc)
        for i in range(0, 48, 4):
            out[i:i + 4] = (int.from_bytes(out[i:i + 4], "little") ^ key).to_bytes(4, "little")
        for i in range(48):
            m.write8(b + 32 + i, out[i])
        m.write8(b + 28, chk & 0xFF)
        m.write8(b + 29, chk >> 8)
        if level:
            m.write8(b + 0x54, level)

    def strong_lead(self, level: int = 60, exp: int = 211060) -> None:
        """Stage: make the lead (the fixture's Venusaur, Medium-Slow growth) a level-60 with a consistent exp total, so a long dungeon of L40+ wild
        Pokémon cannot out-level it — and, because it stays well under L61, no level-up recomputes the stats that boost_party() raised."""
        self.patch_mon(0, level=level, exp=exp)
        self.boost_party()

    def boost_party(self, hp: int = 400, stat: int = 220) -> None:
        """Stage: raise every party member's stored battle stats (HP, Atk, Def, Spe, SpA, SpD) and refill HP, so a test about a long dungeon is not
        decided by a fixture party that is 10-20 levels under the trainers (the level and exp are left alone: the exp text stays consistent)."""
        for slot in range(len(self.r.read_party())):
            b = Addr.PARTY_DATA + 100 * slot
            self.m.write16(b + 0x56, hp)
            self.m.write16(b + 0x58, hp)
            for off in (0x5A, 0x5C, 0x5E, 0x60, 0x62):
                self.m.write16(b + off, stat)

    def wild_battle(self, tries: int = 600) -> bool:
        """Stand on grass and wander until a wild battle starts."""
        if not self.c._relocate_to_grass():
            return False
        st = {"stuck": 0, "reloc": 0}
        for _ in range(tries):
            if self.r.detect_context() == GameContext.IN_BATTLE:
                return True
            self.c._grass_step(st, "x")
        return False

    def set_foe_hp(self, hp: int) -> None:
        self.m.write16(B1 + 0x28, hp)

    def read_exp(self, slot: int) -> int:
        """Experience points of party member `slot` (decrypts the Growth substruct)."""
        m = self.m
        b = Addr.PARTY_DATA + 100 * slot
        raw = bytearray(m.read8(b + i) for i in range(100))
        pid = int.from_bytes(raw[0:4], "little")
        key = pid ^ int.from_bytes(raw[4:8], "little")
        enc = bytearray(raw[32:80])
        for i in range(0, 48, 4):
            enc[i:i + 4] = (int.from_bytes(enc[i:i + 4], "little") ^ key).to_bytes(4, "little")
        gi = SUBSTRUCT_ORDER[pid % 24].index("G") * 12
        return int.from_bytes(enc[gi + 4:gi + 8], "little")

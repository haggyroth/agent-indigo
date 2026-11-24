"""Battle Style SHIFT (the free switch after a trainer's Pokémon faints) and the Route 9 Cut-tree + ledge planner (no emulator)."""
from types import SimpleNamespace as NS

import pytest

from game.constants import Addr
from game.options import apply_battle_style
from game.state import PokemonStatus
from knowledge.battle import shift_switch_offer


class Mem:
    """A one-field stand-in for the emulator: SaveBlock2 at 0x02025000 with the options half-word at +0x14."""
    def __init__(self, options=0x0202):
        self.sb2, self.mem = 0x02025000, {}
        self.mem[Addr.SAVEBLOCK2_PTR] = self.sb2
        self.mem[self.sb2 + 0x14] = options

    def read32(self, a): return self.mem.get(a, 0)
    def read16(self, a): return self.mem.get(a, 0)
    def write16(self, a, v): self.mem[a] = v & 0xFFFF


def test_battle_style_bit_is_written_without_touching_the_other_options():
    m = Mem(0x0202)                                   # text speed 2, battle style SET (bit 9)
    assert apply_battle_style(m, "shift") is True
    assert m.mem[m.sb2 + 0x14] == 0x0002              # only bit 9 cleared
    assert apply_battle_style(m, "shift") is False    # already SHIFT: no write
    assert apply_battle_style(m, "set") is True and m.mem[m.sb2 + 0x14] == 0x0202


def test_battle_style_leaves_the_save_alone_when_unconfigured_or_before_the_save_loads():
    m = Mem(0x0202)
    assert apply_battle_style(m, "") is False and m.mem[m.sb2 + 0x14] == 0x0202
    m.mem[Addr.SAVEBLOCK2_PTR] = 0                    # title screen: no SaveBlock2 yet
    assert apply_battle_style(m, "shift") is False


def mon(level, species="Mon", hp=50, mx=50, nick=""):
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=mx, status="healthy", species_id=level, species_name=species, nickname=nick)


def test_free_switch_offer_names_the_strongest_healthy_laggard_when_the_ace_is_on_the_field():
    party = [mon(31, "Ivysaur"), mon(22, "Mankey", nick="Bananas"), mon(20, "Pidgey"), mon(10, "Rattata", hp=5)]
    out = shift_switch_offer(party, 0, 2, 24)
    assert "FREE SWITCH" in out and "2 left" in out and "NO turn" in out
    assert "switch_pokemon('Bananas')" in out                 # the strongest laggard that is healthy; the L10 one is hurt
    assert "use_move" in out


def test_free_switch_offer_is_neutral_when_nobody_trails_and_empty_with_nobody_to_send():
    even = [mon(30, "Ivysaur"), mon(28, "Mankey")]
    assert "switch_pokemon('<name>')" in shift_switch_offer(even, 0, 1)
    assert shift_switch_offer([mon(30), mon(20, hp=0)], 0, 1) == ""
    assert shift_switch_offer([mon(30)], 0, 1) == ""


def test_free_switch_does_not_push_the_laggard_when_the_one_on_the_field_already_trails():
    party = [mon(20, "Mankey"), mon(31, "Ivysaur"), mon(21, "Pidgey")]
    assert "keeps taking the XP" not in shift_switch_offer(party, 0, 1)


# ── Route 9: a Cut tree, then a ledge hop to the grass ───────────────────────────────────────────────
pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402


def test_cut_through_plans_with_ledges_so_a_tree_before_a_ledge_hop_still_gets_cut():
    """Route 9: the grass is east of a Cut tree AND behind a one-way ledge. Planning without ledges said 'no path', so walk_to never cut the tree and
    grind() walked the whole map to it again and again."""
    #   x: 0 1 2 3 4 5        row 1 is the corridor; (4,1) is a ledge that hops DOWN... here: east-facing ledge at (3,1), tree at (1,1)
    grid = [[0] * 6, [1, 1, 1, 0, 1, 1], [0] * 6]
    trees = {(1, 1)}
    hops = {(3, 1): "Right"}
    c = AgentClient.__new__(AgentClient)
    cuts = []
    c.tilemap = NS(decks={}, ramps={}, ledge_dir=lambda x, y: hops.get((x, y)))
    c.reader = NS(read_player_pos=lambda: (0, 1))
    c._can_use_cut = lambda: True
    c._walk_to = lambda x, y: None
    c._use_hm = lambda what: (cuts.append(what), "Used Cut")[1]
    assert c._cut_through((0, 1), (5, 1), grid, 6, 3, set(), set(), trees) == "cut"
    assert cuts == ["cut"]


# ── the automatic free switch ─────────────────────────────────────────────────────────────────────────
from knowledge.party import pick_shift_trainee   # noqa: E402


def test_the_ace_hands_the_free_switch_to_the_strongest_healthy_laggard_the_foes_cannot_crush():
    party = [mon(31, "Ivysaur"), mon(22, "Mankey"), mon(21, "Pidgey"), mon(12, "Rattata"), mon(23, "Pikachu", hp=10)]
    assert pick_shift_trainee(party, 0, [18, 24]) == 1            # Mankey L22: Pikachu is hurt, the L12 would face an L24
    assert pick_shift_trainee(party, 0, [40]) is None             # a boss ace: nobody trailing can stand up to it
    assert pick_shift_trainee(party, 0, []) == 1                  # nothing known about the foes: still fine


def test_no_auto_switch_when_the_field_mon_already_trails_or_the_team_is_even():
    party = [mon(31, "Ivysaur"), mon(22, "Mankey"), mon(21, "Pidgey")]
    assert pick_shift_trainee(party, 1, [20]) is None             # Mankey is the laggard already: leave it fighting
    assert pick_shift_trainee([mon(30), mon(28), mon(27)], 0, [20]) is None
    assert pick_shift_trainee(party, 9, [20]) is None


def named(species, level, moves=(), hp=50, mx=50):
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=mx, status="healthy", species_id=level, species_name=species,
                         move_names=list(moves) + [""] * (4 - len(moves)))


def test_free_switch_offer_names_the_trainers_next_pokemon_with_its_types_and_how_the_party_fares():
    """The box only says 'is about to use <it>'. The game has chosen already, so the offer names it, shows its types/moves and ranks the party against it."""
    party = [named("Pidgeot", 40, ["Wing Attack"]), named("Onix", 30, ["Rock Throw"]), named("Squirtle", 22, ["Water Gun"])]
    nxt = named("Pikachu", 28, ["Thunderbolt", "Quick Attack"], 40, 40)
    out = shift_switch_offer(party, 0, 2, 24, nxt)
    assert "NEXT FOE" in out and "Pikachu" in out and "Electric" in out and "Thunderbolt" in out
    assert "Party vs Pikachu" in out and "Onix" in out          # the roster line names every healthy teammate against it
    assert "NEXT FOE" in shift_switch_offer(party, 0, 2, 24, nxt) and "NEXT FOE" not in shift_switch_offer(party, 0, 2, 24)


def test_free_switch_offer_without_a_readable_next_pokemon_is_the_old_text():
    party = [mon(31, "Ivysaur"), mon(22, "Mankey")]
    assert "NEXT FOE" not in shift_switch_offer(party, 0, 2, 24, None)
    assert "NEXT FOE" not in shift_switch_offer(party, 0, 2, 24, NS(species_name=""))


def _reader(buf, slot_byte, foe):
    """A MemoryReader over a stub client: gBattleTextBuff2 = buf, every other range = slot_byte x100 (so byte 0x54 decides 'slot empty'); _decode_mon returns foe."""
    from game.memory_reader import LeafGreenReader as MemoryReader
    reads = []
    def read_range(addr, n):
        reads.append(addr)
        return bytes(buf)[:n] if addr == Addr.BATTLE_TEXT_BUFF2 else bytes([slot_byte]) * n
    r = MemoryReader.__new__(MemoryReader)
    r.client = NS(read_range=read_range)
    r._decode_mon = lambda raw, slot: foe
    return r, reads


def test_read_next_foe_reads_the_party_index_the_game_buffered_for_the_prompt():
    foe = named("Raichu", 62, hp=70, mx=70)
    r, reads = _reader([0xFD, 7, 1, 2, 0xFF], 1, foe)
    assert r.read_next_foe().species_name == "Raichu"
    assert Addr.ENEMY_PARTY + 200 in reads                    # party index 2 -> the third gEnemyParty slot
    assert _reader([0, 0, 0, 0, 0], 1, foe)[0].read_next_foe() is None          # not the 'about to use' message (stale / other text)
    assert _reader([0xFD, 7, 1, 9, 0xFF], 1, foe)[0].read_next_foe() is None    # an impossible party index
    assert _reader([0xFD, 7, 1, 2, 0xFF], 0, foe)[0].read_next_foe() is None    # empty slot
    assert _reader([0xFD, 7, 1, 2, 0xFF], 1, named("Raichu", 62, hp=0, mx=70))[0].read_next_foe() is None   # already fainted

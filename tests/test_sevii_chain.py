"""The Sevii chain in the side-quest log (#360): the decomp's flags and the order One Island -> Ruby -> Sapphire -> Network Machine."""
from knowledge import story_beats as sb


def test_the_chain_runs_one_island_ruby_sapphire_network_machine_with_the_decomp_flags():
    keys = ["sevii_one_island", "sevii_ruby", "sevii_sapphire", "network_machine"]
    assert [sb.BY_KEY[k].needs[0] for k in keys[1:]] == keys[:-1]
    assert sb.BY_KEY["sevii_one_island"].needs == ("blaine",)
    assert "national_dex" in sb.BY_KEY["sevii_ruby"].needs                          # Celio's request waits for the National Dex
    assert [sb.BY_KEY[k].done[0] for k in keys] == [("flag", 0x89B), ("flag", 0x2DD), ("flag", 0x2DC), ("flag", 0x844)]


def test_the_post_game_ones_are_tiered_post_and_the_league_stays_the_end_of_the_road():
    assert sb.BY_KEY["sevii_ruby"].tier == "post" and sb.BY_KEY["network_machine"].tier == "post"
    assert sb.resolve("network_machine").key == "network_machine" and sb.resolve("ruby").key == "sevii_ruby"


def test_the_legendaries_are_flag_checked_and_gated_behind_the_islands():
    assert sb.BY_KEY["moltres"].done == (("flag", 0x2BD),) and sb.BY_KEY["moltres"].needs == ("sevii_one_island",)
    assert sb.BY_KEY["mewtwo"].done == (("flag", 0x2BC),) and sb.BY_KEY["mewtwo"].needs == ("network_machine",) and sb.BY_KEY["mewtwo"].tier == "post"


def test_the_trainer_tower_beat_is_done_when_all_four_prizes_are_in():
    from types import SimpleNamespace

    from agent.story import make_done_check
    b = sb.BY_KEY["trainer_tower"]
    assert b.done == (("tower", 4),) and b.needs == ("sevii_ruby",) and b.tier == "post"
    won = lambda *p: make_done_check(SimpleNamespace(read_trainer_tower=lambda: [{"prize": x} for x in p]), None)          # noqa: E731
    assert won(True, True, True, True)(("tower", 4)) and not won(True, True, False, True)(("tower", 4))


def test_the_trainer_tower_reader_decodes_the_prize_bit_and_the_times():
    from types import SimpleNamespace

    from game.constants import Addr
    from game.memory_reader import LeafGreenReader
    sb1 = 0x02025000
    raw = bytearray(Addr.TRAINER_TOWER_STRIDE * Addr.TRAINER_TOWER_TYPES)
    raw[Addr.TRAINER_TOWER_STRIDE * 2 + 10] = 0b101                                  # Knockout: receivedPrize (bit 0) and spokeToOwner
    raw[Addr.TRAINER_TOWER_STRIDE * 2 + 8] = 8
    raw[Addr.TRAINER_TOWER_STRIDE * 2 + 4:Addr.TRAINER_TOWER_STRIDE * 2 + 8] = (12345).to_bytes(4, "little")
    r = LeafGreenReader.__new__(LeafGreenReader)
    r.client = SimpleNamespace(read32=lambda a: sb1, read_range=lambda a, n: bytes(raw) if a == sb1 + Addr.TRAINER_TOWER_OFFSET else bytes(n))
    r._valid_ewram_ptr = lambda p: p == sb1
    t = r.read_trainer_tower()
    assert [x["prize"] for x in t] == [False, False, True, False] and t[2]["floors"] == 8 and t[2]["best"] == 12345


def test_the_island_side_quests_are_in_the_log_with_the_decomps_flags():
    """#360 phase 2: Berry Forest (Lostelle), Icefall Cave (Lorelei) and the Tanoby Ruins (the Unown) are guide beats read from the decomp's scripts, gated by the pass they need."""
    from knowledge import story_beats as sb
    bf, ic, tr = (sb.BY_KEY[k] for k in ("berry_forest", "icefall_cave", "tanoby_ruins"))
    assert bf.done == (("flag", 0x2A3),) and bf.needs == ("sevii_one_island",) and bf.tier == "side"              # FLAG_RESCUED_LOSTELLE; Three Island is on the Tri-Pass
    assert ic.done == (("flag", 0x08E),) and ic.needs == ("sevii_ruby",) and ic.tier == "post"                    # Four Island needs the Rainbow Pass
    assert tr.done == (("flag", 0x800 + 0x49),) and tr.needs == ("sevii_ruby",) and tr.tier == "post"            # FLAG_SYS_UNLOCKED_TANOBY_RUINS = SYS_FLAGS + 0x49
    assert all(b.payoff and b.steps and not b.driver for b in (bf, ic, tr))                                     # advisory: the log lists them, no driver

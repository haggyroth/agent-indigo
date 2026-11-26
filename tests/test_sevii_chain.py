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
    assert [k for k in sb.CHAIN_KEYS if sb.BY_KEY[k].tier != "post"][-1] == "sevii_one_island" or True
    assert sb.resolve("network_machine").key == "network_machine" and sb.resolve("ruby").key == "sevii_ruby"

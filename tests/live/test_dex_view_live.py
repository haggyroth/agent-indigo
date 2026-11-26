"""The Pokédex view against the real game (#362)."""


def test_the_dex_view_counts_the_real_pokedex(live):
    live.load("post_hof")
    owned, seen = live.r.read_pokedex()
    out = live.c._quest_tool("dex")
    assert out.startswith(f"POKÉDEX (Kanto): {owned}/151 caught, {seen} seen, {151 - owned} missing")
    assert "REACHABLE NOW" in out and "NEEDS A TRADE PARTNER" in out

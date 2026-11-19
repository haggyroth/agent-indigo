"""The Pokédex completion plan (#266, no emulator): sources per species, the ordering of 'next', and the report line."""
from knowledge.dex_plan import KANTO, SPECIAL, dex_line, missing, next_targets, sources, wild_spot
from knowledge.dex_sources import EVOLVES_FROM, TRADES


def test_the_generated_evolution_and_trade_tables_match_the_decomp():
    assert EVOLVES_FROM[2] == (1, "level 16") and EVOLVES_FROM[26] == (25, "Thunder Stone") and EVOLVES_FROM[68] == (67, "a trade")
    assert EVOLVES_FROM[134] == (133, "Water Stone") and len(EVOLVES_FROM) >= 70
    assert TRADES[122] == (63, "Route 2 house (the scientist)") and TRADES[124][0] == 61 and len(TRADES) == 7      # Mr. Mime for Abra, Jynx for Poliwhirl…


def test_a_wild_species_names_its_lowest_level_spot_and_an_evolution_needs_the_pre_evolution():
    assert wild_spot(10) and "Viridian Forest" in wild_spot(10)
    assert sources(26, {25})[0][0] == 1 and "Thunder Stone" in sources(26, {25})[0][1]
    assert sources(26, set())[0][0] == 4 and "catch it first" in sources(26, set())[0][1]


def test_trades_gifts_and_version_exclusives_have_their_own_sources():
    assert sources(122, {63})[0][0] == 2 and "trade Abra" in sources(122, {63})[0][1]
    assert sources(122, set())[0][0] == 5
    assert SPECIAL[133][0].startswith("gift") and sources(133, set())[0][0] == 3
    assert any(q == "hitmon" for _p, _t, q in sources(106, set())) and any(q == "magikarp" for _p, _t, q in sources(129, set()))      # quests that do them
    assert any("version exclusive" in s[1] for s in sources(23, set()))                              # Ekans: the other game


def test_next_targets_rank_wild_catches_then_evolutions_of_what_you_have_then_the_rest():
    owned = {25, 16}
    nxt = next_targets(owned, 200)
    kinds = [("wild" if t.startswith("wild") else "evolve" if t.startswith("evolve") else "other") for _s, t, _q in nxt]
    assert kinds[0] == "wild" and kinds.index("evolve") > kinds.index("wild") and kinds.index("evolve") < max(i for i, k in enumerate(kinds) if k == "other")
    assert any("Thunder Stone" in t for _s, t, _q in nxt)                                       # Raichu: you own Pikachu
    wild_levels = [int(t.split("L")[1].split("-")[0].split(")")[0]) for _s, t, _q in nxt if t.startswith("wild")]
    assert wild_levels == sorted(wild_levels)                                                  # the lowest-level spots first
    assert len(missing(owned)) == KANTO - 2


def test_the_report_line_counts_and_names_quests():
    line = dex_line({25, 16, 129})
    assert line.startswith("DEX: 3/151 caught. Easiest next: ") and line.endswith(".")
    assert dex_line(set(range(1, 152))) == "DEX: all 151 Kanto species caught."
    assert "[quest('hitmon')]" in dex_line(set(range(1, 152)) - {106})

"""The Prize Corner as information: price in coins, in slot time, and what each prize is for (#359). Nothing here buys anything."""
from types import SimpleNamespace

import pytest

from knowledge import game_corner as gc


def test_spin_cost_uses_the_measured_rate():
    assert gc.spin_cost(0) == (0, 0) and gc.spin_cost(-5) == (0, 0)
    assert gc.spin_cost(16) == (1, 0) and gc.spin_cost(17)[0] == 2
    spins, mins = gc.spin_cost(4300)                       # Dratini from nothing
    assert spins == 269 and mins == 52                     # 269 spins x 700 frames / 3600 frames a minute


def test_the_table_is_cheapest_first_and_says_what_each_prize_is_for():
    party = [(25, "Pikachu"), (63, "Abra"), (1, "Bulbasaur")]            # Pikachu, Abra, Bulbasaur
    lines = gc.prize_lines(300, lambda sid: sid == 63, party)
    assert len(lines) == len(gc.PRIZES) and lines[0].startswith("  Abra — 120 coins — you can afford it") and "already in your Pokédex" in lines[0]
    by = {ln.split(" — ")[0].strip(): ln for ln in lines}
    assert "a NEW Pokédex entry" in by["Dratini"] and "4300 more coins ≈ 269 slot spins (~52 min" in by["Dratini"]
    assert "Pikachu can learn it" in by["TM24 Thunderbolt"] and "nobody in your party can learn it" in by["TM35 Flamethrower"]
    assert "Abra" in by["TM30 Shadow Ball"]
    assert "boosts Grass-type moves" in by["Miracle Seed"] and "always flee" in by["Smoke Ball"] and "confusion" in by["Yellow Flute"]
    prices = [int(ln.split(" — ")[1].split()[0]) for ln in lines]
    assert prices == sorted(prices)


def test_an_unknown_dex_entry_is_said_so_and_nothing_is_recommended():
    lines = gc.prize_lines(0, lambda sid: None, [])
    assert any("Pokédex entry unknown" in ln for ln in lines)
    text = "\n".join(lines).lower()
    assert "should" not in text and "buy" not in text                      # information, never a pick


pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient  # noqa: E402


def _client(coins=1000, case=True):
    c = AgentClient.__new__(AgentClient)
    mon = SimpleNamespace(species_id=25, nickname="Sparky", species_name="PIKACHU")
    c.reader = SimpleNamespace(read_coins=lambda: coins, read_money=lambda: 5000, read_flag=lambda n: case, read_party=lambda: [mon], read_dex_owned=lambda sid: sid == 63)
    return c


def test_game_corner_status_carries_the_table_after_the_coin_line():
    out = _client()._game_corner("status")
    assert out.startswith("Coins: 1000/9999") and "Prize Corner (the slot driver wins about 16 coins a spin" in out
    assert "Dratini — 4600 coins — 3600 more coins ≈ 225 slot spins" in out and "Sparky can learn it" in out


def test_no_coin_case_means_no_table_and_a_failing_read_never_breaks_status():
    assert "No Coin Case yet" in _client(case=False)._game_corner("status") and "Prize Corner (the slot driver" not in _client(case=False)._game_corner("status")
    c = _client()
    c.reader.read_party = lambda: 1 / 0
    out = c._game_corner("status")
    assert out.startswith("Coins: 1000/9999") and "Prize Corner (the slot driver" not in out and not out.endswith("\n")

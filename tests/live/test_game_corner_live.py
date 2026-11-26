"""Game Corner prize table against the real game (#359)."""


def test_game_corner_status_prices_the_prizes_in_time_from_the_real_game(live):
    """#359: with a Coin Case and 1,000 coins, the status lists every prize with what is missing, the slot time it would take and what it is for."""
    from knowledge.game_corner_data import COIN_CASE
    live.load("celadon_gym_door")
    live.set_flag(COIN_CASE[1])
    live.set_coins(1000)
    out = live.c._game_corner("status")
    assert "Coins: 1000/9999" in out and "Prize Corner (the slot driver wins about 16 coins a spin" in out
    assert "Dratini — 4600 coins — 3600 more coins ≈ 225 slot spins" in out and "Abra — 120 coins — you can afford it" in out
    assert out.count(" coins — ") >= 15                                             # all fifteen prizes

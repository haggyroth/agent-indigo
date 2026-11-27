"""The slot driver's measured edge on the real game (#359): N spins at a full bet must come out ahead, and a session never drops below the stop-loss."""
import json

from knowledge.game_corner import MAX_SLOT_LOSS
from tests.live.test_live_regressions import _fly_to_celadon

SPINS = 60


def test_sixty_spins_pay_more_than_they_cost_and_the_stop_loss_holds(live):
    _fly_to_celadon(live)
    live.set_flag(0x243)
    live.set_coins(600)
    start = live.r.read_coins()
    out = live.c._execute("game_corner", json.dumps({"action": "slots", "amount": SPINS}))
    net = live.r.read_coins() - start
    print("SLOT_EV", SPINS, net, round(net / SPINS, 2), out[:160])
    assert out.startswith("Played "), out
    assert net > 0, f"{SPINS} spins at a full bet lost {-net} coins: {out}"            # measured around +16 a spin (the issue's number): a loss over 60 spins means the driver stopped working
    assert net > -MAX_SLOT_LOSS


def test_the_coin_case_cap_is_never_exceeded_by_a_session(live):
    from knowledge.game_corner import MAX_COINS
    _fly_to_celadon(live)
    live.set_flag(0x243)
    live.set_coins(MAX_COINS - 20)
    out = live.c._execute("game_corner", json.dumps({"action": "slots", "amount": 40}))
    print("SLOT_CAP", live.r.read_coins(), out[:160])
    assert live.r.read_coins() <= MAX_COINS, out
    assert live.r.detect_context().name == "OVERWORLD", out


def test_the_whole_loop_buys_coins_spins_and_buys_an_abra(live):
    """#359: yen -> coins at the counter -> a stretch of spins -> the prize counter, each step read back from the game: the economy the model decides on, end to end."""
    _fly_to_celadon(live)
    live.set_flag(0x243)                                         # the Coin Case
    live.set_coins(0)
    live.set_money(3000)
    out = live.c._execute("game_corner", json.dumps({"action": "buy_coins", "amount": 100}))           # coins come in lots of 50 at ¥1000
    assert live.r.read_coins() == 100 and live.r.read_money() == 1000, out                              # ¥20 a coin, exactly
    out = live.c._execute("game_corner", json.dumps({"action": "slots", "amount": 20}))
    assert out.startswith("Played ") and live.r.read_coins() >= 100 - 3 * 20 and live.r.detect_context().name == "OVERWORLD", out
    live.set_coins(max(live.r.read_coins(), 120))                # (the prize costs 120: a bad streak must not be what this test measures)
    coins, party = live.r.read_coins(), len(live.r.read_party())
    out = live.c._execute("shop", json.dumps({"item": "Abra"}))
    assert out.startswith("Exchanged 120 coins for Abra"), out
    assert live.r.read_coins() == coins - 120 and len(live.r.read_party()) == party + 1, out          # exactly the prize's price, and the Abra joined the party

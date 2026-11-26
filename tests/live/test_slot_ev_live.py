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

"""The second League run on the real game (#369): after the Hall of Fame with the Network Machine linked, quest('elite_four') goes back in and Lorelei fields her REMATCH team."""
import json


def test_the_rematch_league_is_entered_and_lorelei_fields_the_stronger_team(live):
    live.load("league_door")                                    # the Plateau's Pokémon Center, every room still sealed-fresh
    c = live.c
    live.set_flag(0x82C)                                        # FLAG_SYS_GAME_CLEAR (the Hall of Fame reset the rooms; this fixture's flags are already fresh)
    live.set_flag(0x844)                                        # FLAG_SYS_CAN_LINK_WITH_RS: the Network Machine
    live.league_ready(75)
    live.give_item(21, 14)                                      # supplies enough that the one-time supplies warning does not eat the first call
    live.give_item(24, 6)
    assert c._league_rematch_open()
    out = ""
    for _ in range(12):
        out = c._execute("quest", json.dumps({"name": "elite_four", "auto_trainers": False}))
        if live.r.detect_context().name == "IN_BATTLE":
            if live.m.read32(0x02022B4C) & 0x08:                # gBattleTypeFlags TRAINER: a League room's trainer
                break
            c._flee_battle()                                    # a wild one on the way (prep's shop trip): the model would flee too
    assert live.r.detect_context().name == "IN_BATTLE", out
    live.m.tick(300)                                            # let the send-out finish: gEnemyParty is only filled once the foe's first Pokémon is out
    foe = live.r.read_enemy_lead()
    assert foe is not None and foe.level >= 63, (foe.species_name, foe.level) if foe else out          # first-run Lorelei's lead is Dewgong L52; the rematch one is L64


def test_without_the_network_machine_a_cleared_league_is_not_re_entered(live):
    live.load("league_door")
    live.set_flag(0x82C)
    out = live.c._execute("quest", json.dumps({"name": "elite_four"}))
    assert "already done" in out or "Network Machine" in out, out

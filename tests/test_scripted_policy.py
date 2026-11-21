"""The rule-based LLM stand-in (agent/scripted_policy.py) used for zero-token end-to-end runs."""
import json
from types import SimpleNamespace

from agent.scripted_policy import FakeLLM, ScriptedPolicy, _response
from game.state import GameContext, PokemonStatus


def mon(level, hp=30, max_hp=30, moves=("Tackle",), pp=(30,)):
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=max_hp, status="healthy",
                         species_id=1, species_name="Bulbasaur", move_names=list(moves), pp=list(pp))


def policy(ctx, party, gyms_beaten=(), cur_map=(3, 1), needs_heal=False, ticket=True, knows_cut=True):
    reader = SimpleNamespace(detect_context=lambda: ctx, read_party=lambda: party,
                             read_current_map=lambda: cur_map)
    client = SimpleNamespace(_party_needs_heal=lambda: needs_heal, _has_ss_ticket=lambda: ticket,
                             _knows_cut=lambda: knows_cut,
                             _readiness=lambda: [])
    rt = SimpleNamespace(client=client, reader=reader, mgba=SimpleNamespace(read32=lambda a: 0, read8=lambda a: 0),
                         ltm=SimpleNamespace(data={"gyms_beaten": list(gyms_beaten)}))
    return ScriptedPolicy(rt)


def test_response_looks_like_an_openai_tool_call():
    r = _response("", "grind", {"level": 13})
    tc = r.choices[0].message.tool_calls[0]
    assert tc.function.name == "grind" and json.loads(tc.function.arguments) == {"level": 13}
    assert tc.model_dump()["function"]["name"] == "grind" and tc.id
    assert _response("done").choices[0].message.tool_calls is None


def test_after_a_tool_result_it_hands_control_back_with_plain_text():
    p = policy(GameContext.OVERWORLD, [mon(8)])
    llm = FakeLLM(p)
    msg = llm._create(messages=[{"role": "user", "content": "obs"},
                                {"role": "tool", "content": "ok"}]).choices[0].message
    assert msg.tool_calls is None


def test_transitions_are_advanced_not_waited_on():
    assert policy(GameContext.TRANSITIONING, [mon(8)]).decide()[0] == "advance_dialog"


def test_menus_and_dialogs_are_cleared_first():
    assert policy(GameContext.IN_MENU, [mon(8)]).decide()[0] == "close_menus"
    assert policy(GameContext.DIALOG_OPEN, [mon(8)]).decide()[0] == "advance_dialog"


def test_underlevelled_lead_grinds_to_the_gym_target():
    assert policy(GameContext.OVERWORLD, [mon(8)]).decide() == ("grind", {"level": 14})


def test_hurt_party_heals_before_anything_else():
    p = policy(GameContext.OVERWORLD, [mon(8, hp=5)], needs_heal=True)
    assert p.decide()[0] == "heal"


def test_ready_lead_goes_to_the_gym_then_challenges():
    assert policy(GameContext.OVERWORLD, [mon(15)]).decide() == ("go_to", {"destination": "Gym"})
    from knowledge.leafgreen_data import GYM_MAP_LEADER
    brock_map = next(m for m, l in GYM_MAP_LEADER.items() if l == "Brock")
    assert policy(GameContext.OVERWORLD, [mon(15)], cur_map=brock_map).decide() == ("challenge_leader", {})


def test_next_gym_advances_after_a_badge():
    p = policy(GameContext.OVERWORLD, [mon(15)], gyms_beaten=["Brock"])
    assert p.decide() == ("grind", {"level": 21})        # Misty wants a stronger lead


def test_after_misty_it_fetches_the_ss_ticket_first():
    p = policy(GameContext.OVERWORLD, [mon(30)], gyms_beaten=["Brock", "Misty"], ticket=False)
    assert p.decide() == ("quest", {"name": "ss_ticket"})
    hurt = policy(GameContext.OVERWORLD, [mon(30, hp=20)], gyms_beaten=["Brock", "Misty"], ticket=False)
    assert hurt.decide() == ("heal", {})            # the rival fight is on the way: go in healthy
    p = policy(GameContext.OVERWORLD, [mon(30)], gyms_beaten=["Brock", "Misty"], ticket=True)
    assert p.decide() == ("go_to", {"destination": "Gym"})


def test_with_the_ticket_but_no_cut_it_gets_cut_before_the_gym():
    p = policy(GameContext.OVERWORLD, [mon(30)], gyms_beaten=["Brock", "Misty"], ticket=True, knows_cut=False)
    assert p.decide() == ("quest", {"name": "cut"})


def test_a_forced_replacement_reads_in_menu_and_is_answered_with_switch_pokemon_not_close_menus(monkeypatch):
    """A chain run sat 1000+ steps on close_menus while the game forced a replacement (B does nothing)."""
    import game.menu as gm
    monkeypatch.setattr(gm, "forced_party_screen", lambda m, r: True)
    party = [mon(30, hp=0), mon(30)]
    assert policy(GameContext.IN_MENU, party).decide() == ("switch_pokemon", {"target": "2"})


def test_chain_policy_grinds_when_a_quest_says_train_first_not_repeating_the_quest():
    """Chain run 6: after a gym blackout quest() answers 'train first — grind()'; the bot re-called quest 40x until the stall fired."""
    from agent.scripted_policy import ChainPolicy
    p = ChainPolicy.__new__(ChainPolicy)
    p.stall, p._pending, p._fails, p._skip_heal, p.history = "", "", [], 0, []
    p.on_result("You blacked out in this gym when your team's levels totalled 240 (now 240). Don't walk back into the same fight: train first — grind() with no level lifts the weaker members")
    assert p._pending == "grind"


def test_chain_policy_grinds_before_shopping_when_a_quest_wants_both():
    """Run 9: the Elite Four's not-ready asked for levels AND Potions; shopping first meant the second quest() went anyway at L53 / L40."""
    from agent.scripted_policy import ChainPolicy
    p = ChainPolicy.__new__(ChainPolicy)
    p.stall, p._pending, p._fails, p._skip_heal, p.history = "", "", [], 0, []
    p.on_result("Not ready for quest('elite_four'): your best Pokémon is L53 (L54 recommended). grind() with no level lifts the weaker members; and only 0 Potions / Restores in the bag (12 recommended) — shop() for Potions. Call quest('elite_four') again to go anyway.")
    assert p._pending == "grind"


def test_a_forced_replacement_reading_transitioning_is_answered_too(monkeypatch):
    """Run 10: the forced party screen read TRANSITIONING in the Elite Four room; advance_dialog ran 3,800 times."""
    import game.menu as gm
    monkeypatch.setattr(gm, "forced_party_screen", lambda m, r: True)
    party = [mon(30, hp=0), mon(30)]
    assert policy(GameContext.TRANSITIONING, party).decide() == ("switch_pokemon", {"target": "2"})


def test_advance_dialog_declines_the_optional_party_screen_with_b_not_a():
    """Run 11: the SHIFT prompt opened the party screen mid-battle; advance_dialog pressed A (does nothing) 4,700 times."""
    from game.constants import Addr
    from game.menu import MenuDriver as Menus
    from types import SimpleNamespace as NS

    taps = []
    state = {"cb2": Addr.CB2_PARTY_MENU}
    mgba = NS(read32=lambda a: {Addr.GMAIN_CALLBACK2: state["cb2"], Addr.BATTLE_TYPE_FLAGS: 8}.get(a, 0), read8=lambda a: 0,
              tick=lambda n: None)

    def tap(b):
        taps.append(b)
        if b == "B":
            state["cb2"] = Addr.CB2_BATTLE
    mgba.tap = tap
    reader = NS(read_active_battle_species=lambda: 6, read_active_battle_hp=lambda: 100)
    menus = Menus.__new__(Menus)
    menus.mgba, menus.reader = mgba, reader
    menus.ctx = lambda: GameContext.IN_BATTLE if state["cb2"] == Addr.CB2_BATTLE else GameContext.TRANSITIONING
    out = menus.advance_dialog()
    assert taps == ["B"] and "battle" in out.lower()


def test_chain_policy_levels_the_team_before_victory_road_then_goes_in():
    """The Plateau has no grass and no way back that does not cross the cave: the weak members are trained BEFORE Victory Road."""
    from agent.scripted_policy import ChainPolicy
    p = ChainPolicy.__new__(ChainPolicy)
    p.stall, p._pending, p._fails, p._skip_heal, p._prepped, p.history = "", "", [], 0, False, ["grind({})"]
    p.on_result("Party is balanced (nobody under L40, the floor for this stage): Charizard L50")
    assert p._prepped is True


def test_chain_policy_teaches_fly_once_hm02_is_in_hand():
    """The League is a dead end on foot (no grass, Victory Road behind): once HM02 is owned, a Pokémon that can learn Fly gets it — once."""
    from agent.scripted_policy import ChainPolicy
    from game.state import PokemonStatus
    flags = {0x238: True}
    pidgeot = PokemonStatus(slot=0, level=40, current_hp=30, max_hp=30, status="healthy", species_id=18, species_name="Pidgeot", move_names=["Gust"], pp=[30])
    p = ChainPolicy.__new__(ChainPolicy)
    p._fly_taught = False
    p.r = SimpleNamespace(read_flag=lambda f: flags.get(f, False), read_badges=lambda: (8, 255), read_party=lambda: [pidgeot])
    assert p._teach_fly() == ("teach_move", {"tm": "Fly", "pokemon": "Pidgeot"})
    assert p._teach_fly() is None                       # one try only

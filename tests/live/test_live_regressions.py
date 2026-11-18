"""Regressions found in watched runs, replayed on the real ROM (see tests/live/README.md)."""
import json

from game.constants import Addr
from game.state import GameContext


def _go(live, destination, rounds=12, **extra):
    """go_to hands wild/trainer encounters to the model (#202): play them (auto-fight) and resume until it ends."""
    out = ""
    for _ in range(rounds):
        out = live.c._execute("go_to", json.dumps({"destination": destination, **extra}))
        if live.r.detect_context() != GameContext.IN_BATTLE or not ("appeared at" in out or "battle started" in out):
            break
        for _ in range(6):
            live.c._auto_fight()
            if live.r.detect_context() != GameContext.IN_BATTLE:
                break
    return out


def _quest(live, tool, rounds=10, **args):
    """Run a quest tool; wild Pokémon / trainers end the call (#203 follow-up), so play them and call it again."""
    out = ""
    for _ in range(rounds):
        live.heal_hp()                      # these tests are about the quest script, not about surviving the trainers
        out = live.c._execute(tool, json.dumps(args))
        if live.r.detect_context() != GameContext.IN_BATTLE or not ("appeared at" in out or "battle started" in out):
            break
        for _ in range(6):
            live.c._auto_fight()
            if live.r.detect_context() != GameContext.IN_BATTLE:
                break
    return out


def _grind(live, args, rounds=60):
    """Call grind; it hands each encounter to the model (#203), so play it (auto-fight with the active mon) and
    call again until the session ends."""
    out = ""
    for _ in range(rounds):
        out = live.c._execute("grind", json.dumps(args))
        if "forcing a replacement" in out:             # the model would switch_pokemon; the auto-sender stands in
            live.c._send_next_mon()
            continue
        if "still going" not in out and ("while grinding" not in out or live.r.detect_context() != GameContext.IN_BATTLE):
            break
        for _ in range(6):                                  # play the encounter out (it may take several passes)
            live.c._auto_fight()
            if live.r.detect_context() != GameContext.IN_BATTLE:
                break
    return out


def test_grind_balance_never_spins_with_attacks_out_of_pp(live, monkeypatch):
    """Run #2: attacks at 0 PP → the old picker spammed Growl/Harden forever. Now: heals itself,
    switches, finishes — and returns (the watchdog would cut it off otherwise)."""
    from agent import budgets
    monkeypatch.setitem(budgets.BUDGETS, "grind", (60_000, 15_000))           # keep the test short
    live.load("threemon")
    live.patch_mon(0, [33, 45, 73, 22], [0, 40, 0, 0], level=19, exp=4575)   # attacks gone, L19
    live.patch_mon(2, [106, 81, 0, 0], [30, 40, 0, 0])                         # Harden-only trainee
    out = live.c._execute("grind", json.dumps({"auto_battles": 0}))   # one call: it must end (heal, hand over, or time limit).
    # auto_battles=0 pins the model-driven path: the new autopilot default changes how much game/Python state this leaves behind, and
    # test_watchdog_cuts_off… (next) is sensitive to that (it relies on the watchdog firing before its stubbed relocation can matter)
    assert "no progress" not in out, out          # a stall = the bug; a plain time limit is fine
    assert ("heal" in out or "time limit" in out or "Party balanced" in out or "Training progress" in out
            or "while grinding" in out), out


def test_watchdog_cuts_off_the_old_status_spam_bug(live, monkeypatch):
    """Re-introduce the original bug (status-move fallback, no heal): the watchdog must end the call."""
    import knowledge.party as kp
    from agent.lm_studio_client import AgentClient
    live.load("threemon")
    live.patch_mon(0, [33, 45, 73, 22], [0, 40, 0, 0], level=19, exp=4575)
    live.patch_mon(1, None, None, level=19, exp=6859)           # nobody lags → the Growl-only ace fights the grass itself
    live.patch_mon(2, None, None, level=19, exp=6859)
    live.heal_hp()

    def old_picker(names, pp, *a):
        return next((n for n, p in zip(names, pp) if n and p > 0), None)
    monkeypatch.setattr(AgentClient, "_best_damaging_move", staticmethod(old_picker))
    monkeypatch.setattr(live.c, "_no_attack_turn", lambda: live.c._use_move("Growl"))
    monkeypatch.setattr(kp, "can_attack", lambda m: True)
    monkeypatch.setattr(kp, "attack_pp", lambda m: 99)
    monkeypatch.setattr(live.c, "_relocate_to_grass", lambda **kw: True)       # stay in the forest: this test is about the fights
    out = live.c._execute("grind", json.dumps({"level": 40, "auto_battles": 50}))   # autopilot: the bug lives there
    assert "was stopped" in out and "no progress" in out, out


def test_catch_vets_the_nickname_then_names_the_catch(live):
    live.load("threemon")
    assert live.wild_battle()
    foe = live.r.read_enemy_lead().species_name
    balls = live.c._ball_count()
    out = live.c._catch(foe + "1")
    assert out.startswith("No ball thrown") and live.c._ball_count() == balls      # refused, free
    for _ in range(10):
        live.set_foe_hp(1)
        out = live.c._catch("Mr. Zap!")
        if "Gotcha" in out:
            break
    assert "Gotcha" in out and "Mr. Zap!" in out, out
    assert any(p.nickname == "Mr. Zap!" for p in live.r.read_party())


def test_naming_screen_page_comes_from_the_game_and_a_mixed_case_name_types(live, monkeypatch):
    """The keyboard page is read from the game's own struct (NAMING_PAGE), not counted: a mixed-case, spaced nickname crosses UPPER <-> lower
    pages and must land exactly; the page values the RAM read returned include both letter pages."""
    from game.naming import NamingDriver
    seen = []
    orig = NamingDriver.current_page

    def spy(self):
        page = orig(self)
        seen.append((self.m.read8(Addr.NAMING_PAGE), page))
        return page
    monkeypatch.setattr(NamingDriver, "current_page", spy)
    live.load("threemon")
    assert live.wild_battle()
    out = ""
    for _ in range(10):
        live.set_foe_hp(1)
        out = live.c._catch("Zap Daddy")
        if "Gotcha" in out:
            break
    assert "Gotcha" in out and "Named it 'Zap Daddy'" in out, out
    assert any(p.nickname == "Zap Daddy" for p in live.r.read_party())
    assert {1, 2} <= {ram for ram, _p in seen}, seen                       # the RAM read saw the UPPER and the lower page
    assert all({1: 0, 2: 1, 0: 2}[ram] == page for ram, page in seen if ram in (0, 1, 2)), seen


def test_broke_free_ball_returns_without_a_long_menu_wait(live):
    live.load("threemon")
    assert live.wild_battle()
    taps = {"B": 0}
    orig = live.m.tap

    def tap(b):
        taps[b] = taps.get(b, 0) + 1
        return orig(b)
    live.m.tap = tap
    try:
        for _ in range(8):
            if live.r.detect_context() != GameContext.IN_BATTLE:
                break
            live.set_foe_hp(live.m.read16(0x02023BE4 + 0x58 + 0x2C))      # full HP: likely to break free
            taps["B"] = 0
            out = live.c._catch("Wiggles")
            if "broke free" in out:
                assert taps["B"] < 60, f"waited through {taps['B']} B presses at the menu"
                return
    finally:
        live.m.tap = orig
    # every throw succeeded or the foe fled: nothing to assert about the break-free path


def test_disabled_move_is_refused_without_pressing_anything(live):
    live.load("disabled")
    if live.r.detect_context() != GameContext.IN_BATTLE:
        import pytest
        pytest.skip("fixture is not mid-battle")
    out = live.c._use_move("Tackle")
    assert "DISABLED" in out or "refused" in out, out


def test_catching_with_a_full_party_reports_the_box(live):
    from game.constants import Addr
    live.load("threemon")
    for slot in (3, 4, 5):                                   # clone the last mon up to a full party
        for i in range(100):
            live.m.write8(Addr.PARTY_DATA + 100 * slot + i, live.m.read8(Addr.PARTY_DATA + 200 + i))
    live.m.write8(0x02024284 - 4, 6)
    live.heal_hp()
    assert live.wild_battle()
    for _ in range(10):
        live.set_foe_hp(1)
        out = live.c._catch("Box Buddy")
        if "Gotcha" in out:
            break
    assert "PC box" in out, out
    assert len(live.r.read_party()) == 6 and live.r.detect_context() == GameContext.OVERWORLD


def test_get_ss_ticket_then_cross_cerulean_to_vermilion(live):
    """Bill's quest end to end (post-Misty fixture), then the Underground Path to Vermilion — covers the
    Saffron-shell routing fix and the directional stairs probe."""
    live.load("post_misty")
    out = _quest(live, "quest", rounds=30, name="ss_ticket")
    assert "Got the SS Ticket" in out or "already have" in out, out
    assert live.c._has_ss_ticket()
    for _ in range(6):
        out = _go(live, "Vermilion City")
        if live.r.read_current_map() == (3, 5):
            break
        if "heal" in out or "Lost" in out:
            live.heal_hp()                      # a Route 5/6 trainer beat us: top up and retry
    assert live.r.read_current_map() == (3, 5), out


def test_get_cut_then_enter_the_vermilion_gym_and_open_the_locks(live):
    """S.S. Anne → Captain → HM01 → teach Cut → go_to Gym cuts the door tree → trash-can switches read from
    memory open the electric locks."""
    live.load("vermilion")
    live.c.ltm.data["gyms_beaten"] = ["Brock", "Misty"]
    out = _quest(live, "quest", name="cut", auto_trainers=True)
    assert "Got HM01" in out or "already knows Cut" in out, out
    assert live.c._knows_cut()
    for _ in range(6):
        _go(live, "Gym", force=True)
        if live.r.read_current_map() == (9, 6):
            break
    assert live.r.read_current_map() == (9, 6)
    # The game rolls the two switch cans from the RNG on map load, so which cans (and whether a gym trainer stands on
    # an approach tile) depends on how many frames the earlier steps took. Pin them to a pair known to be reachable.
    sb1 = live.m.read32(Addr.SAVEBLOCK1_PTR)
    live.m.write16(sb1 + Addr.VARS_OFFSET, 14)
    live.m.write16(sb1 + Addr.VARS_OFFSET + 2, 9)
    res = live.c._solve_vermilion_switches()
    assert res.startswith("Both") or "already open" in res or live.r.read_flag(0x264), res
    assert live.r.read_flag(0x264)


def test_reorder_party_and_set_lead_drive_the_party_menu(live):
    live.load("threemon")
    out = live.c._execute("reorder_party", json.dumps({"first": "1", "second": "3"}))
    assert out.startswith("Swapped"), out
    assert [p.species_name for p in live.r.read_party()][0] == "Caterpie"
    out = live.c._execute("reorder_party", json.dumps({"first": "Pikachu"}))
    assert out.startswith("Swapped") and live.r.read_party()[0].species_name == "Pikachu", out
    assert live.r.detect_context() == GameContext.OVERWORLD


def test_first_arrival_in_a_town_heals_at_its_center_once(live):
    live.load("post_misty")
    live.c.ltm.data["pc_visited"] = []
    out = _go(live, "Cerulean City")
    assert out.startswith("Arrived"), out
    assert live.c.ltm.data["pc_visited"] == ["3,3"]


def test_grind_points_out_a_worthwhile_wild_pokemon_and_leaves_the_catch_to_the_model(live, monkeypatch):
    import knowledge.catch_policy as cp
    monkeypatch.setattr(cp, "evaluate", lambda party, sid, lvl, max_team=6, dex_owned=None, wanted=None, stored=None: cp.Verdict(True, "test", 0))
    live.load("threemon")
    balls = live.c._ball_count()
    out = ""
    for _ in range(12):                      # the forest's species vary; a duplicate of one we own is never "worth a ball"
        out = live.c._execute("grind", json.dumps({"level": 9}))
        if "Worth a ball" in out:
            break
        live.c._flee_battle()
    assert "Worth a ball" in out and "while grinding" in out, out
    assert live.r.detect_context() == GameContext.IN_BATTLE and live.c._ball_count() == balls
    live.set_foe_hp(2)                       # the model would weaken it first
    caught = ""
    for _ in range(6):                       # a ball can break free
        caught = live.c._execute("catch", json.dumps({"nickname": "Testy"}))
        if "Gotcha" in caught:
            break
    assert "Gotcha" in caught, caught


def test_leaving_the_cerulean_mart_toward_the_north_does_not_loop_through_the_door(live):
    """Run 20261114-101556: from inside the Mart, go_to a northern route walked out, picked an unreachable
    north-edge tile in another region, then 'stepped off the edge' back through the Mart door — forever."""
    live.load("post_misty")
    live.c.ltm.data["gyms_beaten"] = ["Brock"]
    assert _go(live, "Mart").startswith("Arrived")
    out = _go(live, "Route 24")
    assert out.startswith("Arrived") and live.r.read_current_map() == (3, 43), out


def test_level_up_prompt_can_forget_any_slot(live):
    """The old driver could only forget slot 0 and declined everything else (SolarBeam / Razor Leaf refused)."""
    live.load("delete_box")
    for slot, expect in ((2, ["Tackle", "Growl", "Vine Whip", "Scratch"]), (3, ["Tackle", "Growl", "Leech Seed", "Vine Whip"])):
        live.m.load_state_file(str(live.dir / "delete_box.ss1"))
        live.m.tick(10)
        assert live.c._accept_forget_slot(slot)
        assert live.r.read_party()[0].move_names == expect


def test_balance_training_keeps_the_ace_from_stealing_xp(live, monkeypatch):
    from agent import budgets
    monkeypatch.setitem(budgets.BUDGETS, "grind", (90_000, 15_000))
    live.load("threemon")
    # L14 (not 19): the floor is 7 levels under it, which the Viridian Forest wilds (L3-6) can actually train a L5 to — grass on
    # Routes 3/4 would train faster but sits behind Brock's gate for this badge-less fixture.
    live.patch_mon(0, [33, 45, 73, 22], [35, 40, 10, 25], level=14, exp=1612)
    out = _grind(live, {"catch": False}, rounds=120)
    party = live.r.read_party()
    assert party[0].species_name == "Bulbasaur" and party[0].level == 14, (out, [(p.species_name, p.level, p.current_hp) for p in party])
    assert max(p.level for p in party[1:]) > 5, out                              # the trainees actually levelled


def _pc(live, tool, **args):
    """Call a pc_* tool; if go_to handed us a wild encounter on the way to the Center (#202), flee and resume."""
    out = ""
    if tool.startswith("pc_"):                                       # pc_deposit(pokemon=…) → pc(action="deposit", pokemon=…)
        args = {"action": tool[3:], **({"pokemon": args.pop("party_pokemon")} if "party_pokemon" in args else {}), **args}
        tool = "pc"
    for _ in range(12):
        out = live.c._execute(tool, json.dumps(args))
        if "appeared at" not in out or live.r.detect_context() != GameContext.IN_BATTLE:
            break
        live.c._flee_battle()
    return out


def test_pc_deposit_list_and_withdraw_through_the_real_menus(live):
    live.load("threemon")
    out = _pc(live, "pc_deposit", pokemon="Pikachu")
    assert out.startswith("Deposited") and len(live.r.read_party()) == 2, out
    assert live.r.detect_context() == GameContext.OVERWORLD
    assert "Pikachu" in live.c._execute("pc", json.dumps({"action": "list"}))
    out = live.c._execute("pc", json.dumps({"action": "withdraw", "pokemon": "pikachu"}))
    assert out.startswith("Withdrew") and len(live.r.read_party()) == 3, out
    assert live.r.read_boxes() == []


def test_pc_withdraw_from_another_box_and_grid_slot(live):
    live.load("threemon")
    assert _pc(live, "pc_deposit", pokemon="Caterpie").startswith("Deposited")
    base = live.r._storage_ptr()
    src, dst = base + 4, base + 4 + (1 * 30 + 14) * 80          # box 1 slot 0 → box 2 slot 14 (col 2, row 2)
    for i in range(80):
        live.m.write8(dst + i, live.m.read8(src + i))
        live.m.write8(src + i, 0)
    out = live.c._execute("pc", json.dumps({"action": "withdraw", "pokemon": "2:14"}))
    assert out.startswith("Withdrew") and live.r.read_current_box() == 1, out
    assert [p.species_name for p in live.r.read_party()][-1] == "Caterpie"


def test_tagged_out_trainee_shares_the_xp_and_is_never_swapped_back(live, monkeypatch):
    """Watched run: the trainee led, the ace was switched in, then the loop switched the trainee BACK in and
    it was knocked out for no XP. Now: trainee leads, tags out on turn one, the ace finishes; the trainee
    gains experience and keeps its HP."""
    live.load("threemon")
    live.patch_mon(0, [33, 45, 73, 22], [35, 40, 10, 25], level=40, exp=56660)       # Bulbasaur L40: the ace
    live.patch_mon(1, None, None, level=3, exp=27)
    live.patch_mon(2, None, None, level=3, exp=27)
    live.heal_hp()
    assert live.c._lead_trainee(live.r.read_party()[1])                                # a L3 leads
    lead = live.r.read_party()[0]
    sig = (lead.species_id, lead.max_hp)
    exp0 = live.read_exp(0)
    switches = []
    orig = live.c._switch_pokemon
    monkeypatch.setattr(live.c, "_switch_pokemon", lambda t, *a, **k: (switches.append(t), orig(t, *a, **k))[1])
    # a foe above the trainee's level+2 is guaranteed to be "tough" for a L3 → expect a turn-one tag-out
    assert live.wild_battle(), "no wild battle found"
    hp0 = live.r.read_party()[0].current_hp
    live.c._train_fight(sig)
    assert len(switches) <= 1, switches                                                # one tag-out, no swap back
    assert live.read_exp(0) > exp0 or live.r.read_party()[0].level > 3                # the trainee got XP
    if switches:
        assert live.r.read_party()[0].current_hp >= hp0 - 1                            # …without being hurt


def test_go_to_hands_a_worthwhile_wild_pokemon_to_the_model_instead_of_fleeing(live, monkeypatch):
    """The team stalled at four because go_to fled everything; now the model is told it is worth a ball (#202)."""
    import knowledge.catch_policy as cp
    monkeypatch.setattr(cp, "evaluate", lambda party, sid, lvl, max_team=6, dex_owned=None, wanted=None, stored=None: cp.Verdict(True, "test", 0))
    live.load("threemon")
    balls = live.c._ball_count()
    assert live.wild_battle(), "no wild battle found"
    stop = live.c._handle_travel_battle("somewhere", mode="yield")
    assert stop and "appeared at" in stop and live.c._ball_count() == balls
    assert live.r.detect_context() == GameContext.IN_BATTLE


def _copy_boxmon(live, src, dst):
    base = live.r._storage_ptr() + 4
    for i in range(80):
        live.m.write8(base + dst * 80 + i, live.m.read8(base + src * 80 + i))


def test_deposit_into_a_full_box_goes_to_the_next_box(live):
    """#206: the displayed box is full (30/30) — the old code pressed A three times and the game refused."""
    live.load("threemon")
    assert _pc(live, "pc_deposit", pokemon="Pikachu").startswith("Deposited")
    for slot in range(1, 30):                              # fill box 1 with copies of that Pokémon
        _copy_boxmon(live, 0, slot)
    assert len(live.r.read_boxes()) == 30
    out = _pc(live, "pc_deposit", pokemon="Caterpie")
    assert out.startswith("Deposited") and "Box 2" in out and "earlier boxes are full" in out, out
    assert [m["species_name"] for m in live.r.read_boxes() if m["box"] == 1] == ["Caterpie"]
    assert len(live.r.read_party()) == 1


def test_swap_with_duplicates_resolves_the_exact_slot(live):
    """#206: a name matching several boxed Pokémon is listed, never guessed; box:slot swaps the right one."""
    live.load("threemon")
    assert _pc(live, "pc_deposit", pokemon="Pikachu").startswith("Deposited")
    _copy_boxmon(live, 0, 30 + 14)                         # a second Pikachu in box 2, slot 14
    amb = _pc(live, "pc_swap", party_pokemon="Caterpie", box_pokemon="pikachu")
    assert "2 Pokémon match" in amb and "Nothing was deposited" in amb and len(live.r.read_party()) == 2
    out = _pc(live, "pc_swap", party_pokemon="Caterpie", box_pokemon="2:14")
    assert out.startswith("Deposited") and "Withdrew" in out, out
    names = sorted(p.species_name for p in live.r.read_party())
    assert names == ["Bulbasaur", "Pikachu"], names


def test_thunder_stone_evolves_pikachu_and_rare_candy_levels_a_named_target(live):
    """#205: stones and Rare Candy through the real Bag → party screen flow (evolution scene driven with A)."""
    live.load("threemon")
    live.give_item(96, 1)                                  # Thunder Stone
    live.give_item(68, 2)                                  # Rare Candy
    refused = live.c._execute("use_item", json.dumps({"item": "Rare Candy"}))
    assert "Say who gets" in refused, refused
    lv0 = next(p for p in live.r.read_party() if p.species_name == "Caterpie").level
    out = live.c._execute("use_item", json.dumps({"item": "Rare Candy", "target": "Caterpie"}))
    assert f"L{lv0}→L{lv0 + 1}" in out, out
    out = live.c._execute("use_item", json.dumps({"item": "Thunder Stone"}))
    assert "evolved into Raichu" in out, out
    names = [p.species_name for p in live.r.read_party()]
    assert "Raichu" in names and "Pikachu" not in names
    assert live.r.detect_context() == GameContext.OVERWORLD
    assert dict(live.r.read_items_pocket()).get(96, 0) == 0 and dict(live.r.read_items_pocket()).get(68) == 1


def test_decoded_ivs_evs_and_nature_reproduce_the_games_own_stats(live):
    """#208 golden check: base stats + decoded IVs / EVs / nature + the Gen III formula must equal the stats the game
    stored in each party Pokémon — a mismatch anywhere (bit layout, nature table, formula) fails this."""
    from knowledge.mon_quality import projected_stats
    live.load("threemon")
    checked = 0
    for p in live.r.read_party():
        assert len(p.ivs) == 6 and len(p.evs) == 6 and len(p.stats) == 6, p
        assert all(0 <= v <= 31 for v in p.ivs) and all(0 <= v <= 255 for v in p.evs)
        assert projected_stats(p.species_id, p.ivs, p.evs, p.personality, p.level) == p.stats, (
            p.species_name, p.level, p.ivs, p.evs, p.personality % 25, p.stats)
        checked += 1
    assert checked >= 3


def test_inspect_pokemon_and_the_catch_report_use_the_real_ivs(live):
    """#208: inspect_pokemon on a party member and a PC mon; a fresh catch reports its quality after the fact."""
    live.load("threemon")
    out = live.c._execute("inspect_pokemon", json.dumps({"pokemon": "Bulbasaur"}))
    assert "Bulbasaur L" in out and "IV" in out and "Stats: HP" in out and "Hidden Power would be" in out, out
    assert "Compared with your team" in out
    assert "Can't find" in live.c._execute("inspect_pokemon", json.dumps({"pokemon": "Mew"}))
    assert live.wild_battle(), "no wild battle found"
    live.set_foe_hp(1)
    got = ""
    for _ in range(6):
        got = live.c._execute("catch", json.dumps({"nickname": "Judge"}))
        if "Gotcha" in got:
            break
    assert "Gotcha" in got and "Quality: " in got, got
    assert live.c._execute("pc", json.dumps({"action": "list", "detail": True})) is not None


def test_escape_rope_leaves_the_forest_the_threemon_fixture_stands_in(live):
    live.load("threemon")
    assert live.r.read_current_map() == (1, 0)                       # Viridian Forest — allow_escaping
    live.give_item(85, 2)                                            # Escape Rope
    out = live.c._execute("use_item", json.dumps({"item": "Escape Rope"}))
    assert out.startswith("Used Escape Rope (1 left): now in Route 2"), out
    assert live.r.read_current_map() != (1, 0) and live.r.detect_context() == GameContext.OVERWORLD
    again = live.c._execute("use_item", json.dumps({"item": "Escape Rope"}))          # outdoors now: refused, not consumed
    assert "only works inside a cave" in again and dict(live.r.read_items_pocket()).get(85) == 1, again


def test_dig_in_the_forest_then_teleport_outdoors(live):
    """Dig and Teleport through the real party sub-menu → 'return to …?' prompt, each confirmed by the map changing."""
    live.load("threemon")
    live.patch_mon(0, moves=[33, 91, 100, 0], pps=[35, 10, 20, 0])
    out = live.c._execute("use_hm", json.dumps({"move": "Dig"}))
    assert out.startswith("Used Dig: now in Route 2"), out
    assert "only works inside a cave" in live.c._execute("use_hm", json.dumps({"move": "Dig"}))
    here = live.r.read_current_map()
    out = live.c._execute("use_hm", json.dumps({"move": "Teleport"}))
    assert out.startswith("Used Teleport: now in") and live.r.read_current_map() != here, out
    assert live.r.detect_context() == GameContext.OVERWORLD


def test_give_item_equips_swaps_and_x_items_work_in_battle(live):
    """#215: held items through Bag → GIVE → party screen (incl. the 'already holding' swap prompt) and an X item in battle."""
    live.load("threemon")
    live.give_item(182, 1)                                   # Exp. Share
    live.give_item(200, 1)                                   # Leftovers
    out = live.c._execute("give_item", json.dumps({"item": "Exp. Share", "pokemon": "Caterpie"}))
    assert out.lower() == "caterpie now holds exp. share (the holder gets half the exp. of a battle even if it never fought).", out
    held = {p.species_name: p.held_item for p in live.r.read_party()}
    assert held["Caterpie"] == 182 and held["Bulbasaur"] == 0
    out = live.c._execute("give_item", json.dumps({"item": "Leftovers", "pokemon": "Caterpie"}))   # swap
    assert "now holds Leftovers" in out and "Exp. Share went back to the Bag" in out, out
    bag = dict(live.r.read_items_pocket())
    assert bag.get(182) == 1 and bag.get(200, 0) == 0
    assert "already holding" in live.c._execute("give_item", json.dumps({"item": "Leftovers", "pokemon": "Caterpie"}))
    assert "Give it to whom" in live.c._execute("give_item", json.dumps({"item": "Exp. Share", "pokemon": ""}))
    assert live.r.detect_context() == GameContext.OVERWORLD

    live.give_item(75, 2)                                    # X Attack
    assert live.wild_battle()
    out = live.c._execute("use_item", json.dumps({"item": "X Attack"}))
    assert out.startswith("Used X Attack — +1 Attack stage"), out
    assert dict(live.r.read_items_pocket()).get(75) == 1


def test_quest_lists_progress_and_refuses_what_is_blocked(live):
    live.load("threemon")
    out = live.c._execute("quest", "{}")
    assert out.startswith("Story, start to Elite Four") and "ss_ticket" in out and "cut" in out, out
    assert "needs quest('ss_ticket') first" in live.c._execute("quest", json.dumps({"name": "cut"})) or "already" in out


def _fly_to_celadon(live):
    """Stage: Fly (Thunder Badge + visited flag) from the Vermilion fixture to Celadon City."""
    live.load("vermilion")
    live.patch_mon(0, moves=[33, 19, 0, 0], pps=[35, 15, 0, 0])
    live.set_badges(0b111)                                   # Boulder, Cascade, Thunder
    live.set_flag(0x896)                                     # Celadon visited
    out = live.c._execute("fly_to", json.dumps({"town": "Celadon"}))
    assert live.r.read_current_map() == (3, 6), out


def test_shop_item_buys_a_tm_at_the_celadon_dept_store(live):
    """#215: shop(item='TM28') flies nowhere — it walks Celadon City → Dept. Store 2F, stands across the counter from the TM clerk
    and buys; too little money is refused up front; an item nobody sells is explained."""
    _fly_to_celadon(live)
    live.set_money(1500)
    assert "costs ¥2000 and you have ¥1500" in live.c._execute("shop", json.dumps({"item": "TM28"}))
    assert "No clerk sells 'Masterball'" in live.c._execute("shop", json.dumps({"item": "Masterball"}))
    live.set_money(5000)
    had = dict(live.r.read_tmhm_pocket()).get(316, 0)
    out = ""
    for _ in range(8):
        out = live.c._execute("shop", json.dumps({"item": "TM28"}))
        if out.startswith("Bought") or live.r.detect_context() != GameContext.OVERWORLD:
            break
    assert out.startswith("Bought 1× TM28 Dig (¥2000)"), out
    assert dict(live.r.read_tmhm_pocket()).get(316) == had + 1 and live.r.read_money() == 3000
    assert live.r.read_current_map() == (10, 1) and live.r.detect_context() == GameContext.OVERWORLD
    # the other clerk on the same floor (the Items counter two tiles away) sells ordinary goods: quantity and the right clerk
    reps = dict(live.r.read_items_pocket()).get(83, 0)
    out = live.c._execute("shop", json.dumps({"item": "Super Repel", "quantity": 2}))
    assert out.startswith("Bought 2× Super Repel (¥1000)"), out
    assert dict(live.r.read_items_pocket()).get(83) == reps + 2 and live.r.read_money() == 2000


def test_save_game_writes_a_real_save_and_records_it(live):
    """#215: Start → Save → YES → YES (overwrite), confirmed by gSaveCounter rising; ltm remembers badges/battles at the save."""
    live.load("threemon")
    assert live.c._execute("save_game", "{}") .startswith("Saved the game (save #")
    n1 = live.m.read32(Addr.SAVE_COUNTER)
    out = live.c._execute("save_game", "{}")
    assert live.m.read32(Addr.SAVE_COUNTER) == n1 + 1 and out.startswith(f"Saved the game (save #{n1 + 1})"), out
    assert live.r.detect_context() == GameContext.OVERWORLD
    assert live.c.ltm.data["saved_badges"] == live.c.ltm.data["badges_earned"]
    assert live.wild_battle()
    assert "Save from the free overworld" in live.c._execute("save_game", "{}")
    assert live.m.read32(Addr.SAVE_COUNTER) == n1 + 1                       # and nothing was written in the battle


def _fly_to_fuchsia(live):
    live.load("vermilion")
    live.patch_mon(0, moves=[33, 19, 0, 0], pps=[35, 15, 0, 0])
    live.set_badges(0b111)
    live.set_flag(0x897)                                     # Fuchsia visited
    out = live.c._execute("fly_to", json.dumps({"town": "Fuchsia"}))
    assert live.r.read_current_map() == (3, 7), out


def _into_the_safari_zone(live, money=5000):
    """Stage: pay the entrance fee by hand (walk onto a trigger tile and say YES) — the quest driver does this itself."""
    _fly_to_fuchsia(live)
    live.set_money(money)
    live.c._execute("go_to", json.dumps({"destination": "Safari Zone Entrance"}))
    live.c._walk_to(4, 3)
    for _ in range(8):
        live.m.tick(120)
        live.c._advance_to_control(tries=20)
        if live.r.read_current_map() == (1, 63):
            break
    assert live.r.read_current_map() == (1, 63), live.r.read_current_map()


def _safari_encounter(live, tries=500):
    g = live.c._nearest_grass()
    live.c._walk_to(*g)
    for _ in range(tries):
        if live.c._wander_step():
            live.m.tick(200)
            return True
    return False


def test_safari_battle_menu_ball_bait_rock_run(live):
    """#215: a Safari battle has its own menu and tool list; safari(action) drives BALL / BAIT / GO NEAR / RUN."""
    from agent.tools import SAFARI_CONTEXT, tools_for
    _into_the_safari_zone(live)
    assert live.m.read8(Addr.SAFARI_BALLS) == 30 and live.m.read16(Addr.SAFARI_STEPS) > 500
    assert "SAFARI ZONE:" in _observation(live, False)
    assert _safari_encounter(live) and live.c._in_safari_battle()
    assert live.c._tool_context() == SAFARI_CONTEXT
    assert {t["function"]["name"] for t in tools_for(live.c._tool_context())} == {
        "safari", "inspect_pokemon", "team_report", "press_button", "advance_dialog", "answer_prompt", "close_menus"}
    live.m.tick(120)
    obs = _observation(live, True)
    assert "SAFARI battle:" in obs and "Safari Balls" in obs and "safari('ball'" in obs, obs
    assert "no longer" not in live.c._execute("safari", json.dumps({"action": "wave"})) and "one of: ball" in live.c._execute(
        "safari", json.dumps({"action": "wave"}))
    out = live.c._execute("safari", json.dumps({"action": "bait"}))
    assert ("threw bait" in out and "LESS likely to flee" in out) or "ran away" in out, out
    if live.c._in_safari_battle():
        out = live.c._execute("safari", json.dumps({"action": "rock"}))
        assert ("threw a rock" in out) or "ran away" in out, out
    if live.c._in_safari_battle():
        before = live.m.read8(Addr.SAFARI_BALLS)
        out = live.c._execute("safari", json.dumps({"action": "ball"}))
        assert live.m.read8(Addr.SAFARI_BALLS) == before - 1, out
        assert "Gotcha" in out or "broke free" in out, out
    if live.c._in_safari_battle():
        out = live.c._execute("safari", json.dumps({"action": "run"}))
        assert "Got away" in out
    assert live.r.detect_context() in (GameContext.OVERWORLD, GameContext.IN_BATTLE)


def _observation(live, in_battle):
    import copy
    import main
    from agent.observation import build_observation
    s = live.r.read_state()
    run = main._RunState()
    run.current_enemy = "FOE"
    return build_observation(state=s, diff=live.r.diff(None, s), in_battle=in_battle, run=run, reader=live.r,
                             tilemap=live.rt.tilemap, ltm=copy.deepcopy(live.rt.ltm), stm=copy.deepcopy(live.rt.stm),
                             map_key=(s.map_bank, s.map_id))


def test_safari_ball_throws_consume_balls_and_a_catch_is_handled_end_to_end(live):
    """#215: safari('ball') = catch() in the Safari menu: counted by gNumSafariBalls, 'broke free' keeps the battle going, and a
    catch (with a nickname) leaves a clean overworld with the Pokémon in the party or the PC."""
    _into_the_safari_zone(live)
    caught = ""
    thrown = 0
    for _ in range(4):                                       # a few encounters: catch rates are low, so allow some luck
        if not (_safari_encounter(live) and live.c._in_safari_battle()):
            continue
        live.m.tick(120)
        for _ in range(6):
            if not live.c._in_safari_battle():
                break
            before = live.m.read8(Addr.SAFARI_BALLS)
            out = live.c._execute("safari", json.dumps({"action": "ball", "nickname": "Safari Sam"}))
            if out.startswith("No ball thrown"):                 # nickname critique (no ball spent): ask again, as the model would
                out = live.c._execute("safari", json.dumps({"action": "ball", "nickname": "Dusty Rhinoplasty"}))
            thrown += before - live.m.read8(Addr.SAFARI_BALLS)
            if out.startswith("Gotcha"):
                caught = out
                break
        if caught:
            break
        if live.c._in_safari_battle():
            live.c._execute("safari", json.dumps({"action": "run"}))
    assert thrown >= 1
    assert live.r.detect_context() in (GameContext.OVERWORLD, GameContext.IN_BATTLE), live.r.detect_context()
    if caught:
        assert live.r.detect_context() == GameContext.OVERWORLD
        assert len(live.r.read_party()) == 2 or live.r.read_boxes(), "the catch went nowhere"


def _safari_quest(live, name, rounds=40):
    """Run quest(name); a Safari battle ends the call — run from it (the model would throw balls) and resume."""
    out = ""
    for _ in range(rounds):
        out = live.c._execute("quest", json.dumps({"name": name}))
        if live.c._in_safari_battle():
            live.c._execute("safari", json.dumps({"action": "run"}))
            continue
        if "again to continue" not in out:
            break
    return out


def test_quest_strength_goes_through_the_safari_zone_to_the_warden(live):
    """#215: pays ¥500, picks up the Gold Teeth (and the Secret House's HM03 on the same visit), walks out and takes the teeth to
    the Warden for HM04, then teaches it."""
    _fly_to_fuchsia(live)
    live.set_money(5000)
    had03 = live.r.read_flag(0x239)
    out = _safari_quest(live, "strength")
    assert out.startswith("Got HM04"), out
    assert live.r.read_flag(0x23A) and live.r.read_flag(0x189) and (had03 or live.r.read_flag(0x239))
    assert live.r.read_money() == 4500 and not live.c._in_safari_zone()
    assert any(70 in (p.move_ids or []) for p in live.r.read_party())
    assert live.r.detect_context() == GameContext.OVERWORLD
    assert "already done" in live.c._execute("quest", json.dumps({"name": "strength"}))


def test_quest_surf_takes_the_secret_house_hm_and_the_gold_teeth_on_one_visit(live):
    """#215: one paid visit gets HM03 from the Secret House AND the Gold Teeth (so quest('strength') only has to see the Warden)."""
    _fly_to_fuchsia(live)
    live.set_money(5000)
    out = _safari_quest(live, "surf")
    assert live.r.read_flag(0x239) and live.r.read_flag(0x189), out           # HM03 and the Gold Teeth taken
    assert "quest('strength')" in out and live.r.read_money() == 4500 and not live.c._in_safari_zone(), out
    assert live.r.detect_context() == GameContext.OVERWORLD


def test_game_corner_prizes_coins_and_the_coin_case(live):
    """#215: the Prize Corner (coins → TM/item/Pokémon), the coin clerk (yen → coins) and the Coin Case man, on the real ROM."""
    _fly_to_celadon(live)
    live.set_flag(0x243, False)
    assert "No Coin Case" in live.c._execute("game_corner", json.dumps({"action": "status"}))
    out = ""
    for _ in range(6):
        out = live.c._execute("quest", json.dumps({"name": "coin_case"}))
        if out.startswith("Got the Coin Case"):
            break
    assert out.startswith("Got the Coin Case") and live.r.read_flag(0x243), out
    # buy coins with yen
    live.set_money(30000)
    live.set_coins(0)
    out = live.c._execute("game_corner", json.dumps({"action": "buy_coins", "amount": 100}))
    assert out.startswith("Bought 100 coins for ¥2000") and live.r.read_coins() == 100 and live.r.read_money() == 28000, out
    # not enough coins for a prize: explained, with the cost of buying the rest
    out = live.c._execute("shop", json.dumps({"item": "Thunderbolt"}))
    assert "costs 4000 coins" in out and "3900 more" in out, out
    # enough coins: the TM arrives and the coins drop by exactly its price
    live.set_coins(4100)
    had = dict(live.r.read_tmhm_pocket()).get(312, 0)
    out = live.c._execute("shop", json.dumps({"item": "TM24"}))
    assert out.startswith("Exchanged 4000 coins for TM24 Thunderbolt"), out
    assert dict(live.r.read_tmhm_pocket()).get(312) == had + 1 and live.r.read_coins() == 100
    assert live.r.detect_context() == GameContext.OVERWORLD
    # a Pokémon prize goes to the party (or the PC) without a nickname detour
    live.set_coins(200)
    n0 = len(live.r.read_party())
    out = live.c._execute("shop", json.dumps({"item": "Abra"}))
    assert out.startswith("Exchanged 120 coins for Abra (L7)"), out
    assert len(live.r.read_party()) == n0 + 1 and live.r.read_coins() == 80
    assert live.r.detect_context() == GameContext.OVERWORLD


def test_slot_machine_driver_plays_and_pays(live):
    """#215: seat at a machine, bet 3, stop reels on a bias-serving frame, wait for the payout, quit — coins add up exactly."""
    _fly_to_celadon(live)
    live.set_flag(0x243)
    live.set_coins(300)
    start = live.r.read_coins()
    out = live.c._execute("game_corner", json.dumps({"action": "slots", "amount": 12}))
    assert out.startswith("Played ") and "spins at 3 coins" in out, out
    assert live.r.detect_context() == GameContext.OVERWORLD and live.m.read32(Addr.GMAIN_CALLBACK2) != Addr.CB2_SLOT_MACHINE
    net = live.r.read_coins() - start
    assert f"{net:+d} coins" in out, out


def test_go_to_route_4_before_brock_stops_with_the_reason_instead_of_looping_at_pewter(live):
    """Regression: the model ran Viridian Forest → Pewter and then looped on the Gym Guide trying to reach Route 4 badge-less."""
    live.load("threemon")
    assert live.r.read_badges()[0] == 0
    out = live.c._execute("go_to", json.dumps({"destination": "Route 4"}))
    assert "Can't get to Route 4 yet" in out and "Brock" in out and "Gym Guide" in out, out
    assert live.c.last_trip_stop["reason"] == "gated"
    out = live.c._execute("grind", json.dumps({"level": 13}))
    assert live.r.read_current_map() not in ((3, 21), (3, 22)), out         # grind's relocation must not head for gated grass either


def test_foe_battler_read_matches_the_real_wild_mon_and_feeds_the_observation(live):
    """gBattleMons[1]: real moves / Speed / Attack / ability for the foe, and the roster + low-HP line built from them."""
    live.load("threemon")
    assert live.wild_battle()
    foe = live.r.read_foe_battler()
    assert foe["moves"] and all(foe["moves"]) and foe["speed"] > 0 and foe["attack"] > 0 and foe["sp_attack"] > 0, foe
    enemy = live.r.read_enemy_lead()
    from knowledge.matchup import Foe, roster
    party = live.r.read_party()
    line = roster(party, live.r.read_active_battle_species(),
                  foe=Foe(name=enemy.species_name, level=enemy.level, hp=enemy.current_hp, max_hp=enemy.max_hp, **foe))
    assert line.startswith(f"Party vs {enemy.species_name.title()}") and "ACTIVE" in line, line


def test_forced_switch_screen_is_named_in_the_observation_and_blind_presses_are_refused(live):
    """Watched-run finding: after a faint the forced party screen read as TRANSITIONING and the observation said 'press A' — a
    Gemma run pressed A/wait for 319 tool calls. Now the observation says FORCED SWITCH and press_button/advance_dialog
    point at switch_pokemon (which does leave the screen)."""
    import pytest
    live.load("forced_stuck")
    from game.menu import forced_party_screen
    if not forced_party_screen(live.m, live.r):
        pytest.skip("fixture is not on the forced party screen")
    txt = _observation(live, in_battle=False)
    assert "FORCED SWITCH" in txt and "switch_pokemon" in txt and "press A" not in txt, txt
    assert "Party vs" in txt or "Healthy:" in txt
    for out in (live.c._execute("press_button", json.dumps({"button": "A"})), live.c._execute("advance_dialog", "{}")):
        assert "switch_pokemon" in out and "forcing a replacement" in out, out
    party = live.r.read_party()
    fainted_sp = live.r.read_active_battle_species()          # live.load() heals the party structs; the battler is still down
    other = next(p for p in party if p.current_hp > 0 and p.species_id != fainted_sp)
    out = live.c._execute("switch_pokemon", json.dumps({"target": other.nickname or other.species_name}))
    assert not forced_party_screen(live.m, live.r), out


def test_route8_fenced_grass_is_reached_by_cutting_a_tree_not_by_ping_ponging(live, monkeypatch):
    """Watched-run finding: Route 8's tall grass is a pocket walled off by two Cut trees. grind targeted it by distance, walk_to
    saw the trees as NPCs and 'engaged' them one after the other (the bounce), then the run left for Route 10 and came back.
    Now walk_to cuts the tree that is the only way in, and without Cut the grass counts as unreachable (the map is skipped)."""
    import pytest
    live.load("route8")
    if live.r.read_current_map() != (3, 26):
        pytest.skip("fixture is not on Route 8")
    c = live.c
    assert c._can_use_cut(), "the fixture's party must know Cut with the Cascade Badge"
    target = c._nearest_grass()
    assert target is not None and 34 <= target[0] <= 46 and 9 <= target[1] <= 18, target     # inside the fenced pocket
    for _ in range(40):                                       # a wild/trainer battle on the way interrupts a walk: play it out
        if live.r.detect_context().name == "IN_BATTLE":
            c._execute("flee_battle", "{}")
            if live.r.detect_context().name == "IN_BATTLE":
                c._execute("use_move", json.dumps({"move": live.r.read_active_battle_moves()[1][0]}))
            continue
        out = c._walk_to(*target)
        if live.r.read_player_pos() == target:
            break
    assert live.r.read_player_pos() == target, out
    assert c.tilemap.is_tall_grass(*target)
    assert (47, 12) not in c._cut_tree_tiles(*c.tilemap.passable_grid()[1:]), "the east Cut tree should have been cut"
    # without Cut the pocket is a dead end: grind's grass step notices, remembers the map as sealed and relocates
    live.load("route8")
    monkeypatch.setattr(c, "_can_use_cut", lambda: False)
    st = {"stuck": 0, "reloc": 0}
    for _ in range(40):
        if live.r.detect_context().name == "IN_BATTLE":
            c._execute("flee_battle", "{}")
            if live.r.detect_context().name == "IN_BATTLE":
                c._execute("use_move", json.dumps({"move": live.r.read_active_battle_moves()[1][0]}))
            continue
        monkeypatch.setattr(c, "_relocate_to_grass", lambda **kw: False)   # (only the detection is under test, not the trip)
        c._grass_step(st, "grind()")
        if (3, 26) in c._sealed_grass:
            break
    assert (3, 26) in c._sealed_grass and st["stuck"] >= 24


def test_shop_restocks_at_the_celadon_dept_store_with_substitutes(live):
    """Watched run: from Celadon, shop() routed to Saffron's Mart ('gate guards want Tea') and sat at 0 Poké Balls with ¥3044 —
    the Dept. Store was not a mart waypoint, its clerk is not at a Mart's (2,3), and it sells no Poké Ball / Potion."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    live.set_money(6000)
    balls, supers = live.r.count_item(3), live.r.count_item(22)
    out = ""
    for _ in range(6):                                          # a wild/trainer fight on the way interrupts the trip
        out = c._execute("shop", "{}")
        if out.startswith("Bought"):
            break
        if live.r.detect_context().name == "IN_BATTLE":
            c._execute("flee_battle", "{}")
    assert out.startswith("Bought") and "Great Ball (instead of Poké Ball)" in out, out
    assert live.r.read_current_map() == (10, 1)                 # Celadon Dept. Store 2F
    assert live.r.count_item(3) > balls and live.r.count_item(22) > supers
    assert live.r.read_money() < 6000


def test_use_item_heals_the_active_battler_after_a_switch_and_reports_it(live):
    """Watched runs: after a switch / forced replacement the active Pokémon is not party slot 1. use_item judged success by the
    LEAD's HP, so a heal that landed was reported as 'Couldn't use the Super Potion — you're back in the battle' (twice in a row,
    each costing a turn). It now reads the active battler (gBattleMons[0]), and says so when the target is already at full HP."""
    live.load("threemon")
    live.give_item(13, 5)
    live.give_item(22, 3)
    assert live.wild_battle()
    c = live.c
    out = c._execute("switch_pokemon", json.dumps({"target": "Pikachu"}))
    assert "Switched in Pikachu" in out, out
    pika = next(p for p in live.r.read_party() if p.species_name.upper() == "PIKACHU")
    live.m.write16(0x02023BE4 + 0x28, 2)                     # gBattleMons[0].hp: the active Pikachu is nearly dead
    out = c._execute("use_item", json.dumps({"item": "Super Potion"}))
    assert out.startswith("Used Super Potion — Pikachu healed +") and f"/{pika.max_hp})" in out, out
    assert live.r.read_active_battle_hp() == pika.max_hp
    again = c._execute("use_item", json.dumps({"item": "Potion"}))
    assert "already at full HP" in again, again


def test_shop_with_too_little_money_says_so_and_stops_the_readiness_nag(live):
    """Watched run: 13 heal→shop trips at ¥600 'bought nothing' because the Dept. Store's cheapest ball / potion cost more, while the
    READINESS block kept saying shop()."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    live.set_money(300)
    out = ""
    for _ in range(6):
        out = c._execute("shop", "{}")
        if "bought nothing" in out:
            break
        if live.r.detect_context().name == "IN_BATTLE":
            c._execute("flee_battle", "{}")
    assert "you have ¥300" in out and "Earn more first" in out, out
    assert c.ltm.data.get("shop_broke_at") == 300
    c.ltm.data.pop("shop_broke_at", None)


def test_rocket_hideout_quest_ends_with_the_silph_scope_and_back_in_celadon(live):
    """quest('rocket_hideout') end to end on the real ROM (~5 min): Game Corner Grunt + poster → B1F → B2F → the B3F spinner maze (arrow
    tiles slide the player across plain floor to a stop tile — planned by find_path_spin) → B4F west Grunt + Lift Key → the elevator
    (B2F door; the panel list driven by hand; door (2,5)) → B4F south corridor → the two door Grunts open the barrier → Giovanni →
    Silph Scope → the elevator to B1F → the south-wing Grunt opens the barrier → out to Celadon City."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    out = ""
    for _ in range(12):
        live.heal_hp()
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
            continue
        out = c._execute("quest", json.dumps({"name": "rocket_hideout", "auto_trainers": True}))
        if 359 in live.r.read_key_items() and "Got the Silph Scope" in out:
            break
    assert 359 in live.r.read_key_items(), out                       # ITEM_SILPH_SCOPE
    assert 356 in live.r.read_key_items()                            # the Lift Key on the way
    assert "Got the Silph Scope" in out and live.r.read_current_map() == (3, 6), out
    assert "already done" in c._execute("quest", json.dumps({"name": "rocket_hideout"}))


def test_tea_quest_then_the_saffron_gate_guard_lets_you_in(live):
    """quest('tea'): the old woman in Celadon Mansion 1F gives the Tea; go_to Saffron City walks into the Route 7 gate house, the guard drinks
    it (the key item is consumed, FLAG_GOT_TEA stays) and — with only ONE of the doormat's two warp tiles firing — _probe_warp finds the
    one that does. The Saffron gate then counts as met by the flag, not by the (gone) item."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    live.set_badges(0b1111)                       # the fixture predates Erika: with the Rainbow Badge the Hideout and the Tea are open
    listing = c._execute("quest", "{}")
    assert "▶ tea" in listing and "▶ rocket_hideout" in listing and "… pokemon_tower" in listing, listing
    assert "No script for this one yet" in c._execute("quest", json.dumps({"name": "silph_co"}))          # (a beat still without a script)
    assert "Silph Scope" in c._execute("quest", json.dumps({"name": "pokemon_tower"}))                    # the Tower's script says what it needs
    out = ""
    for _ in range(6):
        live.heal_hp()
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
            continue
        out = c._execute("quest", json.dumps({"name": "tea"}))
        if live.r.read_flag(0x2A6):
            break
    assert live.r.read_flag(0x2A6) and 369 in live.r.read_key_items() and out.startswith("Got the Tea"), out
    assert "already done" in c._execute("quest", json.dumps({"name": "tea"})).lower() or "already have" in c._execute("quest", json.dumps({"name": "tea"}))
    for _ in range(8):
        live.heal_hp()
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
            continue
        c._execute("go_to", json.dumps({"destination": "Saffron City", "force": True}))
        if tuple(live.r.read_current_map()) == (3, 10):
            break
    assert tuple(live.r.read_current_map()) == (3, 10), "never got into Saffron City"
    assert 369 not in live.r.read_key_items() and live.r.read_flag(0x2A6)           # the guard drank it; the flag stays


def test_lavender_story_tower_flute_snorlax_end_to_end(live):
    """quest('pokemon_tower') → quest('poke_flute') → quest('snorlax') on the real ROM, staged by flying to Lavender with the Silph Scope: the
    tower's 7 floors (ghost wilds, the rival's trigger on 2F, the 6F Marowak ghost, the three Grunts on 7F), Fuji's warp to his house, the flute,
    then Route 12: the gate house that cuts the north half off, the long walk south and the Snorlax prompt (YES) and fight."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))                  # the fixture is indoors; Fly needs the open air
    live.fly_to("lavender town", key_items=(359,))                                      # Silph Scope in the bag

    def run(name, done, rounds=30):
        out = ""
        for _ in range(rounds):
            live.heal_hp()
            if live.r.detect_context().name == "IN_BATTLE":
                c._auto_fight()
                continue
            out = c._execute("quest", json.dumps({"name": name, "auto_trainers": True}))
            if done():
                break
        return out
    out = run("pokemon_tower", lambda: live.r.read_flag(0x23C))
    assert live.r.read_flag(0x23C), out                                                 # FLAG_RESCUED_MR_FUJI
    out = run("poke_flute", lambda: live.r.read_flag(0x23D), rounds=6)
    assert live.r.read_flag(0x23D) and 350 in live.r.read_key_items(), out              # the Poké Flute
    out = run("snorlax", lambda: live.r.read_flag(0x253))
    assert live.r.read_flag(0x253), out                                                  # FLAG_WOKE_UP_ROUTE_12_SNORLAX
    assert "already awake" in c._execute("quest", json.dumps({"name": "snorlax"})) or "already done" in c._execute("quest", json.dumps({"name": "snorlax"}))


def test_pokemon_mansion_quest_gets_the_secret_key(live):
    """quest('pokemon_mansion') on the real ROM, staged by flying to Cinnabar: the global statue switch (pressed from the tile SOUTH of a statue,
    facing up), the directional stairs (stand on the tile, hold their button), the 3F hole down to 1F, the stairs to B1F and two more presses —
    all planned by knowledge.mansion_route from decomp data (tools/gen_mansion.py) — then the Secret Key at B1F (5,7)."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to("cinnabar island")
    out = ""
    for _ in range(40):
        live.heal_hp()
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
            continue
        out = c._execute("quest", json.dumps({"name": "pokemon_mansion", "auto_trainers": True}))
        if 351 in live.r.read_key_items():
            break
    assert 351 in live.r.read_key_items(), out                                  # ITEM_SECRET_KEY
    assert out.startswith("Got the Secret Key")


def _staged_gym(live, town, beaten, approach, gym_map, flags=(), key_items=()):
    """Fly to `town`, mark every trainer beaten (so the test is about NAVIGATION: a fight on the way is noise), go_to the gym and call challenge_leader()
    until the player stands on the Leader's approach tile. Returns the last message."""
    live.load("celadon_gym_door")
    live.c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to(town, flags=flags, key_items=key_items)
    c = live.c
    old = list(c.ltm.data.get("gyms_beaten", []))
    c.ltm.data["gyms_beaten"] = beaten
    try:
        live.defeat_all_trainers()
        c._execute("go_to", json.dumps({"destination": "Gym", "force": True}))
        assert tuple(live.r.read_current_map()) == gym_map, "never got into the gym"
        out = ""
        for _ in range(6):
            out = c._execute("challenge_leader", "{}")
            if tuple(live.r.read_player_pos()) == approach:
                break
        assert tuple(live.r.read_player_pos()) == approach, out
        return out
    finally:
        c.ltm.data["gyms_beaten"] = old


def test_giovanni_gym_spinner_maze_reaches_the_leader(live):
    """Viridian Gym: arrow tiles slide the player (find_path_spin in walk_to)."""
    _staged_gym(live, "viridian city", ["Brock", "Misty", "Lt. Surge", "Erika", "Koga", "Sabrina", "Blaine"], (2, 3), (5, 1))


def test_koga_gym_invisible_walls_reach_the_leader(live):
    """Fuchsia Gym: the invisible walls are real collisions, so the live grid already has them."""
    _staged_gym(live, "fuchsia city", ["Brock", "Misty", "Lt. Surge", "Erika"], (7, 14), (11, 3))


def test_sabrina_gym_teleport_pads_reach_the_leader(live):
    """Saffron Gym: 30 pads, each teleporting to a partner pad (knowledge.gym_pads plans the chain; walk_to must not cross a pad by accident).
    The Rockets are gone (FLAG_HIDE_SAFFRON_ROCKETS) so the city's gym door is open."""
    _staged_gym(live, "saffron city", ["Brock", "Misty", "Lt. Surge", "Erika", "Koga"], (14, 12), (14, 3), flags=(0x3E,))


def test_blaine_gym_quiz_doors_reach_the_leader(live):
    """Cinnabar Gym: six quiz machines (YES / NO per the decomp, pressed from the tile south of the machine). The gym door unlocks at map load when
    the Secret Key's hide flag (0x1A8) is set."""
    _staged_gym(live, "cinnabar island", ["Brock", "Misty", "Lt. Surge", "Erika", "Koga", "Sabrina"], (5, 5), (12, 0), flags=(0x1A8,), key_items=(351,))


def test_silph_co_quest_clears_the_building(live):
    """quest('silph_co') on the real ROM, staged by flying to Saffron: the floors are solved by knowledge.silph_route (stairs, teleport pads, card-key
    doors), the Card Key comes from the 5F item ball, the worker on 7F gives the Lapras, Giovanni's scene starts on 11F and the President hands over
    the Master Ball."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to("saffron city", flags=(0x23C, 0x2A6))                  # Fuji rescued: the Rocket guard at the Silph door falls asleep
    out = ""
    for _ in range(80):
        live.boost_party()                                       # the fixture party is far under the Rockets / rival / Giovanni
        live.patch_mon(0, moves=[75, 22, 33, 0], pps=[25, 25, 35, 0])
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
            continue
        out = c._execute("quest", json.dumps({"name": "silph_co", "auto_trainers": True}))
        if live.r.read_flag(0x250) and live.r.read_flag(0x246):
            break
    assert 355 in live.r.read_key_items(), out                                  # the Card Key
    assert live.r.read_flag(0x246), out                                         # FLAG_GOT_LAPRAS_FROM_SILPH
    assert live.r.read_flag(0x250), out                                         # FLAG_GOT_MASTER_BALL_FROM_SILPH


def test_victory_road_quest_reaches_indigo_plateau(live):
    """quest('victory_road') on the real ROM, staged by flying to Viridian with all eight badges, Surf + Strength on the lead and a level-60 lead
    (the fixture party is 10-30 levels under the cave's wild Pokémon): go_to carries it through Route 22's rival, Route 23's badge guards and the
    river; inside, knowledge.vr_route plans the three floors — 1F's switch boulder (19 pushes), 2F's west switch, the boulder dropped down 3F's hole
    to 2F's second switch, the 3F side room (a double battle) and 2F's east exit — and go_to walks Route 23's north half to Indigo Plateau."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to("viridian city", badges=0xFF)
    live.strong_lead()
    out = ""
    for _ in range(60):
        if live.r.detect_context().name != "IN_BATTLE":
            live.boost_party()                                                       # between battles only: a level-up recomputes the stats
            live.patch_mon(0, moves=[75, 57, 70, 22], pps=[25, 15, 15, 25])          # Razor Leaf, Surf, Strength, Vine Whip
        else:
            c._auto_fight()
            continue
        out = c._execute("quest", json.dumps({"name": "victory_road", "auto_trainers": True}))
        if live.r.read_flag(0x899):
            break
    assert live.r.read_flag(0x899), out                                          # FLAG_VISITED_INDIGO_PLATEAU


def test_under_levelled_party_is_kept_away_from_cerulean_rival(live):
    """A watched run: grind() relocated to Route 24 and the autopilot lost to the rival's ambush at Cerulean's north exit over and over, reporting
    'no tall grass is reachable'. With the party's best at L19 and the scene undone, Route 24 is gated: go_to says so (rival, L21) and grind() never
    walks north; with the best at L21 the gate opens."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to("cerulean city")                                                     # Fly needs the badges; the run in question had two
    live.set_badges(0b11)
    live.set_flag(0x29B, False)                                                      # the rival scene (FLAG_GOT_FAME_CHECKER) has not happened
    for slot, lv in enumerate((19, 16, 16, 15, 14, 13)):
        live.patch_mon(slot, level=lv)
    out = c._execute("go_to", json.dumps({"destination": "Route 24", "force": True}))
    assert "rival" in out and "L21" in out, out
    assert tuple(live.r.read_current_map())[0] == 3                                  # still outdoors in Cerulean's region, not walked north
    live.patch_mon(0, level=21)
    out = c._execute("go_to", json.dumps({"destination": "Route 24", "force": True}))
    assert "rival" not in out or "ambush" not in out


def test_grind_from_route_4_pocket_goes_back_to_route_3_not_round_to_route_22(live):
    """Regression (watched run): the Mt. Moon-side Pokémon Center exits into Route 4's west pocket, where no grass is reachable; NO_WALK
    wrongly blocked Route 3 one step south, so grind walked the party to Route 22 (wild L2-5) and the misleading SS-ticket gate hint was shown."""
    live.load("route3_weak_team")
    live.c._execute("go_to", json.dumps({"destination": "Pokemon Center"}))
    live.c._execute("walk_to", json.dumps({"x": 7, "y": 8}))
    assert tuple(live.r.read_current_map()) == (3, 22)
    out = live.c._execute("grind", json.dumps({"level": 20}))
    assert tuple(live.r.read_current_map()) == (3, 21), out

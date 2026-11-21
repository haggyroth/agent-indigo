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
    got = ""
    for _ in range(3):                                                               # the fixture has 3 Poké Balls; the foe is kept at 1 HP so each throw is ~96% to catch
        live.set_foe_hp(1)
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
    assert "No script for this one yet" not in c._execute("quest", json.dumps({"name": "silph_co"}))      # silph_co has a driver now: it answers (here: the readiness warning), never "no script"
    tower = c._execute("quest", json.dumps({"name": "pokemon_tower"}))
    if "Silph Scope" not in tower:                                                                          # the first call may be the readiness warning (a 2nd call proceeds)
        tower = c._execute("quest", json.dumps({"name": "pokemon_tower"}))
    assert "Silph Scope" in tower                                                                           # the Tower's script says what it needs
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


def test_shift_style_hands_the_free_switch_to_a_lagging_teammate_after_a_trainer_mon_faints(live):
    """Battle Style SHIFT on the real ROM: Surge's Voltorb faints with Ivysaur (L30) out and five L22 teammates behind it. The 'Will you change
    POKéMON?' box comes up and the bot answers YES itself, sending in the strongest healthy laggard at no cost of a turn (the result says so)."""
    from game.options import apply_battle_style
    live.load("vermilion_gym_surge")
    apply_battle_style(live.m, "shift")
    c = live.c
    ace = live.r.read_party()[0].species_id
    auto = ""
    for _ in range(40):
        live.heal_hp()
        if live.r.detect_context().name != "IN_BATTLE":
            c._execute("challenge_leader", json.dumps({}))
            continue
        moves = live.r.read_active_battle_moves()[1]
        out = c._execute("use_move", json.dumps({"move": moves[0]}))
        if "Auto: the free switch" in out:
            auto = out
            break
    assert auto, "no automatic free switch happened"
    assert "FREE switch" in auto and not c._shift_prompt_live()
    assert live.r.read_active_battle_species() != ace and live.r.read_party()[0].level >= 22


def test_grind_walks_through_route_9s_cut_tree_to_the_grass(live):
    """Regression (watched run): Route 9's grass is behind a Cut tree AND a ledge hop. The Cut planner ignored ledges, so walk_to said 'no path' at the
    map's west edge and grind() relocated Route 11 <-> Route 9 six times. The tree must be cut and the grass reached."""
    live.load("vermilion_gym_surge")
    c = live.c
    for _ in range(8):
        c._execute("go_to", json.dumps({"destination": "Route 9", "force": True}))
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
        elif tuple(live.r.read_current_map()) == (3, 27):
            break
    assert tuple(live.r.read_current_map()) == (3, 27)
    for _ in range(8):                                   # trainers on the route interrupt the walk
        c._walk_to(7, 5)
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
        elif tuple(live.r.read_player_pos()) == (7, 5):
            break
    assert tuple(live.r.read_player_pos()) == (7, 5)


def test_shop_sell_turns_treasure_into_money_and_keeps_the_potions(live):
    """shop(sell=true) at a Mart on the real ROM (#270): the clerk's SELL → the bag → A, A, A per unit. Treasure goes, money rises by its price,
    Potions are untouched, a named protected item is refused, and a second call with nothing left says so."""
    live.load("vermilion_gym_surge")
    c = live.c
    for _ in range(8):                                    # the gym trainer is on the way out
        c._execute("go_to", json.dumps({"destination": "Mart", "force": True}))
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
        elif tuple(live.r.read_current_map()) == (9, 5):
            break
    live.heal_hp()
    live.give_item(110, 2)
    live.give_item(106, 3)
    held = {i: live.r.count_item(i) for i in (14, 17, 15, 18)}              # cures: must survive (a spare A once sold the neighbours of a sold stack)
    money = live.r.read_money()
    out = c._execute("shop", json.dumps({"sell": True, "item": "pearl", "quantity": 3}))
    assert out.startswith("Sold 3× Pearl"), out
    out = c._execute("shop", json.dumps({"sell": True}))                     # whatever treasure is left: the fixture holds a Nugget of its own
    assert out.startswith("Sold") and "Nugget" in out, out
    assert live.r.count_item(106) == 0 and not any(i in live.r.read_bag() for i in (110, 106))
    assert live.r.read_money() > money + 2 * 5000 + 3 * 700 - 1
    assert {i: live.r.count_item(i) for i in held} == held
    assert "Not selling" in c._execute("shop", json.dumps({"sell": True, "item": "antidote"}))
    assert "Nothing spare" in c._execute("shop", json.dumps({"sell": True}))


def test_forget_move_deletes_an_hm_move_at_the_fuchsia_move_deleter(live):
    """forget_move on the real ROM (#273): the Move Deleter removes an HM move that the normal forget prompt refuses. Staged by flying to Fuchsia with a
    Pokémon that knows Cut / Surf / Strength / Tackle; the last Cut in the party is protected, and an unknown move is reported."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to("fuchsia city")
    live.patch_mon(1, moves=[15, 57, 70, 33], pps=[30, 15, 15, 35])
    assert "only one who knows Cut" in c._execute("forget_move", json.dumps({"pokemon": "2", "move": "Cut"}))
    assert "doesn't know" in c._execute("forget_move", json.dumps({"pokemon": "2", "move": "Fly"}))
    out = c._execute("forget_move", json.dumps({"pokemon": "2", "move": "Tackle"}))
    assert "forgot Tackle" in out, out
    assert "Tackle" not in live.r.read_party()[1].move_names
    out = c._execute("forget_move", json.dumps({"pokemon": "2", "move": "Cut", "force": True}))        # an HM move: only the Deleter can
    assert "forgot Cut" in out, out
    assert [m for m in live.r.read_party()[1].move_names if m] == ["Surf", "Strength"], live.r.read_party()[1].move_names     # nothing else went with it
    assert tuple(live.r.read_current_map()) == (11, 9) and live.r.detect_context().name == "OVERWORLD"


def test_elite_four_quest_clears_the_league_to_the_hall_of_fame(live):
    """quest('elite_four') on the real ROM (#259), staged by flying to Indigo Plateau with all eight badges and a boosted L70 lead: prep at the Center
    (heal, shop, save to slot 3), the north door, the five sealed rooms (the forced walk up each, the leader's talk, the door opening on the win) and the
    Hall of Fame, which sets FLAG_SYS_GAME_CLEAR. Every foe is made one hit from fainting so the test is about the driver, not the damage race."""
    import pytest
    from game.constants import Addr
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to("indigo plateau", badges=0xFF)
    live.strong_lead(level=70, exp=344960)
    foe = Addr.BATTLE_MON0_SPECIES + 0x58
    use_move = c._use_move

    def weak_foe(name):
        if live.m.read16(foe) and live.m.read16(foe + 0x28) > 1:
            live.m.write16(foe + 0x28, 1)
        return use_move(name)
    c._use_move = weak_foe
    out = ""
    for _ in range(60):
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
            continue
        live.boost_party()
        live.patch_mon(0, moves=[63, 89, 58, 57], pps=[5, 10, 10, 15])
        out = c._execute("quest", json.dumps({"name": "elite_four", "auto_trainers": True}))
        if live.r.read_flag(0x82C):
            break
    assert live.r.read_flag(0x82C), out                                                  # FLAG_SYS_GAME_CLEAR
    assert tuple(live.r.read_current_map()) == (1, 80), live.r.read_current_map()        # the Hall of Fame


def test_league_prep_sells_treasure_at_the_plateau_clerk_and_buys_revives_and_full_restores(live):
    """The Plateau's Pokémon Center has a clerk (Full Restores, Max Potions, Revives): with ¥1500 and four Nuggets the League prep sells the treasure there
    (the sell bag opens on the LAST used pocket — here the empty Poké Balls pocket — so the driver must switch to Items) and spends the money on Revives, then
    Full Restores; team_report shows the MONEY line while the money is short."""
    live.load("league_door")
    c = live.c
    live.set_money(1500)
    live.give_item(110, 3)
    assert "MONEY:" in c._execute("team_report", json.dumps({}))
    note = c._league_prep("quest('elite_four')")
    assert "Sold" in note and "Revive" in note and "Full Restore" in note, note
    bag = live.r.read_bag()
    assert 110 not in bag and bag.get(24, 0) >= 4 and bag.get(19, 0) >= 1, bag


def test_a_league_loss_resets_the_rooms_and_quest_elite_four_starts_over(live):
    """The loss path on the real ROM (#259): losing in Agatha's room heals the party, takes money, clears every FLAG_DEFEATED_* and respawns at the
    Plateau's Pokémon Center (the decomp's DoWhiteOut → EventScript_ResetEliteFourEnd) — and quest('elite_four') then goes back in from Lorelei."""
    from game.constants import Addr
    live.load("league_agatha")
    c = live.c
    assert live.r.read_flag(0x4B8) and live.r.read_flag(0x4B9) and not live.r.read_flag(0x4BA)
    money = live.r.read_money()
    for _ in range(6):                                           # talk to Agatha without the autopilot: a battle starts
        c._execute("quest", json.dumps({"name": "elite_four", "auto_trainers": False}))
        if live.r.detect_context().name == "IN_BATTLE":
            break
    assert live.r.detect_context().name == "IN_BATTLE"
    for slot in range(len(live.r.read_party())):                 # every Pokémon at 0 HP: the next turn is the loss
        live.m.write16(Addr.PARTY_DATA + 100 * slot + 0x56, 0)
    live.m.write16(Addr.BATTLE_MON0_SPECIES + 0x28, 0)
    for _ in range(80):
        live.m.tap("A")
        live.m.tick(30)
        if tuple(live.r.read_current_map()) == (13, 0):
            break
    live.m.tick(120)
    assert tuple(live.r.read_current_map()) == (13, 0)                                   # the Plateau's Pokémon Center
    assert not any(live.r.read_flag(f) for f in (0x4B8, 0x4B9, 0x4BA, 0x4BB, 0x4BC))      # the whole League is reset
    assert live.r.read_money() < money and all(p.current_hp > 0 for p in live.r.read_party())
    for _ in range(6):
        c._execute("quest", json.dumps({"name": "elite_four", "auto_trainers": False}))
        if live.r.detect_context().name == "IN_BATTLE":
            break
    assert tuple(live.r.read_current_map()) == (1, 75)                                   # back in Lorelei's room


def test_the_credits_end_in_a_soft_reset_and_continue_lands_in_pallet_town(live):
    """What happens after the Champion (#259), on the native backend: the Hall of Fame sets FLAG_SYS_GAME_CLEAR, the game returns to Indigo Plateau and rolls
    the credits (~14,000 frames), then SOFT-RESETS to the title screen (RAM empty for a moment, then the attract-mode loop); the battery save holds the cleared
    game, and Continue (main.drive_into_gameplay) puts you in Pallet Town with the badges and the flag. main()'s run therefore ends at the milestone, before this."""
    import main
    from game.constants import Addr
    live.load("league_champion")
    c = live.c
    foe = Addr.BATTLE_MON0_SPECIES + 0x58
    use_move = c._use_move

    def weak_foe(name):
        if live.m.read16(foe) and live.m.read16(foe + 0x28) > 1:
            live.m.write16(foe + 0x28, 1)
        return use_move(name)
    c._use_move = weak_foe
    live.boost_party()
    for _ in range(40):
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
            continue
        c._execute("quest", json.dumps({"name": "elite_four", "auto_trainers": True}))
        if live.r.read_flag(0x82C):
            break
    assert live.r.read_flag(0x82C) and tuple(live.r.read_current_map()) == (1, 80)
    saw_plateau = reset = False
    for i in range(120):                                         # up to ~29,000 frames: the credits, then the reset
        live.m.tick(240)
        if i % 6 == 0 and i < 60:
            live.m.tap("A")                                      # Oak's speech
        here = tuple(live.r.read_current_map())
        saw_plateau = saw_plateau or here == (3, 9)
        if here == (0, 0) and not live.r.read_party():
            reset = True
            break
    assert saw_plateau and reset, (saw_plateau, reset)
    assert main.drive_into_gameplay(live.m, live.r)
    assert tuple(live.r.read_current_map()) == (3, 0)                                    # Pallet Town
    assert live.r.read_flag(0x82C) and live.r.read_badges()[0] == 8 and len(live.r.read_party()) == 6
    live.m.save_state_file(str(live.dir / "post_hof.ss1"))        # the post-game fixture (Pallet Town, game cleared, 8 badges): the Sevii / Mewtwo / roamer work starts here


def test_flash_and_fly_quests_collect_the_hms(live):
    """quest('flash') and quest('fly') on the real ROM (#268, #293): the Route 2 east building's Aide gives HM05 once 10 species are seen (the fixture has seen
    52), and the Route 16 house's woman gives HM02 — reached from Celadon by go_to through the region graph's Cut-tree link: cut the tree at (41,11), take the
    UPPER gatehouse and walk west (no Poké Flute: the Snorlax guards only the lower road)."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    assert not live.r.read_flag(0x238)
    live.patch_mon(0, moves=[75, 15, 33, 22], pps=[25, 30, 35, 25])                       # Razor Leaf, Cut, Tackle, Vine Whip
    for _ in range(10):
        out = c._execute("quest", json.dumps({"name": "fly", "auto_trainers": True}))
        if live.r.read_flag(0x238):
            break
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
    assert live.r.read_flag(0x238), out                                                   # FLAG_GOT_HM02
    for _ in range(8):                                                                     # out of the house (and past Route 16's trainers): Fly works outdoors only
        c._execute("go_to", json.dumps({"destination": "Celadon City", "force": True}))
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
        elif tuple(live.r.read_current_map()) == (3, 6):
            break
    live.fly_to("viridian city", badges=0xFF)
    live.patch_mon(0, moves=[75, 15, 33, 22], pps=[25, 30, 35, 25])                       # Cut: Route 2's east building is past a tree
    for _ in range(8):
        out = c._execute("quest", json.dumps({"name": "flash", "auto_trainers": True}))
        if live.r.read_flag(0x23B):
            break
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
    assert live.r.read_flag(0x23B), out                                                   # FLAG_GOT_HM05


def test_early_gift_quests_dig_hitmon_and_magikarp(live):
    """quest('dig') / quest('hitmon') / quest('magikarp') on the real ROM (#278): the Cerulean thief gives TM28 back after a battle, the Fighting Dojo's master
    is beaten and Hitmonchan taken (a one-time choice; the party is full so it goes to the PC box, the 'nickname?' box is declined), and the Route 4 salesman
    sells a Magikarp for ¥500 (reached from Pewter: from Cerulean's side of Route 4 go_to stalls at the east end)."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c

    def run(name, flag, tries=8):
        for _ in range(tries):
            out = c._execute("quest", json.dumps({"name": name, "auto_trainers": True}))
            if live.r.read_flag(flag):
                return out
            if live.r.detect_context().name == "IN_BATTLE":
                c._auto_fight()
        return out
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to("cerulean city", badges=0xFF)
    live.strong_lead(level=60)
    live.patch_mon(0, moves=[75, 15, 33, 22], pps=[25, 30, 35, 25])
    for f in (0x23F, 0x03B, 0x663):                                    # TM28 not yet returned; the grunt present and unbeaten
        live.set_flag(f, False)
    count = live.r.count_item
    live.r.count_item = lambda i: 0 if i == 316 else count(i)          # the fixture already carries a TM28
    assert live.r.read_flag(0x23F) is False
    out = run("dig", 0x23F)
    live.r.count_item = count
    assert live.r.read_flag(0x23F), out
    live.fly_to("saffron city", badges=0xFF, flags=(0x2A6, 0x23C, 0x250))
    live.strong_lead(level=60)
    live.patch_mon(0, moves=[75, 15, 33, 22], pps=[25, 30, 35, 25])
    out = run("hitmon", 0x278, 10)
    assert live.r.read_flag(0x278) and "Hitmonchan" in out, out
    c._execute("go_to", json.dumps({"destination": "Saffron City", "force": True}))        # out of the Dojo: Fly works outdoors only
    live.fly_to("pewter city", badges=0xFF)
    live.set_money(2000)
    money = live.r.read_money()
    out = run("magikarp", 0x249)
    assert live.r.read_flag(0x249) and live.r.read_money() == money - 500, out


def test_oak_aides_give_the_itemfinder_and_the_exp_share_for_species_caught(live):
    """quest('itemfinder') / quest('exp_share') on the real ROM (#275): the Route 11 gatehouse aide wants 30 species CAUGHT (told how many more when short), the Route 15
    one wants 50 and the Exp. Share ends up on the Pokémon that lags. The game counts a species caught only when its owned bit and all three seen arrays agree
    (live.set_dex stages all four)."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to("vermilion city", badges=0xFF)
    live.patch_mon(0, moves=[75, 15, 33, 22], pps=[25, 30, 35, 25])
    live.defeat_all_trainers()
    live.set_dex(12)
    assert "caught 12" in c._execute("quest", json.dumps({"name": "itemfinder"}))
    live.set_dex(31)
    for _ in range(10):
        out = c._execute("quest", json.dumps({"name": "itemfinder", "auto_trainers": True}))
        if live.r.read_flag(0x252):
            break
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
    assert live.r.read_flag(0x252), out                                                   # FLAG_GOT_ITEMFINDER
    for _ in range(6):                                                                    # out of the gatehouse: Fly works outdoors only
        c._execute("go_to", json.dumps({"destination": "Vermilion City", "force": True}))
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
        elif tuple(live.r.read_current_map()) == (3, 5):
            break
    live.fly_to("fuchsia city", badges=0xFF)
    live.set_dex(52)
    live.set_flag(0x253)
    for _ in range(10):
        out = c._execute("quest", json.dumps({"name": "exp_share", "auto_trainers": True}))
        if live.r.read_flag(0x256):
            break
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
    assert live.r.read_flag(0x256), out                                                   # FLAG_GOT_EXP_SHARE_FROM_OAKS_AIDE
    party = live.r.read_party()
    holder = next(p for p in party if p.held_item == 182)
    assert holder.level == min(p.level for p in party)                                    # the one that lags behind


def test_pick_up_items_collects_the_worthwhile_hidden_items_on_route_9(live):
    """pick_up_items on Route 9 (#276): the Ether at (15,7) and the Rare Candy at (63,2) are hidden tiles — walk beside each, FACE it (a 3-frame press turns; a tap would step
    onto the walkable tile and A there does nothing) and press A. The Itemfinder is not needed once the tile is known; collected tiles are not walked to again."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to("cerulean city", badges=0xFF)
    live.patch_mon(0, moves=[75, 15, 33, 22], pps=[25, 30, 35, 25])
    for _ in range(10):
        c._execute("go_to", json.dumps({"destination": "Route 9", "force": True}))
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
        elif tuple(live.r.read_current_map()) == (3, 27):
            break
    live.defeat_all_trainers()
    before = dict(live.r.read_bag())
    out = ""
    for _ in range(4):
        out += c._execute("pick_up_items", json.dumps({}))
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
    after = live.r.read_bag()
    assert after.get(34, 0) == before.get(34, 0) + 1 and after.get(68, 0) == before.get(68, 0) + 1, (out, after)       # an Ether and a Rare Candy
    assert {"3/27/15/7", "3/27/63/2"} <= set(c.ltm.data["hidden_taken"])
    assert "No item balls visible" in c._execute("pick_up_items", json.dumps({}))                                      # nothing left to walk to


def test_rod_and_bike_quests_collect_the_key_items(live):
    """quest('old_rod') (Vermilion house 1), quest('bike') (the Fan Club chairman's voucher, then the Cerulean Bike Shop) and quest('good_rod') (Fuchsia house 2)
    on the real ROM (#269); each is a talk with 'Do you like to fish?' / the story → YES."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c

    def run(name, flag, tries=10):
        out = ""
        for _ in range(tries):
            out = c._execute("quest", json.dumps({"name": name, "auto_trainers": True}))
            if live.r.read_flag(flag):
                return out
            if live.r.detect_context().name == "IN_BATTLE":
                c._auto_fight()
        return out

    def outside(town_map, town):
        for _ in range(8):
            c._execute("go_to", json.dumps({"destination": town, "force": True}))
            if live.r.detect_context().name == "IN_BATTLE":
                c._auto_fight()
            elif tuple(live.r.read_current_map()) == town_map:
                return
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to("vermilion city", badges=0xFF)
    live.patch_mon(0, moves=[75, 15, 33, 22], pps=[25, 30, 35, 25])
    live.defeat_all_trainers()
    assert live.r.read_flag(0x240) or "Old Rod" in run("old_rod", 0x240)
    assert live.r.read_flag(0x240) and 262 in live.r.read_key_items()
    outside((3, 5), "Vermilion City")
    out = run("bike", 0x271, 12)
    assert live.r.read_flag(0x241) and live.r.read_flag(0x271) and 360 in live.r.read_key_items(), out        # voucher, then the Bicycle
    for _ in range(6):                                                                                       # out of the shop: Fly works outdoors only
        c._execute("go_to", json.dumps({"destination": "Cerulean City", "force": True}))
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
        elif tuple(live.r.read_current_map()) == (3, 3):
            break
    live.fly_to("fuchsia city", badges=0xFF)
    out = run("good_rod", 0x244)
    assert live.r.read_flag(0x244) and 263 in live.r.read_key_items(), out


def test_fish_hooks_a_wild_pokemon_and_the_bicycle_mounts_and_dismounts(live):
    """fish() on the real ROM (#269): from a Vermilion shore the Old Rod is cast from the Bag (Key Items → rod → USE) and A is pressed through the cast — ignored during
    the dots, landing in the bite window — until a wild Pokémon is on the hook (a battle) or 'not even a nibble'. use_item('Bicycle') flips gPlayerAvatar's bike flag and
    walk_to gets off the bike first (a bike covers two tiles per press and overshot targets into doors)."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to("vermilion city", badges=0xFF)
    live.give_key_item(262)
    live.give_key_item(360)
    hooked = False
    for _ in range(12):
        out = c._execute("fish", json.dumps({"casts": 4}))
        if live.r.detect_context().name == "IN_BATTLE":
            hooked = True
            assert "on the hook" in out, out
            break
        assert "no bite" in out, out
    assert hooked, "twelve rounds of four casts never hooked anything"
    c._auto_fight()
    live.m.tick(60)
    assert live.r.detect_context().name == "OVERWORLD"
    assert not live.r.is_biking()
    assert "riding the Bicycle" in c._execute("use_item", json.dumps({"item": "Bicycle"})) and live.r.is_biking()
    px, py = live.r.read_player_pos()
    c._walk_to(px, py + 1) if False else c._walk_to(px - 1, py)                          # any adjacent walk: it must dismount first
    assert not live.r.is_biking()


def test_move_tutor_teaches_substitute_into_a_free_slot_and_over_a_forgotten_move(live):
    """tutor('Substitute') on the real ROM (#274): the Fuchsia City tutor (a Bug Catcher at (15,11)) — talk, YES, YES, the party screen, and for a Pokémon with four moves the
    summary screen to forget one. Free slot: Venusaur just learns it; full moveset: Pidgeotto replaces a status move (not an HM, not its last attack). The lesson is one-time."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    c._execute("go_to", json.dumps({"destination": "Celadon City"}))
    live.fly_to("fuchsia city", badges=0xFF)
    live.defeat_all_trainers()
    out = c._execute("tutor", json.dumps({"move": "Substitute", "pokemon": "Venusaur"}))
    assert "learned Substitute" in out and live.r.read_flag(0x2C8), out
    assert "Substitute" in live.r.read_party()[0].move_names
    assert "already taught Substitute" in c._execute("tutor", json.dumps({"move": "Substitute"}))                # one-time
    live.set_flag(0x2C8, False)                                                                                    # second Pokémon, the full-moveset path
    out = c._execute("tutor", json.dumps({"move": "Substitute", "pokemon": "Pidgeotto"}))
    pidgeotto = next(p for p in live.r.read_party() if p.species_name == "Pidgeotto")
    assert "learned Substitute" in out and "forgetting" in out, out
    assert "Substitute" in pidgeotto.move_names and len([m for m in pidgeotto.move_names if m]) == 4


def test_quest_brock_travels_to_the_gym_and_challenges_the_leader(live):
    """quest('brock') on the real ROM (#260): from Pewter City it walks into the Gym, gives the once-only lopsided-team warning, then challenges the Gym trainer and Brock (the
    fights are played by the test like the model would) — and the badge flips the beat to done. The parcel counts as delivered from FLAG_SYS_POKEDEX_GET (a save from after the
    parcel has no milestone, which used to block every gym beat)."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    for _ in range(6):
        c._execute("go_to", json.dumps({"destination": "Celadon City", "force": True}))
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
        elif tuple(live.r.read_current_map()) == (3, 6):
            break
    live.fly_to("pewter city", badges=0xFF)
    live.set_badges(0)
    for f in (0x500 + 414, 0x4B0, 0x500 + 142, 0x820):             # Brock and the Camper not yet beaten; FLAG_DEFEATED_BROCK and FLAG_BADGE01_GET clear
        live.set_flag(f, False)
    live.strong_lead(level=30, exp=27000)
    live.patch_mon(0, moves=[75, 22, 33, 0], pps=[25, 25, 35, 0])
    assert c._story()["brock"] == "next"
    first = c._execute("quest", json.dumps({"name": "brock"}))
    assert tuple(live.r.read_current_map()) == (6, 2) and "lopsided" in first, first
    out = ""
    for _ in range(14):
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
            continue
        live.boost_party()
        out = c._execute("quest", json.dumps({"name": "brock"}))
        if live.r.read_badges()[1] & 1:
            break
    assert live.r.read_badges()[1] & 1, out
    assert "already done" in c._execute("quest", json.dumps({"name": "brock"}))


def test_team_report_carries_the_dex_plan_line(live):
    """team_report (#266) ends with the Pokédex line: the caught count from the game's own dex bits and the easiest next catches with where / how."""
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    live.set_dex(19)
    out = live.c._execute("team_report", json.dumps({}))
    line = next(ln for ln in out.splitlines() if ln.startswith("DEX:"))
    assert line.startswith("DEX: 19/151 caught. Easiest next: ") and "wild:" in line, line
    live.set_dex(151)
    assert "DEX: all 151 Kanto species caught." in live.c._execute("team_report", json.dumps({}))


def test_snorlax_is_a_one_shot_the_model_plays_with_a_saved_state(live):
    """quest('snorlax') on the real ROM (#272): the Route 12 Snorlax fight is NOT played by the autopilot (it would knock it out); the battle is handed to the model with the
    ONE-SHOT protocol (gentlest move, never KO) and the battle-start state saved in slot 9 — hitting it and load_state(9) restores its full HP."""
    import pytest
    from types import SimpleNamespace as NS
    from agent.observation import _one_shot
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    for _ in range(6):
        c._execute("go_to", json.dumps({"destination": "Celadon City", "force": True}))
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
        elif tuple(live.r.read_current_map()) == (3, 6):
            break
    live.fly_to("lavender town", flags=(0x23C, 0x23D), key_items=(350,))
    live.give_item(2, 5)
    foe = None
    for _ in range(14):
        c._execute("quest", json.dumps({"name": "snorlax", "auto_trainers": False}))
        if live.r.detect_context().name == "IN_BATTLE":
            foe = live.r.read_enemy_lead()
            if foe and foe.species_id == 143:
                break
            c._auto_fight()                                              # the Route 12 trainers on the way
    assert foe and foe.species_id == 143 and foe.current_hp == foe.max_hp, "the Snorlax fight was not handed to the model"
    _ids, names, pp = live.r.read_active_battle_moves()
    t = NS(run=NS(), map_key=tuple(live.r.read_current_map()), reader=live.r)
    text = _one_shot(t, foe, list(names), list(pp))
    assert "ONE-SHOT: Snorlax" in text and "load_state(9)" in text and t.run.one_shot_saved == (143, (3, 30)), text
    c._use_move(next(n for n in names if n))
    assert live.r.read_enemy_lead().current_hp < foe.max_hp
    assert live.m.load_state(9)
    live.m.tick(30)
    assert live.r.read_enemy_lead().current_hp == foe.max_hp and live.r.detect_context().name == "IN_BATTLE"


def test_zapdos_quest_surfs_to_the_power_plant_and_hands_the_one_shot_battle_to_the_model(live):
    """quest('zapdos') on the real ROM (#264): go_to routes over Route 10's water (the new Surf region links) to the Power Plant door, walks up to Zapdos, and the L50 legendary fight
    is handed to the model under the one-shot protocol with the battle-start state saved in slot 9."""
    import pytest
    from types import SimpleNamespace as NS
    from agent.observation import _one_shot
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    for _ in range(6):
        c._execute("go_to", json.dumps({"destination": "Celadon City", "force": True}))
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
        elif tuple(live.r.read_current_map()) == (3, 6):
            break
    live.fly_to("lavender town", flags=(0x23C, 0x23D))
    live.patch_mon(0, moves=[57, 15, 75, 22], pps=[15, 30, 25, 25])        # Surf, Cut, Razor Leaf, Vine Whip
    live.strong_lead(60)                                                     # out-levels the cave wilds, so Max Repel keeps them away
    live.give_item(2, 5)
    live.give_item(84, 30)
    foe = None
    for _ in range(40):
        if live.r.detect_context().name != "IN_BATTLE":
            c._execute("use_item", json.dumps({"item": "Max Repel"}))
        c._execute("quest", json.dumps({"name": "zapdos", "auto_trainers": False}))
        if live.r.detect_context().name == "IN_BATTLE":
            foe = live.r.read_enemy_lead()
            if foe and foe.species_id == 145:
                break
            c._auto_fight()                                                  # Rock Tunnel / Route 10 trainers and wilds on the way
    assert foe and foe.species_id == 145 and foe.current_hp == foe.max_hp, "the Zapdos fight was not handed to the model"
    assert tuple(live.r.read_current_map()) == (1, 95)
    _ids, names, pp = live.r.read_active_battle_moves()
    t = NS(run=NS(), map_key=(1, 95), reader=live.r)
    text = _one_shot(t, foe, list(names), list(pp))
    assert "ONE-SHOT: Zapdos" in text and "load_state(9)" in text and t.run.one_shot_saved == (145, (1, 95)), text


def test_articuno_quest_drops_the_b3f_boulders_stops_the_current_and_hands_over_the_fight(live):
    """quest('articuno') on the real ROM (#264): from Fuchsia it surfs Route 19/20, walks the Seafoam floors to B3F's boulder room, pushes two boulders through the holes (B4F's reveal
    flags clear), re-enters B4F where the current has stopped, surfs to the platform and starts the L50 Articuno fight under the one-shot protocol."""
    import pytest
    from types import SimpleNamespace as NS
    from agent.observation import _one_shot
    from knowledge import seafoam_data as sd
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    c = live.c
    for _ in range(6):
        c._execute("go_to", json.dumps({"destination": "Celadon City", "force": True}))
        if live.r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
        elif tuple(live.r.read_current_map()) == (3, 6):
            break
    live.fly_to("fuchsia city")
    live.patch_mon(0, moves=[57, 70, 75, 22], pps=[15, 15, 25, 25])        # Surf, Strength, Razor Leaf, Vine Whip
    live.strong_lead(60)
    live.give_item(2, 5)
    live.give_item(84, 30)
    foe, trace = None, []
    for _ in range(200):
        if live.r.detect_context().name != "IN_BATTLE":
            c._execute("use_item", json.dumps({"item": "Max Repel"}))
        out = c._execute("quest", json.dumps({"name": "articuno", "auto_trainers": False}))
        trace.append((tuple(live.r.read_current_map()), tuple(live.r.read_player_pos()), str(out)[:90]))
        if len(trace) > 12 and len({t[:2] for t in trace[-6:]}) == 1:
            break                                                            # the same spot six calls running: stuck, fail with the trace instead of grinding on
        if live.r.detect_context().name == "IN_BATTLE":
            foe = live.r.read_enemy_lead()
            if foe and foe.species_id == 144:
                break
            c._auto_fight()
    assert foe and foe.species_id == 144 and foe.current_hp == foe.max_hp, f"the Articuno fight was not handed to the model; last steps: {trace[-4:]}"
    assert tuple(live.r.read_current_map()) == (1, 87) and live.r.read_flag(sd.STOPPED_FLAG_B4F)
    _ids, names, pp = live.r.read_active_battle_moves()
    t = NS(run=NS(), map_key=(1, 87), reader=live.r)
    text = _one_shot(t, foe, list(names), list(pp))
    assert "ONE-SHOT: Articuno" in text and "load_state(9)" in text and t.run.one_shot_saved == (144, (1, 87)), text


def _outdoors_at_celadon(live):
    import pytest
    live.load("celadon_gym_door")
    if live.r.read_current_map() != (10, 16):
        pytest.skip("fixture is not at the Celadon gym door")
    for _ in range(6):
        live.c._execute("go_to", json.dumps({"destination": "Celadon City", "force": True}))
        if live.r.detect_context().name == "IN_BATTLE":
            live.c._auto_fight()
        elif tuple(live.r.read_current_map()) == (3, 6):
            break


def test_rename_pokemon_changes_a_nickname_at_the_name_rater(live):
    """rename_pokemon on the real ROM (#277): travel to Lavender's Name Rater, answer his two Yes/No boxes, pick the party slot, type the new name on the keyboard."""
    _outdoors_at_celadon(live)
    live.fly_to("lavender town")
    party = live.r.read_party()
    who = party[1].species_name
    out = live.c._execute("rename_pokemon", json.dumps({"pokemon": who, "nickname": "Zippy"}))
    assert live.r.read_party()[1].nickname == "Zippy", out
    assert "Zippy" in out and live.r.detect_context().name == "OVERWORLD"


def test_daycare_takes_a_pokemon_and_gives_it_back_for_a_fee(live):
    """daycare on the real ROM (#277): deposit the second party member at the Route 5 Day Care, walk a little, withdraw it — the party count and the money follow."""
    _outdoors_at_celadon(live)
    from knowledge.story_beats import SS_TICKET
    live.fly_to("cerulean city", flags=(0x234,), key_items=(SS_TICKET,))        # the S.S. Ticket moves the Slowbro that blocks Cerulean's south exit
    live.patch_mon(0, moves=[15, 75, 22, 33], pps=[30, 25, 25, 35])           # Cut: a tree stands in the gap of Cerulean's south wall
    live.set_money(5000)
    n0 = len(live.r.read_party())
    who = live.r.read_party()[1].species_name
    out = live.c._execute("daycare", json.dumps({"action": "deposit", "pokemon": who}))
    assert len(live.r.read_party()) == n0 - 1, out
    out = live.c._execute("daycare", json.dumps({"action": "withdraw"}))
    assert len(live.r.read_party()) == n0 and live.r.read_money() < 5000, out


def test_quest_copycat_buys_the_poke_doll_and_learns_mimic(live):
    """quest('copycat') on the real ROM (#278): the bag has no Poké Doll, so it buys one at the Celadon Dept. Store 2F, walks to Saffron's Copycat and the party learns Mimic (one-time)."""
    _outdoors_at_celadon(live)
    live.fly_to("saffron city", flags=(0x2A6, 0x03E))                           # FLAG_GOT_TEA (the gate guards let you through) + the Saffron Rockets gone (Silph Co. cleared)
    live.defeat_all_trainers()
    live.set_money(9000)
    assert not live.r.count_item(80) and not live.r.read_flag(0x2CD)
    out = ""
    for _ in range(8):
        out = live.c._execute("quest", json.dumps({"name": "copycat", "auto_trainers": True}))
        if live.r.read_flag(0x2CD) or live.r.detect_context().name != "OVERWORLD":
            if live.r.detect_context().name == "IN_BATTLE":
                live.c._auto_fight()
                continue
            break
    assert live.r.read_flag(0x2CD), out
    assert any("Mimic" in (p.move_names or []) for p in live.r.read_party()), out
    assert "already done" in live.c._execute("quest", json.dumps({"name": "copycat"}))                       # the chain marks it done by the tutor's flag


def test_new_game_quest_plays_the_intro_picks_the_starter_and_delivers_the_parcel(tmp_path, monkeypatch):
    """quest('new_game') on the real ROM from the TITLE SCREEN of a blank cartridge (#260): the controls pages and Oak's speech, BOY, the player's and the rival's names on the keyboard, the bedroom, Oak's
    intercept at Route 1, the lab, Squirtle, the rival's battle (played on autopilot here, as the model would), Viridian's Mart (the parcel), and Oak (the Pokédex + the Poké Balls)."""
    import pytest
    from game.constants import GEN3_CHARSET, Addr
    from live.conftest import ROM
    if not ROM.exists():
        pytest.skip(f"ROM not found at {ROM}")
    import config
    import main
    for k, v in ("STARTER", "squirtle"), ("PLAYER_NAME", "kyle"), ("RIVAL_NAME", "gary"):          # the choices come from .env (STARTER / PLAYER_NAME / RIVAL_NAME), not from the call
        monkeypatch.setattr(config, k, v)
    link = tmp_path / "blank.gba"
    link.symlink_to(ROM)                                           # a ROM path with no sibling .sav: the cartridge is blank, the title shows no Continue
    rt = main.build_runtime(new_game=True, rom_path=str(link), ltm_path=str(tmp_path / "ltm.json"), journal_path=str(tmp_path / "j.jsonl"), verbose=False)
    assert rt is not None
    c, r, m = rt.client, rt.reader, rt.mgba
    assert m.read8(Addr.MAP_BANK) == 0 and not r.read_party()          # still at the title
    out = ""
    for _ in range(40):
        if r.detect_context().name == "IN_BATTLE":
            c._auto_fight()
            continue
        out = c._execute("quest", json.dumps({"name": "new_game"}))
        if r.read_flag(0x829):
            break
    assert r.read_flag(0x829) and "delivered" in out, out                                          # FLAG_SYS_POKEDEX_GET
    assert r.read_party()[0].species_name == "Squirtle" and 349 not in r.read_key_items()          # the parcel was handed over
    sb2 = m.read32(Addr.SAVEBLOCK2_PTR)
    assert "".join(GEN3_CHARSET.get(b, "?") for b in m.read_range(sb2, 8) if b != 0xFF) == "KYLE"
    assert c._story()["parcel"] == "done"


def test_watched_run_fixes_stale_move_reply_long_nickname_and_switch_outside_a_battle(live):
    """Three fixes from a watched run, on the real ROM: switch_pokemon on the field settles and says where you are (it used to repeat "only for battles"), use_move with a move the
    Pokémon doesn't have lists the real moves with PP, and a catch with a 15-character nickname is shortened instead of refused (no ball thrown, a wasted call)."""
    live.load("threemon")
    out = live.c._execute("switch_pokemon", json.dumps({"target": "Pikachu"}))
    assert "no battle to switch" in out and "reorder_party" in out, out
    assert live.wild_battle(), "no wild battle found"
    out = live.c._execute("use_move", json.dumps({"move": "Hyper Beam"}))
    assert "not a known move" in out and "(PP " in out and "Tackle" in out, out
    got = ""
    for _ in range(3):
        live.set_foe_hp(1)
        got = live.c._execute("catch", json.dumps({"nickname": "Wolfgang Amadeus"}))
        if "Gotcha" in got:
            break
    assert "Gotcha" in got and "shortened to 'Wolfgang'" in got, got
    assert any(p.nickname == "Wolfgang" for p in live.r.read_party()), [p.nickname for p in live.r.read_party()]


def test_pc_recovers_from_a_failed_open_and_a_failure_saves_a_real_screenshot(live, tmp_path, monkeypatch):
    """A PC open that reports failure while the storage screen is actually up (what a watched run's PC did, six times): the skill backs out through the real menus, tries again and the
    deposit goes through; and a failure result saves a real frame under the run directory."""
    from memory.run_log import RunLog
    live.load("threemon")
    c = live.c
    real, calls = c._open_pc_once, {"opened": 0}

    def flaky(mode=1):
        err = real(mode)
        if err is None:
            calls["opened"] += 1
            if calls["opened"] == 1:
                return "The PC didn't open the storage screen."        # the first open succeeds for real, but is reported as a failure
        return err
    monkeypatch.setattr(c, "_open_pc_once", flaky)
    out = _pc(live, "pc_deposit", pokemon="Pikachu")
    assert out.startswith("Deposited") and calls["opened"] == 2, (out, calls)
    assert live.r.detect_context() == GameContext.OVERWORLD and len(live.r.read_party()) == 2
    old_log = c.run_log
    c.run_log = RunLog(tmp_path / "runs")
    try:
        rel = c._failure_shot("pc", "The PC didn't open the storage screen.")
        shot = c.run_log.dir / rel
        assert rel.startswith("shots/") and shot.exists() and shot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    finally:
        c.run_log = old_log


def test_swap_with_a_full_party_deposits_first_then_withdraws(live):
    """A watched run's stuck PC: with six in the party the storage menu was never steered off WITHDRAW ('Can't take any more POKéMON.', forever). The swap must deposit one, then withdraw."""
    live.load("fullparty")
    before = [p.species_name for p in live.r.read_party()]
    assert len(before) == 6 and any(b["species_name"] == "Sandshrew" for b in live.r.read_boxes()), before
    out = _pc(live, "pc", action="swap", pokemon="1", box_pokemon="Sandshrew")
    after = [p.species_name for p in live.r.read_party()]
    assert out.startswith("Deposited") and "Withdrew" in out and live.r.detect_context() == GameContext.OVERWORLD, out
    assert len(after) == 6 and "Sandshrew" in after and "Zubat" not in after, (out, after)
    assert any(b["species_name"] == "Zubat" for b in live.r.read_boxes())


def test_a_move_disabled_during_the_previous_turn_is_caught_at_the_move_menu_not_after_a_long_stall(live):
    """A watched run: the foe's Disable landed after use_move's pre-flight read, so use_move re-committed the dead move through 60 text rounds (2.5 min of game time, then the watchdog).
    Simulate the missed pre-flight on the Disabled fixture: the move-menu re-check answers at once."""
    live.load("disabled")
    if live.r.detect_context() != GameContext.IN_BATTLE:
        import pytest
        pytest.skip("fixture is not mid-battle")
    real, calls = live.r.read_disabled_move, {"n": 0}

    def miss_once(battler=0):
        calls["n"] += 1
        return (0, 0) if calls["n"] == 1 else real(battler)
    live.r.read_disabled_move = miss_once
    try:
        out = live.c._use_move("Tackle")
    finally:
        live.r.read_disabled_move = real
    assert "DISABLED" in out and "Growl" in out and calls["n"] >= 2, (out, calls)


def test_a_ghost_battle_refuses_the_ball_and_the_observation_says_so(live):
    """Pokémon Tower's ghost Marowak (BATTLE_TYPE_GHOST, 1 << 15) dodges every ball: a watched run threw 18 at it. Set the flag on a real wild battle: catch() refuses without throwing, the bag is
    untouched, and the battle advice says not to catch."""
    from game.constants import Addr
    live.load("threemon")
    assert live.wild_battle(), "no wild battle found"
    balls = live.c._ball_count()
    live.m.write32(Addr.BATTLE_TYPE_FLAGS, live.m.read32(Addr.BATTLE_TYPE_FLAGS) | Addr.BATTLE_TYPE_GHOST)
    out = live.c._catch("Bonehead")
    assert "ghost Marowak" in out and "can't be caught" in out, out
    assert live.c._ball_count() == balls and live.r.detect_context() == GameContext.IN_BATTLE


def test_go_to_fuchsia_walks_the_land_route_over_route_12s_awake_snorlax(live):
    """Watched runs 163742 / 172153: the planner saw the Snorlax's square as a wall, planned a sea trip via Pallet and answered "Route 21 is open water — you need Surf" about 20 times.
    From Route 16 with the Snorlax awake, go_to('Fuchsia City') now walks Lavender → Route 12 gatehouse → over the Snorlax → Routes 13-15 (wild fights fled, trainers pre-beaten)."""
    live.load("fuchsia_by_land")
    live.defeat_all_trainers()
    assert live.r.read_flag(0x253), "fixture: the Route 12 Snorlax should be awake"
    out = ""
    for _ in range(25):
        if live.r.detect_context() == GameContext.IN_BATTLE:
            live.c._execute("flee_battle", "{}")
            continue
        out = live.c._execute("go_to", json.dumps({"destination": "Fuchsia City"}))
        if "Arrived" in out or "Can't get" in out:
            break
    assert tuple(live.r.read_current_map()) == (3, 7) and "Surf" not in out, out


def test_go_to_fuchsia_with_the_snorlax_asleep_names_the_snorlax_not_surf(live):
    live.load("fuchsia_by_land")
    live.set_flag(0x253, on=False)
    out = live.c._execute("go_to", json.dumps({"destination": "Fuchsia City"}))
    assert ("quest('snorlax')" in out or "quest('snorlax_16')" in out) and "Surf" not in out.split("(Before")[0], out      # from Route 16 the shortest plan is the Cycling Road: its Snorlax is named first


def test_quest_bike_gets_the_voucher_and_the_bicycle_from_where_a_run_stalls_on_fuchsia(live):
    """The Bicycle is the Cycling Road's gate. From Route 16 on foot (no Fly hop), quest('bike') travels to Vermilion's Fan Club for the voucher, on to Cerulean's Bike Shop for the Bicycle
    (key item 360), and go_to('Fuchsia City') still takes the Route 12 land road afterwards."""
    live.load("fuchsia_by_land")
    live.defeat_all_trainers()
    assert not live.r.read_flag(0x271) and not live.r.read_flag(0x241), "fixture: no voucher or Bicycle yet"
    for _ in range(40):
        if live.r.detect_context() == GameContext.IN_BATTLE:
            live.c._execute("flee_battle", "{}")
            continue
        live.c._execute("quest", json.dumps({"name": "bike"}))
        if live.r.read_flag(0x271):
            break
    assert live.r.read_flag(0x241) and live.r.read_flag(0x271) and 360 in live.r.read_key_items()
    out = ""
    for _ in range(30):
        if live.r.detect_context() == GameContext.IN_BATTLE:
            live.c._execute("flee_battle", "{}")
            continue
        out = live.c._execute("go_to", json.dumps({"destination": "Fuchsia City"}))
        if "Arrived" in out or "Can't" in out or "stuck" in out:
            break
    assert tuple(live.r.read_current_map()) == (3, 7), out


def test_quest_snorlax_16_walks_to_the_sleeper_and_hands_the_one_shot_fight_to_the_model(live):
    """#272: Route 16's Snorlax (31,13) — flute, face it from (32,13), YES; the fight is the model's (never the autopilot), and FLAG_HIDE_ROUTE_16_SNORLAX (0x080) is set at once."""
    live.load("fuchsia_by_land")
    live.defeat_all_trainers()
    assert not live.r.read_flag(0x080), "fixture: Route 16's Snorlax should still be asleep"
    out = live.c._execute("quest", json.dumps({"name": "snorlax_16"}))
    assert live.r.detect_context() == GameContext.IN_BATTLE and "Snorlax" in out, out
    assert live.r.read_flag(0x080) and tuple(live.r.read_player_pos()) == (32, 13)


def test_go_to_fuchsia_rides_the_cycling_road_from_celadon_in_one_leg(live):
    """#269: with the Bicycle and Route 16's Snorlax gone, Celadon -> Fuchsia is Route 16's gate house and the Cycling Road (the game puts you on the bike and will not let you off: walk_to used to try the
    dismount and left the Start menu open). One call used to end 'stuck at Route 16 (TRANSITIONING)' and then fall back to the long road through Lavender."""
    live.load("cycling_road")
    live.defeat_all_trainers()
    assert 360 in live.r.read_key_items() and live.r.read_flag(0x080)
    seen, out = set(), ""
    for _ in range(12):
        if live.r.detect_context() == GameContext.IN_BATTLE:
            live.c._execute("flee_battle", "{}")
            continue
        out = live.c._execute("go_to", json.dumps({"destination": "Fuchsia City"}))
        seen.add(tuple(live.r.read_current_map()))
        if "Arrived" in out or "Can't get" in out:
            break
    assert tuple(live.r.read_current_map()) == (3, 7), out
    assert (3, 33) not in seen and (3, 30) not in seen, seen               # not round by Routes 15 / 12


def test_shop_item_buys_an_evolution_stone_on_the_dept_store_4f(live):
    """The Celadon Dept. Store's 4F clerk (3,13) sells the elemental stones (¥2100): shop(item='Thunderstone') walks up the stairs, stands across the counter and buys."""
    _fly_to_celadon(live)
    live.set_money(5000)
    had = dict(live.r.read_items_pocket()).get(96, 0)
    out = ""
    for _ in range(10):
        out = live.c._execute("shop", json.dumps({"item": "Thunderstone"}))
        if out.startswith("Bought") or live.r.detect_context() != GameContext.OVERWORLD:
            break
    assert out.startswith("Bought 1× Thunderstone (¥2100)"), out
    assert dict(live.r.read_items_pocket()).get(96) == had + 1 and live.r.read_money() == 2900


def test_shop_restock_buys_the_best_tier_this_mart_sells_and_stocks_up(live):
    """Fuchsia's Mart sells Ultra Balls, Super Potions, Full Heals and Revives: with ¥26,000 and 5 badges the restock is Ultra Balls (not Great), Super Potions, a Full Heal and
    Revive stock and a larger par than the old 10 — and it spends most of the money instead of leaving it."""
    _fly_to_fuchsia(live)
    live.set_badges(0b11111)
    live.c.ltm.data["badges_earned"] = 5
    live.set_money(26000)
    bag0 = dict(live.r.read_bag())
    out = ""
    for _ in range(8):
        out = live.c._execute("shop", "{}")
        if out.startswith("Bought") or live.r.detect_context() != GameContext.OVERWORLD:
            break
    assert out.startswith("Bought"), out
    bag = dict(live.r.read_bag())
    assert bag.get(2, 0) > bag0.get(2, 0) and bag.get(22, 0) > bag0.get(22, 0) and bag.get(23, 0) > bag0.get(23, 0) and bag.get(24, 0) > bag0.get(24, 0), (bag0, bag)
    assert live.r.read_money() < 12000, out


def _count_shuffles(live, fn):
    """Run fn() and return (direction presses, A-B-A reversals of the player's tile): the D / U jitter on stairs and exit mats shows as reversals."""
    calls = []
    m = live.m
    orig_hold, orig_tap = m.hold, m.tap

    def wrap(orig):
        def f(btn, *a, **k):
            out = orig(btn, *a, **k)
            if btn in ("Up", "Down", "Left", "Right"):
                calls.append((tuple(live.r.read_current_map()), tuple(live.r.read_player_pos())))
            return out
        return f
    m.hold, m.tap = wrap(orig_hold), wrap(orig_tap)
    try:
        fn()
    finally:
        m.hold, m.tap = orig_hold, orig_tap
    reversals = sum(1 for i in range(2, len(calls)) if calls[i] == calls[i - 2] and calls[i] != calls[i - 1])
    return len(calls), reversals


def test_the_dept_store_stairs_and_exit_mats_do_not_make_the_walker_shuffle(live):
    """Watched: entering / leaving buildings and changing floors 'jittered' back and forth. Two causes, both in the Celadon Dept. Store: the directional stairs fire on a LEFT / RIGHT press
    while standing on them (walk_to nudged Down first, stepped off, stepped back on — about twenty D / U cycles per floor), and 1F's warp list names wall tiles (1,15) / (3,15) beside the real
    exit mat (2,14), so go_to pressed Down into a wall ~70 times. Up to 4F and back out is now a straight line."""
    live.load("celadon_gym_door")
    live.defeat_all_trainers()
    live.set_money(5000)
    out = {}
    presses, rev = _count_shuffles(live, lambda: out.update(buy=live.c._execute("shop", json.dumps({"item": "Thunderstone"}))))
    assert out["buy"].startswith("Bought 1× Thunderstone"), out
    assert rev <= 12, (presses, rev)
    presses2, rev2 = _count_shuffles(live, lambda: out.update(leave=live.c._execute("go_to", json.dumps({"destination": "Celadon City", "force": True}))))
    assert out["leave"].startswith("Arrived at Celadon City"), out
    assert presses2 < 80 and rev2 <= 4, (presses2, rev2)             # was 259 presses / 70 reversals

"""Overworld skills: heal at a Pokémon Center, shop at a Mart, grind wild
battles, and pick up item balls. See agent.lm_studio_client.AgentClient
(which inherits OverworldMixin)."""

from knowledge.navigation import MAP_NAMES


class OverworldMixin:


    def _bag_and_keys(self) -> tuple[dict, int]:
        return self.reader.read_bag(), self.reader.read_key_item_count()

    def _pick_up_items(self) -> str:
        """Collect every item ball currently visible on this map. For each, walks up
        next to it, faces it, presses A, and advances the 'found ITEM!' text — the
        deterministic version of what the model would otherwise fumble. Confirms each
        pickup by the bag/key-item total rising (or the ball vanishing). Item balls
        are surfaced in the observation so the model knows to call this."""
        from game.state import GameContext
        from knowledge.shopping import ITEM_NAMES
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "Can only pick up items while walking around (not in a menu/battle)."
        got: list[str] = []
        for _ in range(8):                       # bounded: at most 8 balls per call
            balls = self.reader.read_item_ball_tiles()
            if not balls:
                break
            px, py = self.reader.read_player_pos()
            bx, by = min(balls, key=lambda t: abs(t[0] - px) + abs(t[1] - py))
            if not self._approach_adjacent(bx, by):
                return self._pickup_result(got, f"couldn't reach the item at ({bx},{by})")
            before_bag, before_keys = self._bag_and_keys()
            picked = False
            for _ in range(6):
                px, py = self.reader.read_player_pos()
                face = self._facing_dir(px, py, bx, by)
                if face:
                    self.mgba.tap(face)          # turn to face the ball (bumps it, no move)
                self.mgba.tap("A")               # pick up
                self.mgba.tick(15)
                self._advance_to_control()       # advance "found ITEM!" text to control
                after_bag, after_keys = self._bag_and_keys()
                if after_keys > before_keys or sum(after_bag.values()) > sum(before_bag.values()) \
                        or (bx, by) not in self.reader.read_item_ball_tiles():
                    picked = True
                    break
            if not picked:
                return self._pickup_result(got, f"the item at ({bx},{by}) didn't respond")
            after_bag, after_keys = self._bag_and_keys()
            new = [ITEM_NAMES.get(iid, f"item#{iid}") for iid, q in after_bag.items()
                   if q > before_bag.get(iid, 0)]
            if after_keys > before_keys:
                new.append("a key item")
            got.append(", ".join(new) if new else "an item")
        return self._pickup_result(got)

    @staticmethod
    def _pickup_result(got: list[str], problem: str = "") -> str:
        if not got and problem:
            return f"No items picked up — {problem}."
        if not got:
            return "No item balls visible here."
        head = f"Picked up {len(got)} item(s): {'; '.join(got)}."
        return head + (f" Stopped: {problem}." if problem else "")

    # Nurse Joy stands at (7,2) in the shared Pokémon Center interior, behind the
    # counter at (7,3). The player stands one tile below the counter, at (7,4), and
    # presses A facing up — the counter metatile forwards the interaction to the
    # nurse behind it. The heal is a pure dialogue: greeting → YES/NO (defaults to
    # YES) → heal → "restored". So we advance with A and confirm success by the
    # party returning to full HP.
    _NURSE_TILE = (7, 4)

    def _party_full_hp(self) -> bool:
        party = self.reader.read_party()
        return bool(party) and all(m.current_hp == m.max_hp for m in party)

    def _party_needs_heal(self) -> bool:
        """Hurt, OR a mon whose every attacking move is at 0 PP (a Pokémon Center restores PP too —
        full HP alone must not make heal() refuse, or an out-of-PP team can never recover)."""
        from knowledge.party import attack_pp
        party = self.reader.read_party()
        if not party:
            return False
        if any(m.current_hp != m.max_hp for m in party):
            return True
        # Attacks nearly gone also counts (readiness' must-heal): a Center restores PP, and go_to's
        # pre-flight refuses to travel in that state, so heal() must agree it is worth doing.
        from knowledge.readiness import blocking
        if blocking(self._readiness()):
            return True
        return any(m.move_names and m.max_hp and any(m.move_names) and attack_pp(m) == 0
                   and self._has_attack(m) for m in party)

    @staticmethod
    def _has_attack(mon) -> bool:
        from knowledge.leafgreen_data import MOVE_POWER
        return any(n and MOVE_POWER.get(n, 0) > 0 for n in (mon.move_names or []))

    def _heal(self, force: bool = False) -> str:
        """Heal the whole party at a Pokémon Center. Travels to the nearest one if
        not already inside, walks to Nurse Joy, and advances the heal dialogue
        until the party is at full HP. Resumable: if a wild battle/dialog interrupts
        the trip, it stops and reports so the caller can resume."""
        from game.state import GameContext
        from knowledge.map_graph import MAP_KIND
        if not force and not self._party_needs_heal():
            return "Party is already at full HP and PP — no need to heal."
        # Get inside a Pokémon Center first (resumable travel).
        if MAP_KIND.get(self.reader.read_current_map()) != "pokecenter":
            res = self._go_to("Pokemon Center", mode="flee")
            if MAP_KIND.get(self.reader.read_current_map()) != "pokecenter":
                return f"On the way to a Pokémon Center to heal: {res}"
        # Walk to the nurse's counter and face her.
        nx, ny = self._NURSE_TILE
        self._walk_to(nx, ny)
        if self.reader.read_player_pos() != (nx, ny):
            return (f"Couldn't reach Nurse Joy's counter at {self._NURSE_TILE} "
                    f"(at {self.reader.read_player_pos()}). Try walk_to it, then talk.")
        self.mgba.tap("Up")            # face the nurse across the counter
        # Advance greeting → YES/NO (YES is default) → heal → closing. A-mash and
        # watch for full HP; nudge Up before confirming so the cursor sits on YES.
        for i in range(40):
            # force=True (first visit to a town) still talks to Nurse Joy — that is what sets the respawn
            # point — so keep pressing A for the greeting → YES → heal → closing text before returning.
            if not self._party_needs_heal() and (not force or i >= 16):
                # Advance the nurse's closing dialogue AND wait out the heal fade until
                # we're back in real OVERWORLD control. A fixed few A-taps left the
                # player standing on the counter tile still flagged IN_MENU, where
                # walk_to can't move — the Poké Center exit stall (the agent re-issued
                # walk_to(exit) for ~50s until the fade happened to clear).
                self._advance_to_control(tries=24)
                return "Healed the party to full HP at the Pokémon Center."
            self.mgba.tap("Up")        # keep the YES/NO cursor on YES if it's up
            self.mgba.tap("A")
            self.mgba.tick(12)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return "A battle started while healing — handle it, then heal again."
        return ("Talked to Nurse Joy but couldn't confirm a full heal — "
                "try heal again, or check you're facing her at the counter.")

    # ── Poké Mart shopping ────────────────────────────────────────────────────
    # Standard marts share LAYOUT_MART: the clerk is behind a counter at (2,3); the
    # player stands in front at (2,5) (walk_to (2,4) stops there — the counter is
    # impassable) and presses A facing up to talk across it. The buy menu is driven
    # through sShopData (Addr.SHOP_DATA): the highlighted item is
    # itemList[scrollOffset + selectedRow], so we navigate the list by reading those
    # and pressing Down/Up, set quantity by watching itemPrice, and confirm each
    # purchase by the bag count rising. Menu inputs get dropped during animations, so
    # every step re-reads state and retries rather than pressing blindly.
    _MART_CLERK_APPROACH = (2, 4)

    def _buy_list_open(self) -> bool:
        from game.constants import Addr
        lp = self.mgba.read32(Addr.SHOP_DATA + Addr.SHOP_ITEMLIST)
        return (0x08000000 <= lp < 0x0A000000
                and 0 < self.mgba.read16(Addr.SHOP_DATA + Addr.SHOP_ITEMCOUNT) <= 30)

    def _buy_list_interactive(self) -> bool:
        """Probe whether the buy ITEM LIST is live and taking D-pad input: on the list
        a Down nudges selectedRow (we immediately undo it); on a text box / mid-fade /
        transition it's inert. ONLY safe when we're not on the Buy/Sell choice menu
        (i.e. after Buy is selected / after a purchase), where Down would move a
        different cursor. Used to wait out the post-purchase 'Here you go!' text."""
        from game.constants import Addr
        SD = Addr.SHOP_DATA
        r0 = self.mgba.read16(SD + Addr.SHOP_SELROW)
        self.mgba.tap("Down")
        self.mgba.tick(8)
        if self.mgba.read16(SD + Addr.SHOP_SELROW) != r0:
            self.mgba.tap("Up")            # undo the probe, back to where we were
            self.mgba.tick(8)
            return True
        return False

    def _shop_item_list(self) -> list[int]:
        from game.constants import Addr
        lp = self.mgba.read32(Addr.SHOP_DATA + Addr.SHOP_ITEMLIST)
        n = self.mgba.read16(Addr.SHOP_DATA + Addr.SHOP_ITEMCOUNT)
        if not (0x08000000 <= lp < 0x0A000000):
            return []
        return [self.mgba.read16(lp + 2 * i) for i in range(min(n, 30))]

    def _open_buy_menu(self) -> bool:
        """Talk to the clerk, then select Buy so the interactive item list is open.
        sShopData.itemList is set as soon as the Buy/Sell menu appears (before Buy is
        chosen), so 'itemList valid' only means the shop menu is up — we then select
        Buy (top option, default cursor) and let the item list fade in before the
        caller navigates (Task_BuyMenu ignores D-pad while gPaletteFade is active)."""
        self._walk_to(*self._MART_CLERK_APPROACH)   # lands at the counter-front tile
        # 1. Talk to the clerk and advance the greeting until the shop menu appears.
        shop_up = False
        for _ in range(3):
            self.mgba.tap("Up")                       # face the clerk
            for _ in range(8):
                if self._buy_list_open():
                    shop_up = True
                    break
                self.mgba.tap("A")                    # advance greeting
                self.mgba.tick(20)
            if shop_up:
                break
        if not shop_up:
            return False
        # 2. Select Buy (default top option) → enter the item list, then settle so the
        #    fade finishes and the list starts taking D-pad input.
        self.mgba.tap("A")
        if hasattr(self.mgba, "wait_until_idle"):
            self.mgba.wait_until_idle()
        self.mgba.tick(40)
        return self._buy_list_open()

    def _buy_one_item(self, item_id: int, qty: int, unit_price: int) -> int:
        """Navigate to item_id in the open list, buy `qty`, return how many were
        actually added to the bag (0 if not sold here / couldn't afford any)."""
        from game.constants import Addr
        SD = Addr.SHOP_DATA
        items = self._shop_item_list()
        if item_id not in items:
            return 0
        target = items.index(item_id)
        # Move the highlight to the target row (verify each press; retry drops).
        for _ in range(40):
            cur = self.mgba.read16(SD + Addr.SHOP_SCROLL) + self.mgba.read16(SD + Addr.SHOP_SELROW)
            if cur == target:
                break
            self.mgba.tap("Down" if cur < target else "Up")
            self.mgba.tick(8)
        else:
            return 0
        before = self.reader.read_bag().get(item_id, 0)
        idle = getattr(self.mgba, "wait_until_idle", None)
        # Select the item → the "How many?" quantity box. Wait for its init to run
        # (it computes maxQuantity = money/price; 0 means it hasn't run yet).
        if idle:
            idle()
        self.mgba.tap("A")
        maxq = 0
        for _ in range(10):
            if idle:
                idle()
            self.mgba.tick(6)
            maxq = self.mgba.read16(SD + Addr.SHOP_MAXQTY)
            if maxq > 0:
                break
        if maxq <= 0:
            return 0                     # quantity box never opened
        want = max(1, min(qty, maxq))
        # Dial the quantity up from 1 to `want` (Up = +1), confirming via
        # itemPrice = unit×count. Re-read after each press; retry drops.
        for _ in range(want + 15):
            cur_n = self.mgba.read32(SD + Addr.SHOP_ITEMPRICE) // unit_price if unit_price else 1
            if cur_n >= want:
                break
            self.mgba.tap("Up")
            self.mgba.tick(6)
        # Confirm + purchase. A opens the "…you wanted N?" YES/NO box (YES default),
        # another A selects YES → the purchase runs and the bag grows. Press A until
        # the bag actually increases — self-verifying, so a dropped input just means
        # another press rather than a mis-aligned sequence. Then a SINGLE A dismisses
        # the "Here you go!" line back to the list (never press A on the list itself —
        # there it re-selects the highlighted item).
        got = 0
        for _ in range(10):
            self.mgba.tap("A")
            if idle:
                idle()
            self.mgba.tick(10)
            got = self.reader.read_bag().get(item_id, 0) - before
            if got > 0:
                break
        if got > 0:
            # Advance the "Here you go! Thank you!" text (which may still be printing)
            # until the item list is interactive again — probe first so we never press
            # A while ON the list (that would re-select the item).
            for _ in range(12):
                if self._buy_list_interactive():
                    break
                self.mgba.tap("A")
                if idle:
                    idle()
                self.mgba.tick(10)
        return max(0, got)

    def _close_buy_menu(self) -> None:
        from game.state import GameContext
        for _ in range(12):
            if self.reader.detect_context() == GameContext.OVERWORLD:
                return
            self.mgba.tap("B")
            self.mgba.tick(12)

    def _shop(self) -> str:
        """Restock at the Poké Mart per the badge-gated purchase policy: travel to a
        Mart if needed, open the buy menu, buy the affordable par-level list of items
        this mart sells, and leave. The model just calls shop()."""
        from knowledge.map_graph import MAP_KIND
        from knowledge.shopping import compute_shopping_list, ITEM_NAMES, ITEM_PRICES
        if MAP_KIND.get(self.reader.read_current_map()) != "mart":
            res = self._go_to("Mart")
            if MAP_KIND.get(self.reader.read_current_map()) != "mart":
                return f"On the way to a Mart to restock: {res}"
        money = self.reader.read_money()
        plan = compute_shopping_list(self.reader.read_bag(),
                                     self.ltm.data["badges_earned"], money)
        if not plan["lines"]:
            return f"Bag is already stocked (¥{money}) — nothing to buy."
        if not self._open_buy_menu():
            return ("Couldn't open the Mart buy menu — walk up to the clerk at the "
                    "counter and call shop() again.")
        sold = set(self._shop_item_list())
        bought, spent, skipped = [], 0, []
        for line in plan["lines"]:
            iid, qty = line["item_id"], line["qty"]
            if iid not in sold:
                skipped.append(ITEM_NAMES.get(iid, str(iid)))
                continue
            got = self._buy_one_item(iid, qty, ITEM_PRICES.get(iid, line["unit_price"]))
            if got > 0:
                bought.append(f"{got}× {ITEM_NAMES.get(iid, iid)}")
                spent += got * line["unit_price"]
        self._close_buy_menu()
        if not bought:
            return ("At the Mart but bought nothing (this mart doesn't sell the "
                    "recommended items, or you couldn't afford them).")
        msg = f"Bought {', '.join(bought)} (¥{spent}). Money left: ¥{self.reader.read_money()}."
        if skipped:
            msg += f" (Not sold here: {', '.join(dict.fromkeys(skipped))}.)"
        return msg

    _OPPOSITE = {"Up": "Down", "Down": "Up", "Left": "Right", "Right": "Left"}

    def _wander_step(self) -> bool:
        """Take one overworld step to seek a wild encounter, PACING back and forth so
        we stay in the local (grassy) patch instead of drifting out of it. Keeps a
        heading, reverses when blocked, and rotates axis if fully boxed in. Returns
        True if a battle started."""
        from game.state import GameContext
        heading = getattr(self, "_wander_dir", "Up")
        # Try the current heading, then its reverse, then the other axis.
        order = [heading, self._OPPOSITE[heading]]
        for d in ("Up", "Down", "Left", "Right"):
            if d not in order:
                order.append(d)
        for mv in order:
            before = self.reader.read_player_pos()
            self.mgba.tap(mv)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                self._wander_dir = mv
                return True
            if self.reader.read_player_pos() != before:
                self._wander_dir = mv   # keep pacing this way until blocked
                return False
        return False

    def _nearest_grass(self) -> tuple[int, int] | None:
        """Closest tall-grass tile to the player on the current map (Manhattan), or
        None if the map has no grass. Uses the metatile-behavior reader so grind can
        route the player onto a real patch instead of guessing from encounters."""
        self.tilemap.refresh()
        tiles = self.tilemap.grass_tiles()
        if not tiles:
            return None
        px, py = self.reader.read_player_pos()
        return min(tiles, key=lambda t: abs(t[0] - px) + abs(t[1] - py))

    def _relocate_to_grass(self, exclude_current: bool = False, level: int | None = None) -> bool:
        """Deterministically travel to the nearest grass route so grind has grass to
        work with, instead of handing a 'go find grass' message back to the model
        (which it tends to ignore). Returns True if we end up somewhere with grass."""
        from knowledge.grind_routes import best_grass
        if level is None:
            level = (getattr(self, "_grind_run", None) or {}).get("lvl") or 0
        bank, mid = self.reader.read_current_map()
        # Routes whose way in already beat us twice are off the list for the whole session.
        losses = self.__dict__.get("_trainer_losses", {})
        avoid: set = {m for m, n in losses.items() if n >= 2}
        for _attempt in range(3):
            found = best_grass((bank, mid), level, exclude_current=exclude_current, avoid=avoid)
            if found is None:
                return False
            goal_map = found[0]
            if goal_map == (bank, mid):
                return self._nearest_grass() is not None
            name = MAP_NAMES.get(goal_map)
            if not name:
                avoid.add(goal_map)
                continue
            # go_to is resumable and stops early (battle/dialog/guard shuffles). Keep
            # calling it until we land there; if the route is story-gated (e.g. Route 3
            # before Brock) it never arrives, so skip that route and try the next-nearest.
            lost = False
            for _ in range(6):
                out = self._go_to(name, mode="flee")           # relocation is plain travel: flee wild battles
                if self.reader.read_current_map() == goal_map:
                    break
                if out.startswith("Blocked") or "gated" in out:
                    break
                if "Lost a trainer" in out or "Lost to a trainer" in out:
                    # A mandatory trainer (a rival) on the way beat us. Don't loop walking back into
                    # it: heal once, then try a different grass route.
                    lost = True
                    self._heal()
                    break
            if lost:
                avoid.add(goal_map)
                bank, mid = self.reader.read_current_map()
                continue
            if self.reader.read_current_map() == goal_map and self._nearest_grass() is not None:
                return True
            avoid.add(goal_map)
        return False

    def _grass_step(self, st: dict, again: str) -> str | None:
        """One overworld step of a grass-grinding loop: pace on a patch to trigger encounters, or
        route back onto grass / relocate to a grassy route. Returns an abort message when grass
        can't be reached, else None. `st` carries {"stuck", "reloc"} between calls."""
        px, py = self.reader.read_player_pos()
        if self.tilemap.is_tall_grass(px, py):
            self._wander_step()           # on grass — pace back and forth to trigger encounters
            st["stuck"] = 0
            return None
        # Off grass — route back onto the patch (walk_to is ledge-aware).
        target = self._nearest_grass()
        if target is not None:
            self._walk_to(*target)
        st["stuck"] += 1
        # Can't reach any grass on this map — try a deterministic relocation first.
        if st["stuck"] >= 25:
            if st["reloc"] < 2 and self._relocate_to_grass(exclude_current=True):
                st["reloc"] += 1
                st["stuck"] = 0
                return None
            return ("Couldn't reach tall grass to grind. go_to a grassy route yourself, "
                    f"then call {again} again.")
        return None

    # ── Party balancing ─────────────────────────────────────────────────────────
    def _lagging_mons(self, party=None) -> list:
        """Party members more than BALANCE_GAP (7) levels below the top level (knowledge.party), lowest first
        — fainted ones included (they are lagging, just waiting for a heal)."""
        from knowledge.party import lagging_mons
        run = getattr(self, "_grind_run", None)         # inside a grind session the floor is FIXED (see _grind_inner)
        return lagging_mons(party if party is not None else self.reader.read_party(),
                            run["floor"] if run else None)

    def _train_fight(self, trainee_sig: tuple) -> None:
        """Fight one WILD battle so the lagging Pokémon (trainee_sig = species_id, max_hp at battle
        start) earns the experience. Gen III splits a kill's XP between every Pokémon that was on the field
        while the foe was out, so the best play is the classic tag-switch:

          1. the trainee STARTS the battle in front (grind() leads it before the grass step); if it is on the
             bench (travel fights) it is brought in first, but only when that free foe hit is survivable;
          2. an EASY foe (about the trainee's level, trainee healthy) is fought by the trainee alone — it
             keeps all the XP;
          3. otherwise it is tagged out on TURN ONE, before it can be hurt, for a teammate who finishes the
             foe (the lowest-level capable one, so the finishing XP rotates through the team) — and it is
             NEVER swapped back in: that was the bug that fed the trainee to the foe for no XP;
          4. a trainee that gets hurt mid-fight is tagged out the same way."""
        from game.state import GameContext
        from knowledge.party import ace_index, pick_finisher

        def find(party, sig):
            return next((i for i, q in enumerate(party) if (q.species_id, q.max_hp) == sig), None)

        potions_used: list = []
        plan = {"tagged": False, "tried_in": False}
        try:
            self._battle_settle(40)               # gBattleMons[0] is stale until the first action menu is up
        except Exception:
            pass
        for _ in range(40):
            if self._send_next_mon():
                continue
            if self.reader.detect_context() != GameContext.IN_BATTLE:
                break
            if self._maybe_drive_learn():
                continue
            party = self.reader.read_party()
            t = find(party, trainee_sig)
            foe = self.reader.read_enemy_lead()
            active = self.reader.read_active_battle_species()
            tm = party[t] if t is not None else None
            if tm is not None and tm.current_hp > 0 and tm.max_hp and not plan["tagged"]:
                foe_lv = foe.level if foe and foe.max_hp and foe.level else tm.level
                frac = tm.current_hp / tm.max_hp
                if active != tm.species_id:                       # the trainee is on the bench
                    if not plan["tried_in"]:
                        plan["tried_in"] = True
                        if frac >= 0.7 and foe_lv <= tm.level + 10:
                            self._switch_pokemon(str(t + 1))      # costs a foe hit: only when survivable
                            continue
                        plan["tagged"] = True                     # too risky — let the others take this one
                else:                                             # the trainee is out: has it participated?
                    plan["tried_in"] = True
                    if foe_lv > tm.level + 2 or frac < 0.5:
                        plan["tagged"] = True                     # tag out NOW, for good
                        run = getattr(self, "_grind_run", None) or {}
                        ace = ace_index(party) if run.get("balance") else None
                        fin = pick_finisher(party, t, foe_lv, bench=() if ace is None else (ace,))
                        if fin is not None:
                            if fin == ace:
                                run["ace_fought"] = run.get("ace_fought", 0) + 1
                            self._switch_pokemon(str(fin + 1))
                            continue
            if self._maybe_heal_mid_fight(potions_used):
                continue
            _ids, names, pp, _d, _t = self._active_moves_view()
            atk, dfn = self._battle_types()
            mv = self._best_damaging_move(names, pp, atk, dfn, self._battle_ctx())
            if mv:
                self._use_move(mv)
            else:
                self._no_attack_turn()
        self._settle_evolution()

    _GRIND_HP_FLOOR = 0.35
    _AUTO_HEALS = 8          # Pokémon Center round-trips one grind() call may make by itself

    def _train_party(self) -> str:
        """Legacy alias: grind() with no target level (balance the team)."""
        return self._grind(0)

    def _restock(self, why: str) -> str | None:
        """Heal at a Pokémon Center (restores HP *and* PP) and walk back to grass, so a long grind
        needs no LLM round-trips. The trip can be interrupted by wild/trainer battles (go_to stops on
        a new species): flee or finish them, then resume. Returns None when ready to continue, else
        an abort message."""
        from game.state import GameContext
        out = ""
        for _ in range(8):
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                from game.constants import Addr
                if not (self.mgba.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER):
                    self._flee_battle()
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    self._auto_fight()
                continue
            out = self._heal()
            if not self._party_needs_heal():
                break
        else:
            return f"Needed a heal ({why}) but couldn't finish it: {out} Call heal(), then grind() again."
        if self.reader.detect_context() != GameContext.OVERWORLD:
            self._advance_to_control(tries=24)
        if self._nearest_grass() is None and not self._relocate_to_grass():
            return "Healed, but no tall grass is reachable from here — go_to a grassy route, then grind() again."
        return None

    def _grind(self, target_level: int = 0, catch: bool = True, auto_battles: int = 0) -> str:
        """See _grind_inner. A session is resumable across calls (self._grind_run); the strongest Pokémon is put back
        in front when the session ENDS (done / stopped / interrupted), not between encounters handed to the model."""
        try:
            out = self._grind_inner(target_level, catch, auto_battles)
        except BaseException:
            self._grind_finish()
            raise
        if self._grind_run is None:
            self._grind_finish()
        return out

    def _grind_abandon(self) -> None:
        """The model left a grind session unfinished (went to travel/heal/shop…): drop it and put the best
        Pokémon back in front (overworld only — never auto-fights a battle the model is in)."""
        self._grind_run = None
        try:
            from game.state import GameContext
            if getattr(self, "_training_swapped", False) and self.reader.detect_context() == GameContext.OVERWORLD:
                self._grind_finish()
        except Exception:
            pass

    def _grind_finish(self) -> None:
        if not getattr(self, "_training_swapped", False):
            return
        try:
            from game.state import GameContext
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return           # the model's battle (or one a time limit cut off): never auto-play it here —
                                 # the flag stays set, so the next grind/abandon puts the ace back in front
            self._restore_ace_lead()
        except Exception:
            pass
        self._training_swapped = False

    def _lead_trainee(self, trainee) -> bool:
        """Put `trainee` (a PokemonStatus from read_party) in slot 1. Experience is split between every Pokémon
        that took part in a battle, so a strong lead that is merely switched out of a fight still takes half of
        it (and a lead that just stays in takes ALL of it) — the trainee has to START the battle in front.
        Returns True if the order is right afterwards."""
        party = self.reader.read_party()
        idx = next((i for i, p in enumerate(party)
                    if (p.species_id, p.max_hp) == (trainee.species_id, trainee.max_hp)), None)
        if idx is None:
            return False
        if idx == 0:
            return True
        out = self._set_lead(str(idx + 1))
        if out.startswith("Swapped"):
            self._training_swapped = True
            return True
        return False

    def _restore_ace_lead(self) -> None:
        """After training: the highest-level living Pokémon goes back to slot 1 (retried — menus after an abort
        can be mid-fade, and a dropped input must not leave a Level-7 trainee leading the party)."""
        from game.state import GameContext
        for _ in range(4):
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return                                       # a battle the model is in: never auto-play it here
            if self.reader.detect_context() != GameContext.OVERWORLD:
                self._advance_to_control(tries=24)           # post-battle text / fades after an abort
            for _ in range(3):
                if self.reader.detect_context() == GameContext.OVERWORLD:
                    break
                self._close_menus()
                self.mgba.tick(30)
            if self.reader.detect_context() != GameContext.OVERWORLD:
                continue
            party = self.reader.read_party()
            alive = [(p.level, -i) for i, p in enumerate(party) if p.current_hp > 0]
            if not alive:
                return
            best = -max(alive)[1]
            if best == 0:
                return
            self._set_lead(str(best + 1))

    # ── grind(): resumable sessions that hand encounters to the model ─────────────────────────────
    _GRIND_MAX_BATTLES = 150          # encounters (handed over or automatic) one session may take before it reports
    _GRIND_AUTO_MARGIN = 2            # an auto_battles fight needs a foe at most (active level + this)
    _grind_run = None                 # state of the session in progress (None = no session)

    def _grind_level(self, party, lag) -> int:
        """The level of the Pokémon being trained: the lowest lagging member, else the best (target-level mode)."""
        if lag:
            return min(p.level for _, p in lag)
        return max((p.level for p in party), default=0)

    def _grind_floor_now(self, party, target_level: int) -> int:
        from knowledge.party import grind_floor
        from knowledge.readiness import next_gym_target
        if target_level > 0:
            return grind_floor(target_level, balance=False)
        tgt = next_gym_target(self.ltm.data.get("gyms_beaten", []))
        return grind_floor(max(p.level for p in party), tgt[1] if tgt else None)

    def _grind_summary(self, run, party) -> str:
        gains = [f"{p.species_name} L{run['start'][p.species_id]}→L{p.level}" for p in party
                 if p.species_id in run["start"] and p.level > run["start"][p.species_id]]
        lv = ", ".join(f"{p.species_name} L{p.level}" for p in party if p.species_name)
        extra = f", {run['heals']} automatic heal(s)" if run["heals"] else ""
        if run["ace_fought"]:
            extra += f", the ace had to finish {run['ace_fought']} fight(s)"
        return f"{run['battles']} battles{extra} ({'; '.join(gains) or 'no level-ups yet'}). Team: {lv}."

    def _grind_yield(self, run, again: str, trainer: bool, party) -> str:
        """End the grind call on an encounter so the MODEL plays it (moves, items, catch, switches)."""
        from knowledge.party import ace_index
        try:
            where = MAP_NAMES.get(self.reader.read_current_map(), "here")
        except Exception:
            where = "here"
        what, verdict = "Pokémon", ""
        try:
            foe = self.reader.read_enemy_lead()
            if foe and foe.species_id and not (foe.species_name or "").startswith("#"):
                what = f"{foe.species_name} L{foe.level} (HP {foe.current_hp}/{foe.max_hp})"
                balls = self._ball_count()
                if run["catch"] and not trainer and balls > 0 and foe.species_id not in {p.species_id for p in party}:
                    from knowledge.catch_policy import evaluate
                    v = evaluate(party, foe.species_id, foe.level or 0,
                                 dex_owned=getattr(self.reader, "read_dex_owned", lambda _s: None)(foe.species_id))
                    verdict = (f" Worth a ball: {v.reason}." if v.catch else f" Not worth a ball: {v.reason}.") \
                        + f" ({balls} Poké Balls.)"
        except Exception:
            pass
        lead = party[0] if party else None
        lead_name = (lead.nickname or lead.species_name) if lead else "your lead"
        ace = ace_index(party)
        ace_name = (party[ace].nickname or party[ace].species_name) if ace is not None else "the ace"
        if run["balance"]:
            who = (f"Training the team up to L{run['floor']}: fight with {lead_name} L{lead.level if lead else '?'} — it "
                   f"earns the XP. Keep {ace_name} OUT of it (a switch to the ace feeds the ace, which is what this grind "
                   f"is trying not to do): use_move, use_item('Potion') to keep {lead_name} up, switch_pokemon only to "
                   f"another non-ace teammate to save it.")
        else:
            who = (f"Raising your best Pokémon to L{run['target']}"
                   + (f"; teammates under L{run['floor']} lead first" if lead and lead.level < run["floor"] else "")
                   + ". Fight with use_move / use_item.")
        head = "A TRAINER battle" if trainer else f"A wild {what}"
        return (f"{head} started at {where} while grinding.{verdict} {who} Battle {run['battles']}; "
                f"when it is over call {again} to continue.")

    def _grind_inner(self, target_level: int = 0, catch: bool = True, auto_battles: int = 0) -> str:
        """Level up by fighting wild Pokémon in tall grass. grind() walks/paces on grass (healing at a Pokémon Center
        itself when HP or attack PP runs low) until an encounter, then ENDS THE CALL so the model fights it like any
        other battle (use_move / items / catch / flee); the model then calls grind() again — the session (floor,
        starting levels, battle count) persists between calls. `auto_battles=N` lets the next N *boring* wild fights
        (foe at most 2 levels above the active Pokémon, nothing worth a ball) run on autopilot to save LLM turns.

        target_level > 0  → raise the BEST Pokémon to that level; teammates more than 7 levels under it
                            take turns leading each fight (tag-switch) so the team doesn't fall further behind.
        target_level == 0 → BALANCE the team up to a floor FIXED when the session starts (top − 7, capped at the next
                            gym's recommended level) — the ace's gains no longer move the goal. The ace is benched:
                            never a finisher unless nobody else is fit. Stops with a diagnosis if after 20+ battles
                            the fights are feeding the ace instead of the lagging members.

        Routes are chosen by wild level (knowledge.grind_routes): a patch tuned for the ace is no place for a L10."""
        from game.constants import Addr
        from game.state import GameContext
        from knowledge.grind_routes import is_misfit
        from knowledge.party import ace_runaway, healthy_enough, lagging_mons, party_needs_restock
        party = self.reader.read_party()
        if not party:
            return "No Pokémon to grind with."
        balance = int(target_level or 0) <= 0
        target_level = 0 if balance else max(1, min(int(target_level), 100))
        key = (balance, target_level)
        run = self._grind_run if (self._grind_run and self._grind_run["key"] == key) else None
        if run is None:
            floor = self._grind_floor_now(party, target_level)
            if balance:
                if len(party) < 2:
                    return "You only have one Pokémon — nothing to balance. Catch a team first, or grind(<level>)."
                if not lagging_mons(party, floor):
                    lv = ", ".join(f"{p.species_name} L{p.level}" for p in party if p.species_name)
                    return f"Party is balanced (nobody under L{floor}, the floor for this stage): {lv}."
            elif max(p.level for p in party) >= target_level:
                return (f"Your best Pokémon is already L{max(p.level for p in party)} (target L{target_level}) "
                        "— no need to grind.")
            run = self._grind_run = {
                "key": key, "balance": balance, "target": target_level, "floor": floor, "catch": bool(catch),
                "start": {p.species_id: p.level for p in party}, "battles": 0, "heals": 0, "ace_fought": 0,
                "lvl": 0, "fit_moves": 0, "stuck": 0, "reloc": 0}
        run["catch"] = bool(catch)
        run["auto_left"] = max(0, int(auto_battles or 0))
        again = "grind()" if balance else f"grind({target_level})"
        st = run

        # Grass that exists and FITS the Pokémon being trained.
        lag0 = self._lagging_mons(party)
        lvl0 = self._grind_level(party, lag0)
        run["lvl"] = lvl0
        if self.reader.detect_context() == GameContext.OVERWORLD:
            if self._nearest_grass() is None:
                if not self._relocate_to_grass(level=lvl0):
                    self._grind_run = None
                    return ("No tall grass reachable from here — go_to a route with grass "
                            f"(e.g. 'Route 1'/'Route 2' or Viridian Forest), then call {again} again.")
            elif is_misfit(self.reader.read_current_map(), lvl0):
                self._relocate_to_grass(level=lvl0)            # best effort: too hot / too cold for the trainee

        for _ in range(1500 if balance else 600):
            party = self.reader.read_party()
            if not party:
                break
            lag = self._lagging_mons(party)
            if balance and not lag:
                break
            if not balance and max(p.level for p in party) >= target_level:
                break
            if run["battles"] >= self._GRIND_MAX_BATTLES:
                out = (f"Grinding paused after {run['battles']} battles: {self._grind_summary(run, party)} "
                       f"Call {again} to keep going, or do something else first.")
                self._grind_run = None
                return out
            ctx = self.reader.detect_context()
            if ctx != GameContext.IN_BATTLE and self._forced_replacement():
                # the lead fainted and the game wants the next Pokémon: that is the model's call (A would pick blindly)
                from game.menu import _healthy_roster
                return ("Your Pokémon fainted while grinding — the game is forcing a replacement. Call "
                        f"switch_pokemon('<name or slot>') (healthy: {_healthy_roster(self.reader)}); finish the "
                        f"battle, then call {again} to continue.")
            if ctx == GameContext.IN_BATTLE:
                trainer = bool(self.mgba.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER)
                if not self._grind_auto_ok(run, trainer, party):
                    run["battles"] += 1
                    return self._grind_yield(run, again, trainer, party)
                run["auto_left"] -= 1
                run["battles"] += 1
                ok = [p for _, p in lag if healthy_enough(p, self._GRIND_HP_FLOOR)]
                if ok:
                    self._train_fight((ok[0].species_id, ok[0].max_hp))
                else:
                    self._auto_fight()
                st["stuck"] = 0
            elif ctx == GameContext.OVERWORLD:
                if balance:
                    why_stop = ace_runaway(run["start"], party, run["battles"])
                    if why_stop:
                        out = (f"Grinding stopped: {why_stop}. {self._grind_summary(run, party)} Train the lagging "
                               "members elsewhere — a route whose wild Pokémon are closer to their level, or "
                               "catch/Potion-assisted fights — before calling grind() again.")
                        self._grind_run = None
                        return out
                # Between fights: top up HP/PP before the next one rather than into a stalemate.
                why = party_needs_restock(party, self._GRIND_HP_FLOOR)
                if not why and lag and not any(healthy_enough(p, self._GRIND_HP_FLOOR) for _, p in lag):
                    why = "the lagging Pokémon are hurt"
                if why:
                    if run["heals"] >= self._AUTO_HEALS:
                        out = (f"Grinding paused ({why}) after {run['heals']} automatic heals. "
                               f"Call heal(), then {again} again.")
                        self._grind_run = None
                        return out
                    run["heals"] += 1
                    abort = self._restock(why)
                    if abort:
                        self._grind_run = None
                        return abort
                    continue
                lvl = self._grind_level(party, lag)
                if lvl != run["lvl"]:                           # the trainee levelled: is this route still the right one?
                    run["lvl"] = lvl
                    if run["fit_moves"] < 4 and is_misfit(self.reader.read_current_map(), lvl):
                        run["fit_moves"] += 1
                        if self._relocate_to_grass(level=lvl):
                            continue
                if lag:
                    ok_t = [p for _, p in lag if healthy_enough(p, self._GRIND_HP_FLOOR)]
                    if ok_t and (party[0].species_id, party[0].max_hp) != (ok_t[0].species_id, ok_t[0].max_hp):
                        self._lead_trainee(ok_t[0])      # trainee fights alone → all the XP
                abort = self._grass_step(st, again)
                if abort:
                    self._grind_run = None
                    return abort
            elif ctx == GameContext.IN_MENU:
                # A field menu / party screen is open: A would SELECT inside it (it opened a
                # SHIFT/SUMMARY submenu and spun there for 1400 iterations). Back out instead.
                if str(self._close_menus() or "").startswith("In battle"):
                    # a battle's intro text can read as a menu: give it a moment to settle into IN_BATTLE;
                    # if it never does, hand it over rather than spin
                    run["menu_battle"] = run.get("menu_battle", 0) + 1
                    if run["menu_battle"] >= 6:
                        run["menu_battle"] = 0
                        run["battles"] += 1
                        return self._grind_yield(run, again, False, party)
                    self.mgba.tick(30)
                else:
                    run["menu_battle"] = 0
            else:
                self.mgba.tap("A")        # advance a dialog/transition
                self.mgba.tick()
        party = self.reader.read_party()
        summary = self._grind_summary(run, party)
        if balance:
            done = not self._lagging_mons(party)
            if done:
                self._grind_run = None
            return (f"Party balanced after {summary}" if done else
                    f"Training progress after {summary} Call grind() again to continue.")
        if max((p.level for p in party), default=0) >= target_level:
            self._grind_run = None
            return f"Reached L{target_level} after {summary}"
        return f"Grinded after {summary} Call {again} again to continue."

    def _forced_replacement(self) -> bool:
        try:
            from game.menu import forced_party_screen
            return bool(forced_party_screen(self.mgba, self.reader))
        except Exception:
            return False

    def _grind_auto_ok(self, run, trainer: bool, party) -> bool:
        """May this encounter run on autopilot (auto_battles budget)? Only boring wild fights: a foe at most 2
        levels above the active Pokémon, and nothing worth a ball when catching is on."""
        if trainer or run.get("auto_left", 0) <= 0:
            return False
        try:
            foe = self.reader.read_enemy_lead()
            if not foe or not foe.species_id or not foe.max_hp or (foe.species_name or "").startswith("#"):
                return False
            active = self.reader.read_active_battle_species()
            mine = next((p for p in party if p.species_id == active), party[0])
            if foe.level > mine.level + self._GRIND_AUTO_MARGIN:
                return False
            if run["catch"] and self._ball_count() > 0:
                from knowledge.catch_policy import evaluate
                dex = getattr(self.reader, "read_dex_owned", lambda _s: None)(foe.species_id)
                if evaluate(party, foe.species_id, foe.level, dex_owned=dex).catch:
                    return False
            return True
        except Exception:
            return False

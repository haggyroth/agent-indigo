"""Overworld skills: heal at a Pokémon Center, shop at a Mart, grind wild
battles, and pick up item balls. See agent.lm_studio_client.AgentClient
(which inherits OverworldMixin)."""

from agent.skills.base import log_once
from game.state import GameContext
from knowledge.league_rooms import LEAGUE_ROOM_MAPS
from knowledge.navigation import MAP_NAMES
from knowledge.party import boss_lead as boss_lead_slot, travel_lead as travel_lead_slot
from knowledge.travel_rules import no_walk_reason

FLAG_BEAT_RIVAL_IN_OAKS_LAB = 0x258       # from then on Mom heals the party at home in Pallet Town


def _safe_call(fn, default=None):
    try:
        return fn()
    except Exception:
        log_once("overworld._reachable_tiles", "overworld._reachable_tiles: tolerated failure (continuing with a default)")
        return default


_VICTORY_ROAD = {(1, 39), (1, 40), (1, 41)}          # 1F / 2F / 3F: a cave with no Pokémon Center


class OverworldMixin:


    def _bag_and_keys(self) -> tuple[dict, int]:
        return self.reader.read_bag(), self.reader.read_key_item_count()

    def _pick_ball(self, bx: int, by: int, hidden: bool = False) -> tuple[str, str]:
        """Walk next to the item ball at (bx, by), face it, press A and clear the 'found ITEM!' text. Returns (what was
        picked up, "") or ("", why not). Confirmed by the bag / key-item total rising or the ball vanishing."""
        from knowledge.shopping import ITEM_NAMES
        if not self._approach_adjacent(bx, by):
            return "", f"couldn't reach the item at ({bx},{by})"
        before_bag, before_keys = self._bag_and_keys()
        picked = False
        for _ in range(6):
            px, py = self.reader.read_player_pos()
            face = self._facing_dir(px, py, bx, by)
            if face and hidden:
                self.mgba.tick(24)           # let the last step finish: facing and position read mid-step are stale
                if self.reader.read_player_facing() != face:
                    self.mgba.hold(face, 3)  # a 3-frame press only TURNS (a tap steps, and onto a WALKABLE hidden-item tile A does nothing)
                    self.mgba.tick(12)
            elif face:
                self.mgba.tap(face)          # turn to face the ball (bumps it, no move)
            self.mgba.tap("A")               # pick up
            self.mgba.tick(15)
            self._advance_to_control()       # advance "found ITEM!" text to control
            after_bag, after_keys = self._bag_and_keys()
            if after_keys > before_keys or sum(after_bag.values()) > sum(before_bag.values()) \
                    or (not hidden and (bx, by) not in self.reader.read_item_ball_tiles()):        # a hidden item has no ball to vanish: only the bag proves it
                picked = True
                break
        if not picked:
            return "", f"the item at ({bx},{by}) didn't respond"
        after_bag, after_keys = self._bag_and_keys()
        new = [ITEM_NAMES.get(iid, f"item#{iid}") for iid, q in after_bag.items() if q > before_bag.get(iid, 0)]
        if after_keys > before_keys:
            new.append("a key item")
        return (", ".join(new) if new else "an item"), ""

    def _pick_up_items(self) -> str:
        """Collect every item ball currently visible on this map. For each, walks up
        next to it, faces it, presses A, and advances the 'found ITEM!' text — the
        deterministic version of what the model would otherwise fumble. Confirms each
        pickup by the bag/key-item total rising (or the ball vanishing). Item balls
        are surfaced in the observation so the model knows to call this."""
        from game.state import GameContext
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "Can only pick up items while walking around (not in a menu/battle)."
        got: list[str] = []
        for _ in range(8):                       # bounded: at most 8 balls per call
            balls = self.reader.read_item_ball_tiles()
            if not balls:
                break
            px, py = self.reader.read_player_pos()
            bx, by = min(balls, key=lambda t: abs(t[0] - px) + abs(t[1] - py))
            names, problem = self._pick_ball(bx, by)
            if problem:
                return self._pickup_result(got, problem)
            got.append(names)
        got += self._pick_hidden_here()
        return self._pickup_result(got)

    def _pick_hidden_here(self, limit: int = 6) -> list[str]:
        """The worthwhile hidden items (knowledge.hidden_items) this map is known to hold: walk next to the tile, face it, press A. A tile that gives nothing is remembered
        as taken (ltm 'hidden_taken') so it is not walked to again; the result names each find as 'X (hidden)'."""
        from knowledge.hidden_items import hidden_on
        cur = tuple(self.reader.read_current_map())
        taken = self.ltm.data.setdefault("hidden_taken", [])
        got: list[str] = []
        for name, x, y in hidden_on(cur, set(taken))[:limit]:
            names, problem = self._pick_ball(x, y, hidden=True)
            if problem.startswith("couldn't reach"):
                continue                                         # blocked (a trainer, a battle): try again on a later call, don't write it off
            taken.append(f"{cur[0]}/{cur[1]}/{x}/{y}")           # collected, or the tile gave nothing: either way it is done
            if not problem:
                got.append(f"{names} (hidden)")
            if self.reader.detect_context() != GameContext.OVERWORLD:
                break
        return got

    @staticmethod
    def _pickup_result(got: list[str], problem: str = "") -> str:
        if not got and problem:
            return f"No items picked up — {problem}."
        if not got:
            return "No item balls visible here (and no worthwhile hidden items known on this map)."
        head = f"Picked up {len(got)} item(s): {'; '.join(got)}."
        return head + (f" Stopped: {problem}." if problem else "")

    # Nurse Joy stands at (7,2) in the shared Pokémon Center interior, behind the
    # counter at (7,3). The player stands one tile below the counter, at (7,4), and
    # presses A facing up — the counter metatile forwards the interaction to the
    # nurse behind it. The heal is a pure dialogue: greeting → YES/NO (defaults to
    # YES) → heal → "restored". So we advance with A and confirm success by the
    # party returning to full HP.
    _NURSE_TILE = (7, 4)

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

    def _nurse_tile(self) -> tuple[int, int]:
        """Where to stand to talk to Nurse Joy: two tiles below her (the counter between). The mainland Centers share one layout (Joy at (7,2));
        the Sevii Islands' differ (One Island: (5,2)) — and a patient stood on the mainland tile there, so read her from the live objects."""
        nurses = self.reader.read_objects_by_gfx([64])           # OBJ_EVENT_GFX_NURSE
        if nurses:
            jx, jy = min(nurses, key=lambda t: abs(t[0] - self._NURSE_TILE[0]) + abs(t[1] - 2))
            return (jx, jy + 2)
        return self._NURSE_TILE

    def _home_heals(self) -> bool:
        """Mom heals the party for free once the rival is beaten in Oak's lab (FLAG_BEAT_RIVAL_IN_OAKS_LAB) — from then on the player's house in Pallet counts as a Center."""
        try:
            return bool(self.reader.read_flag(FLAG_BEAT_RIVAL_IN_OAKS_LAB))
        except Exception:
            return False

    def _healer_kinds(self):
        from knowledge.map_graph import HEAL_KINDS
        return HEAL_KINDS if self._home_heals() else ("pokecenter",)

    def _next_center(self, tried):
        """The nearest Pokémon Center from here that is not in `tried` — the ones a heal trip already failed to reach (None if there is no other)."""
        from knowledge.map_graph import nearest_of_kind, node_for
        bank, mid = self.reader.read_current_map()
        px, py = self.reader.read_player_pos()
        from knowledge.distance import PLATEAU_CENTER
        found = nearest_of_kind(node_for(bank, mid, px, py), self._healer_kinds(), exclude=[*tried, *(() if self._plateau_side() else (PLATEAU_CENTER,))])
        return found[0] if found else None

    _MOM_GFX = 88                                    # OBJ_EVENT_GFX_MOM
    _MOM_TILE = (8, 4)                               # where she stands in the Pallet Town house (1F)

    def _heal_at_home(self, force: bool = False) -> str:
        """Mom, in the player's house in Pallet Town, restores the whole party (HP, PP, status) for free — no trek to the nearest Center (Cinnabar's, from Route 21).
        Walk next to her, face her and press A through her talk until the party is whole; the same loop as the nurse's."""
        from game.state import GameContext
        moms = self.reader.read_objects_by_gfx([self._MOM_GFX])
        mx, my = moms[0] if moms else self._MOM_TILE
        here = None
        for tx, ty, face in ((mx + 1, my, "Left"), (mx, my + 1, "Up"), (mx - 1, my, "Right"), (mx, my - 1, "Down")):
            self._walk_to(tx, ty)
            if tuple(self.reader.read_player_pos()) == (tx, ty):
                here = face
                break
        if here is None:
            return f"Couldn't reach Mom at {(mx, my)} (at {self.reader.read_player_pos()}). Try walk_to next to her, then talk (A)."
        self.mgba.tap(here)                          # face her
        for _ in range(40):
            if not self._party_needs_heal():
                self._advance_to_control(tries=24)
                from agent import events
                events.emit("heal", "party healed by Mom at home in Pallet Town")
                return "Healed the party to full HP and PP — Mom did it at home in Pallet Town."
            self.mgba.tap("A")
            self.mgba.tick(12)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return "A battle started while healing — handle it, then heal again."
        return "Talked to Mom but couldn't confirm a full heal — try heal again, or check you're facing her."

    def _league_heal(self) -> str:
        """Inside an Elite Four room there is no Pokémon Center to reach (the door sealed behind you): heal from the Bag — Revives for the fainted, then the smallest Potion / Full Restore
        that fills the gap of anyone under 60% — and say what is left. A watched run called heal() and go_to('Pokemon Center') in Lorelei's room for 300 calls."""
        used = self._field_heal(max_uses=12, below=0.6) + self._field_cure() + self._field_pp()
        bag = dict(self.reader.read_items_pocket())
        left = f"{sum(n for i, n in bag.items() if i == 19)} Full Restore, {sum(n for i, n in bag.items() if i in (24, 25))} Revive, {sum(n for i, n in bag.items() if i in (13, 22, 21, 20))} Potions"
        if used:
            return f"The Elite Four's rooms are sealed — no Center to leave for. Healed from the Bag instead: {', '.join(used)}. Left: {left}. Press on: quest('elite_four')."
        return (f"The Elite Four's rooms are sealed — there is no Pokémon Center to leave for, and nothing more in the Bag is worth using now ({left}). "
                "Press on with quest('elite_four'): win outright, or if the whole team faints the whiteout returns you to the Plateau's Center fully healed (the League resets).")

    def _heal(self, force: bool = False) -> str:
        """Heal the whole party at a Pokémon Center. Travels to the nearest one if
        not already inside, walks to Nurse Joy, and advances the heal dialogue
        until the party is at full HP. Resumable: if a wild battle/dialog interrupts
        the trip, it stops and reports so the caller can resume."""
        from game.state import GameContext
        from knowledge.map_graph import MAP_KIND
        try:
            sealed = tuple(self.reader.read_current_map()) in LEAGUE_ROOM_MAPS
        except Exception:
            sealed = False                                   # a half-loaded screen: not the League
        if sealed:
            return self._league_heal()                       # sealed in: no Center, so the Bag's cures count too (a status is not "full HP and PP")
        if not force and not self._party_needs_heal():
            return "Party is already at full HP and PP — no need to heal."
        # Inside Victory Road no Center is reachable (the way out south needs Surf over Route 23, the way on is the puzzle itself): a go_to from there only
        # wandered the cave pushing boulders out of place (chain run 8). Heal from the Bag and push on.
        cave = tuple(self.reader.read_current_map())
        if cave in _VICTORY_ROAD:
            # Grinding in the cave (its wild L32-48 are the closest fit for a team past the gyms), a heal is a walk OUT to Viridian's Center — the reverse puzzle — not an item-by-item drain of the Bag,
            # which a long session cannot afford; and 1F is just the entrance hall (an empty Bag there means walk out, not "push on" through the boulders at 19 pushes to the first switch).
            grinding = bool(self._grind_run)
            used = [] if grinding else self._field_heal()
            if used:
                return f"Victory Road has no Pokémon Center — healed from the Bag instead: {', '.join(used)}."
            if not grinding and cave != (1, 39):
                return ("Victory Road has no Pokémon Center and the Bag has nothing to heal with — push on to the Indigo Plateau Center "
                        "(quest('victory_road') resumes) instead of walking back.")
            if (msg := self._vr_back("heal()")):
                return msg
        # Get inside a Pokémon Center first (resumable travel).
        if MAP_KIND.get(self.reader.read_current_map()) not in self._healer_kinds():
            tried = [self._resolve_destination("Pokemon Center")[0]]       # the Center the trip heads for first
            res = self._go_to("Pokemon Center", mode="flee", resume_call="heal()")
            while (MAP_KIND.get(self.reader.read_current_map()) not in self._healer_kinds() and len(tried) < 3
                   and ("blocked" in res or "stuck at" in res or "Can't reach" in res)):
                # The nearest Center on paper may not be reachable (Route 23: the graph walks its North edge to the Indigo Plateau's Center, but the way is
                # a Surf gap / the League's own gate): try the next-nearest — Viridian's, across the water — before giving up on a Center.
                alt = self._next_center(tried)
                if alt is None:
                    break
                tried.append(alt)
                res = self._go_to(f"map:{alt[0]},{alt[1]}", mode="flee", resume_call="heal()")
            if MAP_KIND.get(self.reader.read_current_map()) not in self._healer_kinds():
                if "blocked" in res or "stuck at" in res or "Can't reach" in res:
                    used = self._field_heal()          # no Center reachable from here (a cave, a Surf gap): the Bag has to do
                    if used:
                        return f"No Pokémon Center is reachable from here ({res}) — healed from the Bag instead: {', '.join(used)}."
                return f"On the way to a Pokémon Center to heal: {res}"
        if MAP_KIND.get(self.reader.read_current_map()) == "home":
            return self._heal_at_home(force)
        # Walk to the nurse's counter and face her.
        nx, ny = self._nurse_tile()
        self._walk_to(nx, ny)
        if self.reader.read_player_pos() != (nx, ny):
            return (f"Couldn't reach Nurse Joy's counter at {(nx, ny)} "
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
                from agent import events
                events.emit("heal", "party healed at the Pokémon Center")
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
    _SHOP_SUBSTITUTES = {4: (3,), 13: (22, 21)}      # Poké Ball → Great Ball; Potion → Super / Hyper Potion (a mart that lacks the cheap grade). (It said 24 = a REVIVE for Hyper Potion until the Plateau's clerk sold one in place of a Potion.)

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

    def _open_buy_menu(self, approach=None, face: str = "Up", sell: bool = False) -> bool:
        """Talk to the clerk, then select Buy so the interactive item list is open.
        sShopData.itemList is set as soon as the Buy/Sell menu appears (before Buy is
        chosen), so 'itemList valid' only means the shop menu is up — we then select
        Buy (top option, default cursor) and let the item list fade in before the
        caller navigates (Task_BuyMenu ignores D-pad while gPaletteFade is active)."""
        from game.constants import Addr
        # sShopData.itemList keeps pointing at the LAST shop's list after it closes; clear it, or "list is valid" would read as
        # "this clerk's menu is up" the instant we arrive and the buy would run against the wrong (stale) stock.
        for off in range(4):                                  # write8 only: the legacy HTTP client has no wider writes
            self.mgba.write8(Addr.SHOP_DATA + Addr.SHOP_ITEMLIST + off, 0)
        self._walk_to(*(approach or self._MART_CLERK_APPROACH))   # lands at the counter-front tile
        # 1. Talk to the clerk and advance the greeting until the shop menu appears.
        shop_up = False
        for _ in range(3):
            self.mgba.tap(face)                       # face the clerk
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
        #    fade finishes and the list starts taking D-pad input. With `sell`, move down to SELL first: that opens the BAG
        #    (callback2 = the bag screen), not an item list.
        if sell:
            self.mgba.tap("Down")
            self.mgba.tick(10)
        self.mgba.tap("A")
        self._wait_idle()
        self.mgba.tick(40)
        if sell:
            from game.constants import Addr
            return self.mgba.read32(Addr.GMAIN_CALLBACK2) == Addr.BAG_CB2
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
        before = self.reader.count_item(item_id)
        # Select the item → the "How many?" quantity box. Wait for its init to run
        # (it computes maxQuantity = money/price; 0 means it hasn't run yet).
        self._wait_idle()
        self.mgba.tap("A")
        maxq = 0
        for _ in range(10):
            self._wait_idle()
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
            self._wait_idle()
            self.mgba.tick(10)
            got = self.reader.count_item(item_id) - before
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
                self._wait_idle()
                self.mgba.tick(10)
        return max(0, got)

    def _close_buy_menu(self) -> None:
        from game.state import GameContext
        for _ in range(12):
            if self.reader.detect_context() == GameContext.OVERWORLD:
                return
            self.mgba.tap("B")
            self.mgba.tick(12)

    def _clerk_approach(self, clerk: tuple):
        """((x, y), facing) — the tile on the customer's side of the counter to stand on to talk to the clerk at `clerk`, read from
        the map (not a fixed tile), or None. A Dept. Store clerk is nowhere near a Mart's (2,3)."""
        from knowledge.shopping import approach_options
        self.tilemap.refresh()
        grid, w, h = self.tilemap.passable_grid()
        floor = (lambda x, y: bool(grid and 0 <= x < w and 0 <= y < h and grid[y][x]))
        px, py = self.reader.read_player_pos()
        seen, todo = {(px, py)}, [(px, py)]              # tiles the player can actually walk to (not the clerk's own side)
        while todo:
            x, y = todo.pop()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) not in seen and floor(nx, ny):
                    seen.add((nx, ny))
                    todo.append((nx, ny))
        spots = approach_options(tuple(clerk), floor, lambda x, y: (x, y) in seen)
        if not spots:
            return None
        return min(spots, key=lambda s: abs(s[0][0] - px) + abs(s[0][1] - py))

    def _shop_for(self, item: str, quantity: int = 1) -> str:
        """shop(item=…): buy a SPECIFIC item (a TM, a stone, a vitamin, an X-item…) from whichever clerk sells it — the nearest
        one by route. Travels there, stands on the customer's side of that clerk's counter (from the map, not a fixed tile),
        buys, and confirms by the bag / TM case count rising."""
        from knowledge.map_graph import node_for, route_to
        from knowledge.shop_stock import PRICES, SHOP_NAMES
        from agent import events
        from knowledge.shopping import FREE_SOURCES, item_label, resolve_item, shops_selling
        from knowledge.tmhm import TMHM
        iid, close = resolve_item(item)
        if iid is None:
            from knowledge.game_corner import resolve_prize
            prize, near = resolve_prize(item)
            if prize is not None:
                return self._buy_prize(prize)                  # paid in Game Corner coins, not yen
            close = close or near
        if iid is None:
            return (f"No clerk sells {item!r}." + (f" Did you mean: {', '.join(close)}?" if close else "")
                    + " (Poké Marts sell balls, potions and cures; the Celadon Dept. Store also sells TMs, stones, vitamins and X-items; the "
                    "Celadon Prize Corner sells TMs, items and Pokémon for Game Corner coins.)")
        label, price = item_label(iid), PRICES.get(iid, 0)
        if iid in FREE_SOURCES and not self.reader.count_item(iid):
            events.emit("note", FREE_SOURCES[iid] + " — buying anyway", log=False)
        money = self.reader.read_money()
        qty = max(1, int(quantity or 1))
        if price and money < price:
            return f"{label} costs ¥{price} and you have ¥{money}."
        if price:
            qty = min(qty, money // price)
        cur = self.reader.read_current_map()
        here = [s for s in shops_selling(iid) if (s[0], s[1]) == tuple(cur)]
        if not here:
            def hops(s):
                bank, mid = cur
                r = route_to(node_for(bank, mid, *self.reader.read_player_pos()), (s[0], s[1]))
                return len(r) if r is not None else 10 ** 6
            best = min(shops_selling(iid), key=hops)
            res = self._go_to(SHOP_NAMES[(best[0], best[1])])
            if tuple(self.reader.read_current_map()) != (best[0], best[1]):
                return f"On the way to {SHOP_NAMES[(best[0], best[1])]} to buy {label}: {res}"
            here = [s for s in shops_selling(iid) if (s[0], s[1]) == (best[0], best[1])]
        clerk = here[0]
        spot = self._clerk_approach((clerk[2], clerk[3]))
        if spot is None:
            return f"Couldn't find a tile beside the clerk at ({clerk[2]},{clerk[3]}) to stand on."
        (ax, ay), face = spot
        before = self.reader.count_item(iid)
        if not self._open_buy_menu((ax, ay), face):
            return f"Couldn't open the buy menu — walk to ({ax},{ay}), face the clerk and call shop(item={item!r}) again."
        got = self._buy_one_item(iid, qty, price) if iid in self._shop_item_list() else 0
        self._close_buy_menu()
        if got <= 0:
            return f"Couldn't buy {label} (it costs ¥{price}; you have ¥{self.reader.read_money()})."
        events.emit("shop", f"bought {got}× {label} (−¥{got * price}, ¥{self.reader.read_money()} left)")
        extra = (" Teach it with teach_move." if iid in TMHM else "") + (f" ({FREE_SOURCES[iid]}.)" if iid in FREE_SOURCES else "")
        return f"Bought {got}× {label} (¥{got * price}). You now have {self.reader.count_item(iid)} (was {before}); ¥{self.reader.read_money()} left.{extra}"

    def _at_a_shop(self) -> bool:
        """On a Mart — or on a map with a clerk in the shop data (the Indigo Plateau's Pokémon Center has one: Full Restores, Max Potions, Revives)."""
        from knowledge.map_graph import MAP_KIND
        from knowledge.shop_stock import SHOPS
        cur = tuple(self.reader.read_current_map())
        return MAP_KIND.get(cur) == "mart" or any((b, m) == cur for b, m, *_rest in SHOPS)

    def _viridian_mart_closed(self) -> str:
        """'' normally. Inside Viridian's Mart before Oak's Pokédex the clerk only has the parcel for you — there is no buy menu (a watched run called shop() a dozen times)."""
        from knowledge.readiness import FLAG_POKEDEX
        if tuple(self.reader.read_current_map()) == (5, 3) and not self.reader.read_flag(FLAG_POKEDEX):
            return ("The Viridian Mart clerk doesn't sell anything yet: he only hands over Oak's Parcel until Prof. Oak has it. Take the parcel to Oak (Pallet Town's lab): quest('parcel'). "
                    "Oak gives you the first Poké Balls; shop() works at the next Mart.")
        return ""

    def _shop(self, item: str = "", quantity: int = 1) -> str:
        """Restock at the Poké Mart per the badge-gated purchase policy: travel to a
        Mart if needed, open the buy menu, buy the affordable par-level list of items
        this mart sells, and leave. With `item`, buy that specific item instead (_shop_for)."""
        if (msg := self._viridian_mart_closed()):
            return msg
        if str(item or "").strip():
            return self._shop_for(str(item), quantity)
        from knowledge.shopping import compute_shopping_list, ITEM_NAMES, ITEM_PRICES
        if not self._at_a_shop():
            res = self._go_to("Mart")
            if not self._at_a_shop():
                return f"On the way to a Mart to restock: {res}"
        money = self.reader.read_money()
        plan = compute_shopping_list(self.reader.read_bag(),
                                     self.ltm.data["badges_earned"], money)
        if not plan["lines"]:
            return f"Bag is already stocked (¥{money}) — nothing to buy."
        approach, face = None, "Up"
        cur = tuple(self.reader.read_current_map())
        from knowledge.shop_stock import SHOPS
        want = {line["item_id"] for line in plan["lines"]}
        clerks = [(x, y, set(items)) for b, m, x, y, items in SHOPS if (b, m) == cur]
        if clerks and (2, 3) not in [(x, y) for x, y, _ in clerks]:
            # A multi-clerk store (Celadon Dept. Store 2F): the standard-mart tile (2,4) is the wrong place. Walk to the clerk
            # that sells the most of what we want, standing on the customer's side of the counter.
            x, y, _items = max(clerks, key=lambda c: len(c[2] & want))
            spot = self._clerk_approach((x, y))
            if spot is not None:
                approach, face = spot
        if not self._open_buy_menu(approach, face):
            return ("Couldn't open the Mart buy menu — walk up to the clerk at the "
                    "counter and call shop() again.")
        sold = set(self._shop_item_list())
        # What THIS mart lists decides the tiers (Ultra over Great over Poké, Hyper over Super over Potion) and, with spare money, a bigger stock.
        from knowledge.shopping import compute_stock_plan
        stock = compute_stock_plan(self.reader.read_bag(), self.ltm.data["badges_earned"], money, sold, reserve=500)
        bought, spent, skipped = [], 0, []
        for line in (stock["lines"] or plan["lines"]):
            iid, qty, unit = line["item_id"], line["qty"], ITEM_PRICES.get(line["item_id"], line["unit_price"])
            if iid not in sold:
                # The Celadon Dept. Store has no Poké Ball / Potion: buy the next grade up with the same BUDGET (fewer of them).
                sub = next((s for s in self._SHOP_SUBSTITUTES.get(iid, ()) if s in sold and ITEM_PRICES.get(s)), None)
                if sub is None:
                    skipped.append(ITEM_NAMES.get(iid, str(iid)))
                    continue
                qty, unit, iid = max(1, min(qty, qty * unit // ITEM_PRICES[sub])), ITEM_PRICES[sub], sub
            got = self._buy_one_item(iid, qty, unit)
            if got > 0:
                bought.append(f"{got}× {ITEM_NAMES.get(iid, iid)}" + ("" if iid == line["item_id"] else f" (instead of {ITEM_NAMES.get(line['item_id'])})"))
                spent += got * unit
        self._close_buy_menu()
        if not bought:
            cand = set()
            for ln in plan["lines"]:                   # what this store sells that fills the plan (the item itself or its substitute)
                cand |= ({ln["item_id"]} | set(self._SHOP_SUBSTITUTES.get(ln["item_id"], ()))) & sold
            cheapest = min((ITEM_PRICES[i] for i in cand if ITEM_PRICES.get(i)), default=0)
            if cheapest and money < cheapest:
                # remembered: the READINESS "shop()" need stays quiet until the money grows (a run made 13 pointless trips at ¥600)
                self.ltm.data["shop_broke_at"] = money
                return (f"At the Mart but bought nothing: you have ¥{money} and the cheapest thing it sells that you need costs "
                        f"¥{cheapest}. Earn more first (trainer battles pay) — shop() will not be suggested again until you have more.")
            return ("At the Mart but bought nothing (this mart doesn't sell the "
                    "recommended items, or you couldn't afford them).")
        msg = f"Bought {', '.join(bought)} (¥{spent}). Money left: ¥{self.reader.read_money()}."
        from agent import events
        events.emit("shop", f"bought {', '.join(bought)} (−¥{spent}, ¥{self.reader.read_money()} left)")
        if skipped:
            msg += f" (Not sold here: {', '.join(dict.fromkeys(skipped))}.)"
        if stock["missing"]:
            msg += f" (A better grade: {', '.join(stock['missing'])} — other marts sell it: Fuchsia / Cinnabar / Saffron / Indigo.)"
        return msg

    _OPPOSITE = {"Up": "Down", "Down": "Up", "Left": "Right", "Right": "Left"}

    def _wander_step(self) -> bool:
        """Take one overworld step to seek a wild encounter, PACING back and forth so
        we stay in the local (grassy) patch instead of drifting out of it. Keeps a
        heading, reverses when blocked, and rotates axis if fully boxed in. Returns
        True if a battle started."""
        from game.state import GameContext
        heading = self._wander_dir
        # Try the current heading, then its reverse, then the other axis.
        order = [heading, self._OPPOSITE[heading]]
        for d in ("Up", "Down", "Left", "Right"):
            if d not in order:
                order.append(d)
        run = self._can_run(self.reader.read_current_map())          # the Running Shoes: twice the steps (so encounters) per frame
        warps = self._warp_tiles()
        here = tuple(self.reader.read_player_pos())
        on_press = self.tilemap.warp_press(*here) if here in warps else None
        for mv in order:
            dx, dy = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}[mv]
            if (here[0] + dx, here[1] + dy) in warps or mv == on_press:
                continue                    # a staircase / door: pacing onto it changes floors (a watched run ping-ponged between Mansion floors)
            before = self.reader.read_player_pos()
            (self.mgba.run_step if run else self.mgba.tap)(mv)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                self._wander_dir = mv
                return True
            if self.reader.read_player_pos() != before:
                self._wander_dir = mv   # keep pacing this way until blocked
                return False
        return False

    def _warp_tiles(self) -> set:
        """The tiles of this map that really warp (stairs, doors, ladders) — never somewhere to pace while hunting encounters."""
        try:
            self.tilemap.refresh()
            return {tuple(w) for w in self.tilemap.read_warps() if self.tilemap.is_real_warp(*w)}
        except Exception:
            log_once("overworld._warp_tiles", "overworld._warp_tiles: tolerated failure (continuing with a default)")
            return set()

    def _reachable_tiles(self) -> set | None:
        """Tiles the player can walk to from here on this map (flood fill over the passable grid; a Cut tree counts as
        open only when the party can Cut — walk_to then cuts it). None when the grid is unavailable."""
        self.tilemap.refresh()
        grid, w, h = self.tilemap.passable_grid(surf=self._surfing())
        if grid is None:
            return None
        trees = self._cut_tree_tiles(w, h)
        shut = set() if self._can_use_cut() else trees        # NPCs move and can be engaged: only an uncuttable tree seals grass
        start = tuple(self.reader.read_player_pos())
        seen, todo = {start}, [start]
        while todo:
            x, y = todo.pop()
            for name, dx, dy in (("Right", 1, 0), ("Left", -1, 0), ("Down", 0, 1), ("Up", 0, -1)):
                n = (x + dx, y + dy)
                if not (0 <= n[0] < w and 0 <= n[1] < h):
                    continue
                if not grid[n[1]][n[0]] and n not in trees and self.tilemap.ledge_dir(*n) == name:
                    n = (x + 2 * dx, y + 2 * dy)               # a one-way ledge: the hop lands two tiles on (walk_to does the same)
                    if not (0 <= n[0] < w and 0 <= n[1] < h) or not grid[n[1]][n[0]]:
                        continue
                if n in seen or n in shut:
                    continue
                if grid[n[1]][n[0]] or n in trees:
                    seen.add(n)
                    todo.append(n)
        return seen

    def _grind_tiles(self) -> list[tuple[int, int]]:
        """Where a step can start a wild battle on this map: its tall grass — or, in the Pokémon Mansion (no grass; every floor tile encounters), its floor."""
        from knowledge.map_graph import CAVE_GRIND_MAPS
        if tuple(self.reader.read_current_map()) in CAVE_GRIND_MAPS:
            warps = self._warp_tiles()
            return [t for t in self.tilemap.land_encounter_tiles() if t not in warps]
        return self.tilemap.grass_tiles()

    def _on_grind_tile(self, px: int, py: int) -> bool:
        from knowledge.map_graph import CAVE_GRIND_MAPS
        if tuple(self.reader.read_current_map()) in CAVE_GRIND_MAPS:
            return self.tilemap.is_land_encounter_tile(px, py)
        return self.tilemap.is_tall_grass(px, py)

    def _nearest_grass(self) -> tuple[int, int] | None:
        """Closest REACHABLE tall-grass tile to the player on the current map (Manhattan), or None if the map has no grass — or
        only grass walled off behind Cut trees we cannot cut (Route 8's fenced pocket: heading for it by distance alone sent the
        run ping-ponging between the two trees and off to Route 10 and back). Uses the metatile-behavior reader so grind can
        route the player onto a real patch instead of guessing from encounters."""
        self.tilemap.refresh()
        tiles = self._grind_tiles()
        if not tiles:
            return None
        here = self.reader.read_current_map()
        reach = _safe_call(self._reachable_tiles)
        if reach is not None:
            usable = [t for t in tiles if t in reach]
            if not usable:
                self._sealed_grass.add(here)
                return None
            self._sealed_grass.discard(here)
            tiles = usable
        px, py = self.reader.read_player_pos()
        return min(tiles, key=lambda t: abs(t[0] - px) + abs(t[1] - py))

    def _grind_objective(self):
        """The map of the next goal the grind should stay near — the city of the next gym still owed — or None once all eight are won."""
        from knowledge.leafgreen_data import GYMS
        ltm = getattr(self, "ltm", None)
        beaten = set(ltm.data.get("gyms_beaten", [])) if ltm is not None else set()
        nxt = next((g for g in GYMS if g["leader"] not in beaten), None)
        return next((key for key, name in MAP_NAMES.items() if name == nxt["city"]), None) if nxt else None

    def _routing_start(self):
        """Where the player stands as a routing node (split maps are region-qualified), for the planners."""
        from knowledge.map_graph import node_for
        bank, mid = self.reader.read_current_map()
        pos = _safe_call(self.reader.read_player_pos)
        return node_for(bank, mid, *(pos or (None, None)))

    def _relocate_to_grass(self, exclude_current: bool = False, level: int | None = None) -> bool:
        """Deterministically travel to the nearest grass route so grind has grass to
        work with, instead of handing a 'go find grass' message back to the model
        (which it tends to ignore). Returns True if we end up somewhere with grass."""
        from knowledge.grind_routes import best_grass
        if level is None:
            level = (self._grind_run or {}).get("lvl") or 0
        # From the Indigo Plateau or inside Victory Road the road back south is the cave's puzzle run in reverse (and Route 23's Surf gap): chain run 10 got wedged on
        # Victory Road 2F looking for grass. Fly out instead when someone can.
        if tuple(self.reader.read_current_map()) in (_VICTORY_ROAD | {(3, 9)}):
            from knowledge.team import hm_status
            try:
                knower, _cap = hm_status(self.reader.read_party(), "Fly")
                if knower and self.reader.read_badges()[1] >> 2 & 1 and self.reader.detect_context() == GameContext.OVERWORLD:
                    self._fly_to("Viridian")
            except Exception:
                log_once("overworld._relocate_to_grass.fly", "overworld._relocate_to_grass: fly-out failed (walking instead)")
        bank, mid = self.reader.read_current_map()
        self._gate_why = ""                                 # only the reasons from THIS search may be told to the model
        # Routes whose way in already beat us twice are off the list for the whole session.
        losses = self._trainer_losses
        best = max((p.level for p in self.reader.read_party()), default=0)
        beaten_goals = {m for m, lvl in self._lost_goals.items() if best < lvl + 3}        # a trainer on the way beat us at that level: not before we are stronger
        avoid: set = {m for m, n in losses.items() if n >= 2} | set(self._sealed_grass) | beaten_goals | {m for m, n in self._failed_grass.items() if n >= 2}   # + grass walled off behind Cut trees
        for _attempt in range(3):
            found = None
            for _probe in range(16):                       # skip grass behind a gate (Brock, a ticket…) without spending an attempt
                found = best_grass(self._routing_start(), level, exclude_current=exclude_current, avoid=avoid, objective=self._grind_objective())
                if found is None:
                    break
                walkable = not no_walk_reason((bank, mid), found[0], self.reader.read_player_pos())      # e.g. back west across Route 4's ledges
                if walkable and not self._grass_route_gated((bank, mid), found[0]):
                    break
                avoid.add(found[0])
                found = None
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
                    self._lost_goals[goal_map] = best               # remembered across grind() calls, until the team is 3 levels stronger
                    self._add_gate_why(f"a trainer on the way to {MAP_NAMES.get(goal_map, goal_map)} beat you at L{best} — "
                                       "that road stays off the list until your best Pokémon is 3 levels higher")
                    self._heal()
                    break
            if lost:
                avoid.add(goal_map)
                bank, mid = self.reader.read_current_map()
                continue
            if self.reader.read_current_map() == goal_map and self._nearest_grass() is not None:
                return True
            self._failed_grass[goal_map] = self._failed_grass.get(goal_map, 0) + 1     # a watched run spent 100 min x 14 grind() calls walking toward Route 21 (open water)
            avoid.add(goal_map)
        return False

    def _add_gate_why(self, why: str) -> None:
        """Remember one more reason a grass route was skipped (up to three, each once) for _why_no_grass."""
        parts = [p for p in self._gate_why.split(" | ") if p]
        if why not in parts and len(parts) < 3:
            parts.append(why)
        self._gate_why = " | ".join(parts)

    def _why_no_grass(self) -> str:
        """' Why: …' when grind skipped the nearest grass because of a story gate or a trainer that beat us (else '')."""
        why, self._gate_why = self._gate_why, ""
        return f" Grass routes skipped on the way: {why}" if why else ""

    def _grass_route_gated(self, here, goal) -> bool:
        """Is the way to the grass map `goal` closed by a story gate the player does not meet (the Pewter guard, a ticket, an HM)?"""
        from knowledge.gates import unmet_gates
        from knowledge.map_graph import node_for, route_to
        try:
            px, py = self.reader.read_player_pos()
            route = route_to(node_for(here[0], here[1], px, py), goal)
            unmet = unmet_gates(route, self._gate_ok) if route else []
            if unmet:
                self._add_gate_why(f"{MAP_NAMES.get(tuple(goal[:2]), goal)}: {unmet[0][1].hint}")      # so a failed grind can say WHY the nearest grass was skipped
            return bool(unmet)
        except Exception:
            log_once("overworld._grass_route_gated", "overworld._grass_route_gated: tolerated failure (continuing with a default)")
            return False

    def _grass_step(self, st: dict, again: str) -> str | None:
        """One overworld step of a grass-grinding loop: pace on a patch to trigger encounters, or
        route back onto grass / relocate to a grassy route. Returns an abort message when grass
        can't be reached, else None. `st` carries {"stuck", "reloc"} between calls."""
        px, py = self.reader.read_player_pos()
        if self._on_grind_tile(px, py):
            self._wander_step()           # on grass — pace back and forth to trigger encounters
            st["stuck"] = 0
            return None
        # Off grass — route back onto the patch (walk_to is ledge-aware).
        target = self._nearest_grass()
        if target is not None:
            res = self._walk_to(*target)
            if "Cut tree blocks" in res:               # the pocket is walled off and we cannot Cut (the trees only load up close)
                self._sealed_grass.add(self.reader.read_current_map())
                st["stuck"] = max(st["stuck"], 24)
            elif res.startswith("No walkable path"):   # the flood fill said reachable, the planner says no: a real run walked Cerulean<->Route 11 <-> Route 9 six times
                here = self.reader.read_current_map()
                self._failed_grass[here] = self._failed_grass.get(here, 0) + 1
                st["stuck"] = max(st["stuck"], 24)
        elif self.reader.read_current_map() in self._sealed_grass:
            st["stuck"] = max(st["stuck"], 24)      # this map's grass is walled off: relocate now, not after 25 idle ticks
        st["stuck"] += 1
        # Can't reach any grass on this map — try a deterministic relocation first.
        if st["stuck"] >= 25:
            if st["reloc"] < 2 and self._relocate_to_grass(exclude_current=True):
                st["reloc"] += 1
                st["stuck"] = 0
                return None
            return ("Couldn't reach tall grass to grind. go_to a grassy route yourself, "
                    f"then call {again} again." + self._why_no_grass())
        return None

    # ── Party balancing ─────────────────────────────────────────────────────────
    def _lagging_mons(self, party=None) -> list:
        """Party members more than BALANCE_GAP (7) levels below the top level (knowledge.party), lowest first
        — fainted ones included (they are lagging, just waiting for a heal)."""
        from knowledge.party import lagging_mons
        run = self._grind_run         # inside a grind session the floor is FIXED (see _grind_inner)
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
            log_once("overworld._train_fight", "overworld._train_fight: tolerated failure (continuing with a default)")
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
                        run = self._grind_run or {}
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
                shiny = self._wild_shiny()
                if shiny:                                     # never flee or autopilot a shiny: hand it to the model to catch
                    return (f"A SHINY {shiny.species_name} L{shiny.level} appeared while healing ({why})! Catch it: weaken it gently, sleep/paralyse it, "
                            "then catch() (load_state(9) retries if it faints). Then call heal() / grind() again.")
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
            return "Healed, but no tall grass is reachable from here — go_to a grassy route, then grind() again." + self._why_no_grass()
        return None

    def _grind(self, target_level: int = 0, catch: bool = True, auto_battles: int | None = None) -> str:
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
            if self._training_swapped and self.reader.detect_context() == GameContext.OVERWORLD:
                self._grind_finish()
        except Exception:
            log_once("overworld._grind_abandon", "overworld._grind_abandon: tolerated failure (continuing with a default)")
            pass

    def _grind_finish(self) -> None:
        if not self._training_swapped:
            return
        try:
            from game.state import GameContext
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return           # the model's battle (or one a time limit cut off): never auto-play it here —
                                 # the flag stays set, so the next grind/abandon puts the ace back in front
            self._restore_ace_lead()
        except Exception:
            log_once("overworld._grind_finish", "overworld._grind_finish: tolerated failure (continuing with a default)")
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
        """After training: the TRAVEL lead goes to the front (knowledge.party.travel_lead — the lowest-level healthy Pokémon close to the top, so the ace is no longer in front of every
        fight outside a gym; retried — menus after an abort can be mid-fade, and a dropped input must not leave a Level-7 trainee leading the party)."""
        self._set_lead_by(travel_lead_slot)

    def _set_lead_by(self, pick) -> None:
        """Put the Pokémon `pick(party)` chooses in slot 1 (retried; never auto-plays a battle)."""
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
            best = pick(self.reader.read_party())
            if best is None or best == 0:
                return
            self._set_lead(str(best + 1))

    def _set_boss_lead(self) -> None:
        """The strongest healthy Pokémon leads a gym leader / Elite Four fight."""
        self._set_lead_by(boss_lead_slot)

    # ── grind(): resumable sessions that hand encounters to the model ─────────────────────────────
    _GRIND_MAX_BATTLES = 150          # encounters (handed over or automatic) one session may take before it reports
    _GRIND_AUTO_DEFAULT = 12          # boring fights a balancing grind() session autopilots per call when auto_battles is omitted
    _GRIND_AUTO_MARGIN = 2            # an auto_battles fight needs a foe at most (active level + this)

    _GRIND_FUTILE_GAP = 12            # a level-target grind is futile when the best OPEN grass tops out this far below the Pokémon

    def _best_open_grass(self, here, level: int, avoid=()):
        """(goal_map, steps) of the best-fitting grass map for `level` whose way in is not story-gated, or None."""
        from knowledge.grind_routes import best_grass
        avoid = {tuple(a[:2]) for a in avoid}
        for _ in range(16):
            found = best_grass(self._routing_start(), level, avoid=avoid, objective=self._grind_objective())
            if found is None:
                return None
            if not self._grass_route_gated(tuple(here[:2]), found[0]):
                return found
            avoid.add(tuple(found[0][:2]))
        return None

    def _grind_futile(self, best: int, target: int) -> str:
        """'' normally; else why grinding the best Pokémon (L`best`) toward L`target` cannot work: a watched run called grind(42) at
        L38 and spent ~700 s of wild fights at L17-22 with the ace gaining nothing (XP scales with the foe's level)."""
        from knowledge.encounters import LAND_LEVELS
        found = self._best_open_grass(self.reader.read_current_map(), best, avoid=self._sealed_grass)
        row = LAND_LEVELS.get(tuple(found[0][:2])) if found else None
        if not row or row[2] >= best - self._GRIND_FUTILE_GAP:
            return ""
        name = MAP_NAMES.get(tuple(found[0][:2]), "the best open route")
        return (f"grind({target}) can't get your L{best} Pokémon there: the best grass you can reach is {name} (wild L{row[0]}–{row[2]}), "
                f"and a kill that far below L{best} gives almost no XP. Don't grind on it. Trainer fights, dungeons and the next story "
                "step give far more; use team_report to judge whether the team already answers the next gym, and balance the weaker "
                "members with grind() (no level), which trains them where it pays.")

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
        from game.state import GameContext
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            try:
                self._battle_settle(40)                   # the foe slot still holds the LAST foe until the first menu is up
            except Exception:
                log_once("overworld._grind_yield.settle", "overworld._grind_yield: could not settle the battle intro (continuing)")
        try:
            where = MAP_NAMES.get(self.reader.read_current_map(), "here")
        except Exception:
            log_once("overworld._grind_yield", "overworld._grind_yield: tolerated failure (continuing with a default)")
            where = "here"
        run["yielded"] = True                             # until the battle ends, a second grind() call is a mistake (see _grind_inner)
        what, verdict = "Pokémon", ""
        try:
            foe = self.reader.read_enemy_lead()
            if foe and foe.species_id and not (foe.species_name or "").startswith("#"):
                what = f"{foe.species_name} L{foe.level} (HP {foe.current_hp}/{foe.max_hp})"
                balls = self._ball_count()
                from game.constants import Addr as _Addr
                if self.mgba.read32(_Addr.BATTLE_TYPE_FLAGS) & _Addr.BATTLE_TYPE_GHOST:
                    verdict = " It is the Tower's ghost: it dodges every ball (can't be caught) — just defeat it with use_move."
                elif run["catch"] and not trainer and balls > 0 and foe.species_id not in {p.species_id for p in party}:
                    from knowledge.catch_policy import evaluate
                    v = evaluate(party, foe.species_id, foe.level or 0,
                                 dex_owned=self.reader.read_dex_owned(foe.species_id),
                                 wanted=self._wanted_species(party), stored=self._stored_species())
                    verdict = (f" Worth a ball: {v.reason}." if v.catch else f" Not worth a ball: {v.reason}.") \
                        + f" ({balls} Poké Balls.)"
        except Exception:
            log_once("overworld._grind_yield", "overworld._grind_yield: tolerated failure (continuing with a default)")
            pass
        lead = party[0] if party else None
        try:
            active_id = self.reader.read_active_battle_species()
            lead = next((p for p in party if p.species_id == active_id), lead)
        except Exception:
            log_once("overworld._grind_yield.active", "overworld._grind_yield: tolerated failure (continuing with a default)")
        lead_name = (lead.nickname or lead.species_name) if lead else "your lead"
        moves = ", ".join(m for m in (lead.move_names if lead else []) if m)
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
        knows = f" {lead_name} knows: {moves}." if moves else ""
        return (f"{head} started at {where} while grinding.{verdict}{knows} {who} Battle {run['battles']}; "
                f"when it is over call {again} to continue.")

    def _grind_inner(self, target_level: int = 0, catch: bool = True, auto_battles: int | None = None) -> str:
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
        live = self._grind_run
        if live is not None:
            if self.reader.detect_context() == GameContext.IN_BATTLE and live.get("yielded"):
                return ("That battle is still going — fight it with use_move / catch / switch_pokemon / flee_battle first. Calling grind "
                        "again mid-battle only miscounts it. When it is over, call grind again; the session continues.")
            if self.reader.detect_context() != GameContext.IN_BATTLE:
                live["yielded"] = False                        # the encounter we handed over is finished
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
            else:
                futile = self._grind_futile(max(p.level for p in party), target_level)
                if futile:
                    return futile
            run = self._grind_run = {
                "key": key, "balance": balance, "target": target_level, "floor": floor, "catch": bool(catch),
                "start": {p.species_id: p.level for p in party}, "battles": 0, "heals": 0, "ace_fought": 0,
                "lvl": 0, "fit_moves": 0, "stuck": 0, "reloc": 0}
        run["catch"] = bool(catch)
        # A BALANCING session (grind() with no level: train the weakest) plays its boring wild fights itself unless told
        # otherwise — a watched run spent ~30 s and ~60k tokens of LLM turns per L13 Spearow, so the trainees gained about
        # one level in 15 minutes while the ace, fed by the forced trainer fights on the way, ended up twice their level.
        run["auto_left"] = max(0, int(auto_battles)) if auto_battles is not None else (self._GRIND_AUTO_DEFAULT if run["balance"] else 0)
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
            log_once("overworld._forced_replacement", "overworld._forced_replacement: tolerated failure (continuing with a default)")
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
            if foe.level > mine.level + self._GRIND_AUTO_MARGIN or getattr(foe, "is_shiny", False):       # a shiny is never autopiloted: it is caught, not beaten
                return False
            if run["catch"] and self._ball_count() > 0:
                from knowledge.catch_policy import evaluate
                dex = self.reader.read_dex_owned(foe.species_id)
                if evaluate(party, foe.species_id, foe.level, dex_owned=dex, wanted=self._wanted_species(party),
                            stored=self._stored_species()).catch:
                    return False
            return True
        except Exception:
            log_once("overworld._grind_auto_ok", "overworld._grind_auto_ok: tolerated failure (continuing with a default)")
            return False

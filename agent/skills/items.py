"""Field (overworld) item use: Potions / Revives / status cures on a chosen Pokémon and
no-target items like Repel. Mixed into AgentClient; `use_item` dispatches here when you are
not in a battle (the battle version lives in BattleMixin).

Menu automation pattern (see memory menu-automation-pattern): read the live cursor, act toward the
target, and CONFIRM THE OUTCOME (item count dropped / HP rose / status cleared), never a button count.
  Start -> Bag (MenuDriver.open_menu) -> Items pocket (L/R until gBagMenuState.pocket == 0)
  -> move gBagList cursor (0x0203AD04) to the item -> A (context menu, USE is row 0) -> A
  -> [party screen: move gPartyMenu.slotId (0x0203B0A9) to the target -> A] -> text -> close.
"""
from game.constants import Addr, MOVE_NAMES  # noqa: F401  (MOVE_NAMES reserved for TM/HM use)
from game.state import GameContext
from knowledge.bag import CANDY_VITAMINS, STONES
from knowledge.escape import ROPE_ID, why_not
from knowledge.pp_items import ONE_MOVE, PP_ITEMS, pick_move, pick_pp_target
from knowledge.evolutions import EVO_BY_ITEM
from knowledge.shopping import ITEM_NAMES

# Which party condition each item addresses (target auto-pick when none is named).
_HEAL_HP = {13, 22, 21, 20, 19}               # Potion, Super, Hyper, Max Potion, Full Restore
_REVIVE = {24}
_STATUS_CURE = {14: "poisoned", 18: "paralyzed", 17: "asleep", 15: "burned", 16: "frozen", 23: None}
_NO_TARGET = {86, 83, 84, 85}                 # Repels, Escape Rope


class FieldItemMixin:

    def _bag_pocket_open(self, pocket: int = 0) -> bool:
        """Switch the open Bag to `pocket` (0 Items, 1 Key Items, 2 Poké Balls; L/R cycles)."""
        cell = Addr.BAG_MENU_STATE + Addr.BAG_POCKET_OFF
        for _ in range(8):
            cur = self.mgba.read16(cell)
            if cur == pocket:
                return True
            self.mgba.tap("Left" if cur > pocket else "Right")
            self._wait_idle()
            self.mgba.tick(14)
        return self.mgba.read16(cell) == pocket

    def _items_pocket_open(self) -> bool:
        return self._bag_pocket_open(Addr.BAG_POCKET_ITEMS)

    def _bag_cursor_to(self, index: int, pocket: int = 0) -> bool:
        """Move the Bag list to absolute `index` (scroll + cursor; each pocket keeps its own pair)."""
        cur_a, scr_a = Addr.BAG_LIST_CURSOR + 2 * pocket, Addr.BAG_LIST_SCROLL + 2 * pocket
        for _ in range(60):
            cur = self.mgba.read8(cur_a) + self.mgba.read8(scr_a)
            if cur == index:
                return True
            self.mgba.tap("Down" if cur < index else "Up")
            self.mgba.tick(14)
        return (self.mgba.read8(cur_a) + self.mgba.read8(scr_a)) == index

    def _pick_field_target(self, iid: int, party, target: str) -> int | None:
        """0-based party slot to use the item on: the named one, else whoever needs it."""
        if target:
            return self._pick_party(target, party)[0]
        if iid in _HEAL_HP:
            hurt = [(p.current_hp / max(p.max_hp, 1), i) for i, p in enumerate(party)
                    if 0 < p.current_hp < p.max_hp]
            return min(hurt)[1] if hurt else None
        if iid in STONES:
            able = [i for i, p in enumerate(party) if (p.species_id, iid) in EVO_BY_ITEM]
            return able[0] if able else None
        if iid in _REVIVE:
            dead = [i for i, p in enumerate(party) if p.current_hp == 0]
            return dead[0] if dead else None
        if iid in _STATUS_CURE:
            want = _STATUS_CURE[iid]
            sick = [i for i, p in enumerate(party)
                    if p.status not in ("healthy", "", None) and (want is None or p.status == want)]
            return sick[0] if sick else None
        if iid in PP_ITEMS:
            return pick_pp_target(party, iid)           # whoever is shortest of PP (None = nobody)
        return 0

    def _field_heal(self, max_uses: int = 10, below: float = 0.5) -> list[str]:
        """Heal from the Bag when no Pokémon Center can be reached (deep in Victory Road, the Surf gap on Route 23): Revives for the
        fainted, then the smallest Potion that fills the gap for whoever is hurt worst. Returns the item names used (empty = nothing
        usable or nothing needed). Stops once nobody is under `below` of their HP (half by default; the Elite Four's sealed rooms ask for more)."""
        used: list[str] = []
        for _ in range(max_uses):
            party = self.reader.read_party()
            if not party:
                break
            bag = dict(self.reader.read_items_pocket())
            dead = [p for p in party if p.current_hp == 0]
            hurt = [p for p in party if 0 < p.current_hp < below * p.max_hp]
            if dead and bag.get(24):
                item = 24
            elif hurt:
                worst = min(hurt, key=lambda p: p.current_hp / max(p.max_hp, 1))
                gap = worst.max_hp - worst.current_hp
                have = [i for i in (13, 22, 21, 20, 19) if bag.get(i)]
                heal = {13: 20, 22: 50, 21: 200, 20: 999, 19: 999}
                fits = [i for i in have if heal[i] >= gap]
                item = min(fits, key=lambda i: heal[i]) if fits else (max(have, key=lambda i: heal[i]) if have else None)
            else:
                break
            if item is None:
                break
            res = self._field_use_item(ITEM_NAMES[item])
            if not res.startswith("Used"):               # "In a battle…", "Couldn't…", "No …": nothing was used — never count it (a refusal looked like twelve Revives)
                break
            used.append(ITEM_NAMES[item])
        return used

    def _field_cure(self, max_uses: int = 6) -> list[str]:
        """Cure the party's major statuses from the Bag with the cheapest item that does it (Antidote / Burn Heal / Ice Heal / Awakening / Paralyze Heal, then Full Heal — never a Full
        Restore, which is worth more as HP). Returns 'Item on Species' for each use; stops at the first refusal."""
        from knowledge.status_cure import NAMES, cure_ids
        used: list[str] = []
        for _ in range(max_uses):
            party = self.reader.read_party()
            bag = dict(self.reader.read_items_pocket())
            todo = [(i, p, [c for c in cure_ids(p.status, bag) if c != 19]) for i, p in enumerate(party) if p.current_hp > 0]
            todo = [(i, p, ids) for i, p, ids in todo if ids]
            if not todo:
                break
            i, p, ids = todo[0]
            res = self._field_use_item(NAMES[ids[0]], target=str(i + 1))
            if not res.startswith("Used"):
                break
            used.append(f"{NAMES[ids[0]]} on {p.species_name}")
        return used

    def _field_pp(self, max_uses: int = 4) -> list[str]:
        """Spend the Bag's PP items where PP has run out: an Elixir / Max Elixir on whoever is short of 15+ PP in total, an Ether / Max Ether on a Pokémon with a DAMAGING move at 0 PP. Neither is sold
        in a Kanto Mart — they are only found — so they exist to be used before the Elite Four's sealed rooms ("Thunder has no PP left"). Returns 'Item on Species' per use; stops at a refusal."""
        from knowledge.leafgreen_data import MOVE_POWER
        from knowledge.pp_items import move_deficits
        used: list[str] = []
        for _ in range(max_uses):
            party = self.reader.read_party()
            bag = dict(self.reader.read_items_pocket())
            choice = None
            for iid in (37, 36):                                           # the big ones first
                if bag.get(iid):
                    slot = pick_pp_target(party, iid)
                    if slot is not None and sum(move_deficits(party[slot])) >= 15:
                        choice = (iid, slot, "")
                        break
            if choice is None:
                for iid in (35, 34):
                    if not bag.get(iid):
                        continue
                    for slot, p in enumerate(party):
                        empty = [n for n, pp in zip(p.move_names or [], p.pp or []) if n and pp == 0 and MOVE_POWER.get(n, 0) > 0]
                        if p.current_hp > 0 and empty:
                            choice = (iid, slot, empty[0])
                            break
                    if choice:
                        break
            if choice is None:
                break
            iid, slot, move = choice
            res = self._field_use_item(ITEM_NAMES[iid], target=str(slot + 1), move=move)
            if not res.startswith("Used"):
                break
            used.append(f"{ITEM_NAMES[iid]} on {party[slot].species_name}" + (f" ({move})" if move else ""))
        return used

    def _pp_move_cursor_to(self, want: int) -> bool:
        """Move the 'Restore which move?' list's cursor to row `want` (0-3), reading the live cursor (Addr.PP_MOVE_CURSOR) after each press instead of counting presses (blind presses were dropped
        while the list was still opening)."""
        for _ in range(8):
            cur = self.mgba.read8(Addr.PP_MOVE_CURSOR)
            if cur == want:
                return True
            self.mgba.tap("Down" if cur < want else "Up")
            self.mgba.tick(16)
        return self.mgba.read8(Addr.PP_MOVE_CURSOR) == want

    def _field_use_item(self, item: str, target: str = "", move: str = "") -> str:
        ctx = self.reader.detect_context()
        if ctx == GameContext.IN_BATTLE:
            return "In a battle — use the battle version."
        key = item.lower().strip().replace("é", "e")
        name2id = {v.lower().replace("é", "e"): k for k, v in ITEM_NAMES.items()}
        iid = name2id.get(key)
        if iid is None:
            hits = [k for n, k in name2id.items() if key and key in n]
            iid = hits[0] if len(hits) == 1 else None
        if iid is None:
            return f"Don't recognise the item '{item}'. Try e.g. Potion, Revive, Antidote, Repel."
        if iid in (1, 2, 3, 4):
            return "Poké Balls are thrown in battle with catch()."
        pocket = self.reader.read_items_pocket()
        order = [i for i, _ in pocket]
        if iid not in order:
            have = ", ".join(ITEM_NAMES.get(i, f"#{i}") for i in order) or "nothing"
            return f"No {ITEM_NAMES.get(iid, item)} in your Items pocket (you have: {have})."
        if iid == ROPE_ID:
            blocked = why_not("Escape Rope", self.reader.read_current_map())
            if blocked:
                return blocked
        party = self.reader.read_party()
        slot = None
        if iid in CANDY_VITAMINS and not target:
            return (f"Say who gets the {ITEM_NAMES[iid]}: use_item('{ITEM_NAMES[iid]}', target='<species or slot>') — "
                    "it permanently changes that Pokémon, so choose deliberately.")
        if iid in STONES and not target and sum((p.species_id, iid) in EVO_BY_ITEM for p in party) > 1:
            return (f"More than one Pokémon can use the {ITEM_NAMES[iid]} — name one: "
                    f"use_item('{ITEM_NAMES[iid]}', target='<species or slot>').")
        if iid not in _NO_TARGET:
            if target:
                _slot, why = self._pick_party(target, party)
                if _slot is None:
                    return why
            slot = self._pick_field_target(iid, party, target)
            if slot is None:
                return (f"Nobody needs {ITEM_NAMES[iid]} right now"
                        f"{' (' + target + ' is not a valid target)' if target else ''}.")
        qty0 = dict(pocket)[iid]
        before = {i: (p.current_hp, p.status) for i, p in enumerate(party)}

        res = self._menus.open_menu("Bag")
        if "Bag screen open" not in res:
            return f"Couldn't open the Bag ({res})"
        self.mgba.tick(40)
        if not self._items_pocket_open():
            self._menus.close_menus()
            return "Couldn't switch the Bag to the Items pocket."
        if not self._bag_cursor_to(order.index(iid)):
            self._menus.close_menus()
            return f"Couldn't move the Bag cursor to {ITEM_NAMES[iid]}."
        # A -> context menu (USE / GIVE / TOSS / CANCEL), A on USE. Press until the screen changes.
        for _ in range(8):
            self.mgba.tap("A")
            self.mgba.tick(30)
            if self.mgba.read32(Addr.GMAIN_CALLBACK2) == Addr.CB2_PARTY_MENU:
                break                                  # target-picking party screen
            if iid in _NO_TARGET and self.reader.read_items_pocket() != pocket:
                break
        if iid not in _NO_TARGET:
            if self.mgba.read32(Addr.GMAIN_CALLBACK2) != Addr.CB2_PARTY_MENU:
                self._menus.close_menus()
                return f"{ITEM_NAMES[iid]} didn't open the party screen — can't be used here."
            self.mgba.tick(30)
            for _ in range(10):
                cur = self.mgba.read8(Addr.PARTY_FIELD_SLOT)
                if cur == slot:
                    break
                self.mgba.tap("Down" if cur < slot else "Up")
                self.mgba.tick(14)
            if self.mgba.read8(Addr.PARTY_FIELD_SLOT) != slot:
                self._menus.close_menus()
                return "Couldn't move the party cursor to the target."
            if iid in ONE_MOVE:
                # An Ether asks "Restore which move?" with a small list over the party menu (the callback stays the party menu's; ItemUseCB_TryRestorePP): A picks the Pokémon, the
                # list opens with the cursor on move 1; read the live cursor to the wanted move, then A.
                self.mgba.tap("A")
                self.mgba.tick(40)
                self._pp_move_cursor_to(pick_move(party[slot], move))
                self.mgba.tap("A")
                self.mgba.tick(40)
            for _ in range(6):                          # A until the item is consumed
                if dict(self.reader.read_items_pocket()).get(iid, 0) < qty0:
                    break
                self.mgba.tap("A")
                self.mgba.tick(40)
        # Advance the result text, then back out to the field. A stone starts an EVOLUTION scene (B would cancel it:
        # drive it with A) and a Rare Candy / vitamin prints level-up and stat boxes (B dismisses them).
        for _ in range(6 if iid in STONES or iid in CANDY_VITAMINS else 4):
            self.mgba.tick(30)
            if self._in_evolution_scene():
                self._finish_evolution()
                self._settle_evolution()
                continue
            self.mgba.tap("B")
        self._menus.close_menus()
        qty1 = dict(self.reader.read_items_pocket()).get(iid, 0)
        after = self.reader.read_party()
        name = ITEM_NAMES[iid]
        if qty1 >= qty0:
            return (f"{name} had no effect (nothing consumed) — e.g. HP already full or the "
                    f"wrong target. Check read_game_state.")
        if iid == ROPE_ID:
            from knowledge.navigation import MAP_NAMES
            self._advance_to_control(tries=20)
            now = self.reader.read_current_map()
            return f"Used {name} ({qty1} left): now in {MAP_NAMES.get(tuple(now), now)}."
        if slot is None:
            return f"Used {name} ({qty1} left)."
        p = after[slot] if slot < len(after) else None
        who = (p.species_name if p else "Pokémon") or "Pokémon"
        if iid in STONES:
            now = next((q for q in after if q.personality == party[slot].personality), p)
            if now is not None and now.species_id != party[slot].species_id:
                return f"Used {name}: {party[slot].species_name} evolved into {now.species_name}! ({qty1} left)"
            return f"Used {name} on {party[slot].species_name} but it didn't evolve (the evolution may have been cancelled)."
        if iid in CANDY_VITAMINS:
            now = next((q for q in after if q.personality == party[slot].personality), p)
            if now is not None and now.level != party[slot].level:
                return f"Used {name} on {now.species_name}: L{party[slot].level}→L{now.level} ({qty1} left)."
            return f"Used {name} on {who} ({qty1} left)."
        hp0, st0 = before[slot]
        if p is not None and p.current_hp != hp0:
            return f"Used {name} on {who}: HP {hp0}->{p.current_hp}/{p.max_hp} ({qty1} left)."
        if p is not None and p.status != st0:
            return f"Used {name} on {who}: {st0} -> {p.status} ({qty1} left)."
        return f"Used {name} on {who} ({qty1} left)."

    # ── held items ───────────────────────────────────────────────────────────────────────
    def _give_item(self, item: str, pokemon: str) -> str:
        """Bag → Items pocket → the item → GIVE → the Pokémon. The Items pocket's menu is always [USE, GIVE, TOSS, CANCEL], so
        GIVE is one Down from the default. Confirmed by the Pokémon's held item changing (a held item already there is swapped
        out and returns to the bag, after the game's own 'make it hold X instead?' prompt)."""
        from knowledge.held_items import HELD_ITEMS, describe
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "give_item works from the overworld (not in battle or a menu)."
        key = str(item).lower().strip().replace("é", "e")
        names = {iid: v[0].lower().replace("é", "e") for iid, v in HELD_ITEMS.items()}
        hits = [iid for iid, n in names.items() if key == n] or [iid for iid, n in names.items() if key and key in n]
        if len(hits) != 1:
            return (f"Which item? '{item}' matches " + (", ".join(HELD_ITEMS[i][0] for i in hits) if hits else "no holdable item")
                    + " — a held item is something like Leftovers, Exp. Share, Quick Claw or a type-boost item (berries aren't supported).")
        iid = hits[0]
        party = self.reader.read_party()
        holder = next((p for p in party if p.held_item == iid), None)
        pocket = self.reader.read_items_pocket()
        order = [i for i, _ in pocket]
        if iid not in order:
            return (f"{holder.nickname or holder.species_name} is already holding the {HELD_ITEMS[iid][0]}." if holder
                    else f"No {HELD_ITEMS[iid][0]} in your Items pocket.")
        slot, err = self._pick_party(pokemon, party) if pokemon else (None, "")
        if slot is None and err:
            return err
        if slot is None:
            from knowledge.held_items import holder_for
            who = holder_for(iid, party)
            return (f"Give it to whom? give_item('{HELD_ITEMS[iid][0]}', '<species or slot>')"
                    + (f" — suggestion: {who.nickname or who.species_name}." if who else "."))
        mon = party[slot]
        if mon.held_item == iid:
            return f"{mon.nickname or mon.species_name} is already holding the {HELD_ITEMS[iid][0]}."
        res = self._menus.open_menu("Bag")
        if "Bag screen open" not in res:
            return f"Couldn't open the Bag ({res})"
        self.mgba.tick(40)
        if not self._items_pocket_open() or not self._bag_cursor_to(order.index(iid)):
            self._menus.close_menus()
            return f"Couldn't select {HELD_ITEMS[iid][0]} in the Bag."
        self.mgba.tap("A")                                  # context menu: USE / GIVE / TOSS / CANCEL
        self.mgba.tick(30)
        self.mgba.tap("Down")
        self.mgba.tick(14)
        for _ in range(8):                                  # GIVE → the party screen in give mode
            self.mgba.tap("A")
            self.mgba.tick(40)
            if self.mgba.read32(Addr.GMAIN_CALLBACK2) == Addr.CB2_PARTY_MENU:
                break
        if self.mgba.read32(Addr.GMAIN_CALLBACK2) != Addr.CB2_PARTY_MENU:
            self._menus.close_menus()
            return f"The {HELD_ITEMS[iid][0]} can't be given right now (the party screen didn't open)."
        self.mgba.tick(30)
        for _ in range(10):
            cur = self.mgba.read8(Addr.PARTY_FIELD_SLOT)
            if cur == slot:
                break
            self.mgba.tap("Down" if cur < slot else "Up")
            self.mgba.tick(14)
        if self.mgba.read8(Addr.PARTY_FIELD_SLOT) != slot:
            self._menus.close_menus()
            return "Couldn't move the party cursor to the target."
        for _ in range(8):
            self.mgba.tap("A")
            self.mgba.tick(40)
            if self._menus.choice_live():                    # 'already holding X — make it hold Y instead?'
                self._menus.answer_prompt("yes")
                self.mgba.tick(40)
            now = next((p for p in self.reader.read_party() if p.personality == mon.personality), None)
            if now is not None and now.held_item == iid:
                break
        for _ in range(4):
            self.mgba.tick(30)
            self.mgba.tap("B")
        self._menus.close_menus()
        now = next((p for p in self.reader.read_party() if p.personality == mon.personality), None)
        who = mon.nickname or mon.species_name
        if now is None or now.held_item != iid:
            return f"Couldn't give the {HELD_ITEMS[iid][0]} to {who} — check read_game_state."
        swapped = f" (its {HELD_ITEMS[mon.held_item][0]} went back to the Bag)" if mon.held_item in HELD_ITEMS else ""
        return f"{who} now holds {describe(iid)}{swapped}."


    # ── the adaptive Exp. Share ──────────────────────────────────────────────
    def _take_item(self, pokemon: str) -> str:
        """Start → POKéMON → the Pokémon → ITEM → TAKE: its held item goes back to the Bag. The Pokémon's sub-menu is [SUMMARY, <field moves>, SWITCH, ITEM, CANCEL], so ITEM sits at
        2 + (field moves); the ITEM sub-menu is [GIVE, TAKE, CANCEL]. Verified by the held item clearing."""
        from knowledge.held_items import describe
        from agent.skills.hm import _FIELD_MOVE_IDS
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "take works from the overworld (not in battle or a menu)."
        party = self.reader.read_party()
        slot, err = self._pick_party(str(pokemon), party)
        if slot is None:
            return err
        mon = party[slot]
        who = mon.nickname or mon.species_name
        if not mon.held_item:
            return f"{who} isn't holding anything."
        item = mon.held_item
        res = self._menus.open_menu("Pokemon")
        if "screen open" not in res:
            return f"Couldn't open the party screen ({res})."
        self.mgba.tick(40)
        try:
            if not self._party_cursor_to(slot):
                return "Couldn't move the party cursor to the Pokémon."
            self.mgba.tap("A")
            self.mgba.tick(50)
            idx = 2 + sum(1 for m in (mon.move_ids or []) if m in _FIELD_MOVE_IDS)
            if not self._menu_cursor_to(idx):
                return "Couldn't reach ITEM in the Pokémon's menu."
            self.mgba.tap("A")
            self.mgba.tick(40)
            if not self._menu_cursor_to(1):                          # GIVE, TAKE, CANCEL
                return "Couldn't reach TAKE in the item menu."
            self.mgba.tap("A")
            for _ in range(10):                                      # "Received the X from Y." — advance until the party struct shows it
                self.mgba.tick(30)
                now = next((p for p in self.reader.read_party() if p.personality == mon.personality), None)
                if now is not None and now.held_item == 0:
                    break
                self.mgba.tap("A")
        finally:
            for _ in range(4):
                self.mgba.tick(20)
                self.mgba.tap("B")
            self._menus.close_menus()
        now = next((p for p in self.reader.read_party() if p.personality == mon.personality), None)
        if now is None or now.held_item:
            return f"Couldn't take the {describe(item)} from {who} — check read_game_state."
        return f"Took the {describe(item)} back from {who}."

    def _menu_cursor_to(self, index: int) -> bool:
        for _ in range(12):
            cur = self.mgba.read8(Addr.MENU_CURSOR)
            if cur == index:
                return True
            self.mgba.tap("Down" if cur < index else "Up")
            self.mgba.tick(14)
        return self.mgba.read8(Addr.MENU_CURSOR) == index

    def _maintain_exp_share(self) -> str | None:
        """Keep the Exp. Share on the LOWEST-level Pokémon of the party (adaptive: when levels change it moves). Cheap when nothing is needed (a party and Bag read); called once per overworld tick.
        Returns a note when it moved the item, else None. A move that keeps failing for the same pair is dropped until the party changes."""
        from knowledge.held_items import EXP_SHARE, exp_share_plan
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return None
        party = self.reader.read_party()
        owns = any(i == EXP_SHARE and q > 0 for i, q in self.reader.read_items_pocket())
        plan = exp_share_plan(party, owns)
        if plan is None:
            return None
        holder, target = plan
        sig = (holder.personality if holder else 0, target.personality, tuple(p.level for p in party))
        fails = self._exp_share_fails
        if fails.get(sig, 0) >= 2:
            return None
        who = target.nickname or target.species_name
        out = ""
        if holder is not None:
            out = self._take_item(holder.nickname or holder.species_name)
            if "Took" not in out:
                fails[sig] = fails.get(sig, 0) + 1
                return f"Exp. Share: {out}"
        out = self._give_item("Exp. Share", who)
        if "now holds" not in out:
            fails[sig] = fails.get(sig, 0) + 1
            return f"Exp. Share: {out}"
        return f"Exp. Share → {who} L{target.level}" + (f" (from {holder.nickname or holder.species_name} L{holder.level})" if holder else "") + " — the lowest level holds it"

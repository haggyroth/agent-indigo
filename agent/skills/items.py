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
        idle = getattr(self.mgba, "wait_until_idle", None)
        cell = Addr.BAG_MENU_STATE + Addr.BAG_POCKET_OFF
        for _ in range(8):
            cur = self.mgba.read16(cell)
            if cur == pocket:
                return True
            self.mgba.tap("Left" if cur > pocket else "Right")
            if idle:
                idle()
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
            return self._resolve_party_target(target, party)
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
        return 0

    def _field_use_item(self, item: str, target: str = "") -> str:
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
            for _ in range(6):                          # A until the item is consumed
                self.mgba.tap("A")
                self.mgba.tick(40)
                if dict(self.reader.read_items_pocket()).get(iid, 0) < qty0:
                    break
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
        slot = self._resolve_party_target(pokemon, party) if pokemon else None
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

"""shop(sell=true): sell treasure (or one named item) at a Poké Mart — the missing half of the Mart driver.

Live-verified flow: talk to the clerk → BUY / SELL / QUIT → Down + A opens the BAG (gMain.callback2 = BAG_CB2) in shop mode → the Items list is driven with
the same cursor variables as use_item (`_bag_cursor_to`) → A on an item opens "How many would you like to sell?" (quantity 1) → A → "I can pay ¥X. Would
that be OK?" (YES is the default) → A → the sale text. So ONE sale is just A, A, A, and the count of that item drops by one; the loop presses A until the
count reaches the target and stops the moment it does (a spare A would select the item again and sell another)."""


class SellMixin:
    def _sell_list_live(self) -> bool:
        """The bag's item list is taking D-pad input (not a text box / quantity box): a Down or Up nudge moves the list position. Undoes the nudge."""
        from game.constants import Addr

        def pos():
            return self.mgba.read8(Addr.BAG_LIST_CURSOR) + self.mgba.read8(Addr.BAG_LIST_SCROLL)
        p0 = pos()
        for go, back in (("Down", "Up"), ("Up", "Down")):
            self.mgba.tap(go)
            self.mgba.tick(10)
            if pos() != p0:
                self.mgba.tap(back)
                self.mgba.tick(10)
                return True
        return False

    def _pocket_total(self, iid: int) -> int:
        """How many of `iid` the Items pocket holds, over ALL its stacks (read_bag keeps only the last stack of an id)."""
        return sum(q for i, q in self.reader.read_items_pocket() if i == iid)

    def _sell_one_item(self, iid: int, qty: int) -> int:
        """Sell `qty` of item `iid` from the open sell bag, ONE unit at a time; returns how many were actually sold.
        Each unit re-reads the pocket and re-aims the cursor at the item first: when a stack empties the list shifts up, and a spare A at the old
        row would sell the NEXT item (a live run sold an Awakening and a Burn Heal beside a Nugget that way)."""
        sold = 0
        for _ in range(qty):
            pocket = [i for i, _q in self.reader.read_items_pocket()]
            if iid not in pocket or not self._bag_cursor_to(pocket.index(iid)):
                break
            before = self._pocket_total(iid)
            for _ in range(10):                   # A, A, A: select → quantity 1 → YES; stop the moment the count drops
                self.mgba.tap("A")
                self._wait_idle()
                self.mgba.tick(14)
                if self._pocket_total(iid) < before:
                    break
            else:
                break                             # the clerk refused (or the menu is not taking input)
            sold += before - self._pocket_total(iid)
            for _ in range(12):                   # the "Turned over …" text: A dismisses it; never press A once the list is live (that re-selects the row)
                if self._sell_list_live():
                    break
                self.mgba.tap("A")
                self._wait_idle()
                self.mgba.tick(14)
        return sold

    def _sell(self, item: str = "", quantity: int = 1) -> str:
        from agent import events
        from knowledge.map_graph import MAP_KIND
        from knowledge.selling import TREASURE, sell_plan
        from knowledge.shopping import item_label
        bag = dict(self.reader.read_bag())
        for iid in {i for i, _q in self.reader.read_items_pocket()}:          # read_bag keeps only the LAST stack of an id: add them all up
            bag[iid] = self._pocket_total(iid)
        plan, msg = sell_plan(bag, item, quantity)
        if not plan:
            return msg
        if MAP_KIND.get(self.reader.read_current_map()) != "mart":
            res = self._go_to("Mart")
            if MAP_KIND.get(self.reader.read_current_map()) != "mart":
                return f"On the way to a Mart to sell: {res}"
        approach, face = None, "Up"
        cur = tuple(self.reader.read_current_map())
        from knowledge.shop_stock import SHOPS
        clerks = [(x, y) for b, m, x, y, _items in SHOPS if (b, m) == cur]
        if clerks and (2, 3) not in clerks:             # a multi-clerk store: stand at the nearest clerk's counter
            spot = self._clerk_approach(clerks[0])
            if spot is not None:
                approach, face = spot
        money0 = self.reader.read_money()
        if not self._open_buy_menu(approach, face, sell=True):
            self._close_buy_menu()
            return "Couldn't open the Mart's SELL menu — walk up to the clerk, choose SELL and call shop(sell=true) again."
        sold, skipped = [], []
        for iid, qty in plan:
            got = self._sell_one_item(iid, qty)
            label = TREASURE[iid][0] if iid in TREASURE else item_label(iid)
            (sold if got > 0 else skipped).append(f"{got or qty}× {label}")
        self._close_buy_menu()
        gained = self.reader.read_money() - money0
        if not sold:
            return f"Couldn't sell {', '.join(skipped)} (the clerk wouldn't buy it, or the menu never took the input)."
        events.emit("shop", f"sold {', '.join(sold)} (+¥{gained}, ¥{self.reader.read_money()} now)")
        tail = f" Couldn't sell: {', '.join(skipped)}." if skipped else ""
        return f"Sold {', '.join(sold)} for ¥{gained}. Money: ¥{self.reader.read_money()}.{tail}"

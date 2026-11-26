"""The Celadon Game Corner: coins from the coin clerk, prizes from the Prize Corner clerks, and the slot machines.

Everything the clerks list and charge comes from the decomp (`knowledge.game_corner`). The clerks run scripts with a multichoice
menu: talk across the counter, advance the greeting until the list is live, move its cursor to the row, press A, answer the
confirmation, then CONFIRM by the numbers that must have changed (coins, the bag / TM case / party)."""
from game.state import GameContext

from knowledge.game_corner import MAX_COINS, MAX_SLOT_LOSS, SPIN_BET, lots_for, prize_plan
from knowledge.game_corner_data import COIN_CASE, COIN_CLERK, COIN_LOTS, GAME_CORNER, PRIZE_ROOM
from knowledge.shopping import approach_options


class GameCornerMixin:
    # ── clerks ───────────────────────────────────────────────────────────────────────────────────
    def _clerk_spot(self, clerk: tuple):
        """((x, y), facing) of the best tile to talk to `clerk` from — beside them, or across their counter."""
        self.tilemap.refresh()
        grid, w, h = self.tilemap.passable_grid()
        floor = (lambda x, y: bool(grid and 0 <= x < w and 0 <= y < h and grid[y][x]))
        px, py = self.reader.read_player_pos()
        seen, todo = {(px, py)}, [(px, py)]
        while todo:
            x, y = todo.pop()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) not in seen and floor(nx, ny):
                    seen.add((nx, ny))
                    todo.append((nx, ny))
        spots = approach_options(clerk, floor, lambda x, y: (x, y) in seen)
        return min(spots, key=lambda s: abs(s[0][0] - px) + abs(s[0][1] - py)) if spots else None

    def _go_to_map_tuple(self, target: tuple, name: str, call: str) -> str | None:
        """Travel to the interior `name`; None on arrival, else the message to hand back."""
        for _ in range(8):
            if tuple(self.reader.read_current_map()) == target:
                return None
            out = self._go_to(name, mode="yield", resume_call=call)
            if tuple(self.reader.read_current_map()) == target:
                return None
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if "Can't get to" in out or "No route" in out:
                return f"Can't reach {name}: {out}"
        return f"Didn't reach {name} yet — call {call} again to continue (it resumes)."

    def _open_clerk_menu(self, clerk: tuple) -> bool:
        """Walk to `clerk`, face them and press A until their multichoice list is live."""
        spot = self._clerk_spot(clerk)
        if spot is None:
            return False
        (ax, ay), face = spot
        for _ in range(4):
            self._walk_to(ax, ay)
            if self.reader.read_player_pos() == (ax, ay):
                break
        if self.reader.read_player_pos() != (ax, ay):
            return False
        self.mgba.tap(face)
        self.mgba.tick(8)
        self.mgba.tap("A")
        for _ in range(16):
            # The list fades in a moment after the greeting ends and ignores the D-pad until then, so probe twice before the next
            # A: an A pressed on the live list would pick the highlighted row.
            for _wait in range(3):
                self.mgba.tick(30)
                if self._menus.choice_live():
                    return True
            self.mgba.tap("A")
        return False

    def _menu_pick(self, index: int) -> bool:
        """Put the open list's cursor on row `index` and press A."""
        for _ in range(index + 8):
            cur = self._menus.menu_cursor()
            if cur == index:
                break
            self.mgba.tap("Down" if cur < index else "Up")
            self.mgba.tick(12)
        if self._menus.menu_cursor() != index:
            return False
        self.mgba.tap("A")
        self.mgba.tick(40)
        return True

    def _leave_clerk(self) -> None:
        """Dismiss the clerk's closing text with B — never A: on the free field A would just talk to the clerk again (and buy again).
        The script flickers between OVERWORLD and TRANSITIONING while it ends, so require a few quiet ticks in a row."""
        calm = 0
        for _ in range(30):
            calm = calm + 1 if self.reader.detect_context() == GameContext.OVERWORLD else 0
            if calm >= 3:
                return
            self.mgba.tap("B")
            self.mgba.tick(20)

    # ── status / coins ───────────────────────────────────────────────────────────────────────────
    def _has_coin_case(self) -> bool:
        return bool(self.reader.read_flag(COIN_CASE[1]))

    def _coin_status(self) -> str:
        coins, yen = self.reader.read_coins(), self.reader.read_money()
        if not self._has_coin_case():
            return ("No Coin Case yet: a man in the Celadon Restaurant gives it to you for free. Without it the slot machines and the "
                    "coin and prize clerks refuse you.")
        return (f"Coins: {coins}/{MAX_COINS}, money ¥{yen}. Coins cost ¥{COIN_LOTS[0][1]} per {COIN_LOTS[0][0]} (¥20 each). "
                "game_corner('slots') plays the machines; shop(item='TM24') (or 'Abra', 'Smoke Ball'…) spends coins at the Prize Corner."
                + (("\n" + table) if (table := self._prize_table(coins)) else ""))

    def _prize_table(self, coins: int) -> str:
        """The prizes with their price in coins, in slot time and what they are for — information; buying is always the model's call."""
        try:
            from knowledge.game_corner import prize_lines, SPIN_NET_COINS, SPIN_FRAMES
            party = [(p.species_id, p.nickname or p.species_name) for p in self.reader.read_party()]
            lines = prize_lines(coins, self.reader.read_dex_owned, party)
            return (f"Prize Corner (the slot driver wins about {SPIN_NET_COINS} coins a spin, ~{SPIN_FRAMES} frames each; buying coins is ¥20 apiece):\n" + "\n".join(lines))
        except Exception:
            return ""

    def _buy_coins(self, coins: int, call: str = "game_corner('buy_coins')") -> str:
        if not self._has_coin_case():
            return self._coin_status()
        have = self.reader.read_coins()
        want = max(1, int(coins))
        got, cost = lots_for(want)
        if have + got > MAX_COINS:
            return f"The Coin Case holds {MAX_COINS} coins and you have {have}."
        if self.reader.read_money() < cost:
            return f"{got} coins cost ¥{cost} and you have ¥{self.reader.read_money()}."
        if (msg := self._go_to_map_tuple(GAME_CORNER, "Celadon Game Corner", call)):
            return msg
        bought = 0
        for lot_coins, lot_yen in sorted(COIN_LOTS, key=lambda l: -l[0]):
            while bought + lot_coins <= got and (got - bought) >= lot_coins:
                before = self.reader.read_coins()
                if not self._open_clerk_menu(COIN_CLERK):
                    self._leave_clerk()
                    return f"Couldn't open the coin clerk's menu (bought {bought} so far) — {call} again."
                if not self._menu_pick(next(i for i, l in enumerate(COIN_LOTS) if l[0] == lot_coins)):
                    self._leave_clerk()
                    return "Couldn't pick the coin lot."
                self._leave_clerk()
                gained = self.reader.read_coins() - before
                if gained <= 0:
                    self._leave_clerk()
                    return f"The clerk didn't sell coins (bought {bought} so far; ¥{self.reader.read_money()} left)."
                bought += gained
        self._leave_clerk()
        from agent import events
        events.emit("shop", f"bought {bought} coins (¥{cost})")
        return f"Bought {bought} coins for ¥{cost}. Coins: {self.reader.read_coins()}, money ¥{self.reader.read_money()}."

    # ── prizes ───────────────────────────────────────────────────────────────────────────────────
    def _buy_prize(self, prize, auto_coins: bool = False) -> str:
        """Exchange coins for `prize` at its Prize Corner clerk (shop(item=…) lands here)."""
        call = f"shop(item={prize.name!r})"
        if not self._has_coin_case():
            return self._coin_status()
        coins, yen = self.reader.read_coins(), self.reader.read_money()
        if coins < prize.coins:
            return prize_plan(prize, coins, yen) + " game_corner('buy_coins', amount) buys coins; game_corner('slots') wins them."
        if (msg := self._go_to_map_tuple(PRIZE_ROOM, "Celadon Prize Corner", call)):
            return msg
        before_item = self.reader.count_item(prize.id) if prize.kind != "mon" else 0
        before_party = len(self.reader.read_party())
        if not self._open_clerk_menu(prize.clerk):
            self._leave_clerk()
            return f"Couldn't open the prize menu — face the clerk at {prize.clerk} and call {call} again."
        if not self._menu_pick(prize.index):
            self._leave_clerk()
            return f"Couldn't pick {prize.name} in the prize menu."
        for _ in range(8):                               # 'You want X?' YES/NO
            if self._menus.choice_live():
                self._menus.answer_prompt("yes")
                break
            self.mgba.tap("A")
            self.mgba.tick(30)
        for _ in range(12):                              # the clerk takes the coins, then the hand-over text
            self.mgba.tick(40)
            if self.reader.read_coins() < coins:
                break
            self.mgba.tap("B")
        if prize.kind == "mon":
            for _ in range(8):
                self.mgba.tick(40)
                if self._menus.choice_live():
                    self._menus.answer_prompt("no")      # 'Give it a nickname?' — the model nicknames wild catches, not prizes
                    break
                self.mgba.tap("B")
        self._leave_clerk()
        spent = coins - self.reader.read_coins()
        if spent <= 0:
            return f"The exchange for {prize.name} didn't go through (coins unchanged at {self.reader.read_coins()})."
        from agent import events
        events.emit("shop", f"won {prize.name} for {spent} coins ({self.reader.read_coins()} left)")
        if prize.kind == "mon":
            where = "in your party" if len(self.reader.read_party()) > before_party else "in the PC"
            return f"Exchanged {spent} coins for {prize.name} (L{prize.level}) — it is {where}. Coins left: {self.reader.read_coins()}."
        got = self.reader.count_item(prize.id) - before_item
        extra = " Teach it with teach_move." if prize.kind == "tm" else ""
        return f"Exchanged {spent} coins for {prize.name} (+{got}).{extra} Coins left: {self.reader.read_coins()}."

    # ── the tool ─────────────────────────────────────────────────────────────────────────────────
    def _game_corner(self, action: str = "status", amount: int = 0) -> str:
        action = str(action or "status").lower().strip()
        if action in ("status", "coins"):
            return self._coin_status()
        if action in ("buy_coins", "buy"):
            if int(amount or 0) <= 0:
                return "game_corner('buy_coins', amount): how many coins? " + self._coin_status()
            return self._buy_coins(int(amount))
        if action in ("slots", "play"):
            return self._play_slots(int(amount or 0))
        return "game_corner(action) is one of: status, buy_coins (amount = coins), slots (amount = spins)."

    # ── slot machines ────────────────────────────────────────────────────────────────────────────
    # Layout of SlotMachineState (src/slot_machine.c) relative to the address of reelIsSpinning[0]:
    #   -16 machineIdx u16, -14 currentReel u16, -12 machineBias u16, -10 slotRewardClass u16, -8 biasCooldown u16, -6 bet u16,
    #    +0 reelIsSpinning[3] u32, +12 reelPositions[3] s16, +18 reelSubpixel[3] s16, +24 destReelPos[3] s16
    SLOT_PRESS_LATENCY = 1               # frames between choosing to press A and the game acting on it (tuned live)

    def _slot_read(self, spin_addr: int) -> dict:
        import struct
        raw = self.mgba.read_range(spin_addr - 16, 16 + 12 + 6 * 3)
        idx, cur, bias, _cls, _cool, bet = struct.unpack_from("<6H", raw, 0)
        spinning = struct.unpack_from("<3I", raw, 16)
        pos = list(struct.unpack_from("<3h", raw, 28))
        sub = list(struct.unpack_from("<3h", raw, 34))
        return {"machine": idx, "reel": cur, "bias": bias, "bet": bet, "spinning": [bool(x) for x in spinning],
                "pos": pos, "sub": sub}

    def _slot_state_addr(self) -> int | None:
        """Find reelIsSpinning[0] of the live SlotMachineState: three u32 1s followed by plausible positions / sub-pixels
        (only valid while the reels turn). The block lives in the heap and does not move during a session."""
        import struct
        raw = self.mgba.read_range(0x02000000, 0x40000)
        needle = b"\x01\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00"
        i = raw.find(needle)
        while i != -1:
            if i % 2 == 0 and 16 <= i and i + 24 <= len(raw):
                pos = struct.unpack_from("<3h", raw, i + 12)
                sub = struct.unpack_from("<3h", raw, i + 18)
                idx, cur, bias, cls, _cool, bet = struct.unpack_from("<6H", raw, i - 16)
                if (all(0 <= p < 21 for p in pos) and all(0 <= s <= 2 for s in sub) and idx < 6 and cur < 3 and bias <= 6
                        and cls <= 6 and 1 <= bet <= 3):
                    return 0x02000000 + i
            i = raw.find(needle, i + 1)
        return None

    def _sit_at_slot_machine(self) -> str | None:
        """Walk to a working machine, say YES to 'want to play?' and wait for the slot screen. None when seated, else why not."""
        from game.constants import Addr
        from knowledge.game_corner_data import SLOT_MACHINES
        usable = [(x, y) for x, y, name in SLOT_MACHINES if not name.startswith("Unusable")]
        px, py = self.reader.read_player_pos()
        for machine in sorted(usable, key=lambda m: abs(m[0] - px) + abs(m[1] - py)):
            spot = self._clerk_spot(machine)
            if spot is None:
                continue
            (ax, ay), face = spot
            for _ in range(3):
                self._walk_to(ax, ay)
                if self.reader.read_player_pos() == (ax, ay):
                    break
            if self.reader.read_player_pos() != (ax, ay):
                continue
            self.mgba.tap(face)
            self.mgba.tick(8)
            self.mgba.tap("A")
            for _ in range(10):
                self.mgba.tick(40)
                if self._menus.choice_live():
                    self._menus.answer_prompt("yes")
                    break
            for _ in range(30):
                self.mgba.tick(30)
                if self.mgba.read32(Addr.GMAIN_CALLBACK2) == Addr.CB2_SLOT_MACHINE:
                    self.mgba.tick(240)                    # the screen fades in before it takes input
                    return None
            self._leave_clerk()
        return "Couldn't sit down at a working slot machine."

    def _slot_exit(self) -> None:
        from game.constants import Addr
        for _ in range(8):
            if self.mgba.read32(Addr.GMAIN_CALLBACK2) != Addr.CB2_SLOT_MACHINE:
                break
            self.mgba.hold("B", 6)
            self.mgba.tick(40)
            if self._menus.choice_live():                 # 'Quit playing?'
                self._menus.answer_prompt("yes")
            self.mgba.tick(60)
        self._leave_clerk()

    def _slot_spin(self, addr: int | None):
        """One full-bet spin: bet 3, stop each reel on a frame that serves the machine's bias, wait out the payout.
        Returns (state address, coins won or lost, bias, jackpot?)."""
        from knowledge.slots import SEVEN, frames_until_good
        start = self.reader.read_coins()
        for _ in range(3):                                # DOWN bets one coin; the third bet starts the reels by itself
            before = self.reader.read_coins()
            for _try in range(80):                         # presses are ignored while the last spin's result is still on screen
                self.mgba.hold("Down", 4)
                self.mgba.tick(14)
                if self.reader.read_coins() < before:
                    break
                self.mgba.tick(14)
            self.mgba.tick(20)                             # the bet's own animation (a second Down inside it is dropped)
        for _ in range(25):                                # the cached address must still hold a live, spinning machine
            st = self._slot_read(addr) if addr else None
            if st and any(st["spinning"]) and st["bet"] == 3:
                break
            addr = self._slot_state_addr()
            self.mgba.tick(4)
        if addr is None:
            return None, 0, 0, False
        st = self._slot_read(addr)
        bias = st["bias"]
        for stage in range(3):
            for _ in range(200):                           # wait until it is this reel's turn
                st = self._slot_read(addr)
                if st["reel"] == stage and st["spinning"][stage]:
                    break
                self.mgba.tick(2)
            wait = frames_until_good(stage, st["pos"], st["sub"], st["spinning"], bias)
            wait = max(0, (wait or 0) - self.SLOT_PRESS_LATENCY)
            if wait:
                self.mgba.tick(wait)
            before = (list(st["pos"]), list(st["sub"]))
            self.mgba.hold("A", 4)
            for _ in range(120):                           # the reel slides to its stop
                self.mgba.tick(3)
                if not self._slot_read(addr)["spinning"][stage]:
                    break
            if self._slot_trace is not None:
                self._slot_trace.append({"stage": stage, "bias": bias, "wanted": wait, "state": before,
                                         "landed": self._slot_read(addr)["pos"][stage]})
        # The win animation counts the coins in a while after the reels stop. The payout is known from where they stopped, so wait for
        # exactly that many coins (or, for a loss, until the machine is back to taking bets).
        from knowledge.slots import REEL_ICONS, payout_of
        fin = self._slot_read(addr)
        grid = [REEL_ICONS[r][(fin["pos"][r] + 1 + k) % 21] for r in range(3) for k in range(3)]
        expected = payout_of(grid)
        target = start - SPIN_BET + expected
        for _ in range(900):
            self.mgba.tick(6)
            st = self._slot_read(addr)
            if self.reader.read_coins() >= target and st["bet"] == 0 and not any(st["spinning"]):
                break
        last = self.reader.read_coins()
        won = last - start
        return addr, won, bias, bias == SEVEN and won > 0

    def _play_slots(self, spins: int) -> str:
        from agent import events
        from game.constants import Addr
        if not self._has_coin_case():
            return self._coin_status()
        spins = max(1, min(int(spins or 10), 200))
        if self.reader.read_coins() < SPIN_BET:
            return f"A spin costs {SPIN_BET} coins and you have {self.reader.read_coins()}. game_corner('buy_coins', 50) first."
        if tuple(self.reader.read_current_map()) != GAME_CORNER:
            if (msg := self._go_to_map_tuple(GAME_CORNER, "Celadon Game Corner", f"game_corner('slots', {spins})")):
                return msg
        if self.mgba.read32(Addr.GMAIN_CALLBACK2) != Addr.CB2_SLOT_MACHINE and (why := self._sit_at_slot_machine()):
            return why
        start, addr, played, jackpots, best = self.reader.read_coins(), None, 0, 0, 0
        for _ in range(spins):
            if self.reader.read_coins() < SPIN_BET or start - self.reader.read_coins() > MAX_SLOT_LOSS:
                break
            addr, delta, _bias, jackpot = self._slot_spin(addr)
            if addr is None:
                break
            played += 1
            jackpots += bool(jackpot)
            best = max(best, delta)
        self._slot_exit()
        net = self.reader.read_coins() - start
        events.emit("shop", f"slots: {played} spins, {net:+d} coins ({self.reader.read_coins()} now)")
        why = ("" if played >= spins else " Stopped early: " + ("out of coins." if self.reader.read_coins() < SPIN_BET else
                                                              f"the stop-loss ({MAX_SLOT_LOSS} coins) was reached." if start - self.reader.read_coins() > MAX_SLOT_LOSS
                                                              else "the machine state could not be read."))
        return (f"Played {played} spins at {SPIN_BET} coins: {net:+d} coins (now {self.reader.read_coins()}); biggest win {best}"
                f"{f', {jackpots} jackpot(s)' if jackpots else ''}.{why}")

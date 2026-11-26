"""quest('rematch'): the VS Seeker loop — charge it, use it, fight every trainer it flags on this map (#367).

A driver, never an automatic one: the model asks for it. Walking (to charge the battery, then up to each trainer) and the item use are deterministic; every BATTLE is handed back to the model — the
call ends, `quest('rematch')` again resumes (the game's own rematch table says who is still waiting). The mechanics are the decomp's (src/vs_seeker.c): the item charges one step at a time while
it is in the bag (100 steps, read from SaveBlock1); a use makes every beaten trainer in range ready with a 70 % chance each, and the flagged ones are withdrawn after 100 more steps or on leaving
the map — so the driver goes straight to the trainers it finds. It stops on a hurt lead instead of walking into the next fight."""
from game.state import GameContext

VS_SEEKER = 362                  # the key item
REMATCH_FIGHTS = 6               # trainers walked up to per call: bounded, resumable
CHARGE_STEPS = 140               # most steps walked per call to charge the battery
LOW_HP = 0.45


class RematchMixin:
    def _rematch(self, arg: str = "") -> str:
        from knowledge import rematches
        call = "quest('rematch')"
        flag = self.reader.read_flag
        keys = self.reader.read_key_items()
        if VS_SEEKER not in keys:
            return ("You have no VS Seeker: the woman in Vermilion City's Pokémon Center gives it (quest('vs_seeker')). " + rematches.line(flag))
        st = self.reader.read_vs_seeker()
        if str(arg or "").strip().lower() in ("status", "info"):
            return self._rematch_status(st)
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "A rematch loop works from the open field — finish what is on screen first (advance_dialog / close_menus / the battle)."
        notes: list[str] = []
        fought = 0
        used = False
        skipped: set[int] = set()
        for _ in range(REMATCH_FIGHTS + 4):
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return self._rematch_wrap("A rematch (or wild) battle started — play it (use_move / switch_pokemon / use_item), then call " + call + " again to go on.", notes, call)
            st = self.reader.read_vs_seeker()
            objs = self.reader.read_objects_by_local()
            here = {loc: rung for loc, rung in st["ready"].items() if loc in objs and loc not in skipped}
            if here:
                if fought >= REMATCH_FIGHTS:
                    notes.append(f"{len(here)} more rematch(es) are waiting here")
                    break
                lead = next((p for p in self.reader.read_party() if p.max_hp), None)
                if lead and lead.hp_percent < LOW_HP:
                    notes.append(f"{lead.nickname or lead.species_name} is at {lead.hp_percent:.0%} — heal() first (the flagged trainers stay ready for {max(0, 100 - st['charge_steps'])} more steps, "
                                 "and until you leave the map; a Pokémon Center is a map change, so you would use the VS Seeker again)")
                    break
                px, py = self.reader.read_player_pos()
                loc = min(here, key=lambda i: abs(objs[i][0] - px) + abs(objs[i][1] - py))
                x, y = objs[loc]
                if not self._approach_adjacent(x, y):
                    if self.reader.detect_context() == GameContext.IN_BATTLE:
                        continue
                    skipped.add(loc)
                    notes.append(f"couldn't reach the trainer at ({x},{y})")
                    continue
                px, py = self.reader.read_player_pos()
                objs = self.reader.read_objects_by_local()
                if loc in objs:
                    x, y = objs[loc]                              # they may have shifted a tile when they raised their hand
                    if self._approach_adjacent(x, y):
                        px, py = self.reader.read_player_pos()
                face = self._facing_dir(px, py, x, y)
                if face:
                    self.mgba.tap(face)
                self.mgba.tap("A")
                self.mgba.tick(20)
                fought += 1
                if self.reader.detect_context() != GameContext.IN_BATTLE:
                    self._advance_to_control()
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    continue                                      # the loop head hands it to the model
                if self.reader.read_vs_seeker()["ready"].get(loc):
                    skipped.add(loc)                              # still flagged: the talk did not start a battle
                    notes.append(f"the trainer at ({x},{y}) did not start a battle")
                continue
            if st["ready"] and not any(loc in objs for loc in st["ready"]):
                notes.append("trainers are flagged but not on screen here — walk toward them, or use the VS Seeker again after they are in range")
            if fought:
                break                                              # this batch is done
            if used:
                notes.append("the VS Seeker found nobody who wants a rematch here (each beaten trainer in range is ready with a 70 % chance; trainers you have not beaten, or whose next team "
                             "waits for story progress, never are) — walk to a spot among more beaten trainers and call " + call + " again")
                break
            if st["bag_steps"] < 100:
                moved = self._rematch_charge(100 - st["bag_steps"])
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    continue
                left = 100 - self.reader.read_vs_seeker()["bag_steps"]
                notes.append(f"walked {moved} steps to charge the battery" + (f" — {left} more steps still needed: call {call} again" if left > 0 else ""))
                if left > 0:
                    break
                continue
            msg = self._use_vs_seeker()
            used = True
            if msg:
                notes.append(msg)
                break
        return self._rematch_wrap("", notes, call)

    def _rematch_status(self, st: dict) -> str:
        from knowledge import rematches
        bits = [rematches.line(self.reader.read_flag)]
        bits.append("The VS Seeker is charged." if st["bag_steps"] >= 100 else f"The VS Seeker needs {100 - st['bag_steps']} more steps (it charges while it is in the Bag).")
        if st["ready"]:
            bits.append(f"{len(st['ready'])} trainer(s) are flagged for a rematch" + (f" (they are withdrawn in {max(0, 100 - st['charge_steps'])} steps or on leaving the map)." if st["charge_steps"] < 100 else "."))
        return " ".join(bits)

    def _rematch_charge(self, need: int) -> int:
        """Walk back and forth between the tile we stand on and a free neighbour: one step per press, and the battery charges per step. Stops on a battle."""
        self.tilemap.refresh()
        grid, w, h = self.tilemap.passable_grid()
        if not grid:
            return 0
        a = self.reader.read_player_pos()
        nb = [(a[0] + dx, a[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        free = [(x, y) for x, y in nb if 0 <= x < w and 0 <= y < h and grid[y][x]]
        if not free:
            return 0
        b = free[0]
        start = self.reader.read_vs_seeker()["bag_steps"]
        here, there = a, b
        for _ in range(min(CHARGE_STEPS, max(need, 1) + 4)):
            if self.reader.detect_context() != GameContext.OVERWORLD or self.reader.read_vs_seeker()["bag_steps"] >= 100:
                break
            self._walk_to(*there)
            here, there = there, here
        return max(0, self.reader.read_vs_seeker()["bag_steps"] - start)

    def _use_vs_seeker(self) -> str:
        """Bag → Key Items → VS Seeker → USE; the proof is the table: a note back only when something went wrong."""
        keys = self.reader.read_key_items()
        res = self._menus.open_menu("Bag")
        if "Bag screen open" not in res:
            return f"Couldn't open the Bag ({res})"
        self.mgba.tick(40)
        if not self._bag_pocket_open(1) or not self._bag_cursor_to(keys.index(VS_SEEKER), pocket=1):
            self._menus.close_menus()
            return "Couldn't select the VS Seeker in the Key Items pocket."
        self.mgba.tap("A")
        self.mgba.tick(30)
        self.mgba.tap("A")
        for _ in range(40):                                       # the use animation: a use that finds trainers resets the in-bag counter when it ends; "no trainers within range" waits on a message instead
            self.mgba.tick(10)
            if self.reader.read_vs_seeker()["bag_steps"] < 100 and self.reader.detect_context() != GameContext.IN_MENU:
                break
        self.mgba.tick(90)
        self._advance_to_control(tries=10)
        return ""

    def _rematch_wrap(self, lead: str, notes: list, call: str) -> str:
        from knowledge import rematches
        st = self.reader.read_vs_seeker()
        parts = [lead] if lead else []
        if notes:
            parts.append("; ".join(notes) + ".")
        objs = self.reader.read_objects_by_local()
        waiting = [loc for loc in st["ready"] if loc in objs]
        if waiting:
            parts.append(f"{len(waiting)} flagged trainer(s) here still want a rematch (withdrawn in {max(0, 100 - st['charge_steps'])} steps or when you leave the map).")
            if not lead:
                parts.append(f"Call {call} again to continue.")
        parts.append(rematches.line(self.reader.read_flag))
        return " ".join(parts)

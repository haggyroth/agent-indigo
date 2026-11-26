"""quest('sweep <area>'): walk an area and finish it — every item ball, every trainer — reading what is left from the game's own flags (knowledge/sweeps.py, #366).

A driver, never an automatic one: the model asks for it. Travel, walking up to a trainer and picking up a ball are deterministic; every BATTLE is handed back to the model (the call ends,
`quest('sweep …')` again resumes — the flags say where it stands). It stops on a hurt lead instead of walking into the next fight, and skips what it cannot reach with a note."""
from game.state import GameContext

SWEEP_STEPS = 14               # targets handled per call: bounded, resumable
LOW_HP = 0.45                  # below this the lead is hurt: say so instead of walking into the next trainer


class SweepMixin:
    def _sweep_area(self, query: str):
        from knowledge.area_sweeps import AREAS
        q = str(query or "").strip().lower().replace("é", "e")
        hits = [a for a in AREAS if q and (a.lower().replace("é", "e") == q or q in a.lower().replace("é", "e"))]
        exact = [a for a in hits if a.lower().replace("é", "e") == q]
        pick = exact or hits
        return pick[0] if len(pick) == 1 else None, pick

    def _sweep_targets(self, area: str, skipped: set) -> list:
        """[(kind, flag, map, x, y)] of what is still open in `area` (hidden items are left to the Itemfinder and pick_up_items), in area map order."""
        from knowledge.area_sweeps import AREAS
        flag = self.reader.read_flag
        d = AREAS[area]
        order = {m: i for i, m in enumerate(d["maps"])}
        rows = [("item", f, m, x, y) for f, m, x, y in d["item_pos"]] + [("trainer", f, m, x, y) for f, m, x, y in d["trainer_pos"]]
        return sorted((r for r in rows if not flag(r[1]) and r[1] not in skipped), key=lambda r: (order.get(r[2], 99), r[0] != "item"))

    def _sweep(self, query: str) -> str:
        from knowledge.area_sweeps import AREAS
        area, hits = self._sweep_area(query)
        call = f"quest('sweep {query}')"
        if area is None:
            names = ", ".join(AREAS)
            return (f"Which area? {len(hits)} match {query!r}: {', '.join(hits)}." if hits else f"No area called {query!r}.") + f" Areas: {names}."
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "Sweeping works from the open field — finish what is on screen first (advance_dialog / close_menus / the battle)."
        flag = self.reader.read_flag
        done, skipped, notes = [], set(), []
        pocketed: set = set()                         # targets whose sealed pocket we already tried to enter
        for _ in range(SWEEP_STEPS):
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return self._sweep_handoff(area, done, notes, call)
            if self._pocket_plan and tuple(self.reader.read_current_map()) == self._pocket_plan[1]:
                src, dest, tile = self._pocket_plan                       # a battle interrupted the trip to a sealed pocket's ladder: finish it from here
                self._pocket_plan = None
                self._walk_to(*tile)
                self._advance_to_control(tries=20)
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    self._pocket_plan = (src, dest, tile)
                    return self._sweep_handoff(area, done, notes, call)
                continue
            lead = next((p for p in self.reader.read_party() if p.max_hp), None)
            targets = self._sweep_targets(area, skipped)
            if not targets:
                break
            here = tuple(self.reader.read_current_map())
            px, py = self.reader.read_player_pos()
            local = [t for t in targets if tuple(t[2]) == here]
            pool = [t for t in local if t[0] == "item"] or local              # the safe things first: a ball never fights back
            kind, f, mp, x, y = min(pool, key=lambda t: abs(t[3] - px) + abs(t[4] - py)) if pool else targets[0]
            if kind == "trainer" and lead and lead.hp_percent < LOW_HP:
                notes.append(f"{lead.nickname or lead.species_name} is at {lead.hp_percent:.0%} — heal() before the next trainer")
                break
            if tuple(mp) != here:
                out = self._go_to_map_tuple(tuple(mp), f"map:{mp[0]},{mp[1]}", call)
                if out:
                    return self._sweep_wrap(area, done, notes, out, call)
                continue
            if kind == "item":
                names, problem = self._pick_ball(x, y)
                if problem.startswith("couldn't reach") and f not in pocketed and self._enter_pocket(x, y, call):
                    pocketed.add(f)
                    continue                                   # arrived by the ladder that serves this pocket: look again from inside
                if problem:
                    skipped.add(f)
                    notes.append(problem)
                elif flag(f):
                    done.append(names)
                else:
                    skipped.add(f)                       # picked up something, but the flag did not set: do not loop on it
                    done.append(names)
            else:
                if not self._approach_adjacent(x, y):
                    if self.reader.detect_context() == GameContext.IN_BATTLE:
                        return self._sweep_handoff(area, done, notes, call)       # a trainer's line of sight got there first
                    if f not in pocketed and self._enter_pocket(x, y, call):
                        pocketed.add(f)
                        continue
                    skipped.add(f)
                    notes.append(f"couldn't reach the trainer at ({x},{y})")
                    continue
                px, py = self.reader.read_player_pos()
                face = self._facing_dir(px, py, x, y)
                if face:
                    self.mgba.tap(face)
                self.mgba.tap("A")
                self.mgba.tick(20)
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    return self._sweep_handoff(area, done, notes, call)
                self._advance_to_control()
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    return self._sweep_handoff(area, done, notes, call)
                if not flag(f):
                    skipped.add(f)                      # no battle came of it (they were not there, or are not a fighter): leave it, say so
                    notes.append(f"the trainer at ({x},{y}) did not start a battle")
        return self._sweep_wrap(area, done, notes, "", call)

    def _enter_pocket(self, tx: int, ty: int, call: str) -> bool:
        """The tile (tx, ty) is in a part of this map the walker cannot reach from where we stand (a sealed room entered only by a ladder — Mt. Moon B2F's two corner rooms): find the warp
        inside that part, go to the map on its other side and step onto the paired warp, which lands us inside. True once we are back on this map and the target has a walkable neighbour."""
        from knowledge.map_graph import MAP_WARPS
        here = tuple(self.reader.read_current_map())
        self.tilemap.refresh()
        grid, w, h = self.tilemap.passable_grid()
        if not grid:
            return False
        seen, todo = set(), [(tx + dx, ty + dy) for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0))]
        while todo:                                                      # the connected floor around the target
            x, y = todo.pop()
            if not (0 <= x < w and 0 <= y < h) or (x, y) in seen or not grid[y][x]:
                continue
            seen.add((x, y))
            todo += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        for wx, wy, dest_id, dest in self.tilemap.read_warp_dests():
            if tuple(dest) == here or not any((wx + dx, wy + dy) in seen or (wx, wy) in seen for dx, dy in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0))):
                continue
            table = MAP_WARPS.get(tuple(dest), [])
            if not (0 <= dest_id < len(table)):
                continue
            self._pocket_plan = (here, tuple(dest), tuple(table[dest_id][:2]))
            if self._go_to_map_tuple(tuple(dest), f"map:{dest[0]},{dest[1]}", call):
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    return True                                          # a wild battle on the way: the loop head hands it to the model, and the next call starts the trip again
                continue
            self._walk_to(*table[dest_id][:2])                           # onto the paired warp: it lands on (wx, wy)
            self._advance_to_control(tries=20)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return True
            if tuple(self.reader.read_current_map()) == here and self._pocket_open(tx, ty):
                self._pocket_plan = None
                return True
        self._pocket_plan = None
        return False

    def _pocket_open(self, tx: int, ty: int) -> bool:
        self.tilemap.refresh()
        grid, w, h = self.tilemap.passable_grid()
        px, py = self.reader.read_player_pos()
        if not grid or not (0 <= px < w and 0 <= py < h):
            return False
        seen, todo = set(), [(px, py)]
        while todo:
            x, y = todo.pop()
            if not (0 <= x < w and 0 <= y < h) or (x, y) in seen or not grid[y][x]:
                continue
            seen.add((x, y))
            todo += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        return any((tx + dx, ty + dy) in seen for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)))

    def _sweep_handoff(self, area: str, done: list, notes: list, call: str) -> str:
        return self._sweep_wrap(area, done, notes, f"A TRAINER/wild battle started — play it (use_move / switch_pokemon / use_item), then call {call} again to continue; the flags say where it stands.", call)

    def _sweep_wrap(self, area: str, done: list, notes: list, lead: str, call: str) -> str:
        from knowledge import sweeps
        prog = sweeps.progress(area, self.reader.read_flag)
        parts = [lead] if lead else []
        if done:
            parts.append("Picked up: " + ", ".join(done) + ".")
        if notes:
            parts.append("Skipped / note: " + "; ".join(notes) + ".")
        left = sweeps.remaining(prog)
        parts.append(sweeps.line(area, prog) + (f" — {left} left (hidden items need the Itemfinder)." if left else " — every trainer and item ball is done."))
        if left and not lead:
            parts.append(f"Call {call} again to continue.")
        note = sweeps.missable_note(area, prog, self.reader.read_flag)
        return " ".join(parts) + (("\n" + note) if note else "")

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
        for _ in range(SWEEP_STEPS):
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return self._sweep_handoff(area, done, notes, call)
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

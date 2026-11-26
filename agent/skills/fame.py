"""quest('fame'): the Fame Checker (Gossip Checker achievement) — what is missing, and a driver that talks to the NPCs / reads the signs that give it (#368).

`quest('fame')` lists every missing entry by person; `quest('fame go')` walks to the next OPEN talkable one (this map first), faces it, presses A through the lines and checks the game's own
flag to see whether the entry arrived. Battles end the call (a trainer who sees you) — call it again to resume. Entries set by a battle or a cutscene are not driven: the list says where."""
from game.state import GameContext

FAME_STEPS = 8                   # entries tried per call: bounded, resumable


class FameMixin:
    def _fame(self, arg: str = "") -> str:
        from knowledge import fame_checker as fc
        flag = self.reader.read_flag
        owned = self.reader.read_fame_checker()
        if str(arg or "").strip().lower() not in ("go", "next", "talk", "run"):
            return fc.view(owned, flag)
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "The Fame Checker run works from the open field — finish what is on screen first (advance_dialog / close_menus / the battle)."
        call = "quest('fame go')"
        got, notes, skip = [], [], set()
        for _ in range(FAME_STEPS):
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return self._fame_wrap(got, notes, f"A battle started — play it, then call {call} again.")
            owned = self.reader.read_fame_checker()
            here = tuple(self.reader.read_current_map())
            e = fc.next_target(owned, flag, here, skip, dist=self._fame_dist(here))
            if e is None:
                break
            person, idx, mp, kind, x, y, label, _h, _n = e
            tag = f"{fc.PERSONS[person]} #{idx + 1}"
            if tuple(mp) != here:
                out = self._go_to_map_tuple(tuple(mp), f"map:{mp[0]},{mp[1]}", call)
                if out:
                    if self.reader.detect_context() == GameContext.IN_BATTLE:
                        return self._fame_wrap(got, notes, out)
                    skip.add((person, idx))
                    notes.append(f"{tag}: couldn't get to {fc.where(e)}")
                continue
            if not self._approach_adjacent(x, y):
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    return self._fame_wrap(got, notes, f"A battle started — play it, then call {call} again.")
                skip.add((person, idx))
                notes.append(f"{tag}: couldn't reach ({x},{y})")
                continue
            px, py = self.reader.read_player_pos()
            face = self._facing_dir(px, py, x, y)
            if face:
                self.mgba.tap(face)
            self.mgba.tap("A")
            self.mgba.tick(20)
            if self.reader.detect_context() != GameContext.IN_BATTLE:
                self._advance_to_control()
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return self._fame_wrap(got, notes, f"A battle started — play it, then call {call} again.")
            if idx in self.reader.read_fame_checker().get(person, set()):
                got.append(tag)
            else:
                skip.add((person, idx))
                notes.append(f"{tag}: talking at ({x},{y}) did not give the entry (it may say it later, or be someone who moved)")
        return self._fame_wrap(got, notes, "")

    @staticmethod
    def _fame_dist(here: tuple):
        """Hops from `here` to another map over the connection / warp graph (cached per call); None when there is no route."""
        from knowledge.map_graph import route_to
        cache: dict = {}

        def dist(mp):
            if mp not in cache:
                try:
                    r = route_to(tuple(here), tuple(mp))
                except Exception:
                    r = None
                cache[mp] = None if r is None else len(r)
            return cache[mp]
        return dist

    def _fame_wrap(self, got: list, notes: list, lead: str) -> str:
        from knowledge import fame_checker as fc
        parts = [lead] if lead else []
        if got:
            parts.append("New entries: " + ", ".join(got) + ".")
        if notes:
            parts.append("Note: " + "; ".join(notes) + ".")
        owned = self.reader.read_fame_checker()
        parts.append(fc.line(owned, self.reader.read_flag))
        here = tuple(self.reader.read_current_map())
        if not lead and fc.next_target(owned, self.reader.read_flag, here, dist=self._fame_dist(here)) is not None:
            parts.append("Call quest('fame go') again to continue.")
        return " ".join(parts)

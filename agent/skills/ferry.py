"""quest('ferry <island>'): ride the Seagallop to Vermilion / One-Seven Island (#360).

Goes to the nearest dock (Vermilion's pier, or the Harbor of the island you are on), talks to the sailor, reads the destination menu the game draws (knowledge/ferry.py: Tri-Pass or Rainbow
Pass lists), moves the cursor to the island asked for, picks it and lets the crossing play. Verified by the map you arrive on. Needs the Tri-Pass (One-Three Island) or the Rainbow Pass (all
seven) and, from Vermilion, the ship having left (VAR_MAP_SCENE_VERMILION_CITY 3). Information only about the passes: the call says what is missing."""
from game.state import GameContext

VAR_VERMILION_SCENE, VAR_ONE_ISLAND_SCENE, VAR_CINNABAR_SCENE = 0x407E, 0x4076, 0x4071


class FerryMixin:
    def _ferry(self, arg: str = "") -> str:
        from knowledge import ferry as fy
        a = str(arg or "").strip().lower().replace("island", "").replace(" city", "").strip()
        words = {"vermilion": 0, "one": 1, "1": 1, "two": 2, "2": 2, "three": 3, "3": 3, "four": 4, "4": 4, "five": 5, "5": 5, "six": 6, "6": 6, "seven": 7, "7": 7}
        stage = self.reader.read_var(VAR_ONE_ISLAND_SCENE)
        if a not in words:
            return (f"Where to? quest('ferry <island>'): {fy.route_text(-1, stage)}. " +
                    ("(Rainbow Pass: all seven islands.)" if stage >= fy.RAINBOW_STAGE else "(Tri-Pass: One, Two and Three Island; the Rainbow Pass — Celio's Network Machine chain — opens Four to Seven.)"))
        dest = words[a]
        call = f"quest('ferry {a}')"
        if stage < 1:
            return "The Seagallop needs a pass: the Tri-Pass (Celio, One Island — after Blaine) or the Rainbow Pass (quest('sevii_ruby'))."
        if dest >= 4 and stage < fy.RAINBOW_STAGE:
            return f"{fy.NAMES[dest]} needs the Rainbow Pass (the Tri-Pass covers One, Two and Three Island): quest('sevii_ruby')."
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "A ferry trip works from the open field — finish what is on screen first (advance_dialog / close_menus / the battle)."
        origin = fy.island_of_map(self.reader.read_current_map())
        if origin is None:
            origin = 0                                        # on the Kanto mainland: the pier at Vermilion
        if origin == dest:
            return f"You are already at {fy.NAMES[dest]}."
        if origin == 0:
            if self.reader.read_var(VAR_VERMILION_SCENE) != 3:
                return "No Seagallop is at Vermilion's pier right now (the S.S. Anne scene has not finished)."
            dock, sailor = fy.VERMILION_SAILOR
        else:
            dock, sailor = self._harbor_map(origin), (8, 6)
        if (msg := self._go_to_map_tuple(tuple(dock), f"map:{dock[0]},{dock[1]}", call)):
            return msg
        start_map = tuple(self.reader.read_current_map())
        if not self._approach_adjacent(*sailor):
            return f"Couldn't get to the sailor at {sailor} — walk up, face him and press A, then call {call}."
        px, py = self.reader.read_player_pos()
        if (face := self._facing_dir(px, py, *sailor)):
            self.mgba.tap(face)
        self.mgba.tap("A")
        self.mgba.tick(30)
        presses = self._ferry_presses(origin, dest, stage)
        if presses is None:
            self._menus.close_menus()
            return f"{fy.NAMES[dest]} is not on {fy.NAMES[origin]}'s ferry list right now."
        step = 0
        for _ in range(60):
            if self._menus.choice_live():
                if step < len(presses):
                    row = presses[step]
                    for _i in range(row):
                        self.mgba.tap("Down")
                        self.mgba.tick(12)
                    step += 1
                self.mgba.tap("A")
                self.mgba.tick(40)
                continue
            if tuple(self.reader.read_current_map()) != start_map and self.reader.detect_context() == GameContext.OVERWORLD:
                break
            self.mgba.tap("A")
            self.mgba.tick(40)
        self._advance_to_control(tries=30)
        here = tuple(self.reader.read_current_map())
        if here == start_map:
            return f"The ferry did not leave — call {call} again."
        return f"Sailed from {fy.NAMES[origin]} to {fy.NAMES[dest]} (now at map {here}). " + ("Walk out of the harbor to the island." if dest else "")

    @staticmethod
    def _harbor_map(island: int) -> tuple:
        from knowledge.ferry import HARBORS
        return HARBORS[island]

    def _ferry_presses(self, origin: int, dest: int, stage: int) -> list | None:
        """Cursor rows to move down before each A: the Rainbow Pass menu is two pages (OTHER opens the second); the Tri-Pass lists are one."""
        from knowledge import ferry as fy
        if stage >= fy.RAINBOW_STAGE:
            seq = fy.rainbow_menu(origin, dest)
            return [row for row, _page in seq] if seq else None
        rows = fy.tri_pass_rows(origin, self.reader.read_var(VAR_CINNABAR_SCENE) >= 4)
        return [rows.index(dest)] if dest in rows else None

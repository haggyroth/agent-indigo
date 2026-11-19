"""fish(casts?): cast the best rod you own at the water in front of you (walks to a shore first) — a wild Pokémon on the hook is handed to the model like any encounter.

From the decomp (field_player_avatar.c Fishing1-16): the cast is a task. It plays 1-3 rounds of 'dots' (A is IGNORED then), decides the bite (50% — never on a map without
fishing Pokémon), and only in the bite window (36 / 33 / 30 frames for the Old / Good / Super Rod) does a NEW press of A reel it in; "Not even a nibble" / "It got away" end
it, "Oh! A bite!" ends in a wild battle. So pressing A every few frames from the cast to the end is safe and always lands inside the window — as long as it STOPS the moment
the cast is over: A facing water on the field opens Surf's prompt. The rod is used from the Bag (Key Items → the rod → USE)."""
from game.state import GameContext

OLD_ROD, GOOD_ROD, SUPER_ROD = 262, 263, 264


class FishingMixin:
    def _best_rod(self):
        keys = self.reader.read_key_items()
        for iid, name in ((SUPER_ROD, "Super Rod"), (GOOD_ROD, "Good Rod"), (OLD_ROD, "Old Rod")):
            if iid in keys:
                return iid, name
        return None, ""

    def _shore_spot(self):
        """(x, y, face) of the nearest reachable shore tile with water in front, or None — the same search Surf uses."""
        t = self.tilemap
        t.refresh()
        grid, w, h = t.passable_grid()
        if grid is None:
            return None
        px, py = self.reader.read_player_pos()
        spots = []
        for y in range(h):
            for x in range(w):
                if not grid[y][x]:
                    continue
                for face, (dx, dy) in (("Down", (0, 1)), ("Up", (0, -1)), ("Right", (1, 0)), ("Left", (-1, 0))):
                    ti = t.read_tile(x + dx, y + dy)
                    if ti is not None and ti.is_water and t.metatile_behavior(x + dx, y + dy) != 0x13:
                        spots.append((abs(x - px) + abs(y - py), (x, y), face))
                        break
        for _d, (sx, sy), face in sorted(spots)[:6]:
            self._walk_to(sx, sy)
            if tuple(self.reader.read_player_pos()) == (sx, sy):
                return sx, sy, face
        return None

    def _cast_rod(self, rod_id: int) -> str:
        """One cast: Bag → Key Items → the rod → USE, then A every few frames until the cast is over. 'battle' | 'nothing' | 'failed:<why>'."""
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "failed:not on the field"
        res = self._menus.open_menu("Bag")
        if "Bag screen open" not in res:
            return f"failed:couldn't open the Bag ({res})"
        self.mgba.tick(40)
        keys = self.reader.read_key_items()
        if rod_id not in keys or not self._bag_pocket_open(1) or not self._bag_cursor_to(keys.index(rod_id), pocket=1):
            self._menus.close_menus()
            return "failed:couldn't select the rod in the Key Items pocket"
        self.mgba.tap("A")                                   # the context menu: USE is the first row
        self.mgba.tick(30)
        self.mgba.tap("A")
        self.mgba.tick(10)
        busy = False
        for _ in range(420):                                 # ~ 7 s of 1/60 s steps x 6 frames is plenty: 3 rounds of dots + the bite window
            ctx = self.reader.detect_context()
            if ctx == GameContext.IN_BATTLE:
                return "battle"
            if ctx != GameContext.OVERWORLD:
                busy = True                                  # the bag closing, then the cast's own (locked-controls) frames
                self.mgba.tap("A")
            elif busy:
                return "nothing"                             # back on the field with control: the cast is over — never press A here (Surf's prompt)
            self.mgba.tick(5)
        return "failed:the cast never finished"

    def _fish(self, casts: int = 3) -> str:
        casts = max(1, min(int(casts or 3), 8))
        rod_id, rod = self._best_rod()
        if rod_id is None:
            return "You have no fishing rod: quest('old_rod') (Vermilion), quest('good_rod') (Fuchsia), quest('super_rod') (Route 12)."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if self._surfing():
            return "Fish from the shore, not while surfing: step onto land first."
        spot = self._shore_spot()
        if spot is None:
            return "No reachable shore with water to face on this map — go_to a coast, lake or pond first."
        sx, sy, face = spot
        done = 0
        for _ in range(casts):
            self.mgba.tick(24)
            if self.reader.read_player_facing() != face:
                self.mgba.hold(face, 3)                       # turn to the water without stepping
                self.mgba.tick(12)
            out = self._cast_rod(rod_id)
            if out.startswith("failed:"):
                return f"Couldn't fish: {out[7:]}."
            done += 1
            if out == "battle":
                from agent import events
                events.emit("note", f"fishing: a wild Pokémon on the {rod}", log=False)
                return (f"Cast {done}× with the {rod} from ({sx},{sy}): something is on the hook!"
                        + (self._quest_battle("fish()", "the fish on the line") or ""))
        return (f"Cast the {rod} {done}× from ({sx},{sy}) facing {face.lower()}: no bite. Try again (fish()), a better rod, or another stretch of water "
                "(maps without fishing Pokémon never bite).")

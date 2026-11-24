"""quest('victory_road'): Viridian → Route 22 → Route 23 → Victory Road (three Strength-boulder floors) → Indigo Plateau.

The road to the cave is plain travel (go_to: Route 22's rival, Route 23's eight badge guards and its Surf crossing are handled there). Inside, the
floors are solved by knowledge.vr_route (decomp data via tools/gen_victory_road.py): 1F → 2F's west half (a boulder pushed onto the floor switch at
(2,19) opens the way, six pushes) → 3F → round to 2F's middle → 3F's side room → 2F's east exit at (48,12). The driver executes the plan's FIRST
action (walk to a warp tile / push one boulder), re-reads the boulders and plans again. The exit lands on Route 23's north half; go_to finishes the
walk to Indigo Plateau (FLAG_VISITED_INDIGO_PLATEAU 0x899). Needs all 8 badges and a Pokémon that knows Strength."""
from game.constants import Addr
from game.state import GameContext
from knowledge import boulder_puzzle as bp
from knowledge import map_graph, vr_route
from knowledge.vr_data import FLOORS

ROUTE_23, INDIGO_PLATEAU = (3, 42), (3, 9)
FLAG_INDIGO = 0x899
FLAG_HIDE_2F_BOULDER = 0x058            # set at the cave's start; cleared when 3F's boulder falls through the hole (2F's extra boulder appears at (33,19))
STRENGTH_MOVE = 70
_STEP = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}


class VictoryMixin:
    def _vr_boulders(self, here):
        """Boulder tiles on this floor. The game only reports the objects it has loaded around the camera (a boulder across the cave is missing from
        the read), so the picture is remembered: on arriving the floor starts from the decomp positions (the cave RESETS its boulders every time a
        floor loads, even when a switch stays pressed), our own pushes move entries, a boulder right beside us that isn't reported is dropped, and
        anything reported is added."""
        rows = FLOORS[here]["rows"]
        live = [o for o in self.reader.read_objects_by_gfx([Addr.OBJ_GFX_BOULDER]) if 0 <= o[0] < len(rows[0]) and 0 <= o[1] < len(rows)]
        epoch = getattr(self.reader, "map_epoch", 0)
        if self._vr_floor != here or self._vr_epoch != epoch:        # a floor left and entered again (a heal trip, a grind relocation) has reloaded: its boulders are back where the decomp has them
            self._vr_floor, self._vr_epoch = here, epoch
            self._vr_known = set(vr_route.initial_boulders(here, self._vr_revealed()))
        px, py = self.reader.read_player_pos()
        kept = {k for k in self._vr_known if abs(k[0] - px) > 7 or abs(k[1] - py) > 4}
        self._vr_known = kept | set(map(tuple, live))
        return sorted(self._vr_known)

    def _vr_revealed(self) -> bool:
        return not self.reader.read_flag(FLAG_HIDE_2F_BOULDER)

    def _vr_pressed(self, here) -> set:
        return {i for i, var in enumerate(vr_route.VAR_SWITCH[here]) if self.reader.read_var(var) == 100}

    def _vr_walk(self, here, pos, target, boulders, pressed) -> str:
        """Walk toward `target` one short straight leg at a time along vr_route's own path (the live pathfinder balks at some long cave walks).
        An arrow warp (the cave entrance, the exit) is never a walk_to destination — walk_to would 'nudge' through it and leave the cave — so a stand
        ON one is reached by a manual step from the neighbouring tile along the path (a sideways or upward step does not fire it)."""
        legs = vr_route.waypoints(here, pos, target, boulders, pressed)
        if not legs:
            return self._walk_to(*target)
        soft = {t for (fl, t) in vr_route.SOFT if fl == here}
        leg = legs[0]
        if leg in soft:
            if len(legs) > 1:
                leg = legs[1]                                        # a longer walk crosses it without stopping on it
            else:
                path = bp.walk_path(vr_route.floor(here), pos, leg, boulders, pressed) or [leg]
                before = path[-2] if len(path) >= 2 else tuple(pos)
                if tuple(pos) != tuple(before):
                    return self._walk_to(*before)
                button = {v: k for k, v in _STEP.items()}.get((leg[0] - pos[0], leg[1] - pos[1]))
                if button:
                    self.mgba.hold(button, 18)
                    self.mgba.tick(24)
                return f"Stepped onto ({leg[0]},{leg[1]})."
        return self._walk_to(*leg)

    def _confirm_with_a(self) -> None:
        """Answer a field 'Use Strength?' box with A only (the cursor starts on YES) until the script engine is idle — never a Down press, for tiles a Down press fires."""
        for _ in range(8):
            if self.mgba.read8(Addr.SCRIPT_RAM) == 0 or self.reader.detect_context() == GameContext.IN_BATTLE:
                return
            self.mgba.tap("A")
            self.mgba.tick(30)

    def _vr_push(self, stand, direction) -> None:
        """From `stand` push the boulder beside it: face it, press A (the first time on a floor: 'use Strength?' → YES), then walk into it."""
        self.mgba.tap(direction)
        self.mgba.tick(8)
        self.mgba.tap("A")
        self.mgba.tick(40)
        if (tuple(self.reader.read_current_map()), tuple(stand)) in vr_route.DOWN_ARROW:
            self._confirm_with_a()          # the cave's entrance tile is a DOWN arrow warp: _answer_field_yes probes the choice box with Down, which walked out and reset the boulders
        else:
            self._answer_field_yes()
        self._advance_to_control(tries=20)
        if tuple(self.reader.read_player_pos()) == tuple(stand):
            self.mgba.hold(direction, 12)              # under one 16-frame step: a longer hold started a SECOND push whenever the frame phase allowed it, and the boulder overshot its stop
            self.mgba.tick(30)
            dx, dy = _STEP[direction]
            old = (stand[0] + dx, stand[1] + dy)
            if tuple(self.reader.read_player_pos()) == old:                  # we stepped into the boulder's tile: it moved one tile on
                self._vr_known.discard(old)
                new = (old[0] + dx, old[1] + dy)
                if new not in vr_route.floor(tuple(self.reader.read_current_map())).holes:
                    self._vr_known.add(new)

    def _vr_warp(self, pos, tile, button, here) -> None:
        if tuple(pos) == tuple(tile) and not button:                # standing on a ladder we arrived by (a walled-in pocket): step off it and back on
            opposite = {"Left": "Right", "Right": "Left", "Up": "Down", "Down": "Up"}
            for d in ("Left", "Right", "Up", "Down"):
                self.mgba.hold(d, 18)
                self.mgba.tick(20)
                if tuple(self.reader.read_player_pos()) != tuple(tile):
                    self.mgba.hold(opposite[d], 18)
                    self.mgba.tick(40)
                    return
            return
        if tuple(pos) == tuple(tile) and button:                    # already standing on an arrow warp: hold its arrow
            self.mgba.hold(button, 20)
            self.mgba.tick(72)
            return
        d = (tile[0] - pos[0], tile[1] - pos[1])
        if d not in {v: k for k, v in _STEP.items()}:
            self._vr_walk(here, pos, tile, self._vr_boulders(here), self._vr_pressed(here))      # not beside it yet: a leg toward it
            return
        step = {v: k for k, v in _STEP.items()}[d]
        self.mgba.hold(step, 18)
        self.mgba.tick(30)
        if button and tuple(self.reader.read_current_map()) == here and tuple(self.reader.read_player_pos()) == tuple(tile):
            self.mgba.hold(button, 20)
            self.mgba.tick(72)

    def _vr_back(self, resume: str, auto_trainers: bool = False):
        """Walk OUT of the cave to Route 23's south half by the reverse puzzle (vr_route.plan_back) — the way home from the Plateau without Fly. None once outside; else the message to hand back
        (a battle for the model, or why it stopped). `resume` is the call that continues it."""
        return self._get_victory_road(auto_trainers, back=True, call=resume)

    def _get_victory_road(self, auto_trainers: bool = False, back: bool = False, call: str = "quest('victory_road')"):
        if not back and self.reader.read_flag(FLAG_INDIGO) and self._plateau_side():
            return "You've reached Indigo Plateau — heal and save at the Pokémon Center, then the Elite Four's door (north)."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if not back and bin(int(self.reader.read_badges()[1])).count("1") < 8:
            return "Route 23's guards want all eight badges before Victory Road."
        if not self._knows_move(STRENGTH_MOVE):
            return "Victory Road's boulders need a Pokémon that knows Strength: quest('strength')."
        stuck, last, resets = 0, None, 0
        for _ in range(160):
            if (b := self._hideout_fight(call, "Victory Road", auto_trainers)):
                return b
            if not back and self.reader.read_flag(FLAG_INDIGO) and self._plateau_side():
                break
            if self.reader.detect_context() != GameContext.OVERWORLD:
                self._advance_to_control(tries=30)
            here = tuple(self.reader.read_current_map())
            pos = tuple(self.reader.read_player_pos())
            if not back and here == INDIGO_PLATEAU:
                break
            if here not in FLOORS:
                if back:
                    return None                       # out of the cave
                north = here == ROUTE_23 and map_graph.region_at(here, *pos) == "0"
                dest, target = ("Indigo Plateau", INDIGO_PLATEAU) if north else ("Victory Road 1F", vr_route.VR_1F)
                if (msg := self._hideout_travel(dest, target, call, auto_trainers)):
                    return msg
                continue
            boulders, pressed = self._vr_boulders(here), self._vr_pressed(here)
            all_pressed = {fl: self._vr_pressed(fl) for fl in FLOORS}
            act = (vr_route.plan_back(here, pos, boulders, pressed, all_pressed) if back
                   else vr_route.plan(here, pos, boulders, pressed, self._vr_revealed(), all_pressed))
            if act is None and (resets := resets + 1) <= 60 and (act := vr_route.reset_action(here, pos, boulders, pressed, self._vr_revealed())):
                pass                                    # a boulder sits where the puzzle cannot use it: leave the floor and come back (the cave reloads its boulders)
            elif act is None:
                return (f"No route through Victory Road {FLOORS[here]['name']} from {pos} — a trainer may be in the way. Clear it, then call {call} again.")
            state = (here, pos, tuple(sorted(boulders)), act)
            stuck = stuck + 1 if state == last else 0
            last = state
            if stuck >= 4:
                return f"Stuck at {pos} on {FLOORS[here]['name']}: couldn't do {act} — call {call} again, or do it by hand (walk_to / use_hm('strength') / push)."
            if act[0] == "push":
                _k, stand, direction = act
                if tuple(pos) != tuple(stand):
                    self._vr_walk(here, pos, stand, boulders, pressed)
                    continue
                self._vr_push(stand, direction)
            else:
                _k, tile, button = act
                self._vr_warp(pos, tile, button, here)
        if back:
            return f"Made progress on the way out of Victory Road — call {call} again to continue (it resumes)."
        if self.reader.read_flag(FLAG_INDIGO) or tuple(self.reader.read_current_map()) == INDIGO_PLATEAU:
            return "Reached Indigo Plateau. Heal and save at its Pokémon Center, stock up, then the Elite Four's door (north)."
        return f"Made progress on the way to Indigo Plateau — call {call} again to continue (it resumes)."

"""quest('rocket_hideout'): the Silph Scope from Giovanni, under the Celadon Game Corner.

The script (decomp: CeladonCity_GameCorner, RocketHideout_B1F..B4F, RocketHideout_Elevator), in order:
  1. Game Corner: the Rocket Grunt at (11,2) stands in front of the poster. Beat him (talk from (11,3)), then press the poster at
     (11,1) from (11,2): the stairs to the hideout appear at (15..17,2) (FLAG_OPENED_ROCKET_HIDEOUT 0x26D).
  2. B1F → B2F (28,2) → B3F (18,2) → B4F (11,15). The arrival half of B4F (west) is walled off from Giovanni's half: the only way
     across is the elevator, which needs the Lift Key.
  3. B4F west: beat the Grunt at (4,2); the Lift Key ball appears at (3,2) (FLAG_CAN_USE_ROCKET_HIDEOUT_LIFT 0x2A5).
  4. Elevator (from B2F's door at (28,16) or B1F's at (24,25)): the panel at (0,2) → choose B4F → exit by the door (1..2,5), which
     lands in B4F's south corridor (20,23), connected to Giovanni's room.
  5. Giovanni at (19,4): talk from (19,5); after the fight the Silph Scope ball appears at (20,5).
  6. Back down the elevator to B1F and out.
Arrow ("spinner") tiles are avoided by walk_to, so the mazes on B2F / B3F are never entered.
"""
from game.state import GameContext

GAME_CORNER = (10, 14)
HIDEOUT_B1F, HIDEOUT_B2F, HIDEOUT_B3F, HIDEOUT_B4F, ELEVATOR = (1, 42), (1, 43), (1, 44), (1, 45), (1, 46)
HIDEOUT_MAPS = (HIDEOUT_B1F, HIDEOUT_B2F, HIDEOUT_B3F, HIDEOUT_B4F, ELEVATOR)
FLAG_OPENED_ROCKET_HIDEOUT = 0x26D
FLAG_CAN_USE_LIFT = 0x2A5
SILPH_SCOPE_ITEM, LIFT_KEY_ITEM = 359, 356
ROCKET_M_GFX, GIOVANNI_GFX, ITEM_BALL_GFX = 49, 87, 92
GRUNT_STAND = ((11, 3), "Up")             # the Game Corner Grunt stands at (11,2)
POSTER_STAND = ((11, 2), "Up")            # the poster is the sign at (11,1)
LIFT_GRUNT_STAND = ((4, 3), "Up")         # B4F's Grunt stands at (4,2)
LIFT_KEY_STAND = ((3, 3), "Up")           # the Lift Key ball is at (3,2)
GIOVANNI_STAND = ((19, 5), "Up")          # Giovanni stands at (19,4); the Silph Scope ball appears at (20,5)
SCOPE_STAND = ((19, 5), "Right")
DOOR_GRUNTS = ((16, 14), (19, 14))        # beat both and the barrier at (17..18,12..13) opens
DOOR_GRUNT_APPROACH = (17, 16)
B1F_EXIT, B1F_GRUNT = (12, 2), (21, 27)  # B1F's exit to the Game Corner; the Grunt whose defeat opens the barrier to the south wing
PANEL_STAND = ((0, 3), "Up")              # the floor-select panel is the sign at (0,2)
ELEVATOR_DOOR = (2, 5)                    # both (1,5) and (2,5) are listed warps, but only (2,5) fires
ELEVATOR_DOORS = {HIDEOUT_B1F: (24, 25), HIDEOUT_B2F: (28, 16)}      # where the elevator is entered on each floor
FLOOR_ROW = {"B1F": 0, "B2F": 1, "B4F": 2}                          # the multichoice list: B1F, B2F, B4F, Exit


def b4f_east(x: int, y: int) -> bool:
    """Is (x, y) on B4F on Giovanni's side (his room and the south corridor), not the west half where the stairs arrive?"""
    return x >= 14 or y >= 19


class HideoutMixin:
    def _has_silph_scope(self) -> bool:
        return SILPH_SCOPE_ITEM in self.reader.read_key_items()

    def _has_lift_key(self) -> bool:
        return bool(self.reader.read_flag(FLAG_CAN_USE_LIFT)) or LIFT_KEY_ITEM in self.reader.read_key_items()

    def _hideout_travel(self, dest: str, target: tuple, call: str, auto_trainers: bool):
        """One resumable travel leg. None = arrived; else the message to return (a battle for the model, or why it stopped)."""
        for _ in range(8):
            if tuple(self.reader.read_current_map()) == target:
                return None
            out = self._go_to(dest, mode="yield", auto_trainers=auto_trainers, resume_call=call)
            if tuple(self.reader.read_current_map()) == target:
                return None
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if "heal()" in out or "Lost a trainer" in out:
                heal = self._heal()
                if not heal.startswith(("Healed", "Party is already")):
                    return f"Couldn't heal on the way to {dest} ({heal}) — heal(), then {call} again."
                continue
            if "Can't get to" in out or "No route" in out or "Blocked" in out or "gated" in out:
                return f"Can't reach {dest}: {out}"
        return f"Didn't reach {dest} yet — call {call} again to continue (it resumes)."

    def _hideout_fight(self, call: str, label: str, auto_trainers: bool):
        """After talking to a trainer: if a battle started, play it on autopilot (auto_trainers) or hand it to the model."""
        if self.reader.detect_context() != GameContext.IN_BATTLE:
            return None
        if auto_trainers:
            self._auto_fight()
            self._advance_to_control(tries=20)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return self._quest_battle(call, label)
            return None
        return self._quest_battle(call, label)

    def _route_exists(self, tile) -> bool:
        """Is there a walkable route to `tile` on the live grid right now (a barrier shut = no)? Plans only, never moves."""
        from game.pathfinding import find_path
        self._advance_to_control(tries=10)               # just off a warp the grid can still be the previous map's: let it settle
        self.mgba.tick(40)
        self.tilemap.refresh()
        grid, w, h = self.tilemap.passable_grid()
        if grid is None:
            return False
        return find_path(tuple(self.reader.read_player_pos()), tuple(tile), lambda x, y: grid[y][x], w, h) is not None

    def _rocket_at(self, x: int, y: int) -> bool:
        return (x, y) in self.reader.read_objects_by_gfx([ROCKET_M_GFX])

    def _ball_at(self, x: int, y: int) -> bool:
        return (x, y) in self.reader.read_objects_by_gfx([ITEM_BALL_GFX])

    def _ride_elevator(self, to_floor: str, call: str):
        """Inside the elevator: the panel → `to_floor` → out by the door. None = on the new floor; else a message.
        The panel opens a list (B1F / B2F / B4F / Exit) with the cursor on the floor the lift thinks it is on; _press_on_tile would
        answer it with A (= whatever is highlighted), so the panel is driven by hand."""
        for _ in range(3):
            self._walk_to(*PANEL_STAND[0])
            if tuple(self.reader.read_player_pos()) != PANEL_STAND[0]:
                return f"Couldn't reach the elevator panel at (0,2) — walk_to (0,3), face up, press A, then pick {to_floor}."
            live = False
            for _ in range(4):
                self.mgba.tap("Up")                         # face the panel (it is a wall sign)
                self.mgba.tick(8)
                self.mgba.tap("A")
                self.mgba.tick(40)
                for _ in range(6):                          # "Which floor do you want?" → the list
                    if self._menus.choice_live():
                        live = True
                        break
                    self.mgba.tap("A")
                    self.mgba.tick(20)
                if live:
                    break
            if not live:
                if not self.reader.read_flag(FLAG_CAN_USE_LIFT):
                    return "The panel wants the Lift Key — get it from the Grunt on B4F first (quest('rocket_hideout') does)."
                continue
            want = FLOOR_ROW[to_floor]
            for _ in range(8):
                cur = self._menus.menu_cursor()
                if cur == want:
                    break
                self.mgba.tap("Down" if cur < want else "Up")
                self.mgba.tick(10)
            self.mgba.tap("A")
            self.mgba.tick(40)
            for _ in range(8):                              # the lift shakes for a few seconds; the panel's text clears
                self._advance_to_control(tries=20)
                self.mgba.tick(30)
            out = self._walk_to(*ELEVATOR_DOOR)             # the door: a dynamic warp to the chosen floor
            if tuple(self.reader.read_current_map()) != ELEVATOR:
                return None
            if "battle" in out.lower():
                return out
        return f"The elevator didn't take you to {to_floor} — call {call} again."

    def _get_silph_scope(self, auto_trainers: bool = False) -> str:
        call = "quest('rocket_hideout')"
        if self._has_silph_scope() and tuple(self.reader.read_current_map()) not in HIDEOUT_MAPS:
            return "You already have the Silph Scope — the Pokémon Tower in Lavender Town can be cleared now."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        poster_tries = door_passes = 0
        for _ in range(40):
            here = tuple(self.reader.read_current_map())
            if (b := self._quest_battle(call, "the Rocket Hideout")):
                return b
            have_scope = self._has_silph_scope()

            # ── Game Corner: beat the Grunt, press the poster ───────────────────────────────────────────────────────
            if here == GAME_CORNER and not self.reader.read_flag(FLAG_OPENED_ROCKET_HIDEOUT) and not have_scope:
                if self._rocket_at(11, 2):
                    if not self._press_on_tile(*GRUNT_STAND):
                        if (b := self._quest_battle(call, "the Game Corner Grunt")):
                            return b
                        return "Couldn't reach the Rocket Grunt in the Game Corner — walk_to (11,3), face up, press A."
                    if (b := self._hideout_fight(call, "the Game Corner Grunt", auto_trainers)):
                        return b
                    continue
                poster_tries += 1
                if poster_tries > 4:
                    return "Couldn't press the poster at (11,1) — walk_to (11,2), face up, press A."
                self._press_on_tile(*POSTER_STAND)
                continue

            if here not in HIDEOUT_MAPS and not self.reader.read_flag(FLAG_OPENED_ROCKET_HIDEOUT) and not have_scope:
                if (msg := self._hideout_travel("Celadon Game Corner", GAME_CORNER, call, auto_trainers)):
                    return msg
                continue

            # ── done: out of the hideout ────────────────────────────────────────────────────────────────────────────
            if have_scope:
                if here == HIDEOUT_B4F and b4f_east(*self.reader.read_player_pos()):
                    if (msg := self._walk_into_elevator(call)):
                        return msg
                    continue
                if here == ELEVATOR:
                    if (msg := self._ride_elevator("B1F", call)):
                        return msg
                    continue
                if here == HIDEOUT_B1F and self.reader.read_player_pos()[1] >= 21 and not self._route_exists(B1F_EXIT):
                    # The elevator lands in B1F's walled-off south wing: the barrier at (20..21,19..20) opens when the Grunt at
                    # (21,27) is beaten.
                    if self._rocket_at(*B1F_GRUNT) and self._press_on_tile((B1F_GRUNT[0], B1F_GRUNT[1] - 1), "Down"):
                        if (b := self._hideout_fight(call, "the Grunt at the elevator", auto_trainers)):
                            return b
                        continue
                    return "The way out of B1F is shut and the Grunt at (21,27) isn't reachable — beat him (face down from (21,26)), then call quest('rocket_hideout')."
                if here in HIDEOUT_MAPS:
                    if (msg := self._hideout_travel("Celadon City", (3, 6), call, auto_trainers)):
                        return msg
                    continue
                try:
                    self.ltm.add_milestone("got_silph_scope", "Silph Scope from Giovanni (Rocket Hideout B4F)")
                except Exception:
                    pass
                return ("Got the Silph Scope from Giovanni! The Pokémon Tower in Lavender Town can be cleared now (Mr. Fuji on 7F "
                        "gives the Poké Flute) — heal first.")

            # ── in the hideout, no Silph Scope yet ──────────────────────────────────────────────────────────────────
            if here == ELEVATOR:
                if (msg := self._ride_elevator("B4F", call)):
                    return msg
                continue
            if here not in HIDEOUT_MAPS:                                   # the stairs are open: go down
                if (msg := self._hideout_travel("Rocket Hideout B1F", HIDEOUT_B1F, call, auto_trainers)):
                    return msg
                continue
            if not self._has_lift_key():
                if here != HIDEOUT_B4F:
                    if (msg := self._hideout_travel("Rocket Hideout B4F", HIDEOUT_B4F, call, auto_trainers)):
                        return msg
                    continue
                px, py = self.reader.read_player_pos()
                if abs(px - LIFT_GRUNT_STAND[0][0]) + abs(py - LIFT_GRUNT_STAND[0][1]) > 4:
                    # Objects only load near the camera, so the Grunt / Lift Key are invisible from the stairs: walk up first
                    # (the Grunt's line of sight starts the fight on the way)
                    self._walk_to(*LIFT_GRUNT_STAND[0])
                    if (b := self._hideout_fight(call, "the Grunt with the Lift Key", auto_trainers)):
                        return b
                    if tuple(self.reader.read_player_pos()) == (px, py):
                        return "Couldn't walk up to the Lift Key Grunt at (4,2) — walk_to (4,3), then talk to him (face up, A)."
                    continue
                if self._ball_at(3, 2):
                    if not self._press_on_tile(*LIFT_KEY_STAND):
                        if (b := self._quest_battle(call, "the Lift Key")):
                            return b
                        return "Couldn't reach the Lift Key at (3,2) — walk_to (3,3), face up, press A."
                    self._advance_to_control(tries=24)
                    continue
                if self._rocket_at(4, 2):
                    if not self._press_on_tile(*LIFT_GRUNT_STAND):
                        if (b := self._quest_battle(call, "the Grunt with the Lift Key")):
                            return b
                        return "Couldn't reach the Grunt at (4,2) — walk_to (4,3), face up, press A."
                    if (b := self._hideout_fight(call, "the Grunt with the Lift Key", auto_trainers)):
                        return b
                    continue
                return "Looked for the Lift Key on B4F but didn't find it — call quest('rocket_hideout') again."
            # have the Lift Key, no scope: Giovanni's half of B4F
            if here == HIDEOUT_B4F and b4f_east(*self.reader.read_player_pos()):
                px, py = self.reader.read_player_pos()
                if abs(px - GIOVANNI_STAND[0][0]) + abs(py - GIOVANNI_STAND[0][1]) > 5:
                    out = self._walk_to(*GIOVANNI_STAND[0])
                    if (b := self._hideout_fight(call, "the Grunts guarding Giovanni", auto_trainers)):
                        return b
                    if tuple(self.reader.read_player_pos()) != (px, py):
                        continue                                    # moved: keep going
                    # No way through: Giovanni's room is walled off until BOTH Grunts at (16,14) and (19,14) are beaten
                    # (the barrier at (17..18,12..13) opens then). Go and fight whichever is left.
                    if (px, py) != DOOR_GRUNT_APPROACH:
                        self._walk_to(*DOOR_GRUNT_APPROACH)
                        if (b := self._hideout_fight(call, "the Grunts guarding Giovanni", auto_trainers)):
                            return b
                    door_passes += 1
                    if door_passes > 3:
                        return f"Couldn't get to Giovanni's room ({out}) — beat the two Grunts at (16,14) and (19,14), then walk_to (19,5)."
                    for (gx, gy) in DOOR_GRUNTS:                 # a beaten Grunt only repeats his post-battle line: the next one
                        if not self._rocket_at(gx, gy):          # (or the retry at the top of the loop) finds the barrier open
                            continue
                        if not self._press_on_tile((gx, gy + 1), "Up"):
                            if (b := self._quest_battle(call, "the Grunts guarding Giovanni")):
                                return b
                            continue
                        if (b := self._hideout_fight(call, "the Grunts guarding Giovanni", auto_trainers)):
                            return b
                    continue
                if self.reader.read_objects_by_gfx([GIOVANNI_GFX]):
                    if not self._press_on_tile(*GIOVANNI_STAND):
                        if (b := self._quest_battle(call, "Giovanni's room")):
                            return b
                        return "Couldn't reach Giovanni at (19,4) — walk_to (19,5), face up, press A."
                    if (b := self._hideout_fight(call, "Giovanni", auto_trainers)):
                        return b
                    continue
                if self._ball_at(20, 5):
                    self._press_on_tile(*SCOPE_STAND)
                    self._advance_to_control(tries=24)
                    continue
                return "Giovanni is gone but the Silph Scope isn't in the bag — call quest('rocket_hideout') again."
            # …which is reached through the elevator, entered from B2F or B1F
            if here in ELEVATOR_DOORS and (here != HIDEOUT_B1F or self._route_exists(ELEVATOR_DOORS[here])):
                # (B1F's door sits in the south wing, walled off until the Grunt at (21,27) is beaten: B2F's door is reached through
                # the spinner maze instead)
                if (msg := self._walk_into_elevator(call)):
                    return msg
                continue
            if (msg := self._hideout_travel("Rocket Hideout B2F", HIDEOUT_B2F, call, auto_trainers)):
                return msg
        return "Made progress in the Rocket Hideout — call quest('rocket_hideout') again to continue (it resumes)."

    def _walk_into_elevator(self, call: str):
        """Step onto the elevator door of this floor. None = now inside the elevator; else a message."""
        here = tuple(self.reader.read_current_map())
        door = ELEVATOR_DOORS.get(here)
        if here == HIDEOUT_B4F:                                              # B4F's south corridor door
            door = (20, 23)
        if door is None:
            return f"No elevator door known on this floor — call {call} again."
        out = ""
        for _ in range(5):                       # a long spinner route is several walk_to calls; stop only when one makes no progress
            before = tuple(self.reader.read_player_pos())
            out = self._walk_to(*door)
            if tuple(self.reader.read_current_map()) == ELEVATOR:
                return None
            if (b := self._quest_battle(call, "the elevator")):
                return b
            if tuple(self.reader.read_player_pos()) == before:
                break
        return f"Couldn't reach the elevator door at {door}: {out}"

"""quest('pokemon_mansion'): the Secret Key on Pokémon Mansion B1F (Cinnabar Island).

The Mansion's barriers hang on ONE global statue switch (FLAG_POKEMON_MANSION_SWITCH_STATE 0x26C): pressing a statue on any floor flips it and
every floor swaps its barrier tiles. knowledge.mansion_route solves the floors + switch as a search (decomp data via tools/gen_mansion.py); this
driver executes its FIRST action (walk to a tile / press a statue / take a stairs), re-reads the real state and plans again, so a trainer in the
way or a dropped input costs only a re-plan. The key itself is an item ball at B1F (5,7) (key item 351); the Cinnabar Gym's door needs it."""
from game.state import GameContext
from knowledge.mansion_data import FLOORS
from knowledge.mansion_route import SECRET_KEY_BALL, plan

MANSION_1F = (1, 59)
SECRET_KEY_ITEM = 351
FLAG_SWITCH_STATE = 0x26C


class MansionMixin:
    def _has_secret_key(self) -> bool:
        return SECRET_KEY_ITEM in self.reader.read_key_items()

    _STEP = {(0, -1): "Up", (0, 1): "Down", (-1, 0): "Left", (1, 0): "Right"}

    def _take_warp(self, pos, tile, button, here) -> None:
        """From the tile BESIDE `tile` (the planner stands us there): step onto it, then — for stairs / arrow warps, which are directional — hold the
        warp's own button while standing on it (the game's TryArrowWarp wants the player FACING it and holding it). A hole (button None) just
        needs the step. walk_to is not used for the last step: it 'nudges' off a door tile, which is exactly the wrong thing here."""
        d = (tile[0] - pos[0], tile[1] - pos[1])
        if d not in self._STEP:
            self._walk_far(tile)                                           # not beside it (a re-plan moved us): get there first
            return
        self.mgba.hold(self._STEP[d], 18)
        self.mgba.tick(30)
        if button and tuple(self.reader.read_current_map()) == here and self.reader.detect_context() == GameContext.OVERWORLD \
                and tuple(self.reader.read_player_pos()) == tuple(tile):
            self.mgba.hold(button, 20)
            self.mgba.tick(72)

    def _mansion_walk(self, goal, floor=None) -> bool:
        """Get to (or beside) `goal` on THIS floor when the live barriers cut the way: the statue switch + stairs are a search (knowledge.mansion_route),
        so any travel inside the Mansion — heal(), go_to a town, a fled battle — can leave it, not just the Secret Key quest. Returns True if it acted."""
        from knowledge.mansion_route import plan
        cur = tuple(self.reader.read_current_map())
        floor0 = tuple(floor) if floor else cur                      # the floor `goal` is on (default: this one)
        if cur not in FLOORS or floor0 not in FLOORS:
            return False
        from knowledge.mansion_data import WARPS
        start = (tuple(self.reader.read_player_pos()), 1 if self.reader.read_flag(FLAG_SWITCH_STATE) else 0)
        exits = [tuple(goal)]
        if WARPS.get((floor0, *goal), "x") is None:        # the target is a way OUT: any of the floor's exits will do (one may be walled off right now)
            exits += [(x, y) for (f, x, y), v in WARPS.items() if f == floor0 and v is None and (x, y) != tuple(goal)]
        gx, gy = exits[0]
        for ex in exits:
            if plan(cur, start[0], start[1], goal=lambda fl, x, y, ex=ex: fl == floor0 and abs(x - ex[0]) + abs(y - ex[1]) <= 1) is not None:
                gx, gy = ex
                break

        def near(fl, x, y):
            return fl == floor0 and abs(x - gx) + abs(y - gy) <= 1

        acted = self._mansion_exec(near)
        if acted and tuple(self.reader.read_current_map()) == floor0 \
                and abs(self.reader.read_player_pos()[0] - gx) + abs(self.reader.read_player_pos()[1] - gy) <= 1:
            self._in_puzzle = True
            try:
                self._walk_to(gx, gy)                                          # step through the exit we could reach
            finally:
                self._in_puzzle = False
        return acted

    def _mansion_exec(self, near) -> bool:
        """Run the Mansion planner's first actions (walk / press a statue / take a stairs or hole), re-planning after each, until `near(floor, x, y)` holds
        or something (a battle, a stuck tile) stops it. True if it acted."""
        from knowledge.mansion_route import plan
        acted, last, stuck = False, None, 0
        for _ in range(40):
            here = tuple(self.reader.read_current_map())
            if here not in FLOORS or self.reader.detect_context() != GameContext.OVERWORLD:
                break
            pos = tuple(self.reader.read_player_pos())
            flag = 1 if self.reader.read_flag(FLAG_SWITCH_STATE) else 0
            actions = plan(here, pos, flag, goal=near)
            if not actions:                                                   # unreachable, or already beside it: the ordinary walk takes over
                break
            state = (here, pos, flag, actions[0])
            stuck = stuck + 1 if state == last else 0
            last = state
            if stuck >= 3:
                break
            kind = actions[0][0]
            self._in_puzzle = True
            try:
                if kind == "goto":
                    self._walk_far(actions[0][2])
                elif kind == "press":
                    self._press_on_tile(actions[0][2], actions[0][3], yesno=True, idle=True)
                else:
                    _k, _floor, tile, button = actions[0]
                    self._take_warp(pos, tile, button, here)
            finally:
                self._in_puzzle = False
            acted = True
        return acted

    def _mansion_to_floor(self, floor) -> bool:
        """Travel between two Mansion floors with the Mansion's own planner (stairs, holes and the statue switch, barriers as they are NOW). go_to's generic
        warp graph knows none of that: after a wild battle on 2F it routed back DOWN to 1F (the shortest hop count to B1F), the planner then led up again,
        and the trip ping-ponged between floors (watched run, 2026-11-22). True if it acted."""
        floor = tuple(floor)
        if tuple(self.reader.read_current_map()) == floor or floor not in FLOORS:
            return False
        return self._mansion_exec(lambda fl, x, y: fl == floor)

    def _mansion_leave(self) -> bool:
        """Out of the Mansion by whichever 1F exit the switch lets us reach (see _mansion_walk). True if it acted."""
        from knowledge.mansion_data import WARPS
        exits = [(x, y) for (f, x, y), v in WARPS.items() if f == MANSION_1F and v is None]
        return bool(exits) and self._mansion_walk(exits[0], floor=MANSION_1F)

    def _get_secret_key(self, auto_trainers: bool = False) -> str:
        call = "quest('pokemon_mansion')"
        if self._has_secret_key():
            return "You already have the Secret Key — Cinnabar Gym's door is open: quest('blaine')."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        stuck, last = 0, None
        for _ in range(80):
            if (b := self._quest_battle(call, "Pokémon Mansion")):
                return b
            if self._has_secret_key():
                break
            here = tuple(self.reader.read_current_map())
            if here not in FLOORS:
                if (msg := self._hideout_travel("Pokemon Mansion 1F", MANSION_1F, call, auto_trainers)):
                    return msg
                continue
            pos = tuple(self.reader.read_player_pos())
            flag = 1 if self.reader.read_flag(FLAG_SWITCH_STATE) else 0
            actions = plan(here, pos, flag)
            if actions is None:
                return ("No route to the Secret Key from here with the barriers as they are — something (a trainer, a boulder) may be in the way. "
                        f"Fight / clear it, then call {call} again.")
            if not actions:                                                   # standing beside the key's item ball
                _names, problem = self._pick_ball(*SECRET_KEY_BALL)
                if problem and not self._has_secret_key():
                    return f"Couldn't pick up the Secret Key: {problem}."
                continue
            state = (here, pos, flag, actions[0])
            stuck = stuck + 1 if state == last else 0
            last = state
            if stuck >= 4:
                return f"Stuck at {pos} on {here}: couldn't do {actions[0]} — call {call} again, or do it by hand (walk_to / face / A)."
            kind = actions[0][0]
            if kind == "goto":
                out = self._walk_far(actions[0][2])
                if tuple(self.reader.read_player_pos()) == pos and "battle" not in out.lower() and "dialog" not in out.lower():
                    stuck += 1
            elif kind == "press":
                _f, _floor, stand, face = actions[0][1], actions[0][1], actions[0][2], actions[0][3]
                self._press_on_tile(stand, face, yesno=True, idle=True)
            else:                                                            # warp: step onto the tile, then press its button ON it
                _k, _floor, tile, button = actions[0]
                self._take_warp(pos, tile, button, here)
        if not self._has_secret_key():
            return f"Made progress in the Mansion — call {call} again to continue (it resumes)."
        return "Got the Secret Key. Cinnabar Gym's door opens with it: quest('blaine') (Fire — bring Water / Ground)."

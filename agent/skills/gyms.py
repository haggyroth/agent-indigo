"""Puzzle-gym solvers used by challenge_leader: Saffron's teleport pads and Blaine's quiz doors.

Saffron (14,3): 30 pads, each teleporting to a partner pad of the same map (knowledge.gym_pads); the plan is a short chain of "walk beside a pad,
step on it". Cinnabar (12,0): six quiz machines — answering one correctly (YES / NO per the decomp) opens a door; a wrong answer starts a trainer
fight. Fuchsia's invisible walls and Viridian's spinners need nothing extra (real collisions; walk_to's spinner planner)."""
from knowledge.gym_pads import SABRINA_PADS, plan

SAFFRON_GYM, CINNABAR_GYM = (14, 3), (12, 0)
_STEP = {(0, -1): "Up", (0, 1): "Down", (-1, 0): "Left", (1, 0): "Right"}
# (machine tile left, machine tile right, answer YES?, FLAG_CINNABAR_GYM_QUIZ_n) from CinnabarIsland_Gym scripts; pressed from the tile SOUTH, facing up
BLAINE_QUIZ = (((22, 10), (23, 10), True, 0x265), ((15, 2), (16, 2), False, 0x267), ((13, 10), (14, 10), False, 0x268),
               ((13, 17), (14, 17), False, 0x269), ((1, 18), (2, 18), True, 0x26A), ((1, 10), (2, 10), False, 0x26B))


class GymPuzzleMixin:
    def _gym_puzzle(self, cur, approach):
        """Prepare the way to the Leader in a puzzle gym. None = ready (walk on); else a message for the model (a battle, or why not)."""
        if tuple(cur) == SAFFRON_GYM:
            return self._saffron_pads(approach)
        if tuple(cur) == CINNABAR_GYM:
            return self._blaine_quiz(approach)
        return None

    def _live_grid(self):
        self.tilemap.refresh()
        grid, w, h = self.tilemap.passable_grid()
        return grid, w, h

    def _saffron_pads(self, approach):
        call = "challenge_leader()"
        for _ in range(60):
            if (b := self._quest_battle(call, "the gym trainers")):
                return b
            pos = tuple(self.reader.read_player_pos())
            if pos == tuple(approach):
                return None
            grid, w, h = self._live_grid()
            if grid is None:
                self.mgba.tick(20)
                continue
            npcs = self._npc_tiles()
            passable = lambda x, y: 0 <= x < w and 0 <= y < h and grid[y][x] and (x, y) not in npcs and (x, y) not in SABRINA_PADS   # noqa: E731
            actions = plan(pos, tuple(approach), passable, SABRINA_PADS)
            if actions is None:
                return "No way to Sabrina through the teleport pads from here (a trainer in the way?) — fight / clear it, then call challenge_leader() again."
            kind, tile = actions[0]
            if kind == "goto":
                self._walk_avoid = set(SABRINA_PADS)
                try:
                    out = self._walk_far(tile)
                finally:
                    self._walk_avoid = None
                if tuple(self.reader.read_player_pos()) == pos and "battle" not in out.lower() and "dialog" not in out.lower():
                    return f"Couldn't walk to {tile} in Saffron Gym ({out})."
            else:                                                            # a pad: step onto it from the tile beside it
                d = (tile[0] - pos[0], tile[1] - pos[1])
                if d not in _STEP:
                    self._walk_far(tile)
                    continue
                self.mgba.hold(_STEP[d], 18)
                self.mgba.tick(70)                                           # the teleport's fade
        return "Still working through Saffron Gym's pads — call challenge_leader() again to continue."

    def _blaine_quiz(self, approach):
        """Answer the quiz machines until a route to Blaine exists."""
        call = "challenge_leader()"
        for _ in range(14):
            if (b := self._quest_battle(call, "the gym trainers")):
                return b
            if self._route_exists_to(approach):
                return None
            todo = [q for q in BLAINE_QUIZ if not self.reader.read_flag(q[3])]
            reachable = []
            for left, right, answer_yes, flag in todo:
                for mx, my in (left, right):
                    stand = (mx, my + 1)
                    if self._route_exists_to(stand):
                        reachable.append((abs(stand[0] - self.reader.read_player_pos()[0]) + abs(stand[1] - self.reader.read_player_pos()[1]),
                                          stand, answer_yes, flag))
            if not reachable:
                return "Every quiz machine in reach is answered but Blaine is still shut off — fight the trainers (or walk_to the next machine) and call challenge_leader() again."
            _d, stand, answer_yes, flag = min(reachable)
            self._walk_far(stand)
            if (b := self._quest_battle(call, "the gym trainers")):
                return b
            if tuple(self.reader.read_player_pos()) != stand:
                continue
            self.mgba.tap("Up")
            self.mgba.tick(8)
            self.mgba.tap("A")
            self.mgba.tick(40)
            self._answer_quiz(answer_yes)
            for _ in range(12):
                if self.reader.read_flag(flag):
                    break
                self._advance_to_control(tries=30)
            self._advance_to_control(tries=24)
        return "Still working through Blaine's quiz — call challenge_leader() again to continue."

    RULES_PAGES = 5            # after the talk press: "Pokémon Quiz!" / "Get it right…" / "Get it wrong…" / "If you want to conserve…" / "Then get it right!" → the question

    def _answer_quiz(self, yes: bool) -> bool:
        """The machine was just pressed (its first page is up). Page through the rules (always the same five A presses — pressing A while the
        QUESTION prints skips to its end and the next A takes the default YES: a 'Bad call'), wait for the question to finish and the YES/NO box
        to open on its own, then answer: YES = A; NO = Down, A. (Probing the cursor / screen state to find the box was unreliable.)"""
        for _ in range(self.RULES_PAGES):
            self.mgba.tap("A")
            self.mgba.tick(45)
        self.mgba.tick(170)                                                  # the question prints, then the box opens by itself
        if not yes:
            self.mgba.tap("Down")
            self.mgba.tick(14)
        self.mgba.tap("A")
        self.mgba.tick(40)
        return True

    def _route_exists_to(self, tile) -> bool:
        from game.pathfinding import find_path
        grid, w, h = self._live_grid()
        if grid is None:
            return False
        npcs = self._npc_tiles()
        tile = tuple(tile)
        return find_path(tuple(self.reader.read_player_pos()), tile, lambda x, y: grid[y][x] and ((x, y) not in npcs or (x, y) == tile), w, h) is not None

"""quest('silph_co'): Silph Co. in Saffron City — the Card Key, the Lapras, Giovanni and the Master Ball.

Eleven floors joined by stairs and teleport pads, with card-key doors. knowledge.silph_route solves the building as a search over (floor, tile)
(decomp data via tools/gen_silph.py); this driver executes its FIRST action (walk / unlock a door / take a stairs or pad), re-reads the real state
(which doors are open, who is in the way) and plans again, so a Rocket or a dropped input only costs a re-plan. Order:
  1. the Card Key — an item ball on 5F at (22,21) (key item 355; FLAG_HIDE_SILPH_CO_5F_CARD_KEY 0x192 once taken) — the doors need it;
  2. the Lapras — the worker at 7F (0,7) gives a level-25 one (FLAG_GOT_LAPRAS_FROM_SILPH 0x246); the rival's trigger tiles (2,4)/(2,5) sit beside him;
  3. Giovanni — stepping on 11F (5,15) or (6,15) starts the scene and the battle (FLAG_HIDE_SAFFRON_ROCKETS 0x3E is set when it ends);
  4. the President at 11F (9,9) gives the Master Ball (FLAG_GOT_MASTER_BALL_FROM_SILPH 0x250)."""
from game.state import GameContext
from knowledge import silph_route as route
from knowledge.silph_data import FLOORS

CARD_KEY_ITEM = 355
FLAG_GIOVANNI_DONE = 0x3E            # FLAG_HIDE_SAFFRON_ROCKETS, set at the end of the 11F scene
FLAG_LAPRAS, FLAG_MASTER_BALL = 0x246, 0x250
FLAG_RESCUED_FUJI = 0x23C            # the Saffron door guard falls asleep (stops blocking the door) once Fuji is rescued
GIOVANNI_TILES = {route.SILPH_11F: {(5, 15), (6, 15)}}
_STEP = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}


class SilphMixin:
    def _has_card_key(self) -> bool:
        return CARD_KEY_ITEM in self.reader.read_key_items()

    def _silph_open_flags(self) -> frozenset:
        return frozenset(flag for f in FLOORS.values() for flag, _t in f["doors"] if self.reader.read_flag(flag))

    def _silph_goal(self, has_key: bool):
        """(stage name, {floor: goal tiles}) for what is still to do, or (None, None) when everything is done."""
        if not has_key and not self.reader.read_flag(FLAG_MASTER_BALL):
            return "the Card Key", {route.SILPH_5F: {t for t, _f in route.beside(route.CARD_KEY_BALL)}}
        if not self.reader.read_flag(FLAG_LAPRAS):
            return "the Lapras", {route.SILPH_7F: {t for t, _f in route.beside(route.LAPRAS_WORKER)}}
        if not self.reader.read_flag(FLAG_GIOVANNI_DONE):
            return "Giovanni", GIOVANNI_TILES
        if not self.reader.read_flag(FLAG_MASTER_BALL):
            return "the President", {route.SILPH_11F: {t for t, _f in route.beside(route.PRESIDENT)}}
        return None, None

    def _silph_talk(self, stand, face, done_flag) -> bool:
        """Walk to `stand`, face `face`, press A and run the talk to its end, answering NO to a nickname box. True once `done_flag` is set."""
        self._in_puzzle = True
        try:
            for _ in range(3):
                self._walk_to(*stand)
                if tuple(self.reader.read_player_pos()) == tuple(stand):
                    break
        finally:
            self._in_puzzle = False
        if tuple(self.reader.read_player_pos()) != tuple(stand):
            return False
        self.mgba.tap(face)
        self.mgba.tick(8)
        self.mgba.tap("A")
        self.mgba.tick(30)
        for _ in range(40):
            if self.reader.read_flag(done_flag) and self.reader.detect_context() == GameContext.OVERWORLD:
                break
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                break
            if self._menus.choice_live():
                self._menus.answer_prompt("no")                  # 'Give it a nickname?'
            else:
                self.mgba.tap("A")
            self.mgba.tick(20)
        self._advance_to_control(tries=20)
        return bool(self.reader.read_flag(done_flag))

    def _get_silph_co(self, auto_trainers: bool = False) -> str:
        call = "quest('silph_co')"
        if self.reader.read_flag(FLAG_MASTER_BALL) and self.reader.read_flag(FLAG_LAPRAS):
            return "Silph Co. is cleared — Giovanni is beaten and you have the Master Ball and the Lapras. Saffron's Gym is open: quest('sabrina')."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if not self.reader.read_flag(FLAG_RESCUED_FUJI):
            return "A Rocket guard blocks Silph Co.'s door until Mr. Fuji is rescued from Pokémon Tower 7F: quest('pokemon_tower')."
        stuck, last = 0, None
        for _ in range(120):
            if (b := self._hideout_fight(call, "Silph Co.", auto_trainers)):
                return b
            if self.reader.detect_context() != GameContext.OVERWORLD:
                self._advance_to_control(tries=30)
            has_key = self._has_card_key()
            stage, goal = self._silph_goal(has_key)
            if stage is None:
                break
            here = tuple(self.reader.read_current_map())
            if here not in FLOORS:
                if (msg := self._hideout_travel("Silph Co. 1F", route.SILPH_1F, call, auto_trainers)):
                    return msg
                continue
            pos = tuple(self.reader.read_player_pos())
            opened = self._silph_open_flags()
            actions = route.plan(here, pos, opened, route.reach(goal), has_key)
            if actions is None:
                return (f"No route to {stage} from {pos} on floor {FLOORS[here]['name']} with the doors as they are — a trainer or worker may be in the way. "
                        f"Clear it, then call {call} again.")
            if not actions:                                                   # standing at the goal
                if stage == "the Card Key":
                    _n, problem = self._pick_ball(*route.CARD_KEY_BALL)
                    if problem and not self._has_card_key():
                        return f"Couldn't pick up the Card Key: {problem}."
                elif stage == "the Lapras":
                    if not self._silph_talk(pos, dict(route.beside(route.LAPRAS_WORKER)).get(pos, "Left"), FLAG_LAPRAS):
                        if (b := self._hideout_fight(call, "the rival", auto_trainers)):
                            return b
                        return "Couldn't get the Lapras from the worker at 7F (0,7) — walk_to (1,7), face left, press A (answer NO to the nickname)."
                elif stage == "the President":
                    if not self._silph_talk(pos, dict(route.beside(route.PRESIDENT)).get(pos, "Up"), FLAG_MASTER_BALL):
                        return "Couldn't get the Master Ball from the President at 11F (9,9) — walk_to (9,10), face up, press A."
                else:                                                         # Giovanni's tiles: the scene starts a few frames AFTER the step
                    self.mgba.tick(90)
                    self._advance_to_control(tries=40)
                    stuck += 1
                    if stuck >= 6:
                        return ("Stood on Giovanni's trigger tile (11F) but his scene never started — step off and back on, or walk to "
                                f"Giovanni at (6,11) and talk. Then call {call} again.")
                continue
            state = (here, pos, opened, actions[0])
            stuck = stuck + 1 if state == last else 0
            last = state
            if stuck >= 4:
                return f"Stuck at {pos} on {FLOORS[here]['name']}: couldn't do {actions[0]} — call {call} again, or do it by hand (walk_to / face / A)."
            kind = actions[0][0]
            if kind == "goto":
                self._walk_far(actions[0][2])
            elif kind == "unlock":
                _k, _fl, stand, face = actions[0]
                self._press_on_tile(stand, face)
            else:                                                             # warp: step onto the tile, then press its button ON it
                _k, _fl, tile, button = actions[0]
                self._take_warp(pos, tile, button, here)
        stage, _g = self._silph_goal(self._has_card_key())
        if stage is not None:
            return f"Made progress in Silph Co. (next: {stage}) — call {call} again to continue (it resumes)."
        return ("Silph Co. is cleared: Giovanni beaten, Master Ball in the bag (keep it for a legendary), Lapras on your team. "
                "Saffron's Gym is open now: quest('sabrina').")

"""quest('zapdos') / quest('articuno'): the legendary birds — travel in, walk up to the bird, press A, and hand the (one-shot) battle to the model.

Decomp: each bird is an object on its map; talking to it plays "Gyaoo!" and starts a L50 legendary battle (StartLegendaryBattle). Win / run / teleport all REMOVE it (EventScript_RemoveStaticMon /
MonFlewAway) — only a catch keeps it, and losing leaves it there. So this is the one-shot protocol (knowledge.one_shot): the model catches it with the Master Ball or Ultra Balls after the
auto-saved battle-start state (slot 9).

* Zapdos: Power Plant (1, 95) at (5,11), across Route 10's water (Surf). FLAG_FOUGHT_ZAPDOS (0x2BF) is set when the fight ends.
* Articuno: Seafoam Islands B4F (1, 87) at (9,2). B4F is swept by strong currents until two boulders from B3F's south-west room have fallen through its holes (knowledge.seafoam_route solves the
  pushes); re-entering B4F then swaps in the calm layout and Surf reaches the platform. FLAG_FOUGHT_ARTICUNO is 0x2BE."""
from game.constants import Addr
from game.state import GameContext
from knowledge import seafoam_data as sd
from knowledge import seafoam_route as sr

POWER_PLANT = (1, 95)
MT_EMBER_SUMMIT, MOLTRES_TILE, FLAG_FOUGHT_MOLTRES, FLAG_HIDE_MOLTRES, MOLTRES = (1, 101), (9, 6), 0x2BD, 0x052, 146
CERULEAN_CAVE_B1F, MEWTWO_TILE, FLAG_FOUGHT_MEWTWO, FLAG_HIDE_MEWTWO, MEWTWO = (1, 74), (7, 12), 0x2BC, 0x081, 150
FLAG_NETWORK_MACHINE, FLAG_WORLD_MAP_ONE_ISLAND = 0x844, 0x89B
ZAPDOS_TILE = (5, 11)
FLAG_FOUGHT_ZAPDOS, FLAG_HIDE_ZAPDOS = 0x2BF, 0x05D
ZAPDOS, ARTICUNO = 145, 144
FLAG_FOUGHT_ARTICUNO, FLAG_HIDE_ARTICUNO = 0x2BE, 0x082
SURF_MOVE, STRENGTH_MOVE = 57, 70
_STEP = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}


class LegendsMixin:
    def _engage_legend(self, call: str, name: str, species: int, tile: tuple, where: tuple, avoid=()) -> str:
        """On the bird's map: walk up to it, face it, A through "Gyaoo!" until the battle starts, wait for the real foe to load, and hand the fight over.
        `avoid` = ladder / hole tiles the walk must not cross (B4F's ladder sits on the shore of the way to Articuno)."""
        self._walk_avoid = set(avoid) or None
        try:
            return self._engage_legend_walk(call, name, species, tile, where)
        finally:
            self._walk_avoid = None

    def _engage_legend_walk(self, call: str, name: str, species: int, tile: tuple, where: tuple) -> str:
        for _ in range(4):                                       # walk up to it (a call can stop partway)
            if self._approach_adjacent(*tile):
                break
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return self._quest_battle(call, f"a {where} Pokémon") or ""
        else:
            return f"Couldn't walk up to {name} at {tile} — walk_to next to it, face it and press A."
        px, py = self.reader.read_player_pos()
        face = self._facing_dir(px, py, *tile)
        if face:
            self.mgba.tap(face)
        for _ in range(10):                                      # A → "Gyaoo!" → A → the battle
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                break
            self.mgba.tap("A")
            self.mgba.tick(40)
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            for _ in range(20):                                  # the battle intro runs before gEnemyParty is filled: the previous fight's mon is still there until it settles
                foe = self.reader.read_enemy_lead()
                if foe and foe.species_id == species:
                    break
                self.mgba.tick(30)
            lvl = f" (L{foe.level})" if foe else ""
            return f"{name}{lvl} is in front of you — ONE-SHOT: catch it, never knock it out. " + (self._quest_battle(call, name) or "")
        return f"Stood next to {name} but the battle didn't start — face it at {tile} and press A, then call {call} again."

    def _legend_gate(self, name: str, species: int, fought: int, hidden: int):
        """None when the bird can be hunted; else the message (in a battle / already caught / gone)."""
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if self.reader.read_dex_owned(species):
            return f"You already caught {name}."
        if self.reader.read_flag(fought) or self.reader.read_flag(hidden):
            return (f"{name} is gone (it was knocked out, fled or you faced it already) and it is not in your Pokédex. A legendary appears once: "
                    "load an earlier save (the battle-start state was in slot 9) if you want to try again.")
        return None

    # ── Zapdos ─────────────────────────────────────────────────────────────────────────────────────────────────────────
    def _get_zapdos(self, auto_trainers: bool = False) -> str:
        call = "quest('zapdos')"
        if (msg := self._legend_gate("Zapdos", ZAPDOS, FLAG_FOUGHT_ZAPDOS, FLAG_HIDE_ZAPDOS)):
            return msg
        for _ in range(10):
            if tuple(self.reader.read_current_map()) == POWER_PLANT:
                break
            out = self._go_to("Power Plant", mode="yield", auto_trainers=auto_trainers, resume_call=call)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if tuple(self.reader.read_current_map()) != POWER_PLANT and any(s in out for s in ("Can't get to", "No route", "Blocked", "gated", "no walking route")):
                return f"Can't get to the Power Plant: {out}"
        if tuple(self.reader.read_current_map()) != POWER_PLANT:
            return f"Didn't reach the Power Plant yet — call {call} again to continue (it resumes)."
        return self._engage_legend(call, "Zapdos", ZAPDOS, ZAPDOS_TILE, "Power Plant")

    # ── Moltres (Sevii) and Mewtwo (Cerulean Cave) ─────────────────────────────────────────────────────────────────────
    def _get_moltres(self, auto_trainers: bool = False) -> str:
        """quest('moltres'): Mt. Ember's summit (1,101) at (9,6): ferry to One Island when you are on the mainland, travel in, walk up and hand the one-shot L50 fight over."""
        from knowledge.ferry import on_sevii
        call = "quest('moltres')"
        if (msg := self._legend_gate("Moltres", MOLTRES, FLAG_FOUGHT_MOLTRES, FLAG_HIDE_MOLTRES)):
            return msg
        if not self.reader.read_flag(FLAG_WORLD_MAP_ONE_ISLAND):
            return "Moltres lives on Mt. Ember (One Island, the Sevii Islands): quest('sevii_one_island') first (Bill's sail after Blaine, then Celio)."
        if not on_sevii(self.reader.read_current_map()):
            out = self._ferry("one")
            if not out.startswith("Sailed"):
                return f"Can't get to One Island: {out}"
        if (msg := self._go_to_map_tuple(MT_EMBER_SUMMIT, "map:1,101", call)):
            return msg
        return self._engage_legend(call, "Moltres", MOLTRES, MOLTRES_TILE, "Mt. Ember")

    def _get_mewtwo(self, auto_trainers: bool = False) -> str:
        """quest('mewtwo'): Cerulean Cave B1F (1,74) at (7,12) — open once the Network Machine is linked (the guard leaves): travel in, walk up and hand the one-shot L70 fight over."""
        call = "quest('mewtwo')"
        if (msg := self._legend_gate("Mewtwo", MEWTWO, FLAG_FOUGHT_MEWTWO, FLAG_HIDE_MEWTWO)):
            return msg
        if not self.reader.read_flag(FLAG_NETWORK_MACHINE):
            return "The Cerulean Cave guard still blocks the way: link the Network Machine first (quest('network_machine'))."
        if (msg := self._go_to_map_tuple(CERULEAN_CAVE_B1F, "map:1,74", call)):
            return msg
        return self._engage_legend(call, "Mewtwo", MEWTWO, MEWTWO_TILE, "Cerulean Cave")

    # ── Articuno ───────────────────────────────────────────────────────────────────────────────────────────────────────
    def _sf_boulders(self, here) -> list:
        """B3F boulder tiles: the decomp positions of those that haven't fallen (the floor reloads them on every entry), moved by our own pushes, plus anything the game reports."""
        live = [o for o in self.reader.read_objects_by_gfx([Addr.OBJ_GFX_BOULDER]) if 0 <= o[0] < len(sd.B3F_ROWS[0]) and 0 <= o[1] < len(sd.B3F_ROWS)]
        if self._sf_floor != here:
            self._sf_floor = here
            self._sf_known = set(sr.initial_boulders(self.reader.read_flag))
        px, py = self.reader.read_player_pos()
        kept = {k for k in self._sf_known if abs(k[0] - px) > 7 or abs(k[1] - py) > 4}
        self._sf_known = kept | set(map(tuple, live))
        return sorted(self._sf_known)

    def _sf_walk(self, x: int, y: int) -> str:
        """walk_to on B3F that never crosses the two fall holes (walkable to the tilemap) or a ladder on the way."""
        self._walk_avoid = ({*sd.B3F_HOLES, *sd.B3F_WARPS} - {(x, y)})
        try:
            return self._walk_to(x, y)
        finally:
            self._walk_avoid = None

    def _sf_push(self, stand, direction) -> None:
        """From `stand` push the boulder beside it: face it, A (the first time: 'use Strength?' → YES), then walk into it. Tracks where it went (or that it fell)."""
        self.mgba.tap(direction)
        self.mgba.tick(8)
        self.mgba.tap("A")
        self.mgba.tick(40)
        self._answer_field_yes()
        self._advance_to_control(tries=20)
        if tuple(self.reader.read_player_pos()) == tuple(stand):
            self.mgba.hold(direction, 12)                                # one step is 16 frames: a longer press starts a second one and shoves the boulder two tiles
            self.mgba.tick(30)
            dx, dy = _STEP[direction]
            old = (stand[0] + dx, stand[1] + dy)
            if tuple(self.reader.read_player_pos()) == old:              # we stepped into the boulder's tile: it moved one tile on
                self._sf_known.discard(old)
                new = (old[0] + dx, old[1] + dy)
                if new not in sd.B3F_HOLES:
                    self._sf_known.add(new)

    def _get_articuno(self, auto_trainers: bool = False) -> str:
        call = "quest('articuno')"
        if (msg := self._legend_gate("Articuno", ARTICUNO, FLAG_FOUGHT_ARTICUNO, FLAG_HIDE_ARTICUNO)):
            return msg
        if not self._knows_move(SURF_MOVE):
            return "Seafoam Islands need Surf (and Strength for its boulders): quest('surf'), then quest('strength')."
        if not self._knows_move(STRENGTH_MOVE):
            return "B3F's boulders need a Pokémon that knows Strength: quest('strength')."
        stuck, last = 0, None
        for _ in range(140):
            if (b := self._hideout_fight(call, "Seafoam Islands", auto_trainers)):
                return b
            if self.reader.detect_context() != GameContext.OVERWORLD:
                self._advance_to_control(tries=30)
            here = tuple(self.reader.read_current_map())
            pos = tuple(self.reader.read_player_pos())
            drops = sr.dropped(self.reader.read_flag)
            stopped = bool(self.reader.read_flag(sd.STOPPED_FLAG_B4F))
            if here == sr.SEAFOAM_B4F and drops >= 2 and stopped:
                return self._engage_legend(call, "Articuno", ARTICUNO, sd.ARTICUNO_TILE, "Seafoam Islands", avoid=(sd.B4F_STAIRS,))
            if here == sr.SEAFOAM_B4F:                           # up the ladder to B3F's boulder room (or, with the boulders down, to re-enter and let the current stop)
                self._walk_to(*sd.B4F_STAIRS)
                state = (here, pos)
            elif here == sr.SEAFOAM_B3F:
                state = (here, pos, drops)
                if drops >= 2:                                    # both down: back to B4F by the ladder at (12, 9), where the current is now stopped
                    self._sf_walk(*sr.B3F_ARRIVAL)
                else:
                    boulders = self._sf_boulders(here)
                    act = sr.next_push(pos, boulders)
                    if act is None:                               # not in the boulder room's half of the cave (B3F's east side): go round through B4F
                        self._sf_walk(*sd.B3F_WARPS[4])           # the ladder down at (29, 5)
                        continue
                    _k, stand, direction = act
                    state = (here, pos, tuple(boulders), act)
                    if tuple(pos) != tuple(stand):
                        self._sf_walk(*stand)
                    else:
                        self._sf_push(stand, direction)
            else:
                # outside the cave the boulder flags mean nothing (Route 20's OnTransition resets them until B4F is stopped): only the STOPPED flag lets us go straight to B4F
                target = sr.SEAFOAM_B4F if stopped else sr.SEAFOAM_B3F
                dest = "Seafoam Islands B4F" if stopped else "Seafoam Islands B3F"
                if (msg := self._hideout_travel(dest, target, call, auto_trainers)):
                    return msg
                state = (here, pos)
            stuck = stuck + 1 if state == last else 0
            last = state
            if stuck >= 5:
                return f"Stuck at {pos} on map {here} — call {call} again, or do it by hand (walk_to / use_hm('strength') / push the boulders into B3F's two holes)."
        return f"Made progress in the Seafoam Islands — call {call} again to continue (it resumes)."

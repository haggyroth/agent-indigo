"""quest('trainer_tower <single|double|knockout|mixed>'): one Trainer Tower challenge on Seven Island (#369).

From the decomp (TrainerTower_Lobby, TrainerTower_1F..8F, TrainerTower_Roof): stepping onto the lobby's trigger tile (9,7) while VAR_MAP_SCENE_TRAINER_TOWER is 0 plays the receptionist's scene — "would
you like to challenge?" (YES / NO / INFO), then the challenge list (SINGLE / DOUBLE / KNOCKOUT / MIXED / EXIT); the party is healed and the clock starts. Floors 1F-8F are all the same shape: the
stairs up are the warp at (15,6), trainers (up to three, at YOUR best level) stand in the way, and the Roof's Owner at (9,7) gives the prize (SaveBlock1 trainerTower[type].receivedPrize). The clock runs
in game time, so the call never loses time between steps. Every trainer battle is handed back to the model (there is no fleeing); calling again continues from the floor you are on."""
from game.state import GameContext

LOBBY, ROOF = (2, 10), (2, 9)
FLOORS = tuple((2, n) for n in range(1, 9))
UP_STAIRS, OWNER, ENTRY_TILE = (15, 6), (9, 7), (9, 7)
VAR_TOWER_SCENE = 0x4082                           # VAR_MAP_SCENE_TRAINER_TOWER (vars.h)
TYPES = {"single": 0, "double": 1, "knockout": 2, "mixed": 3}
TYPE_NAMES = ("Single", "Double", "Knockout", "Mixed")
TOWER_STEPS = 24                                   # floor walks per call: bounded, resumable


class TrainerTowerMixin:
    def _trainer_tower(self, arg: str = "") -> str:
        from knowledge.ferry import on_sevii
        word = str(arg or "").strip().lower().split()
        kind = TYPES.get(word[0]) if word else None
        records = self.reader.read_trainer_tower()
        won = [TYPE_NAMES[i] for i, t in enumerate(records) if t["prize"]]
        status = f"Trainer Tower prizes: {len(won)}/4" + (f" ({', '.join(won)})" if won else "") + "."
        here = tuple(self.reader.read_current_map())
        in_tower = here in FLOORS or here in (LOBBY, ROOF)
        if kind is None and not in_tower:
            return (f"{status} quest('trainer_tower <single|double|knockout|mixed>') runs one challenge: a timed climb of eight floors (up to three trainers each, at your best level) to the Owner on the roof, "
                    "no fleeing, no Exp or money. Seven Island; the Seagallop and a Rainbow Pass get you there.")
        if kind is not None and records[kind]["prize"]:
            return f"The {TYPE_NAMES[kind]} challenge is already won (its prize is in the Bag). {status}"
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first (a Trainer Tower fight cannot be fled)."
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "The Trainer Tower works from the open field — finish what is on screen first (advance_dialog / close_menus)."
        call = f"quest('trainer_tower {TYPE_NAMES[kind].lower()}')" if kind is not None else "quest('trainer_tower')"
        if not in_tower:
            if not on_sevii(here):
                out = self._ferry("seven")
                if not out.startswith("Sailed"):
                    return f"Can't get to Seven Island: {out}"
            if (msg := self._go_to_map_tuple(LOBBY, "map:2,10", call)):
                return msg
            here = LOBBY
        notes = []
        if here == LOBBY and self.reader.read_var(VAR_TOWER_SCENE) == 0:
            if kind is None:
                return "Pick the challenge: quest('trainer_tower single'), 'double', 'knockout' or 'mixed'."
            if not self._tower_start(kind):
                return f"The receptionist's scene did not start the {TYPE_NAMES[kind]} challenge — walk onto (9,7) in the lobby and answer YES, then {TYPE_NAMES[kind].upper()}; then call {call} again."
            notes.append(f"started the {TYPE_NAMES[kind]} challenge")
        return self._tower_climb(kind, notes, call, status)

    def _tower_start(self, kind: int) -> bool:
        self._walk_to(*ENTRY_TILE)                       # onto the trigger tile: the receptionist's scene plays by itself
        stage = 0
        for _ in range(60):
            if self._menus.choice_live():
                if stage == 0:
                    self.mgba.tap("A")                   # YES (first row of YES / NO / INFO)
                else:
                    for _i in range(kind):
                        self.mgba.tap("Down")
                        self.mgba.tick(12)
                    self.mgba.tap("A")
                stage += 1
                self.mgba.tick(60)
                if stage == 2:
                    break
                continue
            self.mgba.tap("A")
            self.mgba.tick(50)
        self._advance_to_control(tries=20)
        return stage == 2 and self.reader.read_var(VAR_TOWER_SCENE) == 1

    def _tower_climb(self, kind, notes: list, call: str, status: str) -> str:
        """Floor by floor: the stairs up, a trainer battle handed back, the Roof's Owner. Verified by the floor you stand on and the prize bit."""
        for _ in range(TOWER_STEPS):
            ctx = self.reader.detect_context()
            if ctx == GameContext.IN_BATTLE:
                return self._tower_wrap(notes, f"A Trainer Tower battle started — win it (use_move / switch_pokemon / use_item; there is no fleeing), then call {call} again.", status)
            if ctx != GameContext.OVERWORLD:
                self._advance_to_control(tries=20)
                continue
            here = tuple(self.reader.read_current_map())
            if here == LOBBY:
                self._walk_to(9, 2)                      # the lobby's stairs up to 1F
                if tuple(self.reader.read_current_map()) == LOBBY:
                    return self._tower_wrap(notes, f"Couldn't get from the lobby to 1F — call {call} again.", status)
            elif here in FLOORS:
                self._walk_to(*UP_STAIRS)
            elif here == ROOF:
                return self._tower_owner(kind, notes, call, status)
            else:
                return self._tower_wrap(notes, f"You are not in the Trainer Tower (map {here}).", status)
        return self._tower_wrap(notes, f"Still climbing (floor {tuple(self.reader.read_current_map())[1]}) — call {call} again.", status)

    def _tower_owner(self, kind, notes: list, call: str, status: str) -> str:
        for _ in range(4):
            if self._approach_adjacent(*OWNER):
                break
        px, py = self.reader.read_player_pos()
        if (face := self._facing_dir(px, py, *OWNER)):
            self.mgba.tap(face)
        for _ in range(30):
            self.mgba.tap("A")
            self.mgba.tick(40)
            if self._menus.choice_live():
                self._menus.answer_prompt("no")
        self._advance_to_control(tries=20)
        records = self.reader.read_trainer_tower()
        idx = kind if kind is not None else 0
        if records[idx]["prize"]:
            notes.append("the Owner gave the prize")
            return self._tower_wrap(notes, "Challenge complete — you reached the Owner on the roof. Walk out (the lobby's door) when you are ready.", self._status_after())
        return self._tower_wrap(notes, f"On the roof, but the Owner's prize did not arrive — talk to him at {OWNER} and call {call} again.", status)

    def _status_after(self) -> str:
        records = self.reader.read_trainer_tower()
        return f"Trainer Tower prizes: {sum(1 for t in records if t['prize'])}/4."

    @staticmethod
    def _tower_wrap(notes: list, lead: str, status: str) -> str:
        return (", ".join(notes).capitalize() + ". " if notes else "") + lead + " " + status

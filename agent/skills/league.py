"""quest('elite_four'): Indigo Plateau's Pokémon League — Lorelei, Bruno, Agatha, Lance, the Champion and the Hall of Fame.

From the decomp (PokemonLeague_*): the Center's north door (4,1) leads into Lorelei's room; entering a room plays a forced walk up and the door SEALS behind
you — no healing, no leaving, until the Champion. Each leader stands in the middle of the room (Lorelei / Bruno / Agatha at (6,5), Lance at (6,8), the
Champion at (6,8)); talking to one starts the battle, and winning opens the exit warp on the room's far wall. The Champion's win walks you on to the Hall of
Fame by script (Oak's speech, FLAG_SYS_GAME_CLEAR 0x82C) and then the credits. So the order is: PREP before the first door (heal, shop, save), then each
room: wait for the forced walk to end → walk to the tile in front of the leader → face + A → (the battle goes to the model, like the other quests) →
walk to the exit. The call resumes from whatever room it finds itself in."""
from agent import events
from game.state import GameContext

CENTER_1F, EXTERIOR = (13, 0), (3, 9)
FLAG_VISITED_PLATEAU = 0x899      # FLAG_VISITED_INDIGO_PLATEAU — set on the first arrival; also what unlocks it as a Fly destination
HALL_OF_FAME = (1, 80)
FLAG_GAME_CLEAR = 0x82C
FLAG_DEFEATED_CHAMP = 0x4BC
CENTER_DOOR = (4, 1)                    # the north door of the Plateau's Pokémon Center: into Lorelei's room
PLATEAU_DOOR = (11, 6)                  # the Center's door on the Exterior
# (map, defeated flag, tile in front of the leader, name, exit warp tile)
ROOMS = (
    ((1, 75), 0x4B8, (6, 6), "Lorelei", (6, 2)),
    ((1, 76), 0x4B9, (6, 6), "Bruno", (6, 2)),
    ((1, 77), 0x4BA, (6, 6), "Agatha", (6, 2)),
    ((1, 78), 0x4BB, (6, 9), "Lance", (6, 5)),
    ((1, 79), 0x4BC, (6, 9), "the Champion", (6, 2)),
)
ROOM_BY_MAP = {r[0]: r for r in ROOMS}
ITEM_LABELS_BY_ID = {24: "Revive", 19: "Full Restore"}
SAVE_SLOT = 3                            # the pre-door save. A loss needs no reload (and must not get one: it would discard the Exp the loss earned): the whiteout runs EventScript_ResetEliteFourEnd (every
                                         # FLAG_DEFEATED_* cleared), heals the party, takes some money and respawns at the Plateau's Center, so the quest just starts over


class LeagueMixin:
    def _league_prep(self, call: str) -> str:
        """Before the first door: heal, restock, save. Returns a note for the final message."""
        notes = []
        heal = self._heal()
        notes.append("healed" if heal.startswith(("Healed", "Party is already")) else f"heal: {heal}")
        try:
            from knowledge.money import treasure_value
            if treasure_value(self.reader.read_bag()):                 # the Center's clerk buys treasure too: Full Restores are ¥3000 each
                sold = self._sell()
                notes.append(sold.split(".")[0] if sold else "sold treasure")
        except Exception:
            notes.append("sell skipped")
        try:
            from knowledge.money import supply_purchases
            bought = []
            bag = self.reader.read_bag()
            for iid, qty in supply_purchases("elite_four", self.reader.read_money(), bag):      # Revives, then Full Restores, with the money we have
                res = self._shop_for(ITEM_LABELS_BY_ID[iid], qty)
                bought.append(res.split(".")[0] if res.startswith("Bought") else f"{ITEM_LABELS_BY_ID[iid]}: {res[:60]}")
            notes.append(", ".join(bought) if bought else "supplies already stocked (or no money)")
        except Exception:
            notes.append("shop skipped")
        ok = self.mgba.save_state(SAVE_SLOT)
        notes.append(f"state saved to slot {SAVE_SLOT}" if ok else "state save FAILED")
        events.emit("note", f"Elite Four prep: {', '.join(notes)}", log=False)
        return ", ".join(notes)

    def _get_elite_four(self, auto_trainers: bool = False) -> str:
        call = "quest('elite_four')"
        if self.reader.read_flag(FLAG_GAME_CLEAR) and tuple(self.reader.read_current_map()) not in (*ROOM_BY_MAP, HALL_OF_FAME):
            return "The Pokémon League is beaten — you are the Champion and the game is cleared. (Rematches are not scripted.)"
        start = tuple(self.reader.read_current_map())
        if start in ROOM_BY_MAP:
            self._league_room = start                          # remembered even when the call only says "finish the battle": a whiteout from here is a loss
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if bin(int(self.reader.read_badges()[1])).count("1") < 8:
            return "The Pokémon League's door needs all eight badges."
        prep = ""
        stuck, last = 0, None
        fly_tried = False
        for _ in range(120):
            if (b := self._hideout_fight(call, "the Pokémon League", auto_trainers)):
                return b
            if self.reader.detect_context() != GameContext.OVERWORLD:
                self._advance_to_control(tries=30)
            here = tuple(self.reader.read_current_map())
            pos = tuple(self.reader.read_player_pos())
            if here == HALL_OF_FAME or self.reader.read_flag(FLAG_DEFEATED_CHAMP):
                return self._league_finish(call)
            if self._league_room is not None and here not in ROOM_BY_MAP:
                # We were in a room and are now outside it (and not in the Hall of Fame): the only way out of a sealed room is a whiteout — the League reset and a respawn at the Center.
                self._league_room = None
                n = self.ltm.add_league_loss()
                events.emit("note", f"Elite Four: lost in the League (#{n}) — the whole League is reset", log=False)
            if here in ROOM_BY_MAP:
                _m, flag, stand, who, exit_tile = ROOM_BY_MAP[here]
                self._league_room = here
                state = (here, pos)
                stuck = stuck + 1 if state == last else 0
                last = state
                if stuck >= 5:
                    return f"Stuck in {who}'s room at {pos} — walk_to {stand if not self.reader.read_flag(flag) else exit_tile} by hand, then call {call} again."
                if self.reader.read_flag(flag):
                    self._walk_to(*exit_tile)                      # the door opened when they fell: through it
                else:
                    used = self._field_heal(max_uses=12, below=0.6) + self._field_cure() + self._field_pp()      # sealed in: the Bag is the only Center, so top the team up before this trainer
                    if used:
                        events.emit("note", f"Elite Four: healed from the Bag before {who}: {', '.join(used)}", log=False)
                    self._set_boss_lead("Gary" if who == "the Champion" else who)      # the best matchup against THIS trainer leads (not simply the strongest)
                    self._walk_to(*stand)
                    if tuple(self.reader.read_player_pos()) == stand:
                        self.mgba.tap("Up")
                        self.mgba.tick(10)
                        self.mgba.tap("A")
                        self.mgba.tick(40)
                        self._advance_to_control(tries=25)
                continue
            if here == CENTER_1F:
                if not prep:
                    prep = self._league_prep(call)
                self._walk_to(*CENTER_DOOR)
                continue
            if here == EXTERIOR:
                if (msg := self._hideout_travel("Pokemon Center", CENTER_1F, call, auto_trainers)):
                    return msg
                continue
            if not fly_tried:
                # Back from a blackout the way on is Victory Road again — whose boulder puzzles RESET when you leave the floor and which this driver cannot solve (the
                # chain looped 300 calls between Route 23 and the cave). Once the Plateau has been visited it is a Fly town: a Fly user takes the League's door directly.
                fly_tried = True
                if self.reader.read_flag(FLAG_VISITED_PLATEAU) and self._fly_to("Indigo Plateau").startswith("Flew"):
                    continue
            if (msg := self._hideout_travel("Indigo Plateau", EXTERIOR, call, auto_trainers)):
                return msg
        return f"Made progress in the Pokémon League — call {call} again to continue (it resumes from the room you are in)."

    def _league_finish(self, call: str) -> str:
        """The Champion is down: the game walks you into the Hall of Fame (Oak's speech) and rolls the credits. A and B carry it through; the flag is the proof."""
        for _ in range(60):
            if self.reader.read_flag(FLAG_GAME_CLEAR):
                break
            self.mgba.tap("A")
            self.mgba.tick(60)
        cleared = bool(self.reader.read_flag(FLAG_GAME_CLEAR))
        if cleared:
            if self.ltm.add_milestone("hall_of_fame", "beat the Pokémon League"):
                events.emit("milestone", "milestone: hall_of_fame — the Pokémon League is beaten, the game is cleared")
            return ("You beat the Champion and entered the Hall of Fame — the game is cleared (FLAG_SYS_GAME_CLEAR). The credits roll next; "
                    "after them the game may save and return you to the title or Pallet Town.")
        return f"The Champion is beaten but the Hall of Fame scene is still running — call {call} again."

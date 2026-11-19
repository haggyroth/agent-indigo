"""quest('new_game') — start the game from the title screen: the intro, the names, Oak's lab, the starter, the rival, Oak's parcel (#260, the one beat that had no driver).

    quest('new_game')                        Bulbasaur, you are RED, the rival BLUE
    quest('new_game charmander')             starter: bulbasaur | charmander | squirtle
    quest('new_game squirtle name=KYLE rival=GARY girl')

Boot the runtime to the title with START_NEW_GAME=true (no save loaded). Every phase is resumable — the driver reads what is on screen / in memory, never counts presses — so a call
that is interrupted (a battle, a long dialogue) is simply called again:

  1. title → (main menu: NEW GAME when a save exists) → the controls pages → Oak's speech → BOY/GIRL → the player's name → the rival's name → the bedroom.
     The screens are told apart by the main callback (title / main menu / Oak speech / naming / overworld) and by a live cursor menu (`choice_live`); the Oak-speech menus
     (gender, the two "NEW NAME / RED / ASH…" lists, the two Yes/No confirmations) are answered in the order they appear.
  2. the house, Pallet Town, Oak's intercept at Route 1, the lab, the starter, the rival's battle (handed to the model).
  3. Route 1 → Viridian's Poké Mart: the clerk gives Oak's Parcel → back to the lab: the Pokédex (FLAG_SYS_POKEDEX_GET) and five Poké Balls — which is what the chain's `parcel` beat checks."""
from game.constants import Addr
from game.state import GameContext

CB2_TITLE, CB2_MAIN_MENU, CB2_OAK_SPEECH = 0x08078B9D, 0x0800C2D5, 0x0812EAE9
STARTERS = {"bulbasaur": 1, "charmander": 4, "squirtle": 7}
LAB, MART = (4, 3), (5, 3)                    # PalletTown_ProfessorOaksLab, ViridianCity_Mart
OAKS_PARCEL, FLAG_POKEDEX = 349, 0x829        # ITEM_OAKS_PARCEL (a key item) / FLAG_SYS_POKEDEX_GET: what the chain's `parcel` beat checks


def parse_options(words) -> dict:
    """['squirtle', 'name=KYLE', 'rival=GARY', 'girl'] -> {'starter': 'squirtle', 'name': 'KYLE', 'rival': 'GARY', 'girl': True}."""
    o = {"starter": "bulbasaur", "name": "RED", "rival": "BLUE", "girl": False}
    for w in words:
        k, _eq, v = str(w).partition("=")
        key = k.strip().lower()
        if key in STARTERS:
            o["starter"] = key
        elif key in ("girl", "female"):
            o["girl"] = True
        elif key in ("boy", "male"):
            o["girl"] = False
        elif key in ("name", "player") and v:
            o["name"] = v.strip().upper()[:7]
        elif key == "rival" and v:
            o["rival"] = v.strip().upper()[:7]
    return o


class NewGameMixin:
    def _in_world(self) -> bool:
        return self.mgba.read8(Addr.MAP_BANK) != 0 and self.mgba.read32(Addr.GMAIN_CALLBACK2) == Addr.CB2_OVERWORLD

    def _ng_intro(self, o: dict):
        """Title → bedroom. None when the player stands in the world; else a message."""
        from game.naming import NamingDriver
        nd = NamingDriver(self.mgba)
        named = menus = 0
        for _ in range(500):
            cb2 = self.mgba.read32(Addr.GMAIN_CALLBACK2)
            if self._in_world():
                for _ in range(6):                                   # the A mashing may have played with the bedroom's NES: B clears any text
                    if self.reader.detect_context() == GameContext.OVERWORLD:
                        break
                    self.mgba.tap("B")
                    self.mgba.tick(30)
                return None
            if nd.active():                                          # the keyboard: the player's name first, the rival's second
                who, nick = ("player", o["name"]) if named == 0 else ("rival", o["rival"])
                out = nd.enter_name(nick)
                if not out.startswith("Named"):
                    nd.abort()
                    return f"Couldn't type the {who}'s name {nick!r} on the keyboard ({out}). Try plainer letters: quest('new_game name=RED rival=BLUE')."
                named += 1
                self.mgba.tick(60)
                continue
            if cb2 == CB2_MAIN_MENU:                                 # a save exists: CONTINUE is highlighted, NEW GAME is below it
                self.mgba.tap("Down")
                self.mgba.tick(12)
                self.mgba.tap("A")
                self.mgba.tick(60)
                continue
            if cb2 == CB2_OAK_SPEECH and self._menus.choice_live():  # a cursor menu inside the speech
                menus += 1
                if menus == 1 and o["girl"]:                         # the first one is BOY / GIRL; every later one wants its first row (NEW NAME / YES)
                    self.mgba.tap("Down")
                    self.mgba.tick(12)
                self.mgba.tap("A")
                self.mgba.tick(60)
                continue
            self.mgba.tap("A")                                       # the title's PRESS START, the controls pages, Oak's text
            self.mgba.tick(30)
        return "The intro didn't finish — call quest('new_game') again to continue (it resumes)."

    # ── the starter: Oak's lab ─────────────────────────────────────────────────────────────────────────────────────────
    def _ng_party(self) -> int:
        return len(self.reader.read_party())

    def _ng_choose_starter(self, o: dict):
        """In Oak's lab, party empty: walk to the ball, face it, A, YES to 'so you want X?', decline the nickname. None once the starter is in the party."""
        ball_x = {"bulbasaur": 8, "squirtle": 9, "charmander": 10}[o["starter"]]      # the balls stand on the table at (8..10, 4)
        for _ in range(4):
            if self._ng_party():
                break
            self._advance_to_control(tries=30)
            self._walk_to(ball_x, 5)
            self.mgba.tap("Up")
            self.mgba.tick(10)
            self.mgba.tap("A")
            self.mgba.tick(50)
            for _ in range(60):
                if self._ng_party() and self.reader.detect_context() == GameContext.OVERWORLD:
                    break
                if self._menus.choice_live():
                    if self._ng_party():                              # the nickname question: no
                        self.mgba.tap("Down")
                        self.mgba.tick(12)
                    self.mgba.tap("A")                                # 'So! You want the … POKéMON?' → YES
                    self.mgba.tick(50)
                else:
                    self.mgba.tap("A")
                    self.mgba.tick(30)
        if not self._ng_party():
            return f"Couldn't pick up the {o['starter'].title()} ball in Oak's lab — walk to ({ball_x},5), face up, press A and answer YES, then call quest('new_game') again."
        for _ in range(8):                                            # the rival picks his, Oak talks: B clears text without talking to anyone
            if self.reader.detect_context() == GameContext.OVERWORLD:
                break
            self.mgba.tap("B")
            self.mgba.tick(40)
        return None

    def _ng_battle(self, msg: str) -> str:
        """The rival's fight in Oak's lab opens with ~35 text boxes (his challenge, both send-outs, Oak's battle tutorial, whose own menus the move-menu check never recognises). Play them
        through here — the fight is a tutorial against a lone L5 and Oak lets you lose it — instead of handing the model a battle that every use_move call fails on."""
        if self.reader.detect_context() != GameContext.IN_BATTLE or tuple(self.reader.read_current_map()) != LAB:
            return msg
        out = self._battle_settle(max_steps=200)
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return msg + f"\n(The battle intro and Oak's tutorial were played through — {out})"
        return "Your rival's first battle (Oak's tutorial fight) is over. Call quest('new_game') again to carry on with Oak's parcel."

    def _get_new_game(self, auto_trainers: bool = False) -> str:
        call = "quest('new_game')"
        o = parse_options(self._quest_opts)
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            if tuple(self.reader.read_current_map()) != LAB:
                return "You're in a battle — finish it first."
            msg = self._ng_battle("You're in the rival's battle in Oak's lab.")          # resumed in the middle of the tutorial fight: play it out
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return msg
        if not self._in_world():
            if (msg := self._ng_intro(o)):
                return msg
        here = tuple(self.reader.read_current_map())
        if not self._ng_party():                                      # no Pokémon yet: Oak's intercept at Route 1's door, then the lab
            if here != LAB:
                for _ in range(6):
                    out = self._go_to("Route 1")                      # walking north through (12..13, 1) fires Oak's "Hey! Wait!" scene, which carries us into the lab
                    if tuple(self.reader.read_current_map()) == LAB:
                        break
                    if self.reader.detect_context() != GameContext.OVERWORLD:
                        self._advance_to_control(tries=30)
                if tuple(self.reader.read_current_map()) != LAB:
                    return f"Couldn't get to Oak's lab ({out}) — walk north out of Pallet Town and Oak stops you; then call {call} again."
            if (msg := self._ng_choose_starter(o)):
                return msg
        if self.reader.read_flag(FLAG_POKEDEX):
            return "Oak's Parcel is delivered and you have the Pokédex: the story chain starts at quest('brock')."
        # Oak's parcel: the Viridian Mart clerk hands it over the moment you walk in (a forced scene), then Oak wants it. Leaving the lab starts the rival's battle (handed to the model).
        if OAKS_PARCEL not in self.reader.read_key_items():
            if (msg := self._hideout_travel("Viridian Mart", MART, call, auto_trainers)):
                return self._ng_battle(msg)
            for _ in range(10):                                       # the clerk's scene: text, then the parcel
                if OAKS_PARCEL in self.reader.read_key_items() and self.reader.detect_context() == GameContext.OVERWORLD:
                    break
                self.mgba.tap("A")
                self.mgba.tick(40)
            if OAKS_PARCEL not in self.reader.read_key_items():
                return f"The Viridian Mart clerk didn't hand over Oak's Parcel — walk inside, talk to the clerk at (2,3), then call {call} again."
        if (msg := self._hideout_travel("Oak's Lab", LAB, call, auto_trainers)):
            return self._ng_battle(msg)
        for _ in range(6):                                            # Oak (6,3): talking to him with the parcel plays the Pokédex scene
            if self.reader.read_flag(FLAG_POKEDEX):
                break
            if not self._approach_adjacent(6, 3):
                return f"Couldn't walk up to Prof. Oak at (6,3) — talk to him with the parcel in the bag, then call {call} again."
            px, py = self.reader.read_player_pos()
            face = self._facing_dir(px, py, 6, 3)
            if face:
                self.mgba.tap(face)
            for _ in range(40):                                       # the dialogue, the rival's entrance, the Pokédex, the Poké Balls
                if self.reader.read_flag(FLAG_POKEDEX) and self.reader.detect_context() == GameContext.OVERWORLD:
                    break
                self.mgba.tap("A")
                self.mgba.tick(40)
        if not self.reader.read_flag(FLAG_POKEDEX):
            return f"Oak didn't hand over the Pokédex yet — talk to him at (6,3), then call {call} again."
        for _ in range(8):                                            # leftover text: B (A would talk to Oak again)
            if self.reader.detect_context() == GameContext.OVERWORLD:
                break
            self.mgba.tap("B")
            self.mgba.tick(40)
        lead = self.reader.read_party()[0]
        return (f"Oak's Parcel is delivered: you have the Pokédex and Poké Balls, and {lead.nickname or lead.species_name} is your partner. The Route 2 road is open — "
                "heal, then quest('brock').")

"""Story quests that gate progress and need a fixed interaction script.

quest('cut'): the S.S. Anne's Captain gives HM01 Cut. Vermilion's harbor lets you aboard with the SS Ticket;
the Captain's Office is on 2F (graph route Vermilion → Exterior → 1F → 2F → office). Talk to him (he is
seasick; the game rubs his back for you), take HM01 (flag 0x237), then teach_move('HM01'). Cut trees
that block the way (the Vermilion Gym door) are then cleared by go_to itself (see nav._go_to).

quest('ss_ticket'): Bill's Sea Cottage (Route 25). Until FLAG_GOT_SS_TICKET is set, Cerulean's south exit is
blocked by a Slowbro + Lass and its east exit by a policeman (decomp `CeruleanCity_EventScript_BlockExits`),
so nothing past Cerulean — Vermilion, Cut, Surge — is reachable. The script, from the decomp scripts
(Route25_SeaCottage/scripts.inc) and verified live:
  1. talk to Bill-as-Clefairy (YES) → he walks into the left teleporter;
  2. use the computer (stand below it, face up, A) → the cell-separation cutscene → human Bill appears;
  3. talk to human Bill → SS Ticket (key item 265, flag 0x234).
"""
from agent.skills.base import log_once
from game.state import GameContext

SS_TICKET_ITEM = 265
FLAG_GOT_SS_TICKET = 0x234
BILL_GFX, CLEFAIRY_GFX = 73, 113          # OBJ_EVENT_GFX_BILL / OBJ_EVENT_GFX_CLEFAIRY
COTTAGE = (30, 0)
FLAG_GOT_HM01 = 0x237
FLAG_GOT_HM03, FLAG_GOT_HM04 = 0x239, 0x23A
FLAG_GOT_COIN_CASE = 0x243
RESTAURANT, COIN_CASE_MAN = (10, 17), (1, 2)       # Celadon Restaurant; the man who gives the Coin Case away
COIN_CASE_SPOTS = (((2, 2), "Left"), ((1, 3), "Up"), ((1, 1), "Down"))
FLAG_GOLD_TEETH_TAKEN = 0x189             # FLAG_HIDE_SAFARI_ZONE_WEST_GOLD_TEETH: set once the item ball is picked up
SURF_MOVE_ID, STRENGTH_MOVE_ID = 57, 70
SAFARI_ENTRANCE, SAFARI_CENTER, SAFARI_WEST, SECRET_HOUSE, WARDENS_HOUSE = (11, 0), (1, 63), (1, 66), (1, 71), (11, 7)
SAFARI_TRIGGER = (4, 3)                   # the middle of three tiles in the entrance hall that start the "¥500?" dialogue
GOLD_TEETH_TILE = (28, 14)                # the item ball in Safari Zone (West)
SAFARI_FEE = 500
FUCHSIA_CITY = (3, 7)
ATTENDANT_SPOTS = (((6, 6), "Up"), ((5, 5), "Right"), ((7, 5), "Left"))     # the Secret House man stands at (6,5)
WARDEN_SPOTS = (((3, 6), "Up"), ((4, 5), "Left"), ((2, 5), "Right"))        # the Warden stands at (3,5)
FLAG_VERMILION_SWITCHES = 0x264           # FLAG_FOUND_BOTH_VERMILION_GYM_SWITCHES
CUT_MOVE_ID = 15
CAPTAIN_OFFICE = (1, 11)
CAPTAIN_SPOT = ((5, 5), "Up")             # the Captain stands at (5,4)
CLEFAIRY_SPOT = ((10, 7), "Up")           # Clefairy-Bill starts at (10,6)
COMPUTER_SPOT = ((4, 6), "Up")            # the computer is the sign at (4,5)


def trash_can_tile(can: int) -> tuple[int, int]:
    """(x, y) of Vermilion Gym trash can `can` (1..15): a 5x3 grid, ids left→right then top→bottom."""
    i = can - 1
    return 1 + 2 * (i % 5), 10 + 2 * (i // 5)


class QuestMixin:
    def _quest_battle(self, call: str, label: str) -> str | None:
        """A walk or trip inside a quest was interrupted by a battle: hand it to the model (like go_to does) and
        say which tool resumes the quest. None when no battle is up."""
        from game.constants import Addr
        if self.reader.detect_context() != GameContext.IN_BATTLE:
            return None
        trainer = bool(self.mgba.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER)
        return self._yield_encounter(label, trainer, None, call)

    def _driver_done(self) -> dict:
        """{beat key: bool} for the beats whose script has a stricter notion of done than the game's flag (Cut TAUGHT, Surf TAUGHT, out of
        the hideout) — they override the flag in the story chain."""
        from agent.skills.hideout import HIDEOUT_MAPS
        out = {"ss_ticket": self._has_ss_ticket(), "cut": self._knows_cut(), "coin_case": bool(self.reader.read_flag(FLAG_GOT_COIN_CASE)),
               "surf": self._knows_move(SURF_MOVE_ID) or bool(self.reader.read_flag(FLAG_GOT_HM03)),
               "strength": self._knows_move(STRENGTH_MOVE_ID) or bool(self.reader.read_flag(FLAG_GOT_HM04)),
               "tea": self._has_tea()}
        # still inside the hideout: quest('rocket_hideout') walks you out
        out["rocket_hideout"] = self._has_silph_scope() and tuple(self.reader.read_current_map()) not in HIDEOUT_MAPS
        return out

    def _tm_shop_note(self) -> str:
        """The TM SHOP line for team_report: the Celadon Dept. Store TMs worth buying for this team, with price ('' when none help / unreadable)."""
        from knowledge.tm_plan import line
        from knowledge.tmhm import TMHM
        try:
            owned = [TMHM[i][0] for i, _q in self.reader.read_tmhm_pocket() if i in TMHM]
            return line(self.reader.read_party(), owned, self.reader.read_money())
        except Exception:
            log_once("quests._tm_shop_note", "quests._tm_shop_note: tolerated failure (no TM shop line)")
            return ""

    def _dex_note(self) -> str:
        """The DEX line for team_report (knowledge.dex_plan): the count and the easiest next catches ('' when unreadable)."""
        from knowledge.dex_plan import dex_line
        try:
            owned = self.reader.read_dex_owned_ids()
            return dex_line(owned) if owned else ""
        except Exception:
            log_once("quests._dex_note", "quests._dex_note: tolerated failure (no dex line)")
            return ""

    def _bag_or_none(self):
        """{item id: count} for the readiness supply check, or None when the bag cannot be read (the levels are then checked alone)."""
        try:
            bag = dict(self.reader.read_bag())
            for iid in {i for i, _q in self.reader.read_items_pocket()}:           # read_bag keeps only the LAST stack of an id
                bag[iid] = sum(q for i, q in self.reader.read_items_pocket() if i == iid)
            return bag
        except Exception:
            log_once("quests._bag_or_none", "quests._bag_or_none: tolerated failure (levels only)")
            return None

    def _money_note(self) -> str:
        """The MONEY line for team_report: what the next story beat wants in yen against what we hold ('' when enough / no beat / unreadable)."""
        from knowledge.money import money_line
        from knowledge.story_beats import next_beats
        try:
            from knowledge.money import MONEY_NEEDS
            ready = [b for b in next_beats(self._story()) if b.key in MONEY_NEEDS]
            if not ready:
                return ""
            return money_line(ready[0].key, self.reader.read_money(), self.reader.read_bag(), self.reader.read_party())
        except Exception:
            log_once("quests._money_note", "quests._money_note: tolerated failure (no money line)")
            return ""

    def _story(self) -> dict:
        from agent.story import story_status
        return story_status(self.reader, self.ltm, self._driver_done())

    def _quest_tool(self, name: str = "", auto_trainers: bool = False) -> str:
        """quest(name?) — the story chain (knowledge.story_beats). No name lists every beat from the Pokédex to the Elite Four with
        ✔ done / ▶ next / … blocked; a name runs its script when it has one (ss_ticket, cut, coin_case, rocket_hideout, tea, surf,
        strength, the eight gyms…) or prints the state-aware plan (only the game start, `parcel`, is guide-only now)."""
        from knowledge import story_beats as sb
        status = self._story()
        if not str(name or "").strip():
            return sb.listing(status)
        head, *self._quest_opts = str(name).split()                 # 'new_game squirtle name=KYLE': the words after the name are the driver's options
        name = head
        beat = sb.resolve(name)
        if beat is None:
            return f"No quest called {name!r}. " + sb.listing(status)
        if status.get(beat.key) == "done":
            return f"{beat.title}: already done."
        if not beat.driver:
            return "No script for this one yet — here is the plan:\n" + sb.plan(beat, status)
        if beat.driver in ("brock", "misty", "surge", "erika", "koga", "sabrina", "blaine", "giovanni") and status.get(beat.key) == "blocked":
            return "Not yet — " + sb.plan(beat, status)                     # a locked Gym: say what comes first instead of walking up to the guard
        legacy_needs = {"cut": ("ss_ticket",)}
        missing = [n for n in legacy_needs.get(beat.key, ()) if status.get(n) != "done"]
        if missing:
            return f"quest('{beat.key}') needs quest('{missing[0]}') first."
        from knowledge.beat_readiness import readiness
        if beat.key not in self._ready_warned and (warn := readiness(beat.key, self.reader.read_party(), self._bag_or_none())):
            self._ready_warned.add(beat.key)            # once per beat: a second call (or a resumed one) goes ahead
            return warn
        if beat.key == "victory_road" and "victory_road:fly" not in self._ready_warned and not self.reader.read_flag(0x899) and not self._fly_ready():
            self._ready_warned.add("victory_road:fly")
            return ("Past Victory Road there is no grass to train on and no quick way home: the Plateau's Center is the only one, and the way back south is the cave's puzzle in reverse. "
                    "Fly is the way home — get it first (quest('fly'), then teach it) and train the team up before you go (the Elite Four wants a best Pokémon of L54 and five at L46+). "
                    "Call quest('victory_road') again to go anyway.")
        return {"ss_ticket": self._get_ss_ticket, "cut": self._get_cut, "surf": self._get_surf,
                "strength": self._get_strength, "coin_case": self._get_coin_case,
                "rocket_hideout": self._get_silph_scope, "tea": self._get_tea, "pokemon_tower": self._get_pokemon_tower,
                "poke_flute": self._get_poke_flute, "snorlax": self._get_snorlax, "snorlax_16": self._get_snorlax_16,
                "pokemon_mansion": self._get_secret_key, "silph_co": self._get_silph_co,
                "victory_road": self._get_victory_road, "elite_four": self._get_elite_four,
                "flash": self._get_flash, "fly": self._get_fly, "dig": self._get_dig, "hitmon": self._get_hitmon, "copycat": self._get_copycat,
                "magikarp": self._get_magikarp, "itemfinder": self._get_itemfinder, "exp_share": self._get_exp_share,
                "old_rod": lambda a: self._get_rod("old", a), "good_rod": lambda a: self._get_rod("good", a),
                "super_rod": lambda a: self._get_rod("super", a), "bike": self._get_bike, "new_game": self._get_new_game, "zapdos": self._get_zapdos, "articuno": self._get_articuno,
                **{g: (lambda a, g=g: self._get_gym(g, a)) for g in ("brock", "misty", "surge", "erika", "koga", "sabrina", "blaine", "giovanni")}}[beat.driver](auto_trainers)

    # ── Safari Zone: HM03 Surf (Secret House) and HM04 Strength (Gold Teeth → the Warden) ─────────────────────
    def _in_safari_zone(self) -> bool:
        from game.constants import Addr
        return bool(self.mgba.read8(Addr.SAFARI_BALLS) or self.mgba.read16(Addr.SAFARI_STEPS))

    def _fly_ready(self) -> bool:
        """Can someone in the party fly home from the Plateau right now (a Pokémon that knows Fly and the badge that obeys it)?"""
        from knowledge.team import hm_status
        try:
            knower, _cap = hm_status(self.reader.read_party(), "Fly")
            return bool(knower and self.reader.read_badges()[1] >> 2 & 1)
        except Exception:
            return False

    def _knows_move(self, move_id: int) -> bool:
        return any(move_id in (p.move_ids or []) for p in self.reader.read_party())

    def _safari_leg(self, dest: str, call: str, auto_trainers: bool = False) -> str | None:
        """Travel to `dest` inside the Safari Zone. Returns None on arrival, else the message to hand back (a Safari battle,
        a problem). Wild battles end the call so the model plays them with safari(...); the call resumes the quest."""
        want = {"Safari Zone (West)": SAFARI_WEST, "Safari Zone Secret House": SECRET_HOUSE}.get(dest)
        for _ in range(10):
            if want and tuple(self.reader.read_current_map()) == want:
                return None
            self._avoid_maps = (SAFARI_ENTRANCE, FUCHSIA_CITY)      # never walk out through the exit (it would end the visit)
            try:
                out = self._go_to(dest, mode="yield", auto_trainers=auto_trainers, resume_call=call)
            finally:
                self._avoid_maps = ()
            if want and tuple(self.reader.read_current_map()) == want:
                return None
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if not self._in_safari_zone():
                return ("The Safari Zone visit ended before you got there (out of steps or Safari Balls) — "
                        f"call {call} again to re-enter (¥{SAFARI_FEE}).")
            if "Can't get to" in out or "No route" in out or "Blocked" in out:
                return f"Can't reach {dest} inside the Safari Zone: {out}"
        return f"Didn't reach {dest} yet — call {call} again to continue (it resumes)."

    def _enter_safari_zone(self, call: str, auto_trainers: bool = False) -> str | None:
        """Pay the ¥500 at the entrance hall and walk in (30 Safari Balls, 600 steps). None once inside, else a message."""
        if self._in_safari_zone():
            return None
        if self.reader.read_money() < SAFARI_FEE:
            return f"The Safari Zone costs ¥{SAFARI_FEE} and you have ¥{self.reader.read_money()}."
        if tuple(self.reader.read_current_map()) != SAFARI_ENTRANCE:
            for _ in range(10):
                out = self._go_to("Safari Zone Entrance", mode="yield", auto_trainers=auto_trainers, resume_call=call)
                if tuple(self.reader.read_current_map()) == SAFARI_ENTRANCE:
                    break
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    return out
                if "heal()" in out or "Lost a trainer" in out:
                    if not self._heal().startswith(("Healed", "Party is already")):
                        return f"Couldn't heal on the way to the Safari Zone — heal(), then {call} again."
                    continue
                if "Can't get to" in out or "No route" in out or "gated" in out:
                    return f"Can't reach the Safari Zone: {out}"
            if tuple(self.reader.read_current_map()) != SAFARI_ENTRANCE:
                return f"Didn't reach the Safari Zone entrance yet — call {call} again to continue (it resumes)."
        self._walk_to(*SAFARI_TRIGGER)             # the trigger tile starts the attendant's "play for ¥500?" dialogue
        for _ in range(10):
            self.mgba.tick(60)
            if self._menus.choice_live():
                self._menus.answer_prompt("yes")
            else:
                self._advance_to_control(tries=20)
            if tuple(self.reader.read_current_map()) == SAFARI_CENTER and self._in_safari_zone():
                return None
        if self.reader.read_money() >= SAFARI_FEE and not self._in_safari_zone():
            return ("The attendant didn't let you in (your party and every PC box may be full — pc('deposit') or release some, "
                    f"then {call} again).")
        return f"Couldn't get into the Safari Zone — talk to the attendant at the entrance hall counter, then {call} again."

    def _leave_safari_zone(self) -> None:
        """Walk back out through the entrance hall ('leaving early?' → YES) and onto the street."""
        for _ in range(6):
            if not self._in_safari_zone():
                break
            self._go_to("Safari Zone Entrance", mode="flee")
            self._advance_to_control(tries=30)                # 'Are you going to leave early?' defaults to YES
        if tuple(self.reader.read_current_map()) == SAFARI_ENTRANCE:
            self._go_to("Fuchsia City", mode="flee")

    _FACE_DELTA = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}

    def _live_spots(self, spots) -> list:
        """Where to stand to talk to an NPC that is NOT on its home tile. `spots` are written for the NPC's home tile (stand + facing = that tile); some wander (the Route 16 house's
        woman has MOVEMENT_TYPE_WANDER_AROUND, and a few frames of difference in how we walked in left her one tile over: the player stood on her home tile and pressed A at nothing).
        Returns [] when the NPC is home (or none is near), else the approach to the nearest loaded NPC within four tiles."""
        if not spots:
            return []
        (sx, sy), face = spots[0]
        dx, dy = self._FACE_DELTA.get(face, (0, 0))
        home = (sx + dx, sy + dy)
        try:
            npcs = set(self._npc_tiles())
        except Exception:
            return []
        if home in npcs:
            return []
        near = [t for t in npcs if abs(t[0] - home[0]) + abs(t[1] - home[1]) <= 4]
        if not near:
            return []
        spot = self._clerk_approach(min(near, key=lambda t: abs(t[0] - home[0]) + abs(t[1] - home[1])))
        return [spot] if spot else []

    def _talk_to(self, spots) -> bool:
        for stand, face in [*self._live_spots(spots), *spots]:
            if self._press_on_tile(stand, face):
                return True
        return False

    def _safari_expedition(self, call: str, want_teeth: bool, want_hm03: bool, auto_trainers: bool = False) -> str | None:
        """One paid visit: the Gold Teeth and/or the Secret House's HM03, then back out. None when everything wanted is in
        hand, else the message to hand back (a battle, no money, out of steps…)."""
        need = lambda: ((want_teeth and not self.reader.read_flag(FLAG_GOLD_TEETH_TAKEN) and not self.reader.read_flag(FLAG_GOT_HM04))  # noqa: E731
                        or (want_hm03 and not self.reader.read_flag(FLAG_GOT_HM03)))
        if not need():
            return None
        if (msg := self._enter_safari_zone(call, auto_trainers)):
            return msg
        if (msg := self._safari_leg("Safari Zone (West)", call, auto_trainers)):
            return msg
        if want_teeth and not self.reader.read_flag(FLAG_GOLD_TEETH_TAKEN) and not self.reader.read_flag(FLAG_GOT_HM04):
            problem = ""
            for _ in range(6):                   # a wild encounter can cut the walk short: hand it over, or just retry
                _what, problem = self._pick_ball(*GOLD_TEETH_TILE)
                if not problem and self.reader.read_flag(FLAG_GOLD_TEETH_TAKEN):
                    break
                if (b := self._quest_battle(call, "the Gold Teeth")):
                    return b
                if not self._in_safari_zone():
                    return f"The Safari Zone visit ended before the Gold Teeth were found — {call} again to re-enter (¥{SAFARI_FEE})."
            if not self.reader.read_flag(FLAG_GOLD_TEETH_TAKEN):
                return f"Couldn't pick up the Gold Teeth at {GOLD_TEETH_TILE}: {problem or 'no change'} — {call} again to retry."
        if want_hm03 and not self.reader.read_flag(FLAG_GOT_HM03):
            if (msg := self._safari_leg("Safari Zone Secret House", call, auto_trainers)):
                return msg
            if not self._talk_to(ATTENDANT_SPOTS):
                if (b := self._quest_battle(call, "the Secret House")):
                    return b
                return "Couldn't reach the man in the Secret House — walk_to (6,6), face up, press A."
            for _ in range(10):
                if self.reader.read_flag(FLAG_GOT_HM03):
                    break
                self._advance_to_control(tries=30)
            if not self.reader.read_flag(FLAG_GOT_HM03):
                return f"Talked to the man but no HM03 yet — {call} again."
            self._advance_to_control(tries=24)
        self._leave_safari_zone()
        return None

    def _get_coin_case(self, auto_trainers: bool = False) -> str:
        if self.reader.read_flag(FLAG_GOT_COIN_CASE):
            return "You already have the Coin Case — game_corner('status')."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        for _ in range(10):
            if tuple(self.reader.read_current_map()) == RESTAURANT:
                break
            out = self._go_to("Celadon Restaurant", mode="yield", auto_trainers=auto_trainers, resume_call="quest('coin_case')")
            if tuple(self.reader.read_current_map()) == RESTAURANT:
                break
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if "Can't get to" in out or "No route" in out:
                return f"Can't reach the Celadon Restaurant: {out}"
        if tuple(self.reader.read_current_map()) != RESTAURANT:
            return "Didn't reach the Celadon Restaurant yet — call quest('coin_case') again to continue (it resumes)."
        if not self._talk_to(COIN_CASE_SPOTS):
            if (b := self._quest_battle("quest('coin_case')", "the Coin Case man")):
                return b
            return "Couldn't reach the man in the corner — walk_to (2,2), face left, press A."
        for _ in range(10):
            if self.reader.read_flag(FLAG_GOT_COIN_CASE):
                break
            self._advance_to_control(tries=30)
        if not self.reader.read_flag(FLAG_GOT_COIN_CASE):
            return "Talked to the man but no Coin Case yet — quest('coin_case') again."
        self._advance_to_control(tries=24)
        return "Got the Coin Case. The Game Corner is next door: game_corner('buy_coins', 50) then game_corner('slots', 20)."

    def _get_surf(self, auto_trainers: bool = False) -> str:
        if self._knows_move(SURF_MOVE_ID):
            return "A Pokémon in your party already knows Surf — use_hm('surf') at a shore, or just go_to."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if (msg := self._safari_expedition("quest('surf')", want_teeth=True, want_hm03=True, auto_trainers=auto_trainers)):
            return msg
        out = self._teach_move("HM03", "", "")
        teeth = " You also have the Gold Teeth — quest('strength') takes them to the Warden." if (
            self.reader.read_flag(FLAG_GOLD_TEETH_TAKEN) and not self.reader.read_flag(FLAG_GOT_HM04)) else ""
        if not self._knows_move(SURF_MOVE_ID):
            return f"Got HM03 but couldn't teach it: {out} — teach_move('HM03') yourself (pick a Pokémon that can learn Surf).{teeth}"
        return (f"Got HM03 and {out} Surf needs the Soul Badge to use outside battle; use_hm('surf') at a shore, and go_to "
                f"does it for you when water blocks the way.{teeth}")

    def _get_strength(self, auto_trainers: bool = False) -> str:
        if self._knows_move(STRENGTH_MOVE_ID):
            return "A Pokémon in your party already knows Strength — use_hm('strength') next to a boulder."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if not self.reader.read_flag(FLAG_GOT_HM04):
            if (msg := self._safari_expedition("quest('strength')", want_teeth=True, want_hm03=not self.reader.read_flag(FLAG_GOT_HM03),
                                               auto_trainers=auto_trainers)):
                return msg
            if tuple(self.reader.read_current_map()) != WARDENS_HOUSE:
                for _ in range(10):
                    out = self._go_to("Warden's House", mode="yield", auto_trainers=auto_trainers, resume_call="quest('strength')")
                    if tuple(self.reader.read_current_map()) == WARDENS_HOUSE:
                        break
                    if self.reader.detect_context() == GameContext.IN_BATTLE:
                        return out
                if tuple(self.reader.read_current_map()) != WARDENS_HOUSE:
                    return "Didn't reach the Warden's House yet — call quest('strength') again to continue (it resumes)."
            if not self._talk_to(WARDEN_SPOTS):
                return "Couldn't reach the Warden — walk_to (3,6), face up, press A."
            for _ in range(12):
                if self.reader.read_flag(FLAG_GOT_HM04):
                    break
                self._advance_to_control(tries=30)
            if not self.reader.read_flag(FLAG_GOT_HM04):
                return "Talked to the Warden but no HM04 yet — do you have the Gold Teeth? quest('strength') again."
            self._advance_to_control(tries=24)
        out = self._teach_move("HM04", "", "")
        extra = " You also have HM03 (Surf): quest('surf') teaches it." if (
            self.reader.read_flag(FLAG_GOT_HM03) and not self._knows_move(SURF_MOVE_ID)) else ""
        if not self._knows_move(STRENGTH_MOVE_ID):
            return f"Got HM04 but couldn't teach it: {out} — teach_move('HM04') yourself.{extra}"
        return f"Got HM04 and {out} Move boulders with use_hm('strength').{extra}"

    def _has_ss_ticket(self) -> bool:
        return (SS_TICKET_ITEM in self.reader.read_key_items()
                or bool(self.reader.read_flag(FLAG_GOT_SS_TICKET)))

    def _get_ss_ticket(self, auto_trainers: bool = False) -> str:
        if self._has_ss_ticket():
            return "You already have the SS Ticket — Cerulean's exits are open. go_to Vermilion City."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        # 1. Get to the cottage: resumable travel. A wild Pokémon / trainer ends the call so the model plays it
        # (auto_trainers=true auto-fights the Nugget Bridge trainers; it then stops on a lost fight / low HP with
        # advice), so keep calling it, healing when it asks.
        for _ in range(12):
            if self.reader.read_current_map() == COTTAGE:
                break
            before = (tuple(self.reader.read_current_map()), tuple(self.reader.read_player_pos()))
            out = self._go_to("Bill's Sea Cottage", mode="yield", auto_trainers=auto_trainers,
                              resume_call="quest('ss_ticket')")
            if self.reader.read_current_map() == COTTAGE:
                break
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if "heal()" in out or "Lost a trainer" in out:
                heal = self._heal()
                if not heal.startswith(("Healed", "Party is already")):
                    return f"Couldn't heal on the way to Bill's cottage ({heal}) — heal(), then quest('ss_ticket') again."
                continue
            if "Blocked" in out or "gated" in out:
                return f"Can't reach Bill's Sea Cottage: {out}"
            if before == (tuple(self.reader.read_current_map()), tuple(self.reader.read_player_pos())):
                return f"Can't reach Bill's Sea Cottage — no progress: {out}"       # a watched run looped 12x here in 0.03 s and told the model nothing
        if self.reader.read_current_map() != COTTAGE:
            return "Didn't reach Bill's Sea Cottage yet — call quest('ss_ticket') again to continue (it resumes)."

        # 2. Clefairy-Bill → teleporter. (Skipped on a re-run if he's already gone.)
        if self.reader.read_objects_by_gfx([CLEFAIRY_GFX]) and not self.reader.read_objects_by_gfx([BILL_GFX]):
            if not self._press_on_tile(*CLEFAIRY_SPOT, yesno=True):
                if (b := self._quest_battle("quest('ss_ticket')", "Bill's cottage")):
                    return b
                return "Couldn't reach the Clefairy (Bill) in the cottage — walk_to (10,7), face up, press A, answer YES."
        # 3. The computer runs the cell separator; wait for human Bill to appear.
        if not self.reader.read_objects_by_gfx([BILL_GFX]):
            if not self._press_on_tile(*COMPUTER_SPOT):
                if (b := self._quest_battle("quest('ss_ticket')", "Bill's cottage")):
                    return b
                return "Couldn't reach Bill's computer at (4,5) — walk_to (4,6), face up, press A."
            for _ in range(30):
                if self.reader.detect_context() == GameContext.OVERWORLD and self.reader.read_objects_by_gfx([BILL_GFX]):
                    break
                self._advance_to_control(tries=30)
        bill = self.reader.read_objects_by_gfx([BILL_GFX])
        if not bill:
            return "Ran Bill's computer but he didn't appear — call quest('ss_ticket') again."
        # 4. Talk to Bill (stand below him), take the ticket.
        bx, by = bill[0]
        for stand, face in (((bx, by + 1), "Up"), ((bx - 1, by), "Right"), ((bx + 1, by), "Left")):
            if self._press_on_tile(stand, face):
                break
            if (b := self._quest_battle("quest('ss_ticket')", "Bill's cottage")):
                return b
        for _ in range(12):
            if self._has_ss_ticket():
                break
            self._advance_to_control(tries=30)
        if not self._has_ss_ticket():
            return "Talked to Bill but no ticket yet — call quest('ss_ticket') again."
        self._advance_to_control(tries=24)
        return ("Got the SS Ticket from Bill! Cerulean's south and east exits are open now — "
                "go_to Vermilion City (heal first if hurt).")

    # ── HM01 Cut from the S.S. Anne's Captain ──────────────────────────────────
    def _knows_cut(self) -> bool:
        return any(CUT_MOVE_ID in (p.move_ids or []) for p in self.reader.read_party())

    def _get_cut(self, auto_trainers: bool = False) -> str:
        if self._knows_cut():
            return "A Pokémon in your party already knows Cut — use_hm('cut') on a tree, or just go_to."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if not self.reader.read_flag(FLAG_GOT_HM01):
            if not self._has_ss_ticket():
                return "You need the SS Ticket to board the S.S. Anne — call quest('ss_ticket') first."
            for _ in range(14):
                if self.reader.read_current_map() == CAPTAIN_OFFICE:
                    break
                out = self._go_to("S.S. Anne Captain's Office", mode="yield", auto_trainers=auto_trainers,
                                  resume_call="quest('cut')")
                if self.reader.read_current_map() == CAPTAIN_OFFICE:
                    break
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    return out
                if "heal()" in out or "Lost a trainer" in out:
                    heal = self._heal()
                    if not heal.startswith(("Healed", "Party is already")):
                        return f"Couldn't heal on the way to the S.S. Anne ({heal}) — heal(), then quest('cut') again."
                    continue
                if "Can't get to" in out or "No route" in out:
                    return f"Can't reach the S.S. Anne's Captain: {out}"
            if self.reader.read_current_map() != CAPTAIN_OFFICE:
                return "Didn't reach the Captain's Office yet — call quest('cut') again to continue (it resumes)."
            if not self._press_on_tile(*CAPTAIN_SPOT):
                if (b := self._quest_battle("quest('cut')", "the Captain")):
                    return b
                return "Couldn't reach the Captain — walk_to (5,5), face up, press A."
            for _ in range(12):
                if self.reader.read_flag(FLAG_GOT_HM01):
                    break
                self._advance_to_control(tries=30)
            if not self.reader.read_flag(FLAG_GOT_HM01):
                return "Talked to the Captain but no HM01 yet — call quest('cut') again."
            self._advance_to_control(tries=24)
        out = self._teach_move("HM01", "", "")
        if not self._knows_cut():
            return f"Got HM01 but couldn't teach it: {out} — teach_move('HM01') yourself (pick a Pokémon that can learn Cut)."
        return (f"Got HM01 and {out} Cut trees now clear with use_hm('cut') — and go_to does it for you "
                "when one blocks the way (Vermilion Gym's door).")

    # ── Vermilion Gym: the two electric-lock switches (trash cans) ──────────────────────────────
    def _solve_vermilion_switches(self) -> str:
        """Lt. Surge's gym hides two switches in the 15 trash cans (a 5x3 grid at x=1,3,5,7,9 / y=10,12,14).
        The game rolls them on map load into VAR_TEMP_0 / VAR_TEMP_1 (can ids 1..15, read left→right,
        top→bottom), so instead of guessing we READ them and press exactly those two cans. (A wrong second
        can would reset both locks, so there is no guessing here.)"""
        if self.reader.read_flag(FLAG_VERMILION_SWITCHES):
            return "The electric locks are already open."
        s1, s2 = self.reader.read_var(0x4000), self.reader.read_var(0x4001)
        if 1 <= s1 <= 15 and 1 <= s2 <= 15:
            self._vermilion_cans = (s1, s2)          # remember: a gym trainer's battle can interrupt us mid-way
        elif self._vermilion_cans:
            s1, s2 = self._vermilion_cans            # …and the temp vars may read 0 after it
        if not (1 <= s1 <= 15 and 1 <= s2 <= 15):
            return f"Couldn't read the trash-can switches (got {s1}, {s2}) — search the cans by hand (A on each)."
        for can in (s1, s2):
            x, y = trash_can_tile(can)
            # Below the can first; if a (beaten) gym trainer stands there, press it from either side instead.
            for stand, face in (((x, y + 1), "Up"), ((x - 1, y), "Right"), ((x + 1, y), "Left")):
                if self._press_on_tile(stand, face):
                    break
                if (b := self._quest_battle("challenge_leader()", "Surge's trash cans")):
                    return b
            else:
                return f"Couldn't reach trash can {can} at ({x},{y}) — walk_to ({x},{y + 1}), face up, press A."
        if not self.reader.read_flag(FLAG_VERMILION_SWITCHES):
            return "Pressed both switch cans but the locks didn't open — try again."
        return "Both electric locks are open — the way to Lt. Surge is clear."

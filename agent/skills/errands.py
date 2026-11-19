"""Small story errands with a fixed script (one NPC, one item).

quest('tea'): the old woman in Celadon Mansion (Condominiums) 1F gives the Tea for free (FLAG_GOT_TEA 0x2A6, key item 369). Walk into a
Saffron gate house (Routes 5-8) and the thirsty guard drinks it and lets you into Saffron City for good (the item is consumed, the flag stays).
Decomp: CeladonCity_Condominiums_1F (EventScript_TeaWoman at (2,9)), Route5/6/7/8 gate scripts.

quest('flash'): Prof. Oak's Aide in the Route 2 east building (15,2) at (4,6) gives HM05 Flash once 10 species have been SEEN (FLAG_GOT_HM05 0x23B).
quest('dig'): the Rocket grunt behind the robbed house in Cerulean City, at (33,6): beat him and he returns TM28 Dig (FLAG_GOT_TM28_FROM_ROCKET 0x23F).
quest('hitmon'): Saffron's Fighting Dojo (14,2): beat Master Koichi at (6,5), then take Hitmonchan from the ball at (7,3) (FLAG_GOT_HITMON_FROM_DOJO 0x278) — a one-time
choice, the other ball goes. quest('magikarp'): the salesman at (1,3) in Route 4's Pokémon Center (16,0) sells a L5 Magikarp for ¥500 (FLAG_BOUGHT_MAGIKARP 0x249).
quest('old_rod') / ('good_rod') / ('super_rod'): the Fishing Gurus — Vermilion house 1 (9,0) at (4,5) [flag 0x240], Fuchsia house 2 (11,8) at (6,5) [0x244], Route 12's fishing house
(23,2) at (4,4) [0x255]: "Do you like to fish?" YES and the rod is a key item. quest('bike'): the Pokémon Fan Club chairman (Vermilion, (9,3), at (5,4)) tells his story and gives the
Bike Voucher [0x241]; the Cerulean bike shop clerk (7,6) at (9,3) swaps it for the Bicycle [0x271].
quest('fly'): the woman in the Route 16 house (25,0), at (4,2), just gives HM02 Fly (FLAG_GOT_HM02 0x238). The house is on Route 16's WEST end; Celadon's exit lands
on the east end: cut the tree at (41,11), take the upper gatehouse (27,6)→(20,6) and walk west (the sleeping Snorlax at (31,13) blocks only the lower road to Route
17, so no Poké Flute is needed). go_to plans this with the region graph's Cut-tree links (#293)."""
from game.state import GameContext

CELADON_MANSION_1F = (10, 7)
FLAG_GOT_TEA = 0x2A6
TEA_ITEM = 369
TEA_WOMAN_SPOTS = (((2, 10), "Up"), ((3, 9), "Left"), ((1, 9), "Right"))      # she stands at (2,9)
ROUTE2_EAST_BUILDING, ROUTE16_HOUSE = (15, 2), (25, 0)
FLAG_GOT_HM05, FLAG_GOT_HM02 = 0x23B, 0x238
CERULEAN, SAFFRON_DOJO, ROUTE4_CENTER = (3, 3), (14, 2), (16, 0)
FLAG_GOT_TM28, FLAG_GOT_HITMON, FLAG_BOUGHT_MAGIKARP = 0x23F, 0x278, 0x249
FLAG_COPYCAT_MIMIC, POKE_DOLL, FLAG_HIDE_SAFFRON_ROCKETS = 0x2CD, 80, 0x03E                                  # the Mimic tutor's one-time flag (knowledge.tutors) / ITEM_POKE_DOLL
FLAG_BEAT_KOICHI = 0x500 + 317                                          # TRAINER_BLACK_BELT_KOICHI's trainer flag
TM28_ITEM = 316                                                         # TM01 = 289
MAGIKARP_PRICE = 500
GRUNT_SPOTS = (((33, 7), "Up"), ((32, 6), "Right"), ((34, 6), "Left"))              # the grunt stands at (33,6)
KOICHI_SPOTS = (((6, 6), "Up"), ((5, 5), "Right"), ((7, 5), "Left"))                # Master Koichi at (6,5)
HITMONCHAN_SPOTS = (((7, 4), "Up"),)                                                # the ball at (7,3); Hitmonlee's is at (5,3)
SALESMAN_SPOTS = (((1, 4), "Up"), ((2, 3), "Left"), ((0, 3), "Right"))              # the Magikarp salesman at (1,3)
AIDE_SPOTS = (((4, 7), "Up"), ((3, 6), "Right"), ((5, 6), "Left"))            # the Aide stands at (4,6)
FLY_WOMAN_SPOTS = (((4, 3), "Up"), ((3, 2), "Right"), ((5, 2), "Left"))      # the woman stands at (4,2)
AIDE_SEEN_NEEDED = 10          # (the aides count species CAUGHT — see knowledge.aides)
ROUTE11_GATE_2F, ROUTE15_GATE_2F = (22, 1), (24, 1)
OLD_ROD_HOUSE, GOOD_ROD_HOUSE, SUPER_ROD_HOUSE, FAN_CLUB, BIKE_SHOP = (9, 0), (11, 8), (23, 2), (9, 3), (7, 6)
FLAG_OLD_ROD, FLAG_GOOD_ROD, FLAG_SUPER_ROD, FLAG_BIKE_VOUCHER, FLAG_BICYCLE = 0x240, 0x244, 0x255, 0x241, 0x271
FLAG_B_DASH = 0x800 + 0x2F                                              # FLAG_SYS_B_DASH: the Running Shoes (Oak's Aide, Pewter City)
GURU_SPOTS = {"old": (((4, 6), "Up"), ((3, 5), "Right"), ((5, 5), "Left")), "good": (((6, 6), "Up"), ((5, 5), "Right"), ((7, 5), "Left")),
              "super": (((4, 5), "Up"), ((3, 4), "Right"), ((5, 4), "Left"))}              # the guru stands at (4,5) / (6,5) / (4,4)
CHAIRMAN_SPOTS = (((5, 5), "Up"), ((4, 4), "Right"), ((6, 4), "Left"))                        # the chairman stands at (5,4)
FLAG_GOT_ITEMFINDER, FLAG_GOT_EXP_SHARE = 0x252, 0x256
ITEMFINDER_AIDE_SPOTS = (((2, 7), "Up"), ((3, 6), "Left"), ((1, 6), "Right"))      # the aide stands at (2,6)
EXP_SHARE_AIDE_SPOTS = (((5, 6), "Up"), ((4, 5), "Right"), ((6, 5), "Left"))        # the aide stands at (5,5)


class ErrandsMixin:
    def _has_tea(self) -> bool:
        return bool(self.reader.read_flag(FLAG_GOT_TEA)) or TEA_ITEM in self.reader.read_key_items()

    def _get_tea(self, auto_trainers: bool = False) -> str:
        call = "quest('tea')"
        if self._has_tea():
            return "You already have (or already gave) the Tea — walk into a Saffron gate house (Routes 5, 6, 7 or 8) and the guard lets you in."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        for _ in range(10):
            if tuple(self.reader.read_current_map()) == CELADON_MANSION_1F:
                break
            out = self._go_to("Celadon Mansion 1F", mode="yield", auto_trainers=auto_trainers, resume_call=call)
            if tuple(self.reader.read_current_map()) == CELADON_MANSION_1F:
                break
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if "Can't get to" in out or "No route" in out:
                return f"Can't reach Celadon Mansion: {out}"
        if tuple(self.reader.read_current_map()) != CELADON_MANSION_1F:
            return f"Didn't reach Celadon Mansion yet — call {call} again to continue (it resumes)."
        if not self._talk_to(TEA_WOMAN_SPOTS):
            if (b := self._quest_battle(call, "the Tea lady")):
                return b
            return "Couldn't reach the old woman at (2,9) — walk_to (2,10), face up, press A."
        for _ in range(10):
            if self._has_tea():
                break
            self._advance_to_control(tries=30)
        if not self._has_tea():
            return f"Talked to the old woman but no Tea yet — call {call} again."
        self._advance_to_control(tries=24)
        return ("Got the Tea. Walk into a Saffron gate house (the buildings on Routes 5, 6, 7 and 8 next to Saffron): the thirsty guard "
                "drinks it and lets you into Saffron City. Silph Co. (quest('silph_co')) is the next story step there.")

    def _gift_errand(self, call: str, dest: str, dest_map: tuple, spots, flag: int, who: str, auto_trainers: bool,
                     answers: tuple = ("yes",)) -> str | None:
        """Travel to `dest`, talk to `who` and run the dialogue until `flag` is set. `answers` are the Yes/No answers in the order the boxes come (the last one
        repeats): a purchase wants YES, the 'give it a nickname?' that follows a gift Pokémon wants NO. A trainer who fights first hands the battle back.
        None = the gift is in the bag; else the message to return."""
        for _ in range(10):
            if tuple(self.reader.read_current_map()) == dest_map:
                break
            out = self._go_to(dest, mode="yield", auto_trainers=auto_trainers, resume_call=call)
            if tuple(self.reader.read_current_map()) == dest_map:
                break
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if "Can't get to" in out or "No route" in out or "Blocked" in out or "gated" in out or "no walking route" in out:
                return f"Can't reach {dest}: {out}"
        if tuple(self.reader.read_current_map()) != dest_map:
            return f"Didn't reach {dest} yet — call {call} again to continue (it resumes)."
        if not self._talk_to(spots):
            if (b := self._quest_battle(call, who)):
                return b
            return f"Couldn't reach {who} — walk up to them, face them and press A."
        if (b := self._hideout_fight(call, who, auto_trainers)):
            return b
        asked = 0
        for _ in range(14):
            if self.reader.read_flag(flag) and not self._menus.choice_live():
                break
            if self._menus.choice_live():
                self._menus.answer_prompt(answers[min(asked, len(answers) - 1)])
                asked += 1
                self.mgba.tick(30)
            else:
                self._advance_to_control(tries=30)
            if (b := self._hideout_fight(call, who, auto_trainers)):
                return b
        if not self.reader.read_flag(flag):
            return f"Talked to {who} but nothing was given — call {call} again."
        self._advance_to_control(tries=24)
        return None

    def _get_flash(self, auto_trainers: bool = False) -> str:
        call = "quest('flash')"
        if self.reader.read_flag(FLAG_GOT_HM05):
            return "You already have HM05 Flash — teach_move('Flash') to a Pokémon, then use_hm('Flash') in a dark cave (Rock Tunnel)."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        caught = self.reader.read_pokedex()[0]
        if caught < AIDE_SEEN_NEEDED:
            return (f"Prof. Oak's Aide wants {AIDE_SEEN_NEEDED} Pokémon species CAUGHT (complete Pokédex data) and you have caught {caught}. Catch more, "
                    f"then call {call} again.")
        if (msg := self._gift_errand(call, "Route 2 East Building", ROUTE2_EAST_BUILDING, AIDE_SPOTS, FLAG_GOT_HM05, "Prof. Oak's Aide at (4,6)", auto_trainers)):
            return msg
        return "Got HM05 Flash from Prof. Oak's Aide. teach_move('Flash') to a Pokémon that can learn it, then use_hm('Flash') lights a dark cave (Rock Tunnel)."

    def _get_fly(self, auto_trainers: bool = False) -> str:
        call = "quest('fly')"
        if self.reader.read_flag(FLAG_GOT_HM02):
            return "You already have HM02 Fly — teach_move('Fly') to a Pokémon, then fly_to(<town>) (needs the Thunder Badge) goes to any town you have visited."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if not self._can_use_cut():
            return ("The Fly house is on Route 16's west end: from Celadon's exit you cut the tree at (41,11), take the upper gatehouse and walk west. That needs a "
                    "Pokémon that knows Cut (and the Cascade Badge): quest('cut').")
        if (msg := self._gift_errand(call, "Route 16 House", ROUTE16_HOUSE, FLY_WOMAN_SPOTS, FLAG_GOT_HM02, "the woman at (4,2)", auto_trainers)):
            return msg
        return "Got HM02 Fly. teach_move('Fly') to a Pokémon that can learn it (Pidgeotto, Fearow…), then fly_to(<town>) — it needs the Thunder Badge and an outdoor spot."

    def _get_dig(self, auto_trainers: bool = False) -> str:
        call = "quest('dig')"
        if self.reader.read_flag(FLAG_GOT_TM28) or self.reader.count_item(TM28_ITEM):
            return "You already have TM28 Dig — teach_move('Dig') to a Pokémon (Diglett, Sandshrew, Nidoking, Golem… ). The Rocket grunt is gone."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if (msg := self._gift_errand(call, "Cerulean City", CERULEAN, GRUNT_SPOTS, FLAG_GOT_TM28, "the Rocket grunt behind the robbed house", auto_trainers)):
            return msg
        return "Beat the Rocket grunt and got TM28 Dig back. teach_move('Dig') to a Pokémon that can learn it (Ground types, Sandshrew, Diglett…)."

    def _get_copycat(self, auto_trainers: bool = False) -> str:
        """quest('copycat'): the Saffron Copycat teaches Mimic (a one-time tutor lesson) for a Poké Doll — buy one at the Celadon Dept. Store 2F if the bag has none, then tutor('Mimic')."""
        call = "quest('copycat')"
        if self.reader.read_flag(FLAG_COPYCAT_MIMIC):
            return "The Copycat already taught Mimic (it is a one-time lesson)."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if not self._has_tea():
            return "The Copycat lives in Saffron City, behind the gate guards: they want Tea (quest('tea'))."
        if not self.reader.read_flag(FLAG_HIDE_SAFFRON_ROCKETS):
            return "A Rocket grunt stands in front of the Copycat's door until Silph Co. is cleared: quest('silph_co') first."
        if not self.reader.count_item(POKE_DOLL):
            out = self._shop_for("Poké Doll", 1)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return self._quest_battle(call, "Celadon Dept. Store") or out
            if not self.reader.count_item(POKE_DOLL):
                return f"Couldn't get a Poké Doll for the Copycat: {out}"
        return self._tutor("Mimic")

    def _get_hitmon(self, auto_trainers: bool = False) -> str:
        call = "quest('hitmon')"
        if self.reader.read_flag(FLAG_GOT_HITMON):
            return "You already took a Pokémon from the Dojo (Hitmonlee and Hitmonchan are a one-time choice) — it is in your party or the PC."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if not self._has_tea():
            return "Saffron's gate guards want Tea first: quest('tea')."
        where = "it went to the PC box: your party is full — pc('swap')" if len(self.reader.read_party()) >= 6 else "it joined your party"
        if not self.reader.read_flag(FLAG_BEAT_KOICHI):                               # the Dojo's master: a trainer battle, then the balls behind him are free
            if (msg := self._gift_errand(call, "Saffron Dojo", SAFFRON_DOJO, KOICHI_SPOTS, FLAG_BEAT_KOICHI, "Master Koichi", auto_trainers)):
                return msg
        if (msg := self._gift_errand(call, "Saffron Dojo", SAFFRON_DOJO, HITMONCHAN_SPOTS, FLAG_GOT_HITMON, "the Hitmonchan ball", auto_trainers, ("yes", "no"))):
            return msg
        return (f"Took Hitmonchan from the Dojo ({where}; Hitmonlee is gone: a one-time choice). It is L25 with Fighting punches — teach it Thunder Punch / "
                "Ice Punch / Fire Punch if you find the TMs.")

    def _get_magikarp(self, auto_trainers: bool = False) -> str:
        call = "quest('magikarp')"
        if self.reader.read_flag(FLAG_BOUGHT_MAGIKARP):
            return "You already bought the Magikarp — it is in your party or the PC."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if self.reader.read_money() < MAGIKARP_PRICE:
            return f"The Magikarp costs ¥{MAGIKARP_PRICE} and you have ¥{self.reader.read_money()}."
        full = len(self.reader.read_party()) >= 6
        if (msg := self._gift_errand(call, "Route 4 Magikarp House", ROUTE4_CENTER, SALESMAN_SPOTS, FLAG_BOUGHT_MAGIKARP, "the Magikarp salesman", auto_trainers,
                                     ("yes", "no"))):
            return msg
        where = "it went to the PC box (your party was full)" if full else "it joined your party"
        return f"Bought a L5 Magikarp for ¥500; {where}. It is weak until L20 (Gyarados): grind() balances it, or leave it in the PC."

    def _aide_reward(self, call: str, label: str, dest: str, dest_map: tuple, spots, flag: int, needed: int, who: str, auto_trainers: bool) -> str | None:
        """An Oak's Aide who trades `label` for `needed` species CAUGHT. None = collected; else the message to return."""
        if self.reader.read_flag(flag):
            return f"You already have {label}."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        caught = self.reader.read_pokedex()[0]
        if caught < needed:
            return f"{who} wants {needed} species CAUGHT for {label} and you have caught {caught} — catch {needed - caught} more, then call {call} again."
        return self._gift_errand(call, dest, dest_map, spots, flag, who, auto_trainers)

    def _get_itemfinder(self, auto_trainers: bool = False) -> str:
        call = "quest('itemfinder')"
        if self.reader.read_flag(FLAG_GOT_ITEMFINDER):
            return "You already have the Itemfinder — it shows hidden items beside you (and pick_up_items collects the worthwhile hidden ones it knows about)."
        if (msg := self._aide_reward(call, "the Itemfinder", "Route 11 East Gate 2F", ROUTE11_GATE_2F, ITEMFINDER_AIDE_SPOTS, FLAG_GOT_ITEMFINDER, 30,
                                     "Prof. Oak's Aide on Route 11", auto_trainers)):
            return msg
        return "Got the Itemfinder from Prof. Oak's Aide. Hidden items are collected by pick_up_items on the maps that have worthwhile ones."

    def _get_exp_share(self, auto_trainers: bool = False) -> str:
        call = "quest('exp_share')"
        if self.reader.read_flag(FLAG_GOT_EXP_SHARE):
            return "You already have the Exp. Share — give_item('Exp. Share', '<the Pokémon that lags>') if nobody holds it."
        if (msg := self._aide_reward(call, "the Exp. Share", "Route 15 West Gate 2F", ROUTE15_GATE_2F, EXP_SHARE_AIDE_SPOTS, FLAG_GOT_EXP_SHARE, 50,
                                     "Prof. Oak's Aide on Route 15", auto_trainers)):
            return msg
        from knowledge.held_items import holder_for
        party = self.reader.read_party()
        who = holder_for(182, party)                              # ITEM_EXP_SHARE: the one that lags behind
        note = ""
        if who is not None and not any(p.held_item == 182 for p in party):
            held = self._give_item("Exp. Share", who.nickname or who.species_name)
            note = f" {held}"
        return f"Got the Exp. Share from Prof. Oak's Aide.{note}"

    def _get_rod(self, which: str, auto_trainers: bool = False) -> str:
        name, dest, dest_map, flag = {"old": ("Old Rod", "Old Rod House", OLD_ROD_HOUSE, FLAG_OLD_ROD),
                                      "good": ("Good Rod", "Good Rod House", GOOD_ROD_HOUSE, FLAG_GOOD_ROD),
                                      "super": ("Super Rod", "Super Rod House", SUPER_ROD_HOUSE, FLAG_SUPER_ROD)}[which]
        call = f"quest('{which}_rod')"
        if self.reader.read_flag(flag):
            return f"You already have the {name} — fish(): face water (Surf's shore) and cast."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if (msg := self._gift_errand(call, dest, dest_map, GURU_SPOTS[which], flag, f"the Fishing Guru ({name})", auto_trainers)):
            return msg
        return f"Got the {name} from the Fishing Guru. fish() casts it from a shore tile; better rods catch better water Pokémon."

    def _get_bike(self, auto_trainers: bool = False) -> str:
        call = "quest('bike')"
        if self.reader.read_flag(FLAG_BICYCLE):
            return "You already have the Bicycle — it is a key item: use_item('Bicycle') mounts and dismounts (not indoors, in caves or on Surf)."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if not self.reader.read_flag(FLAG_BIKE_VOUCHER):
            if (msg := self._gift_errand(call, "Pokemon Fan Club", FAN_CLUB, CHAIRMAN_SPOTS, FLAG_BIKE_VOUCHER, "the Pokémon Fan Club chairman", auto_trainers)):
                return msg
        if tuple(self.reader.read_current_map()) != BIKE_SHOP:
            for _ in range(10):
                out = self._go_to("Cerulean Bike Shop", mode="yield", auto_trainers=auto_trainers, resume_call=call)
                if tuple(self.reader.read_current_map()) == BIKE_SHOP:
                    break
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    return out
                if "Can't get to" in out or "No route" in out or "Blocked" in out or "gated" in out or "no walking route" in out:
                    return f"Got the Bike Voucher but can't reach Cerulean's Bike Shop: {out}"
        if tuple(self.reader.read_current_map()) != BIKE_SHOP:
            return f"Got the Bike Voucher; didn't reach Cerulean's Bike Shop yet — call {call} again."
        spot = self._clerk_approach((9, 3))
        spots = (spot,) if spot else (((9, 4), "Up"),)
        if (msg := self._gift_errand(call, "Cerulean Bike Shop", BIKE_SHOP, spots, FLAG_BICYCLE, "the Bike Shop clerk", auto_trainers)):
            return msg
        return "Got the Bicycle (voucher swapped at the Cerulean Bike Shop). use_item('Bicycle') mounts it: about twice walking speed, outdoors only."

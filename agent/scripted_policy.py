"""A rule-based stand-in for the LLM: drives the real skills end to end with NO model calls.

`FakeLLM` is a drop-in for the OpenAI client the AgentClient talks to. Each time the agent asks for a
decision it asks `ScriptedPolicy.decide()` for one tool call (from live emulator state); on the follow-up
round (after the tool result) it replies with plain text so control returns to the main loop, exactly
like a real model that has nothing more to call. Everything else — observations, statistics, ltm
bookkeeping, run logging, checkpoints, the watchdog — is the real run_episode.

Use it to find where the skill chain stalls (item 5 of #185) without spending a token:
    python tools/scripted_run.py --goal badges:2 --max-steps 300
"""
from __future__ import annotations

import json
from types import SimpleNamespace

# Lead level wanted before each gym, and the town to head for once that badge is in hand.
GYM_PLAN = [
    {"leader": "Brock", "city": "Pewter City", "lead_level": 14},
    {"leader": "Misty", "city": "Cerulean City", "lead_level": 21},
    {"leader": "Lt. Surge", "city": "Vermilion City", "lead_level": 26},
    {"leader": "Erika", "city": "Celadon City", "lead_level": 40},
]


class ScriptedPolicy:
    def __init__(self, rt):
        self.rt = rt
        self.c, self.r, self.m, self.ltm = rt.client, rt.reader, rt.mgba, rt.ltm
        self.history: list[str] = []
        self.last_result = ""

    # ── helpers ─────────────────────────────────────────────────────────────
    def _next_gym(self):
        beaten = set(self.ltm.data.get("gyms_beaten", []))
        return next((g for g in GYM_PLAN if g["leader"] not in beaten), None)

    def _battle(self):
        from game.constants import Addr
        from game.menu import forced_party_screen
        from knowledge.party import can_attack
        if forced_party_screen(self.m, self.r):
            party = self.r.read_party()
            ok = [i for i, p in enumerate(party) if p.current_hp > 0]
            return "switch_pokemon", {"target": str((ok or [0])[0] + 1)}
        trainer = bool(self.m.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER)
        _ids, names, pp, _d, _t = self.c._active_moves_view()
        atk, dfn = self.c._battle_types()
        mv = self.c._best_damaging_move(names, pp, atk, dfn, self.c._battle_ctx())
        if mv:
            return "use_move", {"move": mv}
        if not any(n and q > 0 for n, q in zip(names, pp)):
            return "use_move", {"move": "Struggle"}
        party = self.r.read_party()
        active = self.r.read_active_battle_species()
        backups = [i for i, p in enumerate(party) if p.species_id != active and p.current_hp > 0 and can_attack(p)]
        if backups:
            return "switch_pokemon", {"target": str(backups[0] + 1)}
        if not trainer:
            return "flee_battle", {}
        return "use_move", {"move": next(n for n, q in zip(names, pp) if n and q > 0)}

    # ── the decision ────────────────────────────────────────────────────────
    def decide(self):
        from game.state import GameContext
        ctx = self.r.detect_context()
        if ctx == GameContext.IN_BATTLE:
            return self._battle()
        if ctx != GameContext.OVERWORLD:
            from game.menu import forced_party_screen
            if forced_party_screen(self.m, self.r):         # a faint's forced replacement reads IN_MENU or TRANSITIONING: B / A do nothing, pick someone
                ok = [i for i, p in enumerate(self.r.read_party()) if p.current_hp > 0]
                return "switch_pokemon", {"target": str((ok or [0])[0] + 1)}
        if ctx == GameContext.IN_MENU:
            return "close_menus", {}
        if ctx == GameContext.DIALOG_OPEN:
            return "advance_dialog", {}
        if ctx != GameContext.OVERWORLD:
            # TRANSITIONING / UNKNOWN: a blackout's text, a fade, a warp — A carries it forward; waiting
            # alone sat in the post-blackout "(0,0)" screen forever.
            return "advance_dialog", {}
        party = self.r.read_party()
        if not party:
            return "wait_frames", {"frames": 30}
        # The model-facing go_to refuses to start while the readiness check says must-heal, so the bot heals
        # on the same rule (any member below half, a faint, attacks out of PP) before it travels.
        from knowledge.readiness import blocking
        if blocking(self.c._readiness()):
            return "heal", {}
        # Recover first: hurt, or attacks out of PP.
        if self.c._party_needs_heal() and any(p.current_hp < 0.6 * p.max_hp or not _has_pp(p) for p in party):
            return "heal", {}
        gym = self._next_gym()
        if gym is None:
            return "wait_frames", {"frames": 30}
        lead = party[0]
        if lead.level < gym["lead_level"]:
            return "grind", {"level": gym["lead_level"]}
        # Past Misty the story needs Bill's SS Anne ticket before Cerulean's exits open. Walking out of
        # Cerulean's north side triggers the mandatory rival fight, so go in healthy.
        if gym["leader"] == "Lt. Surge" and not self.c._has_ss_ticket():
            if any(p.current_hp < 0.9 * p.max_hp for p in party):
                return "heal", {}
            return "quest", {"name": "ss_ticket"}
        # Vermilion Gym's door is behind a Cut tree: HM01 from the S.S. Anne's Captain first.
        if gym["leader"] == "Lt. Surge" and not self.c._knows_cut():
            if any(p.current_hp < 0.9 * p.max_hp for p in party):
                return "heal", {}
            return "quest", {"name": "cut"}
        cur = self.r.read_current_map()
        from knowledge.leafgreen_data import GYM_MAP_LEADER
        if GYM_MAP_LEADER.get(cur) == gym["leader"]:
            return "challenge_leader", {}
        return "go_to", {"destination": "Gym"}

    def on_result(self, result: str) -> None:
        """Hook: the tool result of the call this policy just made (the plain policy ignores it)."""

    # ── fake OpenAI surface ─────────────────────────────────────────────────
    def respond(self, messages):
        """One chat.completions response for the agent's current message list."""
        last = messages[-1]["role"] if messages else "user"
        if last == "tool":
            self.last_result = str(messages[-1].get("content", ""))
            self.on_result(self.last_result)
            return _response("")
        name, args = self.decide()
        self.history.append(f"{name}({json.dumps(args)})")
        return _response("", name, args)


class ChainPolicy(ScriptedPolicy):
    """The WHOLE story chain without a model (#260): at each free moment run the next open beat's `quest(...)` (knowledge.story_beats), prepare when a quest says the team is not ready
    (grind, heal, shop), and hand every fight to the same battle logic as ScriptedPolicy. It is the regression test for the chain end to end: where it stalls is where a model would —
    `stall` records the first beat that could not progress (the same failure text three times, or the same beat with no change in badges / map for `STALL_CALLS` calls)."""

    STALL_REPEATS = 3                 # the same failure text this many times in a row = a stall
    STALL_CALLS = 40                  # calls spent on one beat with no new badge / key item / map progress

    OPTIONAL_WANTED = ("fly",)        # optional beats the chain takes anyway: HM02 Fly is the only way back from the Indigo Plateau (no grass there, Victory Road behind)

    NOT_READY = ("Not ready for quest", "lopsided", "likely lose", "under-levelled", "Your highest-level Pokémon is L", "Call grind", "train first", "grind()")
    NEEDS_HEAL = ("heal()", "Call heal", "must-heal", "Not travelling yet")
    NEEDS_SHOP = ("shop()", "Potions / Restores in the bag", "Revives in the bag")

    def __init__(self, rt):
        super().__init__(rt)
        self.stall: str = ""
        self._pending = ""             # what the last result asked for: "grind" | "heal" | "shop" | ""
        self._fails: list[str] = []
        self._fly_taught = False       # HM02 Fly was offered to a Pokémon (once: a refusal must not loop)
        self._prepped = False          # the team was levelled BEFORE Victory Road (past it there is no grass to train on: Plateau → back through the cave)
        self._skip_heal = 0            # decisions to go on WITHOUT healing after a heal that could not (a cave with no Center, an empty Bag)
        self._calls_on: dict[str, int] = {}
        self._progress: dict = {}
        self._maps_seen: dict[str, set] = {}

    def on_result(self, result: str) -> None:
        low = result
        self._pending = ""
        if self.history and self.history[-1].startswith("heal(") and low.startswith(("Victory Road has no", "On the way to a Pokémon Center to heal", "No Pokémon Center is reachable")) and "healed from the Bag" not in low:
            self._skip_heal = 6
            return
        if any(k in low for k in self.NEEDS_HEAL) and "Healed" not in low:
            self._pending = "heal"
        elif "grind(" in low and "Not ready for quest" in low:
            self._pending = "grind"          # levels first: a not-ready that asks for BOTH (levels and Potions) went shopping, then charged the Elite Four at L53 / L40 and blacked out 5x
        elif any(k in low for k in self.NEEDS_SHOP):
            self._pending = "shop"
        elif any(k in low for k in self.NOT_READY):
            self._pending = "grind"
        failed = any(k in low for k in ("Can't reach", "Can't get to", "No route", "stuck at", "No walkable path", "couldn't", "Couldn't", "isn't working", "was stopped"))
        if self.history and self.history[-1].startswith("grind(") and low.startswith(("Party is balanced", "Your best Pokémon is already", "No tall grass", "Not worth", "Training isn't")):
            self._prepped = True
        self._fails = (self._fails + [low[:160]] if failed else [])[-self.STALL_REPEATS:]
        if len(self._fails) >= self.STALL_REPEATS and len(set(self._fails)) == 1 and not self.stall:
            self.stall = f"{self._beat_key() or '?'}: {self._fails[-1]}"

    def _status(self):
        from agent.story import story_status
        moves = {m for p in self.r.read_party() for m in (p.move_ids or [])}
        flag = self.r.read_flag
        return story_status(self.r, self.ltm, {"cut": 15 in moves, "surf": 57 in moves or bool(flag(0x239)), "strength": 70 in moves or bool(flag(0x23A))})

    def _beat_key(self) -> str:
        from knowledge.story_beats import next_beats
        ready = [b for b in next_beats(self._status(), include_optional=True) if b.driver and (not b.optional or b.key in self.OPTIONAL_WANTED)]
        return ready[0].key if ready else ""

    def _teach_fly(self):
        """Once HM02 is in the Bag and the Thunder Badge is won, teach Fly to a Pokémon that can learn it (one try): the move that gets the team out of the League's dead end."""
        if self._fly_taught or not self.r.read_flag(0x238) or not self.r.read_badges()[1] >> 2 & 1:
            return None
        from knowledge.tmhm import HM_MOVES, ITEM_HM01
        from knowledge.tmhm_learnsets import can_learn
        party = self.r.read_party()
        if any("Fly" in (p.move_names or []) for p in party):
            self._fly_taught = True
            return None
        iid = ITEM_HM01 + HM_MOVES.index("Fly")
        able = [p for p in party if can_learn(p.species_id, iid)]
        self._fly_taught = True
        if not able:
            return None
        mon = min(able, key=lambda p: p.level)          # the weakest able member: its fourth move matters least
        return "teach_move", {"tm": "Fly", "pokemon": mon.species_name}

    def _progress_sig(self, key: str = ""):
        """What counts as progress on a beat: a badge, a key item, a level, or a map not yet visited FOR THIS BEAT — not merely a different map (a heal trip that
        bounces between two maps forever changed the old signature every call and hid a 2,800-call loop)."""
        seen = self._maps_seen.setdefault(key, set())
        seen.add(tuple(self.r.read_current_map()))
        return (self.r.read_badges()[0], len(self.r.read_key_items()), len(seen), sum(p.level for p in self.r.read_party()))

    def decide(self):
        from game.state import GameContext
        if self.r.detect_context() != GameContext.OVERWORLD:
            return super().decide()                     # battles, menus, dialogue, fades: the plain policy's rules
        party = self.r.read_party()
        if not party:
            return "wait_frames", {"frames": 30}
        from knowledge.readiness import blocking
        key = self._beat_key()
        if key:                                         # count EVERY call against the beat (a heal / shop / grind loop that goes nowhere is a stall too)
            sig = self._progress_sig(key)
            if self._progress.get(key) != sig:
                self._progress[key], self._calls_on[key] = sig, 0
            self._calls_on[key] = self._calls_on.get(key, 0) + 1
            if self._calls_on[key] > self.STALL_CALLS and not self.stall:
                self.stall = f"{key}: {self.STALL_CALLS} calls with no new badge, key item, map or level (last: {self.last_result[:160]})"
        if self._skip_heal > 0:
            self._skip_heal -= 1
        elif blocking(self.c._readiness()) or self._pending == "heal":
            self._pending = ""
            return "heal", {}
        if self._pending == "shop":
            self._pending = ""
            return "shop", {}
        if self._pending == "grind":
            self._pending = ""
            return "grind", {}
        if (teach := self._teach_fly()):
            return teach
        if not key:
            return "wait_frames", {"frames": 30}
        if key == "victory_road" and not self._prepped and tuple(self.r.read_current_map()) not in {(1, 39), (1, 40), (1, 41), (3, 9)}:
            return "grind", {}                          # level the weakest on Routes 22 / 23 first: the Elite Four wants five Pokémon near L46+ and the Plateau has no grass
        return "quest", {"name": key, "auto_trainers": True}


def _has_pp(mon) -> bool:
    from knowledge.party import can_attack
    return can_attack(mon)


_ids = iter(range(10**9))


def _response(content: str, tool: str | None = None, args: dict | None = None):
    calls = None
    if tool:
        fn = SimpleNamespace(name=tool, arguments=json.dumps(args or {}))
        cid = f"scripted_{next(_ids)}"
        tc = SimpleNamespace(id=cid, function=fn, type="function")
        tc.model_dump = lambda: {"id": cid, "type": "function",
                                 "function": {"name": tool, "arguments": json.dumps(args or {})}}
        calls = [tc]
    msg = SimpleNamespace(content=content, tool_calls=calls, model_extra={}, role="assistant")
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                           usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0))


class FakeLLM:
    """Quacks like the `openai.OpenAI` client for chat.completions.create only."""

    def __init__(self, policy: ScriptedPolicy):
        self.policy = policy
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        return self.policy.respond(kw["messages"])

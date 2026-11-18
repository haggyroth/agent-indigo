"""The one-line observation the LLM sees each tick, built from live state + memory.

Extracted from `main.py` (#214): `build_observation` used to be a 370-line function with nested try/excepts and function-local
imports on the per-tick path. It is now a short composition of named sections, each returning the lines it contributes, in the
order the model has always seen them. The only side effects are the ones documented on `_loop_signals` (re-queue the area map when
stuck) and `bag_sig` bookkeeping in `_readiness_and_bag`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent.lm_studio_client import AgentClient
from agent.skills.base import log_once
from config import IV_PEEK_BEFORE_CATCH, USE_VISION
from game.constants import Addr  # noqa: F401  (kept for callers that patch it)
from game.menu import MenuDriver
from game.pathfinding import door_centers
from game.state import GameContext
from knowledge.area_guide import guide_for as area_guide
from knowledge.bag import bag_digest, booster_note, stone_notes
from knowledge.battle import (battle_idle_nudge, battle_summary, overworld_pp_summary, xp_share_hint)
from knowledge.catch_policy import evaluate as catch_evaluate
from knowledge.escape import hint as escape_hint
from knowledge.gym_advice import brief as gym_brief
from knowledge.game_corner import PRIZES
from knowledge.game_corner_data import COIN_CASE, GAME_CORNER, PRIZE_ROOM
from knowledge.held_items import holding_line, suggest as held_suggest
from knowledge.leafgreen_data import GYM_MAP_LEADER, POKEMON_TYPES
from knowledge.map_graph import MAP_KIND
from knowledge.matchup import Foe, better_matchup, low_hp_advice, roster
from knowledge.mon_quality import assess as assess_iv, hidden_power
from knowledge.move_semantics import catch_setup_hint
from knowledge.navigation import DIRECTION_BUTTON, MAP_NAMES, get_travel_direction, infer_building_type
from knowledge.party import can_attack, healthy_enough
from knowledge.readiness import assess as readiness_assess, render as readiness_render, battles_total, save_note
from knowledge.repel import REPEL_IDS, VAR_REPEL_STEP_COUNT, note as repel_note
from knowledge.shopping import shopping_summary
from knowledge.team import wanted_species

if TYPE_CHECKING:                       # annotations only — main.py owns these types
    from game.memory_reader import LeafGreenReader
    from game.state import GameState, StateDiff
    from game.tilemap_reader import TilemapReader
    from memory.long_term import LongTermMemory
    from memory.short_term import ShortTermMemory

BALL_IDS = (1, 2, 3, 4)
POTION_IDS = (13, 22, 21, 20, 19)
HEAL_HP = {13: ("Potion", 20), 22: ("Super Potion", 50), 21: ("Hyper Potion", 200), 20: ("Max Potion", 999), 19: ("Full Restore", 999)}
BAG_SIG_ITEMS = (63, 64, 65, 66, 67, 68, 70, 93, 94, 95, 96, 97, 98)     # vitamins, candy, stones: the bag-digest signature


@dataclass
class Tick:
    """Everything a section may read; one per tick."""
    state: "GameState"
    diff: "StateDiff"
    in_battle: bool
    run: object                         # main._RunState
    reader: "LeafGreenReader"
    tilemap: "TilemapReader"
    ltm: "LongTermMemory"
    stm: "ShortTermMemory"
    map_key: tuple
    trip: dict | None = None

    @property
    def overworld(self) -> bool:
        return self.state.context == GameContext.OVERWORLD

    @property
    def here(self) -> tuple:
        return (self.state.map_bank, self.state.map_id)


def _safe(key: str, fn, default):
    """Run a read that may fail on a half-loaded screen; log the first failure of each kind and use `default`."""
    try:
        return fn()
    except Exception:
        log_once(f"observation.{key}", f"observation.{key}: tolerated failure (continuing with a default)")
        return default


# ── sections ──────────────────────────────────────────────────────────────────────────────────────
def _header(t: Tick) -> list[str]:
    # LTM's badge count is the authoritative one (game RAM can hold stale badge data from old saves).
    out = [f"Context: {t.state.context.name}", f"Badges: {t.ltm.data['badges_earned']}/8"]
    if not t.in_battle and t.state.context in (GameContext.IN_MENU, GameContext.DIALOG_OPEN):
        hint = MenuDriver(t.reader.client, t.reader).describe()                   # read-only
        if hint:
            out.append(f"MENU: {hint}")
    prev = t.run.prev_state
    if prev is not None:
        dx, dy = t.state.player_x - prev.player_x, t.state.player_y - prev.player_y
        out.append("Movement: none (position unchanged since last step)" if dx == 0 and dy == 0
                   else f"Movement: moved ({dx:+d},{dy:+d})")
    return out


def _lead_line(t: Tick) -> list[str]:
    lead = t.state.party[0]
    word = "Lead"
    if t.in_battle:       # after a switch party[0] is NOT the one fighting: name the ACTIVE battler (a fainted lead read as "healthy")
        active = _safe("active", t.reader.read_active_battle_species, 0)
        lead, word = next((p for p in t.state.party if p.species_id == active), lead), "Active"
    state = "FAINTED" if lead.current_hp <= 0 else lead.status
    out = [f"{word}: {lead.species_name or '?'} L{lead.level} HP={lead.current_hp}/{lead.max_hp} ({state})"]
    if not t.in_battle and lead.max_hp and lead.hp_percent < 0.40 and t.overworld:       # proactive heal nudge
        out.append(f"⚠ Lead HP low ({lead.hp_percent:.0%}) — call heal() to restore the party at the nearest Pokémon Center")
    return out


def _readiness_and_bag(t: Tick) -> list[str]:
    """The fundamentals a good player sorts out BEFORE walking on (heal, restock, team, levels, TMs…) plus the bag digest."""
    r, party, out = t.reader, t.state.party, []

    def supplies():
        bag = r.read_bag()
        return (sum(bag.get(b, 0) for b in BALL_IDS), sum(q for i, q in r.read_items_pocket() if i in (13, 22, 21)), r.read_money())

    balls, pots, money = _safe("supplies", supplies, (0, 0, 0))
    dex = _safe("pokedex", r.read_pokedex, None)
    tms, items = _safe("bag_pockets", lambda: (r.read_tmhm_pocket(), r.read_items_pocket()), (None, []))
    # The PC contents are only read where the PC is: "you already own one — pc('swap') it in".
    boxes = _safe("boxes", lambda: r.read_boxes() if MAP_KIND.get(t.here) == "pokecenter" else None, None)
    d = t.ltm.data
    due = save_note(d.get("badges_earned", 0), battles_total(d), d.get("saved_badges"), d.get("saved_battles", 0))
    block = readiness_render(readiness_assess(party, balls, pots, money, d.get("gyms_beaten", []),
                                              dex=dex, tms=tms, boxes=boxes, save_due=due))
    if block:
        out.append(block)
    if tms is not None:                  # shown when it changes, then every 30 ticks — the model forgot TMs picked up long ago
        sig = (tuple(tms), tuple((i, q) for i, q in items if i in BAG_SIG_ITEMS),
               tuple(tuple(p.move_names) for p in party), tuple(p.held_item for p in party))
        if sig != t.run.bag_sig or t.run.step_count % 30 == 0:
            t.run.bag_sig = sig
            line = bag_digest(party, tms, items)
            if line:
                out.append(line)
            out.extend(stone_notes(party, items))
            if holding_line(party):
                out.append(holding_line(party))
            out.extend(held_suggest(party, items))
    return out


def _shortcuts(t: Tick) -> list[str]:
    """Escape Rope / Dig / Teleport where they apply, and the Repel strategy line."""
    r, party, out = t.reader, t.state.party, []
    rope = _safe("rope", lambda: dict(r.read_items_pocket()).get(85, 0), 0)
    hint = escape_hint(t.here, {m for p in party for m in (p.move_ids or [])}, rope)
    if hint:
        out.append(hint)

    def repel():
        have = dict(r.read_items_pocket())
        lead = next((p for p in party if p.current_hp > 0), party[0])
        return repel_note(t.here, lead.level, r.read_var(VAR_REPEL_STEP_COUNT), sum(have.get(i, 0) for i in REPEL_IDS), len(party))

    note = _safe("repel", repel, "")
    if note:
        out.append(note)
    return out


def _area(t: Tick) -> list[str]:
    """What to do on this map (dungeon / puzzle gym / late-game stretch): shown on arrival and as a reminder every 25 ticks."""
    if t.in_battle or not t.overworld:
        return []
    text = area_guide(t.here)
    if not text:
        t.run.area_shown = None
        return []
    if t.run.area_shown == t.here and t.run.step_count % 25:
        return []
    t.run.area_shown = t.here
    return [text]


def _trip(t: Tick) -> list[str]:
    trip = t.trip
    if trip and not t.in_battle and t.overworld:
        resume = (f"call {trip['call']} to resume." if trip.get("call") else
                  f"call go_to() with no destination — or go_to({trip['dest']!r}) — to resume.")
        return [f"TRIP IN PROGRESS → {trip['target']} (an encounter interrupted it): {resume}"]
    return []


def _safari_status(t: Tick) -> list[str]:
    """Inside the Safari Zone the visit ends when EITHER the steps or the Safari Balls run out (you are walked out)."""
    c = t.reader.client
    balls, steps = c.read8(Addr.SAFARI_BALLS), c.read16(Addr.SAFARI_STEPS)
    if not (balls or steps):
        return []
    return [f"SAFARI ZONE: {steps} steps and {balls} Safari Balls left — at 0 of either you are escorted out. Wild Pokémon here "
            "are fought with safari('ball' | 'bait' | 'rock' | 'run'), not moves. Walking out through the entrance ends the visit early."]


def _safari_battle(t: Tick) -> list[str]:
    """A Safari battle has no moves, party or Bag: the foe, the stock of balls, and what BAIT / ROCK do."""
    r, party = t.reader, t.state.party
    enemy = r.read_enemy_lead()
    balls, steps = r.client.read8(Addr.SAFARI_BALLS), r.client.read16(Addr.SAFARI_STEPS)
    out = []
    if enemy:
        out.append(f"SAFARI battle: {enemy.species_name} L{enemy.level} — you have {balls} Safari Balls and {steps} steps left. "
                   "Act with safari('ball'|'bait'|'rock'|'run').")
        v = catch_evaluate(party, enemy.species_id, enemy.level or 0, dex_owned=r.read_dex_owned(enemy.species_id),
                           wanted=wanted_species(party, None, t.ltm.data.get("gyms_beaten", [])),
                           stored=_safe("stored", r.read_stored_species, set()))
        if v.catch:
            taken = [p.nickname for p in party if p.nickname]
            out.append(f"Worth catching: {v.reason}. A rock doubles the catch rate (but it may flee), bait halves it (but calms it); "
                       "rock then ball is the usual line. When you throw the ball, pass a funny, inventive nickname you make up"
                       + (f" (taken: {', '.join(taken)})" if taken else "") + ".")
        else:
            out.append(f"Not worth a ball: {v.reason}. safari('run') unless you want it for the Pokédex.")
    return out


def _foe_info(t: Tick, enemy) -> Foe:
    """The opponent as the matchup maths wants it: gEnemyParty identity + the live battler's moves / Spe / Atk / ability."""
    return Foe(name=enemy.species_name or t.run.current_enemy, level=enemy.level or 0, hp=enemy.current_hp, max_hp=enemy.max_hp,
               **_safe("foe_battler", t.reader.read_foe_battler, {}))


def _forced_switch(t: Tick) -> list[str]:
    """The party screen the game forces open when your active Pokémon faints mid-battle: B cannot cancel it and A just
    selects the highlighted (fainted) lead, so the ONLY way out is switch_pokemon. Its callback is the party menu's, which
    reads as TRANSITIONING — and the old 'dialog not advancing — press A' hint sent a run into 319 useless presses."""
    from game.menu import _healthy_roster, forced_party_screen
    r = t.reader
    if t.state.context.name not in ("TRANSITIONING", "IN_MENU", "UNKNOWN") or not _safe("forced", lambda: forced_party_screen(r.client, r), False):
        return []
    out = ["FORCED SWITCH: your Pokémon fainted and the game is waiting for you to choose the next one. B cannot cancel and "
           f"pressing A does nothing useful — call switch_pokemon('<name or slot>') NOW. Healthy: {_healthy_roster(r)}."]
    enemy = _safe("forced_enemy", r.read_enemy_lead, None)
    if enemy and enemy.max_hp:
        line = roster(t.state.party, r.read_active_battle_species(), foe=_foe_info(t, enemy))
        if line:
            out.append(line)
    return out


def _battle(t: Tick) -> list[str]:
    """Moves/PP of the ACTIVE battler, the foe, volatile conditions, catch advice. (party[0] is not necessarily the one
    fighting after a switch; a Disabled move's PP is zeroed so it is never suggested.)"""
    r, run, party, stm = t.reader, t.run, t.state.party, t.stm
    if r.client.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_SAFARI:
        return _safari_battle(t)
    out = []
    active = r.read_active_battle_species()
    me = next((p for p in party if p.species_id == active), party[0])      # the ACTIVE battler, not necessarily slot 1
    _ids, a_names, a_pp, d_slot, d_turns = r.read_active_battle_usable_pp()
    if any(a_names):
        move_names, pp_view = list(a_names), a_pp
    else:
        move_names, pp_view, d_slot, d_turns = list(me.move_names), me.pp, None, 0
    lead_types = POKEMON_TYPES.get((me.species_name or "").upper().strip(), ())     # STAB comes from the mon using the move
    enemy = r.read_enemy_lead()
    backups = [f"{p.species_name} (slot {i + 1})" for i, p in enumerate(party)
               if p.species_id != active and healthy_enough(p, 0.3) and can_attack(p)]
    hint = ("Teammates that can still attack: " + ", ".join(backups) + " — switch_pokemon to one.") if backups else ""
    out.append(battle_summary(move_names, run.current_enemy, me.hp_percent, pp_view, attacker_types=lead_types,
                              opponent_status=enemy.status if enemy else "", disabled_slot=d_slot, disabled_turns=d_turns,
                              backup_hint=hint, wild=not run.battle_is_trainer, user_level=me.level, user_hp_frac=me.hp_percent,
                              foe_level=(enemy.level or 0) if enemy else 0, foe_hp=enemy.current_hp if enemy else 0,
                              hidden_power=hidden_power(me.ivs)))
    if enemy and enemy.max_hp:           # who is down, who is up, and who matches up well against THIS foe
        foe = _foe_info(t, enemy)
        heals = _safe("heals", lambda: [HEAL_HP[i] for i, q in r.read_items_pocket() if q and i in HEAL_HP], [])
        for line in (roster(party, active, foe=foe), better_matchup(party, active, foe=foe),
                     low_hp_advice(party, active, foe, heals, wild=not run.battle_is_trainer)):
            if line:
                out.append(line)
    boosters = _safe("boosters", lambda: booster_note(r.read_items_pocket(), run.battle_is_trainer), "")
    if boosters:
        out.append(boosters)
    if IV_PEEK_BEFORE_CATCH and enemy and not run.battle_is_trainer:
        q = assess_iv(enemy)
        if q is not None:
            out.append(f"Foe IVs (peek enabled): {q.summary()}")
    xp = _safe("xp_share", lambda: xp_share_hint(party, active, enemy.level if enemy and enemy.max_hp else 0), "")
    if xp:
        out.append(xp)
    out.extend(_volatiles(_safe("volatiles", lambda: r.read_battle_volatiles(0), {})))
    foe_types = POKEMON_TYPES.get((enemy.species_name or "").upper().strip(), ()) if enemy else ()
    nudge = battle_idle_nudge(stm.action_history, AgentClient._best_damaging_move(
        move_names, pp_view, lead_types, foe_types,
        {"user_level": me.level, "user_hp_frac": me.hp_percent, "foe_level": (enemy.level or 0) if enemy else 0,
         "foe_asleep": "asleep" in (enemy.status if enemy else "")}))
    if nudge:
        out.append(nudge)
    if enemy:
        out.append(f"Opponent HP: {enemy.current_hp}/{enemy.max_hp} (L{enemy.level})")
    if run.battle_is_trainer:
        out.append("TRAINER battle — you cannot flee; win or switch.")
    else:
        out.append("WILD battle — you may flee_battle() to escape if you're just passing through or HP is low.")
        out.extend(_catch_advice(t, enemy, move_names, pp_view))
    return out


def _volatiles(v: dict) -> list[str]:
    out = []
    if v.get("wrapped") or v.get("escape_prevention"):
        out.append("⛓ TRAPPED — a trapping move (Wrap/Bind/Fire Spin/Clamp/Whirlpool: 2-5 turns) or Mean Look/Spider "
                   "Web/Block holds you: you CANNOT run or switch voluntarily. Attack (or use an item) until it ends.")
    if v.get("tormented"):
        out.append("TORMENTED — you can't use the same move twice in a row: alternate attacks.")
    if v.get("confused"):
        out.append("CONFUSED — you may hurt yourself; it wears off in a few turns (switching cures it).")
    if v.get("infatuated"):
        out.append("INFATUATED (Attract) — you may be unable to move; switching out cures it.")
    if v.get("recharge"):
        out.append("Recharging after Hyper Beam — this turn is lost.")
    return out


def _catch_advice(t: Tick, enemy, move_names, pp_view) -> list[str]:
    """A NEW species while you have balls: is it worth one? (Called for wild battles only.)"""
    r, party = t.reader, t.state.party
    balls = sum(r.read_bag().get(b, 0) for b in BALL_IDS)
    if balls > 0 and enemy and enemy.species_id and enemy.species_id not in {p.species_id for p in party}:
        v = catch_evaluate(party, enemy.species_id, enemy.level or 0, dex_owned=r.read_dex_owned(enemy.species_id),
                           wanted=wanted_species(party, None, t.ltm.data.get("gyms_beaten", [])),
                           stored=_safe("stored", r.read_stored_species, set()))
        if not v.catch:
            return [f"NOT worth a ball right now: {v.reason}. "
                    "Skip it (flee_battle) unless you have a reason to want it."]
        taken = [p.nickname for p in party if p.nickname]
        return [f"NEW SPECIES you don't own ({balls} Poké Balls in bag) — worth catching: {v.reason}. "
                "Weaken it first with use_move (low HP raises the catch rate). When you catch it, pass a funny, inventive "
                "nickname you make up (not the species name)" + (f"; already taken: {', '.join(taken)}" if taken else "")
                + ". " + catch_setup_hint(move_names, pp_view)]
    if balls == 0 and len(party) < 6:
        return ["You have no Poké Balls — buy some with shop() to catch wild Pokémon for your team."]
    return []


def _supplies(t: Tick) -> list[str]:
    """Money and consumables, lead PP, the Mart restock and the PC reminder (outside battle only)."""
    r, state, out = t.reader, t.state, []
    money, bag = r.read_money(), r.read_bag()
    balls = sum(bag.get(b, 0) for b in BALL_IDS)
    out.append(f"Bag: ¥{money} | Poké Balls: {balls} | Potions/heals: {sum(bag.get(p, 0) for p in POTION_IDS)}")
    # Lead move PP: the agent is otherwise blind to it outside battle and ran its attacks dry across a trainer gauntlet.
    lead = state.party[0] if state.party else None
    if lead:
        pp_line, pp_warn = overworld_pp_summary(lead.move_names, lead.pp)
        out.extend(x for x in (pp_line, pp_warn) if x)
    if MAP_KIND.get(t.here) == "mart":
        rec = shopping_summary(bag, t.ltm.data["badges_earned"], money)
        if rec:
            out.append("MART — " + rec + ". Call shop() to buy the recommended restock automatically.")
    if t.here in (GAME_CORNER, PRIZE_ROOM) and r.read_flag(COIN_CASE[1]):
        coins = r.read_coins()
        buys = [f"{p.name} ({p.coins})" for p in PRIZES if p.coins <= coins]
        out.append(f"GAME CORNER: {coins} coins. " + (f"Affordable now with shop(item=…): {', '.join(buys[:6])}. " if buys else "")
                   + "game_corner('slots', N) wins coins (a full bet is 3); game_corner('buy_coins', N) buys them at ¥20 each.")
    if MAP_KIND.get(t.here) == "pokecenter":                    # the PC is right here: remind the model it exists
        stored = _safe("pc_count", lambda: len(r.read_boxes()), 0)
        if stored:
            out.append(f"PC: {stored} Pokémon stored in the boxes — pc('list', detail=true) to look, "
                       "pc('swap') / pc('withdraw') to bring one into the party.")
    return out


def _gym(t: Tick) -> list[str]:
    """Inside a gym point at the Leader — unless already beaten (the agent once looped in/out of Pewter Gym)."""
    if t.in_battle or not t.overworld or MAP_KIND.get(t.here) != "gym":
        return []
    leader = GYM_MAP_LEADER.get(t.here)
    if leader and leader in t.ltm.data["gyms_beaten"]:
        return [f"GYM ALREADY BEATEN: you already defeated {leader} here — do NOT challenge them again. LEAVE the gym "
                "(walk_to the exit door) and head to your NEXT objective in the Navigation section."]
    return ["GYM: to fight the Leader, call challenge_leader() — it walks up to them and starts the battle. (heal() and "
            "save_state first.) Do NOT use go_to inside a gym." + (f"\nLeader: {gym_brief(leader)}" if leader else "")]


def _field(t: Tick) -> list[str]:
    """Map size, surrounding tiles, item balls and the suggested direction (overworld with a ready tilemap)."""
    state, tm, out = t.state, t.tilemap, []
    if not (t.overworld and tm.ready):
        return out
    if tm._width and tm._height:
        out.append(f"Map size: {tm._width}×{tm._height} (walk_to needs 0≤x<{tm._width}, 0≤y<{tm._height})")
    out.append(f"Tiles: {tm.surroundings_str(state.player_x, state.player_y)}")
    balls = t.reader.read_item_ball_tiles()
    if balls:
        where = ", ".join(f"({x},{y})" for x, y in balls[:5])
        out.append(f"Items on the ground: item ball(s) at {where} — call pick_up_items() to collect them before leaving.")
    direction = get_travel_direction(state)
    if direction:
        passable = tm.passable_directions(state.player_x, state.player_y)
        if passable.get(direction):
            out.append(f"Suggested: press {DIRECTION_BUTTON[direction]} ({direction} tile is floor, matches travel direction)")
        else:
            alts = [f"{DIRECTION_BUTTON[d]}({d})" for d, ok in passable.items() if ok]
            out.append(f"Travel {direction} blocked — passable: {', '.join(alts) or 'none'} (find a detour)")
    return out


def _exits(t: Tick) -> list[str]:
    """Indoors: the door/stairs tiles. Outdoors: which edge leads to which map."""
    state, tm = t.state, t.tilemap
    if tm.ready and infer_building_type(state.map_bank, state.map_id) == "interior":
        # A door can span several adjacent warp tiles but usually only the CENTER one warps: collapse each run to its middle.
        warps = door_centers(tm.read_warps())
        if not warps:
            return []
        px, py = state.player_x, state.player_y
        nearest = min(warps, key=lambda w: abs(w[0] - px) + abs(w[1] - py))
        steps = []
        if nearest[1] > py:
            steps.append(f"{nearest[1] - py} Down")
        elif nearest[1] < py:
            steps.append(f"{py - nearest[1]} Up")
        if nearest[0] > px:
            steps.append(f"{nearest[0] - px} Right")
        elif nearest[0] < px:
            steps.append(f"{px - nearest[0]} Left")
        toward = ", then ".join(steps) if steps else "you are next to it — step onto it"
        coords = ", ".join(f"({x},{y})" for x, y in warps[:4])
        return [f"EXITS (door/stairs tiles): {coords}. To leave the building, call walk_to{nearest} — it will path there "
                f"and step through. (Nearest is {nearest}: {toward}.)"]
    if tm.ready and t.overworld:
        conns = tm.read_connections()
        if conns:
            parts = [f"{c['direction']}→{MAP_NAMES.get((c['map_bank'], c['map_id']), str(c['map_bank']) + '/' + str(c['map_id']))}"
                     for c in conns]
            return ["Map edges (call go_to_map(direction) to travel there): " + ", ".join(parts)]
    return []


def _loop_signals(t: Tick) -> list[str]:
    """Changes since last tick, revisit and stuck warnings. Side effect: when stuck on the overworld with vision on and no map
    queued, re-queue the area map so the agent can re-orient."""
    state, stm, out = t.state, t.stm, []
    forced = _forced_switch(t)
    if forced:
        return (["Changes: " + "; ".join(t.diff.notes)] if t.diff.notes else []) + forced      # never "press A" here
    if t.diff.notes:
        out.append("Changes: " + "; ".join(t.diff.notes))
    visits = stm.visit_count(state.player_x, state.player_y)
    if visits >= 4 and t.overworld:
        out.append(f"REVISIT #{visits}: you have been at ({state.player_x},{state.player_y}) {visits} times — choose a "
                   "direction you have NOT tried recently")
    if stm.stuck:
        ctx = state.context.name
        if ctx == "IN_BATTLE":
            out.append("STUCK: same battle action repeating — try a different move or switch Pokémon")
        elif ctx in ("DIALOG_OPEN", "TRANSITIONING"):
            out.append("STUCK: dialog/transition not advancing — press A")
        elif ctx == "IN_MENU":
            out.append("STUCK in a menu — press B to close it and return to the field, or navigate with the D-pad and A")
        else:
            out.append("STUCK: position unchanged after repeated input — wall or obstacle ahead, try a different direction "
                       "or press B to cancel any open menu")
            if USE_VISION and t.run.pending_map_b64 is None:
                t.run.pending_map_b64, t.run.pending_map_name = AgentClient.load_area_map(*t.map_key)
    return out


def build_observation(*, state: "GameState", diff: "StateDiff", in_battle: bool, run, reader: "LeafGreenReader",
                      tilemap: "TilemapReader", ltm: "LongTermMemory", stm: "ShortTermMemory", map_key: tuple,
                      trip: dict | None = None) -> str:
    """The one-line observation the LLM sees each tick (sections joined with ' | ')."""
    t = Tick(state, diff, in_battle, run, reader, tilemap, ltm, stm, map_key, trip)
    parts = _header(t)
    if not in_battle and t.overworld:
        parts += _safari_status(t)
    if state.party:
        parts += _lead_line(t)
        if not in_battle and t.overworld:
            parts += _readiness_and_bag(t) + _shortcuts(t)
        parts += _trip(t)
        if in_battle:
            parts += _battle(t)
    parts.append(f"Pos: ({state.player_x},{state.player_y}) Map: {state.map_bank}/{state.map_id}")
    if not in_battle and state.context in (GameContext.OVERWORLD, GameContext.IN_MENU):
        parts += _supplies(t)
    parts += _gym(t) + _area(t) + _field(t) + _exits(t) + _loop_signals(t)
    # Close every turn with an explicit call to action: some models read a bare state dump as "no question asked".
    parts.append("→ Your turn: decide the best next action and call a tool NOW (do not reply with text only)")
    return " | ".join(parts)

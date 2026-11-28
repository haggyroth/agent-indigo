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
from agent.skills.newgame import env_configured, env_defaults
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
from knowledge.league_rooms import LEAGUE_ORDER, LEAGUE_ROOM_MAPS, LEAGUE_TRAINER, PLATEAU_CENTER_MAP, league_notice
from knowledge.status_cure import cure_hint
from knowledge.nicknames import suggest as nickname_ideas
from knowledge.leafgreen_data import GYM_MAP_LEADER, POKEMON_TYPES
from knowledge.map_graph import MAP_KIND
from knowledge.story_beats import story_line
from knowledge.matchup import Foe, better_matchup, low_hp_advice, roster
from knowledge.mon_quality import assess as assess_iv, hidden_power
from knowledge.move_semantics import catch_setup_hint
from knowledge.navigation import DIRECTION_BUTTON, MAP_NAMES, get_travel_direction, infer_building_type
from knowledge.party import can_attack, healthy_enough
from knowledge.readiness import FLAG_POKEDEX, assess as readiness_assess, render as readiness_render, battles_total, save_note
from knowledge.repel import REPEL_IDS, VAR_REPEL_STEP_COUNT, note as repel_note
from knowledge.shopping import shopping_summary

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
    if t.overworld:                                                                    # how the player is travelling right now
        if _safe("biking", t.reader.is_biking, False):
            on_road = _safe("cycling_road", lambda: bool(t.reader.read_flag(0x830)), False)         # FLAG_SYS_ON_CYCLING_ROAD
            out.append("Travelling: riding the Bicycle (twice walking speed; " + ("the Cycling Road keeps you on it, one way: south)" if on_road
                       else "walk_to / go_to get off it when they must; use_item('Bicycle') toggles it)"))
        elif _safe("surfing", t.reader.is_surfing, False):
            out.append("Travelling: surfing (walk_to / go_to_map cross water; step onto land to stop)")
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


def _story_status_for(t: Tick) -> dict:
    """The story chain's state from the live game (flags / key items / badges / milestones). Cut / Surf count as done only once TAUGHT."""
    from agent.story import story_status
    r, party = t.reader, t.state.party
    moves = {m for p in party for m in (p.move_ids or [])}
    flag = r.read_flag
    overrides = {"cut": 15 in moves, "surf": 57 in moves or bool(flag(0x239)), "strength": 70 in moves or bool(flag(0x23A))}
    return story_status(r, t.ltm, overrides)


def _sweep_line(t: Tick) -> list[str]:
    """Area progress for the named area (Mt. Moon, the S.S. Anne ...) the player is in — read from the game's own flags (knowledge.sweeps) — plus the warning when leaving would
    lose something (the S.S. Anne sails once HM01 is taken). Shown when it CHANGES (entering the area, a trainer beaten, an item taken), never every tick; silent in unnamed maps."""
    from knowledge import sweeps
    area = sweeps.area_of_map(t.here)
    if area is None:
        t.run.sweep_sig = None
        return []
    flag = t.reader.read_flag
    prog = sweeps.progress(area, flag)
    note = sweeps.missable_note(area, prog, flag)
    sig = (area, tuple(prog.values()), bool(note))
    if sig == t.run.sweep_sig:
        return []
    t.run.sweep_sig = sig
    if sweeps.complete(prog) and not note:
        return [f"AREA COMPLETE: {sweeps.line(area, prog)}"]
    return [f"AREA PROGRESS: {sweeps.line(area, prog)}" + (f"\n{note}" if note else "")]


def _side_quest_line(t: Tick) -> list[str]:
    """The side-quest digest (knowledge.story_beats.digest): shown when the SET of open side quests changes — never repeated every tick; quest() always lists them."""
    from agent.story import side_ctx
    from knowledge import story_beats as sb
    status = _story_status_for(t)
    ctx = side_ctx(t.reader)
    sq = sb.side_quests(status, ctx)
    sig = (tuple(b.key for b in sq["now"]), len(sq["locked"]))
    if sig == t.run.sidequest_sig:
        return []
    t.run.sidequest_sig = sig
    line = sb.digest(status, ctx)
    return [line] if line else []


def _post_game_line(t: Tick) -> list[str]:
    """After the Hall of Fame: what is left (knowledge.completion.post_game_text) — information only, shown when it changes and every 60 ticks, silent before the game is cleared."""
    from agent.story import side_ctx
    from knowledge import completion
    ctx = side_ctx(t.reader)
    if not ctx.game_clear:
        return []
    status = _story_status_for(t)
    national = bool(t.reader.read_flag(completion.NATIONAL_DEX_FLAG))
    sig = (ctx.owned, national, ctx.flags, tuple(completion.open_side_quests(status, ctx)))
    if sig == t.run.postgame_sig and t.run.step_count % 60 != 0:
        return []
    t.run.postgame_sig = sig
    return [completion.post_game_text(ctx.owned, national, status, ctx)]


def _achievement_line(t: Tick) -> list[str]:
    """RetroAchievements of the LeafGreen set (local tracking, #358): the progress once per run, then only the unlocks as they happen — shown when the journal's count changes (main refreshes it every
    few ticks), never repeated. quest('achievements') lists what is left and what can still be lost."""
    d = t.ltm.data
    sig = (int(d.get("achievements", 0) or 0), int(d.get("achievement_points", 0) or 0))
    if sig == t.run.achv_sig:
        return []
    from agent import ra
    from knowledge import ra_progress
    from knowledge.ra_set import ACHIEVEMENTS
    states = ra.states(t.reader, t.ltm)
    yes = frozenset(aid for aid, st in states.items() if st == "yes")
    seen, t.run.achv_sig, t.run.achv_seen = t.run.achv_seen, sig, yes
    if seen is None:                                                  # the first look of this run: the baseline
        return [f"{ra_progress.line(states)} quest('achievements') lists what is left and what can still be lost."]
    new = [(title, pts) for aid, title, _d, pts, _k in ACHIEVEMENTS if aid in yes and aid not in seen]
    if not new:
        return []
    shown = ", ".join(f"'{title}' (+{pts})" for title, pts in new[:3]) + (f" and {len(new) - 3} more" if len(new) > 3 else "")
    return [f"★ Achievement unlocked (local tracking): {shown}. {ra_progress.line(states)}"]


def _rematch_line(t: Tick) -> list[str]:
    """Rematch progress once the VS Seeker is owned (knowledge.rematches): shown when the counts change, silent otherwise and before the item exists."""
    from knowledge import rematches
    flag = t.reader.read_flag
    if not flag(rematches.VS_SEEKER_FLAG):
        return []
    s = rematches.status(flag)
    sig = (s["at_top"], s["ready"], tuple(sorted(s["waiting"].items())))
    if sig == t.run.rematch_sig:
        return []
    t.run.rematch_sig = sig
    return [rematches.line(flag)]


def _next_beat_money(t: Tick, items) -> str:
    """The MONEY line when the next story beat wants more yen than we hold (knowledge.money): the gap and how to earn it."""
    from knowledge.money import money_line
    from knowledge.story_beats import next_beats
    from knowledge.money import MONEY_NEEDS
    ready = [b for b in next_beats(_story_status_for(t)) if b.key in MONEY_NEEDS]          # the first open beat that costs money to prepare for
    if not ready:
        return ""
    bag: dict = {}
    for iid, qty in items:                                           # the pocket can hold the same id in two stacks
        bag[iid] = bag.get(iid, 0) + qty
    return money_line(ready[0].key, t.reader.read_money(), bag, t.state.party)


def _aide_line(t: Tick) -> str:
    """One line when an Oak's Aide reward can be collected now (Flash 10 caught, Itemfinder 30, Exp. Share 50), or the next one is within 3 species."""
    from knowledge.aides import next_reward, ready
    owned = t.reader.read_pokedex()[0]
    claim = ready(owned, t.reader.read_flag)
    if claim:
        key, label, _need = claim[0]
        extra = " (Route 15's west gatehouse, 2nd floor — it is held automatically by your lowest-level Pokémon)" if key == "exp_share" else ""
        return f"OAK'S AIDE: you have caught {owned} species — {label} is waiting: quest('{key}'){extra}."
    nxt = next_reward(owned, t.reader.read_flag)
    if nxt and nxt[1] <= 3:
        return f"OAK'S AIDE: {nxt[1]} more species caught and an aide gives you {nxt[0]}."
    return ""


PARCEL_ITEM = 349       # ITEM_OAKS_PARCEL (a key item)


def _opening_line(t: Tick) -> str:
    """The first phase of the game, before Oak's Pokédex: what to do next, and what NOT to do (a watched run shopped and grinded with the parcel in its bag)."""
    if PARCEL_ITEM in _safe("key_items", t.reader.read_key_items, []):
        return ("OAK'S PARCEL is in your bag — take it to Prof. Oak in his lab (Pallet Town): quest('parcel') does it. Until he has it the Viridian Mart sells nothing and the road north "
                "stays shut, so do NOT shop() or grind() yet (Oak gives you the first Poké Balls).")
    return ("OPENING: the Viridian Mart clerk gives you Oak's Parcel when you walk in — fetch it, then take it to Prof. Oak (quest('parcel') does both). "
            "Shopping, grinding and the gyms wait until Oak has given you the Pokédex.")


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
    broke = d.get("shop_broke_at")                 # a shop() visit that bought nothing for lack of money: no "shop()" nag until richer
    if broke is not None:
        if money > broke:
            d.pop("shop_broke_at", None)
        else:
            money = 0                              # (money only feeds the shop() need in readiness)
    due = save_note(d.get("badges_earned", 0), battles_total(d), d.get("saved_badges"), d.get("saved_battles", 0))
    opening = not _safe("pokedex_flag", lambda: r.read_flag(FLAG_POKEDEX), True)      # before Oak's Pokédex: the starter / rival / parcel phase
    block = readiness_render(readiness_assess(party, balls, pots, money, d.get("gyms_beaten", []),
                                              dex=dex, tms=tms, boxes=boxes, save_due=due, pokedex=not opening))
    if block:
        out.append(block)
    if opening:
        out.append(_opening_line(t))
    story = _safe("story", lambda: story_line(_story_status_for(t)), "")        # what the main story wants next (after Brock)
    if story and (d.get("badges_earned", 0) >= 1 or opening):
        out.append(story)
        nxt = _safe("money", lambda: _next_beat_money(t, items), "")
        if nxt:
            out.append(nxt)
    aide = _safe("aide", lambda: _aide_line(t), "")
    if aide and d.get("badges_earned", 0) >= 1:
        out.append(aide)
    if t.overworld and not opening:
        out.extend(_rematch_line(t))
    if t.overworld and not opening and d.get("badges_earned", 0) >= 1:
        out.extend(_side_quest_line(t))
        out.extend(_post_game_line(t))
    if t.overworld and not opening:
        out.extend(_sweep_line(t))
        out.extend(_safe("achievements", lambda: _achievement_line(t), []))
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
                           stored=_safe("stored", r.read_stored_species, set()))
        if v.catch:
            taken = [p.nickname for p in party if p.nickname]
            out.append(f"Worth catching: {v.reason}. A rock doubles the catch rate (but it may flee), bait halves it (but calms it); "
                       "rock then ball is the usual line. When you throw the ball, pass a funny, inventive nickname you make up"
                       + (f" (taken: {', '.join(taken)})" if taken else "") + f" — e.g. {', '.join(nickname_ideas(enemy.species_name, taken, 3))}.")
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
    vol = _safe("volatiles", lambda: r.read_battle_volatiles(0), {})
    trapped = bool(vol.get("wrapped") or vol.get("escape_prevention"))      # the game refuses switch AND run: advice to do either only makes the model try (a watched run failed 6 switches)
    hint = ("Teammates that can still attack: " + ", ".join(backups) + " — switch_pokemon to one.") if backups and not trapped else ""
    out.append(battle_summary(move_names, run.current_enemy, me.hp_percent, pp_view, attacker_types=lead_types,
                              opponent_status=enemy.status if enemy else "", disabled_slot=d_slot, disabled_turns=d_turns,
                              backup_hint=hint, wild=not run.battle_is_trainer, user_level=me.level, user_hp_frac=me.hp_percent,
                              foe_level=(enemy.level or 0) if enemy else 0, foe_hp=enemy.current_hp if enemy else 0,
                              hidden_power=hidden_power(me.ivs),
                              foe_ability=_safe("foe_ability", lambda: r.read_foe_battler().get("ability", 0), 0)))
    if enemy and enemy.max_hp:           # who is down, who is up, and who matches up well against THIS foe
        foe = _foe_info(t, enemy)
        heals = _safe("heals", lambda: [HEAL_HP[i] for i, q in r.read_items_pocket() if q and i in HEAL_HP], [])
        for line in (roster(party, active, foe=foe), "" if trapped else better_matchup(party, active, foe=foe),
                     low_hp_advice(party, active, foe, heals, wild=not run.battle_is_trainer, trapped=trapped)):
            if line:
                out.append(line)
    cure = _safe("status_cure", lambda: cure_hint(me.nickname or me.species_name or "Your lead", me.status, dict(r.read_items_pocket()), me.hp_percent), "")
    if cure:
        out.append(cure)                                      # the Bag holds the cure; nothing else ever tells the model so
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
    out.extend(_volatiles(vol))
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
        shot = _safe("one_shot", lambda: _one_shot(t, enemy, move_names, pp_view), "")
        if shot:
            out.append(shot)                                  # a Snorlax / a legend: catch it, never KO it
        else:
            out.append("WILD battle — you may flee_battle() to escape if you're just passing through or HP is low.")
        out.extend(_catch_advice(t, enemy, move_names, pp_view))
    return out


def _one_shot(t: Tick, enemy, move_names, pp_view) -> str:
    """The ONE-SHOT protocol for a Snorlax / legendary foe (knowledge.one_shot), and the battle-start save it promises (slot 9, once per encounter)."""
    from knowledge.leafgreen_data import MOVE_POWER
    from knowledge.one_shot import SAVE_SLOT, gentlest_move, is_one_shot, protocol
    shiny = bool(enemy and not getattr(t.run, "battle_is_trainer", False) and getattr(enemy, "is_shiny", False))
    if not enemy or not enemy.max_hp or not is_one_shot(enemy.species_id, t.map_key, shiny):
        return ""
    key = (enemy.species_id, tuple(t.map_key))
    if getattr(t.run, "one_shot_saved", None) != key:
        if t.reader.client.save_state(SAVE_SLOT):             # the very first look at this foe: nothing has hit it yet
            t.run.one_shot_saved = key
    balls = {b: n for b, n in t.reader.read_bag().items() if b in BALL_IDS}
    asleep = any(w in (enemy.status or "") for w in ("asleep", "paraly"))
    return protocol(enemy.species_id, enemy.current_hp, enemy.max_hp, balls, catch_setup_hint(move_names, pp_view),
                    gentlest_move(move_names, pp_view, MOVE_POWER), asleep, map_key=t.map_key, shiny=shiny, species_name=enemy.species_name)


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
    if enemy and getattr(enemy, "is_shiny", False):           # the ONE-SHOT block above already says to catch it; the verdicts below ("you already have one", "not worth a ball") must not talk the model out of it
        taken = [p.nickname for p in party if p.nickname]
        return ["Pass a funny, inventive nickname to catch() — a shiny deserves a good one (e.g. " + ", ".join(nickname_ideas(enemy.species_name, taken, 3)) + "). "
                "A full party sends it to the PC box; pc('swap') brings it into the team."]
    if r.client.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_GHOST:
        return ["GHOST — the Pokémon Tower's ghost Marowak dodges every ball (it CAN'T be caught): don't catch(); defeat it with use_move, then carry on."]
    balls = sum(r.read_bag().get(b, 0) for b in BALL_IDS)
    if balls > 0 and enemy and enemy.species_id and enemy.species_id not in {p.species_id for p in party}:
        v = catch_evaluate(party, enemy.species_id, enemy.level or 0, dex_owned=r.read_dex_owned(enemy.species_id),
                           stored=_safe("stored", r.read_stored_species, set()))
        if not v.catch:
            return [f"NOT worth a ball right now: {v.reason}. "
                    "Skip it (flee_battle) unless you have a reason to want it."]
        taken = [p.nickname for p in party if p.nickname]
        return [f"NEW SPECIES you don't own ({balls} Poké Balls in bag) — worth catching: {v.reason}. "
                "Weaken it first with use_move (low HP raises the catch rate). When you catch it, pass a funny, inventive "
                "nickname you make up (not the species name; it needn't relate to the Pokémon — e.g. "
                + ", ".join(nickname_ideas(enemy.species_name, taken, 3)) + ")" + (f"; already taken: {', '.join(taken)}" if taken else "")
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
    if MAP_KIND.get(t.here) == "mart" and _safe("pokedex_flag", lambda: r.read_flag(FLAG_POKEDEX), True):      # the Viridian Mart sells nothing before Oak's Pokédex
        rec = shopping_summary(bag, t.ltm.data["badges_earned"], money)
        if rec:
            out.append("MART — " + rec + ". Call shop() to buy the recommended restock automatically.")
    if t.here == (3, 6) or t.here[0] == 10:                    # Celadon City / its Dept. Store: the only place that sells evolution stones (4F)
        from knowledge.shop_stock import ITEM_LABELS, PRICES
        from knowledge.shopping import stone_wants
        wants = _safe("stone_wants", lambda: stone_wants(state.party, bag, money, reserve=3000), [])
        if wants:
            out.append("STONES — the Dept. Store (4F) sells evolution stones: " + "; ".join(
                f"{ITEM_LABELS[sid]} ¥{PRICES[sid]} → {who} evolves into {into}" for sid, who, into in wants[:3])
                + ". shop(item='<stone>') buys it, then use_item('<stone>', '<pokemon>') evolves it.")
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


def _league(t: Tick) -> list[str]:
    """Inside an Elite Four room: say plainly that there is no leaving to heal (a run walked the sealed room, calling heal() and go_to('Pokemon Center') for 300 calls)."""
    if t.here == PLATEAU_CENTER_MAP and not _safe("league_clear", lambda: bool(t.reader.read_flag(0x82C)), False):
        scouting = " ‖ ".join(gym_brief(name) for name in LEAGUE_ORDER if gym_brief(name))
        return [f"ELITE FOUR AHEAD (north door of this Center; five sealed rooms, one after another, no healing but the Bag): {scouting}"] if scouting else []
    if t.here not in LEAGUE_ROOM_MAPS:
        return []
    bag = _safe("league_bag", lambda: dict(t.reader.read_items_pocket()), None)
    note = league_notice(t.here, t.state.party or None, bag)
    out = [f"ELITE FOUR: {note}"] if note else []
    brief = gym_brief(LEAGUE_TRAINER.get(t.here, ""))
    if brief:
        out.append(f"THIS ROOM: {brief} — use team_report() to see who of yours answers it")
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


def _env_choice_note() -> str:
    """When .env sets STARTER / PLAYER_NAME / RIVAL_NAME (the human chose for the model): say what they are, so the model just calls quest('new_game')."""
    if not env_configured():
        return ""
    d = env_defaults()
    return f". .env already chose: {d['starter']}, you are {d['name']}, the rival {d['rival']} — plain quest('new_game') uses them"


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
    parts += _league(t) + _gym(t) + _area(t) + _field(t) + _exits(t) + _loop_signals(t)
    if not in_battle and (state.map_bank == 0 or not state.party):
        parts.append("NEW GAME: the game has not started (title screen / intro / no Pokémon yet) — quest('new_game') plays the intro, names you, picks the starter and "
                     "fetches Oak's Parcel. YOU choose your name, your rival's name and your starter (bulbasaur | charmander | squirtle): quest('new_game squirtle name=KYLE rival=GARY girl'). "
                     "It will also ask you to nickname your starter" + _env_choice_note())
    # Close every turn with an explicit call to action: some models read a bare state dump as "no question asked".
    parts.append("→ Your turn: decide the best next action and call a tool NOW (do not reply with text only)")
    return " | ".join(parts)

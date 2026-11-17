"""The game-event stream: one compact terminal line (and one run.jsonl record) per thing that happens.

At native speed the terminal is the only live view of a run, and skills such as grind() / go_to() / heal() play
hundreds of turns inside ONE tool call. So events are emitted from where they happen:

  * explicit emits in the skills (a catch, a heal, a shop trip, a PC move, a trip leg …);
  * `observe(reader)` — a cheap snapshot diff called after every tool, after every battle move and every main-loop
    tick — which turns party / badge / battle changes into level-ups, evolutions, faints, new moves, badges and
    battle start/end lines, wherever in the code the game state moved.

Verbosity (LOG_LEVEL): ``quiet`` (milestone events only), ``events`` (default: + every tool call and the quieter
events), ``debug`` (+ observation / reasoning lines). Until `configure()` is called (tests, scripts) nothing prints;
events are still kept in `recent()` so they can be asserted on.
"""
from __future__ import annotations

import time
from collections import Counter, deque

from agent.skills.base import log_once

LEVELS = {"quiet": 0, "events": 1, "debug": 2}

# kind -> (icon, rich style)
STYLE = {
    "tool": ("▸", "cyan"), "battle_start": ("⚔", "magenta"), "battle_end": ("⚑", "magenta"),
    "foe_ko": ("✓", "green"), "faint": ("💥", "red"), "catch": ("🎯", "green bold"),
    "level_up": ("⬆", "green"), "evolve": ("✨", "green bold"), "learn_move": ("📖", "green"),
    "heal": ("✚", "green"), "shop": ("🛒", "yellow"), "pc": ("💾", "blue"), "badge": ("🏅", "yellow bold"),
    "gym_leader": ("🏆", "yellow bold"), "key_item": ("🔑", "cyan bold"), "town": ("🗺", "cyan"),
    "blackout": ("☠", "red bold"), "hm_use": ("🌿", "green"), "trip": ("➜", "blue"), "party": ("👥", "dim"),
    "checkpoint": ("⚑", "dim"), "status": ("●", "dim"), "milestone": ("★", "green bold"), "note": ("·", "dim"),
}

_S: dict = {"console": None, "run_log": None, "level": 1, "t0": time.time(), "last": None, "party": None,
            "badges": None, "battle": None, "hooks": []}
_RECENT: deque = deque(maxlen=300)
COUNTS: Counter = Counter()
OUTCOMES: Counter = Counter()        # battle outcome label -> count, this run (won / lost / fled / caught / …)
TRAINER_WINS: Counter = Counter()    # {"n": trainer battles won this run}


def configure(console=None, run_log=None, level: str = "events") -> None:
    """Turn printing on (console) and run-log recording on. Called once by main."""
    _S.update(console=console, run_log=run_log, level=LEVELS.get(str(level).lower(), 1), t0=time.time(),
              party=None, badges=None, battle=None, hooks=[])
    COUNTS.clear()
    OUTCOMES.clear()
    TRAINER_WINS.clear()
    _RECENT.clear()


def reset() -> None:
    configure(None, None)


_STAT_KINDS = {"catches": "catch", "level_ups": "level_up", "evolutions": "evolve", "faints": "faint",
               "blackouts": "blackout", "badges": "badge", "new_towns": "town", "key_items": "key_item",
               "heals": "heal"}


def run_stats() -> dict:
    """What happened this run, from the event stream: the scoreboard that replaced the reward counter (#212).
    Battles are by real outcome (won / lost / fled / caught / drew …)."""
    out = {name: COUNTS[kind] for name, kind in _STAT_KINDS.items()}
    out["battles"] = dict(OUTCOMES)
    out["trainer_wins"] = TRAINER_WINS["n"]
    return out


def stats_line(stats: dict | None = None) -> str:
    """'badges 2 · battles 41 (36 won, 3 fled, 2 caught) · catches 2 · level-ups 17 · faints 4 · blackouts 0'."""
    s = stats if stats is not None else run_stats()
    b = s.get("battles", {})
    detail = ", ".join(f"{n} {k}" for k, n in sorted(b.items(), key=lambda kv: -kv[1]))
    return (f"badges {s.get('badges', 0)} · battles {sum(b.values())}" + (f" ({detail})" if detail else "")
            + f" · catches {s.get('catches', 0)} · level-ups {s.get('level_ups', 0)} · evolutions {s.get('evolutions', 0)}"
            f" · faints {s.get('faints', 0)} · blackouts {s.get('blackouts', 0)}")


def recent(kind: str | None = None) -> list[dict]:
    return [e for e in _RECENT if kind is None or e["kind"] == kind]


def on_battle_end(fn) -> None:
    """Register `fn(summary: dict)`, called exactly once for every finished battle wherever it was fought —
    inside a skill, inside a tool call or on the main loop. This is where the journal, the win/loss/fled/caught
    counters and the journal rows are booked (the old main-loop edge detector never saw battles inside a skill)."""
    _S["hooks"].append(fn)


def note_move(name: str) -> None:
    """A move was used in the current battle (a turn)."""
    b = _S["battle"]
    if b is not None and name:
        b["turns"] += 1
        b["moves"].append(name)


def current_foe() -> str | None:
    """'Rattata L4' for the battle the observer is tracking, else None."""
    b = _S["battle"]
    return b["foe"] if b and b.get("foe") else None


def _clock() -> str:
    return time.strftime("%H:%M:%S")


def emit(kind: str, text: str, *, major: bool = True, log: bool = True, debug: bool = False, **fields) -> dict:
    """Record one event. `major` events print even at LOG_LEVEL=quiet; `debug` ones only at debug; `log=False`
    keeps it out of run.jsonl (the tool event already has its own richer record)."""
    rec = {"kind": kind, "text": text, **fields}
    _RECENT.append(rec)
    COUNTS[kind] += 1
    lvl = _S["level"]
    if _S["run_log"] is not None and log:
        try:
            _S["run_log"].event("ev", ev=kind, text=text, **fields)
        except Exception:
            log_once("events.emit", "events.emit: tolerated failure (continuing with a default)")
            pass
    con = _S["console"]
    if con is None or (debug and lvl < 2) or (not major and lvl < 1):
        return rec
    icon, style = STYLE.get(kind, ("·", "dim"))
    try:
        from rich.markup import escape
        con.print(f"[dim]{_clock()}[/] [{style}]{icon} {escape(text)}[/]", highlight=False)
    except Exception:
        log_once("events.emit", "events.emit: tolerated failure (continuing with a default)")
        pass
    return rec


# ── tool calls ─────────────────────────────────────────────────────────────────────────────────────
def _compact_args(args_json: str) -> str:
    import json
    try:
        args = json.loads(args_json) if args_json else {}
    except Exception:
        log_once("events._compact_args", "events._compact_args: tolerated failure (continuing with a default)")
        return str(args_json)[:60]
    if not isinstance(args, dict):
        return str(args)[:60]
    return ", ".join(f"{k}={v!r}" for k, v in args.items() if v not in ("", None, False))[:90]


def tool(name: str, args_json: str, result, secs: float) -> dict:
    """`use_move(move='Tackle') → Used Tackle. [foe …]  (2.3s)` — arguments, a one-line result, timing."""
    one = " ".join(str(result).split())
    if len(one) > 170:
        one = one[:167] + "…"
    slow = f"  ({secs:.1f}s)" if secs >= 1.0 else ""
    return emit("tool", f"{name}({_compact_args(args_json)}) → {one}{slow}", major=False, log=False,
                name=name, secs=round(secs, 2))


# ── outcome classification (shared with the battle accounting) ─────────────────────────────────────────
OUTCOME_LABELS = {1: "won", 2: "lost", 3: "drew", 4: "fled", 5: "teleported", 6: "foe fled", 7: "caught",
                  8: "foe teleported"}


def battle_outcome_label(code: int, all_fainted: bool = False) -> str:
    """gBattleOutcome → words. A wiped party is a loss whatever the byte says."""
    if all_fainted:
        return "lost"
    return OUTCOME_LABELS.get(int(code), "ended")


# ── the snapshot observer ─────────────────────────────────────────────────────────────────────────────
def _plausible(p) -> bool:
    return 1 <= getattr(p, "species_id", 0) <= 411 and 1 <= getattr(p, "level", 0) <= 100 and getattr(p, "max_hp", 0) > 0


def _name(p) -> str:
    return getattr(p, "nickname", "") or getattr(p, "species_name", "") or "?"


def observe(reader, ltm=None) -> None:
    """Diff the live game against the last snapshot and emit what changed. Safe to call as often as you like
    (it reads the party block, the badge byte and the battle flag); never raises."""
    if reader is None:
        return
    for step in (_observe_party, _observe_badges, _observe_battle):
        try:
            step(reader)
        except Exception:
            log_once("events.observe", "events.observe: tolerated failure (continuing with a default)")
            pass


def _observe_party(reader) -> None:
    party = list(reader.read_party())
    if not party or not all(_plausible(p) for p in party):       # a battle-load / transition frame can read as garbage
        return
    new = {p.personality: p for p in party if getattr(p, "personality", 0)}
    old = _S["party"]
    _S["party"] = new
    if old is None or not new:
        return
    for pid, p in new.items():
        o = old.get(pid)
        if o is None:
            emit("party", f"{_name(p)} joined the party ({p.species_name} L{p.level})", major=False)
            continue
        if p.species_id != o.species_id:
            emit("evolve", f"{_name(o)} evolved into {p.species_name}!", species=p.species_name)
        if p.level > o.level:
            emit("level_up", f"{_name(p)} reached L{p.level}" + (f" (+{p.level - o.level})" if p.level - o.level > 1 else ""),
                 level=p.level, species=p.species_name)
        if o.current_hp > 0 and p.current_hp == 0:
            emit("faint", f"{_name(p)} fainted", species=p.species_name)
        learned = [m for m in (p.move_names or []) if m and m not in (o.move_names or [])]
        for m in learned:
            emit("learn_move", f"{_name(p)} learned {m}", move=m)
    for pid, o in old.items():
        if pid not in new:
            emit("party", f"{_name(o)} left the party", major=False)


def _observe_badges(reader) -> None:
    count, bits = reader.read_badges()
    old = _S["badges"]
    _S["badges"] = bits
    if old is None or bits == old:
        return
    from knowledge.leafgreen_data import GYMS
    for bit in range(8):
        if bits & (1 << bit) and not old & (1 << bit):
            gym = next((g for g in GYMS if g["badge_bit"] == bit), None)
            emit("badge", f"{gym['badge'] if gym else 'badge'} #{count} — beat {gym['leader'] if gym else '?'}!",
                 badge=bit)


def _battle_settled(reader) -> bool:
    """The player's controller is at the action / move menu — gBattleMons[1] (the foe) is the REAL foe now, not
    the previous battle's leftovers that sit there during the intro."""
    from game.constants import Addr
    return reader.client.read32(Addr.BATTLE_CTRL_FUNC) in (
        Addr.CTRL_CHOOSE_ACTION, Addr.CTRL_CHOOSE_ACTION_ALT, Addr.CTRL_CHOOSE_MOVE)


def _observe_battle(reader) -> None:
    from game.constants import Addr
    from game.state import GameContext
    in_battle = reader.detect_context() == GameContext.IN_BATTLE
    cur = _S["battle"]
    if in_battle:
        if cur is None:
            trainer = bool(reader.client.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER)
            try:
                from knowledge.navigation import MAP_NAMES
                where = MAP_NAMES.get(reader.read_current_map(), "")
            except Exception:
                log_once("events._observe_battle", "events._observe_battle: tolerated failure (continuing with a default)")
                where = ""
            _S["battle"] = cur = {"trainer": trainer, "foe": None, "foe_hp": None, "foe_species": None,
                                  "where": where, "announced": False, "turns": 0, "moves": [], "lead": "",
                                  "active": 0, "foe_name": "", "foe_level": 0}
        if not _battle_settled(reader):
            return                                   # intro / animations: the foe slot may still hold the last foe
        foe = None
        try:
            foe = reader.read_enemy_lead()
        except Exception:
            log_once("events._observe_battle", "events._observe_battle: tolerated failure (continuing with a default)")
            pass
        if not (foe and foe.species_id and foe.max_hp and not (foe.species_name or "").startswith("#")):
            return
        label = f"{foe.species_name} L{foe.level}"
        try:
            cur["active"] = reader.read_active_battle_species()
            if not cur["lead"]:
                cur["lead"] = (reader.read_party() or [None])[0].species_name
        except Exception:
            log_once("events._observe_battle", "events._observe_battle: tolerated failure (continuing with a default)")
            pass
        if not cur["announced"]:
            cur["announced"] = True
            emit("battle_start", f"{'trainer battle' if cur['trainer'] else 'wild'} {label}"
                 + (f" @ {cur['where']}" if cur["where"] else ""), trainer=cur["trainer"], foe=label)
        elif cur["foe_hp"] and foe.current_hp == 0 and cur["foe_species"] == foe.species_id:
            emit("foe_ko", f"{foe.species_name} fainted", major=False)
        cur["foe"], cur["foe_hp"], cur["foe_species"] = label, foe.current_hp, foe.species_id
        cur["foe_name"], cur["foe_level"] = foe.species_name, foe.level or 0
        return
    if cur is not None:
        _S["battle"] = None
        party = reader.read_party()
        wiped = bool(party) and all(p.current_hp == 0 for p in party)
        outcome = battle_outcome_label(reader.client.read8(Addr.BATTLE_OUTCOME), wiped)
        kind = "trainer" if cur["trainer"] else "wild"
        OUTCOMES[outcome] += 1
        if cur["trainer"] and outcome == "won":
            TRAINER_WINS["n"] += 1
        if cur["announced"]:
            emit("battle_end", f"{outcome} vs {cur['foe']}", outcome=outcome, trainer=cur["trainer"], foe=cur["foe"])
        else:                                        # never saw the menu (fled / ended inside one call)
            emit("battle_end", f"{kind} battle {outcome}", outcome=outcome, trainer=cur["trainer"])
        active = next((p for p in party if p.species_id == cur["active"]), party[0] if party else None)
        summary = {"outcome": outcome, "trainer": cur["trainer"], "foe_name": cur["foe_name"],
                   "foe_level": cur["foe_level"], "where": cur["where"], "turns": cur["turns"],
                   "moves": list(dict.fromkeys(cur["moves"])), "lead": cur["lead"],
                   "active": (active.species_name if active else cur["lead"]),
                   "hp_pct": (active.current_hp / active.max_hp if active and active.max_hp else 0.0),
                   "wiped": wiped, "announced": cur["announced"]}
        _S["last_battle"] = summary
        for fn in list(_S["hooks"]):
            try:
                fn(summary)
            except Exception:
                log_once("events._observe_battle", "events._observe_battle: tolerated failure (continuing with a default)")
                pass

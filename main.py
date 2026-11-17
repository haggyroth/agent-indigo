from datetime import datetime
from config import (RESUME, CHECKPOINT_EVERY, MODEL_NAME, TEMPERATURE, MGBA_BACKEND, START_FROM_SAVE, START_FROM_STATE, MAX_STEPS,
                    USE_VISION, PROGRESS_PATH, MAX_LLM_CALLS, TOKEN_BUDGET,
                    LLM_BASE_URL, MAX_WALL_SECONDS, LOG_LEVEL, STATUS_EVERY, IV_PEEK_BEFORE_CATCH)
from game.memory_reader import LeafGreenReader
from game.state import GameContext, GameState, StateDiff
from game.tilemap_reader import TilemapReader
from agent.lm_studio_client import AgentClient
from agent import events
from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory
from memory.battle_journal import BattleJournal, BattleRecord
from knowledge.system_prompt import build_system_prompt
from knowledge.navigation import get_travel_direction, DIRECTION_BUTTON, MAP_NAMES, infer_building_type
from knowledge.leafgreen_data import BADGE_BIT_MILESTONE, GYMS, GYM_MAP_LEADER, POKEMON_TYPES
from knowledge.shopping import shopping_summary
from knowledge.map_graph import MAP_KIND
from game.constants import Addr
from game.pathfinding import door_centers
from knowledge.battle import battle_summary, overworld_pp_summary
from knowledge.move_semantics import catch_setup_hint
from knowledge.mon_quality import hidden_power as _hidden_power
from rich.console import Console
from dataclasses import dataclass, field
from typing import Callable, Optional
from pathlib import Path
import os, time, sys, traceback

console = Console()

# Where uncaught per-tick exceptions are recorded (full tracebacks). The console
# only shows a scrolling summary; this file is the durable record for debugging a
# run after the fact. Sits alongside progress.json in the logs dir.
ERRORS_LOG = Path(PROGRESS_PATH).parent / "errors.log"

# Bail out if this many decision ticks fail in a row. A persistent fault (LLM
# endpoint down, poisoned message history, a coding bug) would otherwise spin
# forever at ~1 Hz printing the same line; stopping cleanly saves progress and
# surfaces the failure instead of hiding it.
MAX_CONSECUTIVE_ERRORS = 30


def _log_exception(exc: Exception) -> None:
    """Append a timestamped full traceback to ERRORS_LOG (best-effort)."""
    try:
        ERRORS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(ERRORS_LOG, "a") as f:
            f.write(f"\n===== {datetime.now().isoformat(timespec='seconds')} "
                    f"{type(exc).__name__}: {exc} =====\n")
            traceback.print_exc(file=f)
    except Exception:
        pass  # logging must never mask the original error


def _party_brief(s: GameState) -> list:
    """Compact party snapshot for the run log: [species, level, hp, max_hp]."""
    out = []
    for p in s.party:
        out.append([getattr(p, "species_name", getattr(p, "species", "?")),
                    getattr(p, "level", 0), getattr(p, "current_hp", 0),
                    getattr(p, "max_hp", 0)])
    return out


def _run_summary(client, steps: int) -> str:
    """One-line end-of-run tally: steps, what happened (the event-stream statistics) and LLM usage (spend visibility)."""
    return (f"steps={steps}  {events.stats_line()}  "
            f"llm_calls={client.llm_calls}  tokens={client.total_tokens} "
            f"(prompt={client.total_prompt_tokens}, completion={client.total_completion_tokens})")


# A goal predicate: given the live state + long-term memory, has the episode's
# objective been met? Used by the eval harness (run_episode(goal=...)); None for
# an open-ended real run.
Goal = Callable[[GameState, LongTermMemory], bool]


@dataclass
class AgentRuntime:
    """Everything a decision loop needs, built once. Shared by the real run
    (main) and the eval harness so the two never drive the game differently."""
    mgba:    object
    reader:  LeafGreenReader
    client:  AgentClient
    ltm:     LongTermMemory
    stm:     ShortTermMemory
    journal: BattleJournal
    tilemap: TilemapReader


@dataclass
class EpisodeResult:
    """Outcome of one run_episode() call — the eval scorecard for a scenario."""
    reason:            str            # goal | max_steps | max_wall | max_llm_calls | token_budget | interrupted | error_budget
    passed:            bool           # goal predicate satisfied
    steps:             int
    llm_calls:         int
    prompt_tokens:     int
    completion_tokens: int
    final_map:         tuple[int, int]
    final_pos:         tuple[int, int]
    badges:            int
    stats:             dict = field(default_factory=dict)    # events.run_stats(): battles by outcome, catches, level-ups, faints…
    milestones:        list[str] = field(default_factory=list)
    stuck_ratio:       float = 0.0    # fraction of overworld decision ticks with no movement
    goal_desc:         str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def summary(self) -> str:
        flag = "PASS" if self.passed else "----"
        return (f"[{flag}] {self.reason}  steps={self.steps}  "
                f"map={self.final_map} pos={self.final_pos}  badges={self.badges}  "
                f"stuck={self.stuck_ratio:.0%}  llm_calls={self.llm_calls}  "
                f"tokens={self.total_tokens}")

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["total_tokens"] = self.total_tokens
        return d


def _status_line(state, ltm, client, reader, step: int, t_start: float) -> str:
    """The periodic one-line status: where the run stands without reading the whole scrollback."""
    try:
        party = ", ".join(f"{p.nickname or p.species_name} L{p.level} {p.current_hp}/{p.max_hp}" for p in state.party)
        bag = reader.read_bag()
        balls = sum(bag.get(b, 0) for b in (1, 2, 3, 4))
        money = reader.read_money()
    except Exception:
        party, balls, money = "?", "?", "?"
    mins = (time.time() - t_start) / 60
    return (f"STATUS step {step} · badges {ltm.data['badges_earned']}/8 · [{party}] · ¥{money} · balls {balls} · "
            f"LLM {client.llm_calls} calls / {client.total_tokens // 1000}k tok · {mins:.0f} min wall")


def _frame_chroma(mgba) -> float:
    """Mean chroma (max−min channel) over a coarse grid of the framebuffer.

    The FRLG quest-log recap renders the whole screen in a heavily *desaturated*
    palette (chroma ≈ 8–15), while normal gameplay is full color (chroma ≈ 60+).
    That gap is what lets us tell the recap apart from real play. Native backend
    only; returns a high value if no framebuffer is available so callers treat it
    as "not a recap".
    """
    fb_fn = getattr(mgba, "framebuffer", None)
    if fb_fn is None:
        return 999.0
    fb = fb_fn()
    W, H = 240, 160
    total = count = 0
    for y in range(0, H, 9):
        for x in range(0, W, 9):
            i = (y * W + x) * 4
            total += max(fb[i], fb[i + 1], fb[i + 2]) - min(fb[i], fb[i + 1], fb[i + 2])
            count += 1
    return total / count


# Above this mean chroma the screen is full-color gameplay; below it we're still
# in the desaturated quest-log recap. The two regimes are ~8 vs ~60, so the exact
# cutoff is not sensitive.
_RECAP_CHROMA_CUTOFF = 40.0


def _has_control(mgba, reader) -> bool:
    """True only if the player actually responds to input — the definitive test
    for *real* overworld control vs. the quest-log recap (which ignores the D-pad
    and only ends on B). The chroma gate alone false-positives on a bright recap
    frame or mid-fade (#79), so we confirm by moving.

    Note the Gen III turn-vs-step rule: the FIRST press of a direction you are not
    already facing only TURNS the character (no tile change); the second press
    steps. So we press each direction TWICE before concluding it didn't move —
    otherwise a real, controllable player reads as stuck. Any axis that steps ⇒
    control; we restore position with two opposite presses (turn, then step).
    """
    if reader.detect_context() != GameContext.OVERWORLD:
        return False
    for mv, back in (("Down", "Up"), ("Right", "Left"), ("Up", "Down"), ("Left", "Right")):
        before = reader.read_player_pos()
        mgba.tap(mv)                          # may only turn to face mv
        if reader.read_player_pos() == before:
            mgba.tap(mv)                      # now step
        if reader.read_player_pos() != before:
            mgba.tap(back)                    # turn back
            mgba.tap(back)                    # step back → restore origin
            return True
    return False


def drive_into_gameplay(mgba, reader, attempts: int = 4) -> bool:
    """Boot from the loaded battery save through the pre-gameplay gates into real
    player control. Returns True once normal gameplay is CONFIRMED (the player
    responds to input), retrying the whole boot up to `attempts` times because the
    recap skip is timing-flaky (#79).

    Two gates, each with its own tell:

      1. **Title screen / Continue menu** — not in the game world yet (map bank
         reads 0). Press A until a map loads (this taps through "PRESS START" and
         selects Continue).
      2. **Quest recap** ("Previously on your quest…") — the trap. It auto-plays a
         desaturated replay of recent events and *masquerades as OVERWORLD*
         (field callback, no fade, no menu), so detect_context() and position
         both lie: the recap even auto-animates the player. Neither A-mashing nor
         waiting escapes it — **B skips it**, and the palette snaps back to full
         color when it clears. We press B until the frame is no longer desaturated
         (see _frame_chroma) AND the player actually responds to input
         (_has_control) — chroma alone isn't enough.
    """
    for _attempt in range(attempts):
        mgba.reset()
        mgba.run_frames(200)                  # boot logos

        for _ in range(80):                   # gate 1: title + Continue → game world
            if mgba.read8(Addr.MAP_BANK) != 0:
                break
            mgba.tap("A")

        for _ in range(120):                  # gate 2: skip the recap with B
            if _frame_chroma(mgba) > _RECAP_CHROMA_CUTOFF:
                mgba.tick(10)                 # let the last transition settle
                if _has_control(mgba, reader):
                    return True               # full color AND input-responsive
            mgba.tap("B")
        # This attempt never reached confirmed control — reset and try again.
    return False                              # budget exhausted; hand off anyway


def build_runtime(*, backend: str = MGBA_BACKEND,
                  start_save: str = START_FROM_SAVE,
                  start_state: str = START_FROM_STATE,
                  ltm_path: Optional[str] = None,
                  journal_path: Optional[str] = None,
                  fresh_session: bool = True,
                  verbose: bool = True) -> Optional[AgentRuntime]:
    """Connect to the emulator, load the requested start point, and build every
    component the decision loop needs. Returns None if the emulator isn't ready.

    ltm_path / journal_path isolate persistent state — the eval harness points
    them at a scratch dir so a scenario never touches the real logs/progress.json.
    """
    def say(msg):
        if verbose:
            console.print(msg)

    if verbose:
        console.rule("[bold green]Pokemon LeafGreen LLM Agent")
    if backend == "native":
        from game.mgba_core import NativeMGBAClient
        mgba = NativeMGBAClient()
    else:
        from game.mgba_client import MGBAClient
        mgba = MGBAClient()
    if not mgba.verify_connection():
        say(f"[red]ERROR: emulator not ready or wrong ROM (backend={backend}).[/]")
        say("Expected AGB-BPGE (Pokemon LeafGreen). Check ROM_PATH / startup order.")
        return None
    say(f"[green]Connected ({backend}): {mgba.get_game_title()} ({mgba.get_game_code()})")

    # Warn on the one config that can run up real money: a non-local LLM endpoint
    # with no stopping condition at all. The run still proceeds (the user may want
    # it), but the cost exposure should be explicit rather than silent.
    _is_local = any(h in LLM_BASE_URL for h in ("localhost", "127.0.0.1", "::1"))
    if not _is_local and not (MAX_STEPS or MAX_LLM_CALLS or TOKEN_BUDGET):
        say(f"[yellow]⚠ Cloud endpoint ({LLM_BASE_URL}) with no run cap "
            f"(MAX_STEPS / MAX_LLM_CALLS / TOKEN_BUDGET all unset) — this "
            f"loop is unbounded and will keep spending until interrupted.[/]")

    reader = LeafGreenReader(mgba, decrypt=True)

    # Optionally load an mGBA save STATE directly — instant, no title/Continue/
    # recap. Takes precedence over start_save (native only).
    if start_state and backend == "native":
        if mgba.load_state_file(start_state):
            mgba.tick(30)   # let post-load fade/flags settle before first read
            s = reader.read_state()
            say(f"[green]Loaded save state: {start_state} "
                f"(map {s.map_bank}/{s.map_id}, pos ({s.player_x},{s.player_y}))[/]")
        else:
            say(f"[red]Could not load save state: {start_state}[/]")
    # Otherwise, optionally boot from a battery save and drive to "Continue" so the
    # agent starts in real gameplay instead of the new-game intro (native only).
    elif start_save and backend == "native":
        if mgba.load_save(start_save):
            got_control = drive_into_gameplay(mgba, reader)
            where = f"map {mgba.read8(Addr.MAP_BANK)}/{mgba.read8(Addr.MAP_ID)}"
            if got_control:
                say(f"[green]Continued from save: {start_save} ({where})[/]")
            else:
                say(f"[yellow]Continued from save but could not confirm player "
                    f"control ({where}) — may still be in the quest recap[/]")
        else:
            say(f"[red]Could not load save: {start_save}[/]")

    tilemap = TilemapReader(mgba)
    ltm     = LongTermMemory(path=ltm_path)
    client  = AgentClient(mgba, reader, ltm)
    stm     = ShortTermMemory()
    journal = BattleJournal(path=journal_path)

    if fresh_session:
        ltm.new_session()
    say(f"Session #{ltm.data['session_count']} | Badges: {ltm.data['badges_earned']}/8 | "
        f"Milestones: {len(ltm.data['milestones'])}")

    # ── Startup badge reconciliation ─────────────────────────────────────────
    # Sync LTM to EXACTLY match the loaded cartridge's badges (the ground truth for
    # this run) — adopting any the save has AND dropping any the journal claims but
    # the save doesn't. A journal left ahead of the save (e.g. testing an older save,
    # or an in-memory gym win that never hit the cartridge) otherwise deadlocks the
    # agent: it thinks a gym is beaten, heads on, and the game's guard NPC marches it
    # back. Read via the RELOCATION-SAFE reader.read_badges() (NOT the fixed
    # Addr.BADGES). Mid-session stays monotonic so a load_state retry can't un-earn.
    _sync = ltm.reconcile_badges_authoritative(reader.read_badges()[1])
    if _sync["dropped"]:
        say(f"[red bold]⚠ Journal was AHEAD of the save — dropped "
            f"{', '.join(_sync['dropped'])} to match the cartridge "
            f"(badges now {ltm.data['badges_earned']}/8). "
            f"Use `python -m tools.reset_journal` for a full reset.[/]")
    if _sync["adopted"]:
        say(f"[yellow]Adopted from the save into LTM: {', '.join(_sync['adopted'])}[/]")

    return AgentRuntime(mgba=mgba, reader=reader, client=client, ltm=ltm,
                        stm=stm, journal=journal, tilemap=tilemap)


@dataclass
class _RunState:
    """Mutable per-tick state carried across the run_episode decision loop.

    Collapses the ~18 free locals the former monolith threaded through each tick
    into one object, so the loop's phases are named helper calls mutating named
    fields instead of a wall of `nonlocal` reads/writes. One instance per episode.
    """
    prev_state: Optional[GameState] = None
    battle_was_active: bool = False
    current_enemy: str = ""
    battle_is_trainer: bool = False
    prev_key_items: Optional[int] = None
    prev_dex_owned: Optional[int] = None
    bag_sig: Optional[tuple] = None
    prev_map_key: Optional[tuple[int, int]] = None
    transitioning_steps: int = 0
    pending_map_b64: Optional[str] = None
    pending_map_name: str = ""
    blackout_active: bool = False
    decision_ticks: int = 0
    stuck_ticks: int = 0
    step_count: int = 0
    consecutive_errors: int = 0


# gBattleOutcome label (agent.events.battle_outcome_label) -> the LTM counter it bumps. A fled, caught or drawn
# battle is NOT a win (the old rule said "win unless the whole party fainted", so every Run and every Poké Ball
# padded battles_won).
_OUTCOME_COUNTER = {"won": "battles_won", "lost": "battles_lost", "caught": "battles_caught", "fled": "battles_fled",
                    "foe fled": "battles_fled", "teleported": "battles_fled", "foe teleported": "battles_fled"}
_JOURNAL_OUTCOME = {"won": "win", "lost": "loss", "drew": "draw"}
_last_ltm_save = 0.0


def _record_battle(s: dict, run: "_RunState", reader: LeafGreenReader,
                   ltm: LongTermMemory, journal: BattleJournal) -> None:
    """Book one finished battle — called by the event stream exactly once per battle wherever it was fought (a
    skill, a tool call or the main loop): counters by real outcome and a journal row with the foe,
    turns and moves actually used."""
    global _last_ltm_save
    ltm.data["total_battles"] = ltm.data.get("total_battles", 0) + 1
    key = _OUTCOME_COUNTER.get(s["outcome"])
    if key:
        ltm.data[key] = ltm.data.get(key, 0) + 1
    if s["outcome"] == "caught":
        ltm.data["pokemon_caught"] = ltm.data.get("pokemon_caught", 0) + 1
        try:
            owned = reader.read_pokedex()[0]
        except Exception:
            owned = None
        if owned is not None:
            run.prev_dex_owned = owned
    foe = (s.get("foe_name") or "").upper().strip()
    bits = [f"{'trainer' if s['trainer'] else 'wild'} {s.get('foe_name') or '?'}", s["outcome"]]
    if s.get("wiped"):
        bits.append("whole party fainted")
    journal.log(BattleRecord(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        location=s.get("where") or "unknown",
        enemy_name=foe or "unknown",
        enemy_level=int(s.get("foe_level") or 0),
        player_lead=s.get("active") or s.get("lead") or "",
        outcome=_JOURNAL_OUTCOME.get(s["outcome"], s["outcome"]),
        turns=int(s.get("turns") or 0),
        moves_used=list(s.get("moves") or []),
        hp_remaining_pct=round(float(s.get("hp_pct") or 0.0), 2),
        notes=", ".join(bits),
    ))
    now = time.time()
    if now - _last_ltm_save > 5 or s["outcome"] in ("lost", "caught"):     # many battles per second inside a skill
        _last_ltm_save = now
        ltm.save()


def _handle_battle_end(run: _RunState) -> None:
    """The tick where `in_battle` flips False: the battle itself was booked by _record_battle (event stream);
    here only the loop's per-battle scratch is reset."""
    run.current_enemy = ""


def _apply_progress(run: _RunState, state: GameState, diff: StateDiff,
                    reader: LeafGreenReader, ltm: LongTermMemory) -> None:
    """Auto-milestones and long-term progress derived from this tick's state diff (badges, key items, the starter).

    Reads `run.prev_state` for "increased" comparisons and updates
    `run.prev_key_items` so the next tick can detect a new key item."""
    if diff.badges_changed:
        # Only record when badge count genuinely increased. A spurious read
        # (e.g. badge_bits glitches 0→non-0→0) triggers badges_changed without
        # state.badges > run.prev_state.badges.
        if run.prev_state is not None and state.badges > run.prev_state.badges:
            # A badge increase means a gym leader was just defeated.
            # Use raw bitmask diff — state.badges is a popcount (0-8), not a
            # bitmask, so "state.badges & ~prev_state.badges" was WRONG.
            newly_set = state.badge_bits & (~run.prev_state.badge_bits & 0xFF)
            for bit in range(8):
                if newly_set & (1 << bit):
                    ms = BADGE_BIT_MILESTONE.get(bit)
                    if ms:
                        ltm.add_milestone(ms)
                        events.emit("milestone", f"milestone: {ms}")
                    gym = next((g for g in GYMS if g["badge_bit"] == bit), None)
                    if gym:
                        ltm.add_badge(gym["leader"])

    # A key item was obtained (bag key-items pocket count increased).
    key_items = reader.read_key_item_count()
    if run.prev_key_items is not None and key_items > run.prev_key_items:
        events.emit("key_item", f"key item obtained (bag now holds {key_items})")
    run.prev_key_items = key_items
    try:
        run.prev_dex_owned = reader.read_pokedex()[0]       # absorbs dex gains from evolutions; catches book theirs in _record_battle
    except Exception:
        pass

    if run.prev_state is not None and state.party_count > run.prev_state.party_count:
        # first-party addition → starter chosen
        if run.prev_state.party_count == 0 and state.party_count == 1:
            starter = state.party[0].species_name or "Unknown"
            if ltm.data.get("starter") is None:
                ltm.data["starter"] = starter
            if ltm.add_milestone("starter_chosen", f"chose {starter}"):
                events.emit("milestone", f"milestone: starter_chosen ({starter})")


def build_observation(*, state: GameState, diff: StateDiff, in_battle: bool,
                      run: _RunState, reader: LeafGreenReader,
                      tilemap: TilemapReader, ltm: LongTermMemory,
                      stm: ShortTermMemory, map_key: tuple[int, int],
                      trip: dict | None = None) -> str:
    """Build the one-line observation the LLM sees each tick.

    Pure string assembly from live state + memory; the only side effect is
    re-injecting the area map into `run.pending_map_b64` when the agent is stuck on
    the overworld and no map is already queued."""
    # Use LTM badge count for display — it is the authoritative source
    # (game RAM can hold stale badge data from old saves/sessions).
    obs_parts = [f"Context: {state.context.name}",
                 f"Badges: {ltm.data['badges_earned']}/8"]
    if not in_battle and state.context in (GameContext.IN_MENU, GameContext.DIALOG_OPEN):
        from game.menu import MenuDriver
        _hint = MenuDriver(reader.client, reader).describe()   # read-only
        if _hint:
            obs_parts.append(f"MENU: {_hint}")
    if run.prev_state is not None:
        dx = state.player_x - run.prev_state.player_x
        dy = state.player_y - run.prev_state.player_y
        if dx == 0 and dy == 0:
            obs_parts.append("Movement: none (position unchanged since last step)")
        else:
            obs_parts.append(f"Movement: moved ({dx:+d},{dy:+d})")
    if state.party:
        lead = state.party[0]
        obs_parts.append(
            f"Lead: {lead.species_name or '?'} L{lead.level} "
            f"HP={lead.current_hp}/{lead.max_hp} ({lead.status})"
        )
        # Proactive heal nudge: low HP outside battle → recommend heal().
        if (not in_battle and lead.max_hp and lead.hp_percent < 0.40
                and state.context == GameContext.OVERWORLD):
            obs_parts.append(
                f"⚠ Lead HP low ({lead.hp_percent:.0%}) — call heal() to "
                f"restore the party at the nearest Pokémon Center")
        # Team-building nudge: a lone/pair Pokémon can't sustain a dungeon (its
        # HP + move PP drain with no way to spread the load) or the Elite Four.
        # go_to now stops on new wild species so the model can catch a roster.
        # Readiness: the fundamentals a good player sorts out BEFORE walking on — heal (HP/PP), restock,
        # catch a real team, level the whole party, level for the next gym. Replaces the separate
        # "team too small / imbalance / under-levelled for Brock" nudges.
        if not in_battle and state.context == GameContext.OVERWORLD and state.party:
            from knowledge.readiness import assess as _assess, render as _render
            try:
                _bag = reader.read_bag()
                _balls = sum(_bag.get(b, 0) for b in (1, 2, 3, 4))
                _pots = sum(q for iid, q in reader.read_items_pocket() if iid in (13, 22, 21))
                _money = reader.read_money()
            except Exception:
                _balls = _pots = _money = 0
            try:
                _dex = reader.read_pokedex()
            except Exception:
                _dex = None
            try:
                _tms = reader.read_tmhm_pocket()
                _items = reader.read_items_pocket()
            except Exception:
                _tms, _items = None, []
            try:       # the PC contents only matter (and are only read) where the PC is: "you already own one — pc_swap it in"
                _boxes = reader.read_boxes() if MAP_KIND.get((state.map_bank, state.map_id)) == "pokecenter" else None
            except Exception:
                _boxes = None
            _block = _render(_assess(state.party, _balls, _pots, _money, ltm.data.get("gyms_beaten", []),
                                     dex=_dex, tms=_tms, boxes=_boxes))
            if _block:
                obs_parts.append(_block)
            # The bag digest (TMs / HMs / stones / candy): shown when it changes, then every 30 ticks as a reminder —
            # the model forgot TMs it picked up many turns ago.
            if _tms is not None:
                from knowledge.bag import bag_digest, stone_notes
                sig = (tuple(_tms), tuple((i, q) for i, q in _items if i in (63, 64, 65, 66, 67, 68, 70, 93, 94, 95, 96, 97, 98)),
                       tuple(tuple(p.move_names) for p in state.party))
                if sig != run.bag_sig or run.step_count % 30 == 0:
                    run.bag_sig = sig
                    _line = bag_digest(state.party, _tms, _items)
                    if _line:
                        obs_parts.append(_line)
                    obs_parts.extend(stone_notes(state.party, _items))
        if not in_battle and state.context == GameContext.OVERWORLD and state.party:
            from knowledge.escape import hint as _escape_hint
            try:
                _rope = dict(reader.read_items_pocket()).get(85, 0)
            except Exception:
                _rope = 0
            _ids = {m for p in state.party for m in (p.move_ids or [])}
            _eh = _escape_hint((state.map_bank, state.map_id), _ids, _rope)
            if _eh:
                obs_parts.append(_eh)
        if trip and not in_battle and state.context == GameContext.OVERWORLD:
            resume = (f"call {trip['call']} to resume." if trip.get("call") else
                      f"call go_to() with no destination — or go_to({trip['dest']!r}) — to resume.")
            obs_parts.append(f"TRIP IN PROGRESS → {trip['target']} (an encounter interrupted it): {resume}")
        if in_battle:
            # Moves/PP of the ACTIVE battler (gBattleMons[0]) — party[0] is not necessarily the one
            # fighting after a switch — with a Disabled move's PP zeroed so it is never suggested.
            _ids, a_names, a_pp, d_slot, d_turns = reader.read_active_battle_usable_pp()
            if any(a_names):
                move_names, pp_view = list(a_names), a_pp
            else:
                move_names, pp_view, d_slot, d_turns = list(lead.move_names), lead.pp, None, 0
            lead_types = POKEMON_TYPES.get((lead.species_name or "").upper().strip(), ())
            enemy = reader.read_enemy_lead()
            from knowledge.party import can_attack as _can_attack, healthy_enough as _healthy
            _act = reader.read_active_battle_species()
            _backups = [f"{p.species_name} (slot {i + 1})" for i, p in enumerate(state.party)
                        if p.species_id != _act and _healthy(p, 0.3) and _can_attack(p)]
            _hint = (("Teammates that can still attack: " + ", ".join(_backups) +
                      " — switch_pokemon to one.") if _backups else "")
            _me = next((p for p in state.party if p.species_id == _act), lead)
            bsummary = battle_summary(move_names, run.current_enemy,
                                      lead.hp_percent, pp_view,
                                      attacker_types=lead_types,
                                      opponent_status=enemy.status if enemy else "",
                                      disabled_slot=d_slot, disabled_turns=d_turns,
                                      backup_hint=_hint,
                                      wild=not run.battle_is_trainer,
                                      user_level=_me.level, user_hp_frac=_me.hp_percent,
                                      foe_level=(enemy.level or 0) if enemy else 0,
                                      foe_hp=enemy.current_hp if enemy else 0,
                                      hidden_power=_hidden_power(_me.ivs))
            obs_parts.append(bsummary)
            if IV_PEEK_BEFORE_CATCH and enemy and not run.battle_is_trainer:
                from knowledge.mon_quality import assess as _assess_iv
                _qf = _assess_iv(enemy)
                if _qf is not None:
                    obs_parts.append(f"Foe IVs (peek enabled): {_qf.summary()}")
            try:
                from knowledge.battle import xp_share_hint as _xp_hint
                _xp = _xp_hint(state.party, _act, enemy.level if enemy and enemy.max_hp else 0)
                if _xp:
                    obs_parts.append(_xp)
            except Exception:
                pass
            try:
                _vol = reader.read_battle_volatiles(0)
            except Exception:
                _vol = {}
            if _vol.get("wrapped") or _vol.get("escape_prevention"):
                obs_parts.append(
                    "⛓ TRAPPED — a trapping move (Wrap/Bind/Fire Spin/Clamp/Whirlpool: 2-5 turns) or Mean Look/Spider "
                    "Web/Block holds you: you CANNOT run or switch voluntarily. Attack (or use an item) until it ends.")
            if _vol.get("tormented"):
                obs_parts.append("TORMENTED — you can't use the same move twice in a row: alternate attacks.")
            if _vol.get("confused"):
                obs_parts.append("CONFUSED — you may hurt yourself; it wears off in a few turns (switching cures it).")
            if _vol.get("infatuated"):
                obs_parts.append("INFATUATED (Attract) — you may be unable to move; switching out cures it.")
            if _vol.get("recharge"):
                obs_parts.append("Recharging after Hyper Beam — this turn is lost.")
            from agent.lm_studio_client import AgentClient as _AC
            from knowledge.battle import battle_idle_nudge
            _nudge = battle_idle_nudge(
                stm.action_history,
                _AC._best_damaging_move(move_names, pp_view, lead_types,
                                        POKEMON_TYPES.get((enemy.species_name or "").upper().strip(), ())
                                        if enemy else (),
                                        {"user_level": _me.level, "user_hp_frac": _me.hp_percent,
                                         "foe_level": (enemy.level or 0) if enemy else 0,
                                         "foe_asleep": "asleep" in (enemy.status if enemy else "")}))
            if _nudge:
                obs_parts.append(_nudge)
            if enemy:
                obs_parts.append(f"Opponent HP: {enemy.current_hp}/{enemy.max_hp} (L{enemy.level})")
            # Tell the model whether it can flee (wild) or must fight (trainer).
            if run.battle_is_trainer:
                obs_parts.append("TRAINER battle — you cannot flee; win or switch.")
            else:
                obs_parts.append("WILD battle — you may flee_battle() to escape "
                                 "if you're just passing through or HP is low.")
                # Suggest catching a wild Pokémon that would add to the team:
                # a NEW species (not already in your party) when you have balls.
                balls = sum(reader.read_bag().get(b, 0) for b in (1, 2, 3, 4))
                party_species = {p.species_id for p in state.party}
                if (balls > 0 and enemy and enemy.species_id
                        and enemy.species_id not in party_species):
                    from knowledge.catch_policy import evaluate as _catch_eval
                    from knowledge.team import wanted_species as _wanted
                    _v = _catch_eval(state.party, enemy.species_id, enemy.level or 0,
                                     dex_owned=reader.read_dex_owned(enemy.species_id),
                                     wanted=_wanted(state.party, None, ltm.data.get("gyms_beaten", [])))
                    if _v.catch:
                        obs_parts.append(
                            f"NEW SPECIES you don't own ({balls} Poké Balls in bag) — worth catching: "
                            f"{_v.reason}. Weaken it first with use_move (low HP raises the catch rate). "
                            "When you catch it, pass a funny, inventive nickname you make up (not the "
                            "species name)"
                            + ((f"; already taken: "
                                f"{', '.join(n for n in (p.nickname for p in state.party) if n)}")
                               if any(p.nickname for p in state.party) else "") + ". "
                            + catch_setup_hint(move_names, pp_view))
                    else:
                        obs_parts.append(
                            f"New species, but NOT worth a ball right now: {_v.reason}. "
                            "Skip it (flee_battle) unless you have a reason to want it.")
                elif balls == 0 and len(state.party) < 6:
                    obs_parts.append(
                        "You have no Poké Balls — buy some with shop() to catch "
                        "wild Pokémon for your team.")
    obs_parts.append(f"Pos: ({state.player_x},{state.player_y}) Map: {state.map_bank}/{state.map_id}")
    # Money + key consumables (for heal/catch/shopping decisions). Cheap
    # reads; only meaningful outside battle transitions.
    if not in_battle and state.context in (GameContext.OVERWORLD, GameContext.IN_MENU):
        money = reader.read_money()
        bag = reader.read_bag()
        balls = sum(bag.get(b, 0) for b in (1, 2, 3, 4))   # any Poké Ball type
        potions = sum(bag.get(p, 0) for p in (13, 22, 21, 20, 19))
        obs_parts.append(
            f"Bag: ¥{money} | Poké Balls: {balls} | Potions/heals: {potions}")
        # Lead move PP — the agent is otherwise blind to PP outside battle and
        # would run its attacking moves dry across a trainer gauntlet (it did,
        # for 11 hours). A Pokémon Center heal restores PP, so warn while it
        # can still retreat. (In battle the per-move PP is already in the obs.)
        lead = state.party[0] if state.party else None
        if lead:
            pp_line, pp_warn = overworld_pp_summary(lead.move_names, lead.pp)
            if pp_line:
                obs_parts.append(pp_line)
            if pp_warn:
                obs_parts.append(pp_warn)
        # At a Mart: recommend a badge-gated, par-level restock the agent can afford.
        if MAP_KIND.get((state.map_bank, state.map_id)) == "mart":
            rec = shopping_summary(bag, ltm.data["badges_earned"], money)
            if rec:
                obs_parts.append(
                    "MART — " + rec + ". Call shop() to buy the recommended "
                    "restock automatically.")
        # In a Pokémon Center the PC is right here: say what is in the boxes so the model remembers it exists.
        if MAP_KIND.get((state.map_bank, state.map_id)) == "pokecenter":
            try:
                stored = len(reader.read_boxes())
            except Exception:
                stored = 0
            if stored:
                obs_parts.append(f"PC: {stored} Pokémon stored in the boxes — pc_boxes(detail=true) to look, "
                                 "pc_swap / pc_withdraw to bring one into the party.")
    # Inside a gym: point the agent at the Leader — UNLESS this Leader is
    # already beaten, in which case say so and tell it to leave (the agent
    # looped in/out of Pewter Gym re-challenging Brock). go_to is useless
    # here; you have to WALK UP to the Leader.
    if (not in_battle and state.context == GameContext.OVERWORLD
            and MAP_KIND.get((state.map_bank, state.map_id)) == "gym"):
        gym_leader = GYM_MAP_LEADER.get((state.map_bank, state.map_id))
        if gym_leader and gym_leader in ltm.data["gyms_beaten"]:
            obs_parts.append(
                f"GYM ALREADY BEATEN: you already defeated {gym_leader} here — "
                "do NOT challenge them again. LEAVE the gym (walk_to the exit "
                "door) and head to your NEXT objective in the Navigation section.")
        else:
            from knowledge.gym_advice import brief as _gym_brief
            obs_parts.append(
                "GYM: to fight the Leader, call challenge_leader() — it walks up "
                "to them and starts the battle. (heal() and save_state first.) "
                "Do NOT use go_to inside a gym."
                + (f"\nLeader: {_gym_brief(gym_leader)}" if gym_leader else ""))
    if state.context == GameContext.OVERWORLD and tilemap.ready:
        if tilemap._width and tilemap._height:
            obs_parts.append(f"Map size: {tilemap._width}×{tilemap._height} "
                             f"(walk_to needs 0≤x<{tilemap._width}, 0≤y<{tilemap._height})")
        surr = tilemap.surroundings_str(state.player_x, state.player_y)
        obs_parts.append(f"Tiles: {surr}")
        balls = reader.read_item_ball_tiles()
        if balls:
            where = ", ".join(f"({x},{y})" for x, y in balls[:5])
            obs_parts.append(
                f"Items on the ground: item ball(s) at {where} — call "
                "pick_up_items() to collect them before leaving.")
        travel_dir = get_travel_direction(state)
        if travel_dir:
            passable = tilemap.passable_directions(state.player_x, state.player_y)
            btn = DIRECTION_BUTTON[travel_dir]
            if passable.get(travel_dir):
                obs_parts.append(f"Suggested: press {btn} ({travel_dir} tile is floor, matches travel direction)")
            else:
                alts = [f"{DIRECTION_BUTTON[d]}({d})" for d, ok in passable.items() if ok]
                obs_parts.append(f"Travel {travel_dir} blocked — passable: {', '.join(alts) or 'none'} (find a detour)")
    # Indoors: surface the door/stairs tiles so the agent can leave. The
    # outdoor route is unreachable until it does (see get_route_guidance).
    if tilemap.ready and infer_building_type(state.map_bank, state.map_id) == "interior":
        # A door can span several adjacent warp tiles but usually only the
        # CENTER one actually warps (the side tiles "arrive" without exiting).
        # Collapse each contiguous run to its middle so we point at the tile
        # that works (fixes suggesting an off-by-one non-functional door).
        warps = door_centers(tilemap.read_warps())
        if warps:
            px, py = state.player_x, state.player_y
            nearest = min(warps, key=lambda w: abs(w[0] - px) + abs(w[1] - py))
            steps = []
            if nearest[1] > py:   steps.append(f"{nearest[1]-py} Down")
            elif nearest[1] < py: steps.append(f"{py-nearest[1]} Up")
            if nearest[0] > px:   steps.append(f"{nearest[0]-px} Right")
            elif nearest[0] < px: steps.append(f"{px-nearest[0]} Left")
            toward = ", then ".join(steps) if steps else "you are next to it — step onto it"
            coords = ", ".join(f"({x},{y})" for x, y in warps[:4])
            obs_parts.append(
                f"EXITS (door/stairs tiles): {coords}. To leave the building, "
                f"call walk_to{nearest} — it will path there and step through. "
                f"(Nearest is {nearest}: {toward}.)")
    # Outdoors: surface map connections (which edge leads to which map).
    # These are seamless — walk off that edge to cross; not warp tiles.
    elif tilemap.ready and state.context == GameContext.OVERWORLD:
        conns = tilemap.read_connections()
        if conns:
            parts = []
            for c in conns:
                name = MAP_NAMES.get((c["map_bank"], c["map_id"]),
                                     f"{c['map_bank']}/{c['map_id']}")
                parts.append(f"{c['direction']}→{name}")
            obs_parts.append("Map edges (call go_to_map(direction) to travel there): "
                             + ", ".join(parts))
    if diff.notes:
        obs_parts.append("Changes: " + "; ".join(diff.notes))
    # Revisit warning — explicit signal to explore new directions
    visits = stm.visit_count(state.player_x, state.player_y)
    if visits >= 4 and state.context == GameContext.OVERWORLD:
        obs_parts.append(
            f"REVISIT #{visits}: you have been at ({state.player_x},{state.player_y}) "
            f"{visits} times — choose a direction you have NOT tried recently"
        )

    if stm.stuck:
        ctx = state.context.name
        if ctx == "IN_BATTLE":
            obs_parts.append("STUCK: same battle action repeating — try a different move or switch Pokémon")
        elif ctx == "DIALOG_OPEN" or ctx == "TRANSITIONING":
            obs_parts.append("STUCK: dialog/transition not advancing — press A")
        elif ctx == "IN_MENU":
            obs_parts.append("STUCK in a menu — press B to close it and return to the field, or navigate with the D-pad and A")
        else:
            obs_parts.append("STUCK: position unchanged after repeated input — wall or obstacle ahead, try a different direction or press B to cancel any open menu")
            # Re-inject the area map when stuck on the overworld so the agent can re-orient
            if USE_VISION and run.pending_map_b64 is None:
                run.pending_map_b64, run.pending_map_name = AgentClient.load_area_map(*map_key)

    # Close every turn with an explicit call to action — the state dump alone
    # reads to some models as "no question asked", and they reply with prose
    # instead of acting. Make the imperative unmissable.
    obs_parts.append("→ Your turn: decide the best next action and call a tool NOW (do not reply with text only)")
    return " | ".join(obs_parts)


def _handle_blackout(run: _RunState, state: GameState, mgba, reader: LeafGreenReader,
                     ltm: LongTermMemory) -> bool:
    """Handle an all-fainted party: announce the blackout once, then recover.

    Returns True if the caller should `continue` (the blackout path never falls
    through to the LLM decision step). Tries a slot-0 state reload first; if none
    was saved this session, advances the game's own whiteout sequence with A."""
    party_wiped = bool(state.party) and all(p.current_hp == 0 for p in state.party)
    if not party_wiped:
        run.blackout_active = False   # recovered (respawn/heal) → re-arm
        return False
    # Announce ONCE per blackout, not every tick while the party stays fainted.
    if not run.blackout_active:
        run.blackout_active = True
        events.emit("blackout", "BLACKOUT — all party fainted")
        ltm.save()
    # Try to reload the pre-fight state. If none was saved this session the load
    # FAILS (slot file missing) — don't pretend it worked and spin; let the game's
    # own whiteout sequence carry the player to the last Pokémon Center by advancing
    # its dialog with A.
    if mgba.load_state(0):
        events.emit("note", "loaded slot 0 after the blackout")
        mgba.tick(60)
        run.prev_state = None
        run.battle_was_active = False
        run.blackout_active = False   # recovered via reload
    else:
        events.emit("note", "no save state in slot 0 — advancing the whiteout / Nurse Joy recovery")
        # The blackout plays a multi-box sequence (out of Pokémon → scurried to a
        # Center → warp → auto-heal) that only advances on A. Press it several times
        # per pass (not once) so recovery actually progresses instead of crawling one
        # box per tick.
        for _ in range(6):
            mgba.tap("A")
            mgba.tick(12)
            if bool(reader.read_party()) and any(
                    p.current_hp > 0 for p in reader.read_party()):
                break   # auto-heal landed — party revived
    return True


def run_episode(rt: AgentRuntime, *, goal: Optional[Goal] = None, goal_desc: str = "",
                max_steps: int = 0, max_wall_s: float = MAX_WALL_SECONDS,
                verbose: bool = True, run_log=None) -> EpisodeResult:
    """Drive the decision loop until the goal is met, a cap is hit, or the run is
    interrupted / exceeds the error budget. Returns an EpisodeResult scorecard.

    With goal=None and max_steps=0 this is the open-ended real run (what main()
    uses). The eval harness passes a goal predicate + step budget per scenario.
    Spend caps (MAX_LLM_CALLS/TOKEN_BUDGET) always apply as a safety net.

    The body is a thin phase sequence — battle bookkeeping, milestone / progress updates,
    observation, blackout recovery, and the LLM decision — each a helper above.
    Only the per-tick locals (state/diff/in_battle) and loop accounting live here.
    """
    mgba, reader, client = rt.mgba, rt.reader, rt.client
    ltm, stm, journal, tilemap = rt.ltm, rt.stm, rt.journal, rt.tilemap

    run = _RunState()
    t_start = time.time()
    wall_deadline = time.time() + max_wall_s if max_wall_s else 0.0
    from memory.run_log import NullRunLog
    rlog = run_log or NullRunLog()
    client.run_log = rlog
    events.configure(console if verbose else None, rlog, LOG_LEVEL)
    events.on_battle_end(lambda s: _record_battle(s, run, reader, ltm, journal))
    ckpt = None
    if getattr(rlog, "dir", None) and CHECKPOINT_EVERY > 0 and hasattr(mgba, "save_state_file"):
        from memory.checkpoints import CheckpointManager
        ckpt = CheckpointManager(rlog.dir / "checkpoints", mgba.save_state_file, CHECKPOINT_EVERY)
    _s0 = reader.read_state()
    rlog.event("start", map=[_s0.map_bank, _s0.map_id], pos=[_s0.player_x, _s0.player_y],
               badges=_s0.badges, party=_party_brief(_s0), goal=goal_desc)

    def _result(reason: str, passed: bool, s: Optional[GameState] = None) -> EpisodeResult:
        res = _result_inner(reason, passed, s)
        rlog.event("end", **res.to_dict())
        rlog.write_meta(result=res.to_dict())
        return res

    def _result_inner(reason: str, passed: bool, s: Optional[GameState] = None) -> EpisodeResult:
        if s is None:
            s = reader.read_state()
        return EpisodeResult(
            reason=reason, passed=passed, steps=run.step_count,
            stats=events.run_stats(), llm_calls=client.llm_calls,
            prompt_tokens=client.total_prompt_tokens,
            completion_tokens=client.total_completion_tokens,
            final_map=(s.map_bank, s.map_id), final_pos=(s.player_x, s.player_y),
            badges=ltm.data["badges_earned"],
            milestones=list(ltm.data.get("milestones", [])),
            stuck_ratio=round(run.stuck_ticks / run.decision_ticks, 3) if run.decision_ticks else 0.0,
            goal_desc=goal_desc,
        )

    while True:
        try:
            # A level-up can trigger an evolution scene on return to the field. It
            # flickers between TRANSITIONING and IN_MENU, so the model kept cancelling
            # it with B and the lead never evolved. Complete it here (advance with A,
            # never B) before anything else acts, so the model never sees it.
            if client._in_evolution_scene():
                client._finish_evolution()
            state = reader.read_state()
            diff  = reader.diff(run.prev_state, state)

            # Goal reached? (eval harness only; no-op for the open-ended real run.)
            if goal is not None and goal(state, ltm):
                if verbose:
                    console.print(f"[green bold]GOAL reached: {goal_desc}[/]")
                ltm.save()
                return _result("goal", True, state)

            in_battle = state.context == GameContext.IN_BATTLE
            if in_battle and not run.battle_was_active:
                stm.reset_for_new_battle()
                # Classify the battle from gBattleTypeFlags (set at battle init).
                run.battle_is_trainer = bool(mgba.read32(Addr.BATTLE_TYPE_FLAGS)
                                             & Addr.BATTLE_TYPE_TRAINER)
                # Identify the opponent from memory (gEnemyParty[0]) — do NOT rely
                # on the model to read the species off the screen (it guessed wrong).
                enemy = reader.read_enemy_lead()
                run.current_enemy = (enemy.species_name or "").upper().strip() if enemy else ""
                client._current_opponent = run.current_enemy

            # Keep the opponent identity fresh from memory every battle tick (it
            # can load a frame or two after the battle callback, and the lead
            # changes when a trainer sends out its next Pokémon). Memory is
            # authoritative — never let the model's guess override it.
            if in_battle:
                enemy = reader.read_enemy_lead()
                if enemy and enemy.species_name:
                    run.current_enemy = enemy.species_name.upper().strip()

            # ── Battle end detection ────────────────────────────────────────
            if run.battle_was_active and not in_battle:
                _handle_battle_end(run)
            # Save the pre-update value so the auto-tap guard below can see
            # whether we were in battle on the PREVIOUS tick (battle_was_active
            # is about to be overwritten with the current tick's value).
            was_in_battle_prev_tick = run.battle_was_active
            run.battle_was_active = in_battle

            # Auto-advance a stuck dialog / transition with A. Fires for
            # DIALOG_OPEN (where NPC/sign/item dialogs live) and TRANSITIONING
            # (post-warp/fade message boxes). Not IN_MENU — pressing A there would
            # select a menu item.
            # Guards:
            #   • not in_battle            — don't tap during a battle turn
            #   • not was_in_battle_prev_tick — don't tap on the first tick after
            #                                  leaving IN_BATTLE; context can read
            #                                  TRANSITIONING during post-battle
            #                                  animations and turn-change fades
            if (state.context in (GameContext.DIALOG_OPEN, GameContext.TRANSITIONING)
                    and not in_battle
                    and not was_in_battle_prev_tick):
                run.transitioning_steps += 1
                # Auto-advance a genuine transition/dialog by tapping A. This branch
                # `continue`s BEFORE the step/wall-clock budget checks below, so it must
                # be BOUNDED — a game state stuck in TRANSITIONING would otherwise tap A
                # forever and bypass every guardrail (an eval hung here for hours). The
                # wall-clock cap is enforced inline, and after a cap we fall through so a
                # normal step runs (LLM re-engages + the budgets get checked).
                if wall_deadline and time.time() >= wall_deadline:
                    ltm.save()
                    return _result("max_wall", False, state)
                if 5 <= run.transitioning_steps < 45:
                    mgba.tap("A")
                    console.print("[dim]transition: tap A[/]")
                    mgba.tick()
                    continue
            else:
                run.transitioning_steps = 0

            # Refresh tilemap cache whenever the map changes
            map_key = (state.map_bank, state.map_id)
            if map_key != run.prev_map_key:
                tilemap.refresh()
                stm.reset_for_new_map()
                # Town-visit tracking
                town_name = MAP_NAMES.get(map_key)
                if town_name and state.map_bank == 3 and state.map_id < 19:
                    if ltm.add_town(town_name):
                        events.emit("town", f"new town: {town_name}")
                # Load overhead reference map (attach to next decision step)
                if USE_VISION:
                    run.pending_map_b64, run.pending_map_name = AgentClient.load_area_map(*map_key)
                    if run.pending_map_b64:
                        console.print(f"[blue]Area map loaded: {run.pending_map_name}[/]")
                run.prev_map_key = map_key

            # ── Auto-milestones / long-term progress from the state diff ────────
            events.observe(reader)                    # books any battle that just ended (see _record_battle)
            _apply_progress(run, state, diff, reader, ltm)

            # ── Build observation string ─────────────────────────────────────
            obs = build_observation(state=state, diff=diff, in_battle=in_battle,
                                    run=run, reader=reader, tilemap=tilemap,
                                    ltm=ltm, stm=stm, map_key=map_key,
                                    trip=getattr(client, "_trip", None))
            events.emit("note", f"OBS: {obs[:140]}", debug=True, log=False)

            # ── Blackout check ───────────────────────────────────────────────
            if _handle_blackout(run, state, mgba, reader, ltm):
                continue

            # ── LLM decision step ────────────────────────────────────────────
            client.set_system(build_system_prompt(ltm, journal, state,
                                                   current_enemy=run.current_enemy))
            screenshot = client.capture_screenshot() if USE_VISION else None
            reasoning, actions = client.step(obs, screenshot,
                                             area_map_b64=run.pending_map_b64,
                                             area_map_name=run.pending_map_name)
            # Map is attached on entry only — clear so it won't repeat next tick
            run.pending_map_b64 = None
            run.pending_map_name = ""
            if actions:
                stm.record_action(";".join(actions), state.player_x, state.player_y)
            elif reasoning:
                stm.record_action(reasoning[:80], state.player_x, state.player_y)
            if reasoning:
                events.emit("note", f"💭 {reasoning[:160]}", major=False, log=False)

            # set_opponent is now only a fallback — memory (read_enemy_lead) is
            # authoritative and refreshed each tick above. Use the tool's value
            # only if we somehow couldn't read the opponent from memory.
            if not run.current_enemy and client._current_opponent:
                run.current_enemy = client._current_opponent
            # Clear on battle end
            if not in_battle:
                client._current_opponent = ""

            # A full decision tick completed without raising — reset the
            # consecutive-error budget. (The transition/blackout `continue` paths
            # above don't reach here, but they don't raise either, so the counter
            # simply holds; only a real exception grows it.)
            run.consecutive_errors = 0

            # Stuck tracking: an overworld decision tick that didn't move the
            # player. A high ratio is the signature of the Route-2 "can't cross"
            # thrash — surfaced as EpisodeResult.stuck_ratio for the eval harness.
            if state.context == GameContext.OVERWORLD:
                run.decision_ticks += 1
                if run.prev_state is not None and \
                        (state.player_x, state.player_y) == (run.prev_state.player_x, run.prev_state.player_y):
                    run.stuck_ticks += 1

            run.prev_state = state
            mgba.tick()

            run.step_count += 1
            rlog.event("tick", step=run.step_count, ctx=state.context.name,
                       map=[state.map_bank, state.map_id],
                       pos=[state.player_x, state.player_y], badges=state.badges,
                       party=_party_brief(state), obs=obs, reasoning=(reasoning or "")[:1500],
                       actions=actions,
                       llm_calls=client.llm_calls, tokens=client.total_tokens)
            if STATUS_EVERY and run.step_count and run.step_count % STATUS_EVERY == 0:
                events.emit("status", _status_line(state, ltm, client, reader, run.step_count, t_start), major=False)
            if ckpt:
                saved = ckpt.maybe(run.step_count, state.badges, state.context.name,
                                   meta={"map": [state.map_bank, state.map_id], "badges": state.badges,
                                         "party": _party_brief(state), "llm_calls": client.llm_calls})
                if saved:
                    events.emit("checkpoint", f"checkpoint saved: {getattr(saved, 'name', saved)}", major=False)
            if max_steps and run.step_count >= max_steps:
                if verbose:
                    console.print(f"[green]Reached max_steps={max_steps} — stopping. "
                                  f"{_run_summary(client, run.step_count)}[/]")
                ltm.save()
                return _result("max_steps", False, state)
            # Spend guards (matter for cloud endpoints; 0 = unlimited). Stop
            # cleanly, same as max_steps, so an unattended run can't run up an
            # unbounded bill.
            if MAX_LLM_CALLS and client.llm_calls >= MAX_LLM_CALLS:
                if verbose:
                    console.print(f"[green]Reached MAX_LLM_CALLS={MAX_LLM_CALLS} — stopping. "
                                  f"{_run_summary(client, run.step_count)}[/]")
                ltm.save()
                return _result("max_llm_calls", False, state)
            if TOKEN_BUDGET and client.total_tokens >= TOKEN_BUDGET:
                if verbose:
                    console.print(f"[green]Reached TOKEN_BUDGET={TOKEN_BUDGET} — stopping. "
                                  f"{_run_summary(client, run.step_count)}[/]")
                ltm.save()
                return _result("token_budget", False, state)
            # Wall-clock guard: an unattended run (esp. a local model that degrades on a
            # marathon) can't hang for hours — checked each step, so at worst one over-
            # long step past the deadline (LLM_TIMEOUT bounds that single step).
            if wall_deadline and time.time() >= wall_deadline:
                if verbose:
                    console.print(f"[green]Reached wall-clock cap ({max_wall_s:.0f}s) — stopping. "
                                  f"{_run_summary(client, run.step_count)}[/]")
                ltm.save()
                return _result("max_wall", False, state)

        except KeyboardInterrupt:
            if verbose:
                console.print(f"\n[red]Stopped.[/] {_run_summary(client, run.step_count)}")
            ltm.save()
            return _result("interrupted", False)
        except Exception as e:
            run.consecutive_errors += 1
            _log_exception(e)
            if verbose:
                console.print(f"[red]Error ({run.consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): "
                              f"{type(e).__name__}: {e}[/] — see {ERRORS_LOG}")
                console.print_exception(max_frames=4)
            if run.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                if verbose:
                    console.print(f"[red bold]{run.consecutive_errors} consecutive errors — "
                                  f"stopping. Full tracebacks in {ERRORS_LOG}. "
                                  f"{_run_summary(client, run.step_count)}[/]")
                ltm.save()
                return _result("error_budget", False)
            time.sleep(1.0)


def _resume_state() -> str:
    """Resolve RESUME ('latest' or a path) to a checkpoint file, or '' for a normal start."""
    if not RESUME:
        return ""
    if RESUME.lower() != "latest":
        path = os.path.expanduser(RESUME)
        if not os.path.exists(path):
            console.print(f"[red]RESUME={RESUME}: no such checkpoint — starting normally.[/]")
            return ""
        return path
    from memory.checkpoints import find_latest
    info = find_latest(PROGRESS_PATH.parent / "runs")
    if not info:
        console.print("[yellow]RESUME=latest: no checkpoint found under logs/runs — starting normally.[/]")
        return ""
    console.print(f"[cyan]Resuming from checkpoint {info['tag']} (step {info['step']}, saved "
                  f"{info['time']}): {info.get('meta', {})}[/]")
    return info["path"]


def main():
    resume = _resume_state()
    rt = build_runtime(verbose=True, **({"start_state": resume} if resume else {}))
    if rt is None:
        sys.exit(1)
    from memory.run_log import RunLog
    rlog = RunLog(PROGRESS_PATH.parent / "runs")
    rlog.write_meta(model=MODEL_NAME, backend=MGBA_BACKEND, max_steps=MAX_STEPS,
                    max_llm_calls=MAX_LLM_CALLS, token_budget=TOKEN_BUDGET,
                    start_from_save=START_FROM_SAVE, use_vision=USE_VISION,
                    temperature=TEMPERATURE, started=time.strftime("%Y-%m-%d %H:%M:%S"))
    console.print(f"[cyan]Run log: {rlog.dir}[/]")
    try:
        result = run_episode(rt, max_steps=MAX_STEPS, verbose=True, run_log=rlog)
    finally:
        rlog.close()
    # run_episode already printed the stop line. Propagate any non-goal stop (a
    # budget cap, interruption, or the error budget) as a non-zero exit so a
    # wrapping shell/CI notices the run didn't actually finish; 0 means the goal
    # was achieved.
    if result.reason != "goal":
        sys.exit(1)


if __name__ == "__main__":
    main()

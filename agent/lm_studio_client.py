from agent.skills.base import log_once
import base64
import json
import re
import time
from pathlib import Path
from openai import OpenAI
from agent.usage import cached_prompt_tokens
from agent.llm_retry import call_with_retry
from agent.tool_args import repair_args, signature
from agent.tools import SAFARI_CONTEXT, tool_schema, tools_for, normalize_button
from agent.history import trim_messages, strip_control_tokens
from game.memory_reader import LeafGreenReader
from typing import TYPE_CHECKING
from memory.long_term import LongTermMemory
from memory.run_log import NullRunLog
from knowledge.leafgreen_data import MILESTONES
from knowledge.navigation import get_map_image_path, MAP_NAMES
from config import (LLM_BASE_URL, LLM_API_KEY, MODEL_NAME, TEMPERATURE, MAX_TOKENS,
                    ENABLE_THINKING, SCREENSHOT_PATH, LLM_TIMEOUT, LLM_RETRIES)
from agent import events
from agent.skills.base import SkillBase
from agent.skills.gamecorner import GameCornerMixin
from agent.skills.selling import SellMixin
from agent.skills.deleter import MoveDeleterMixin
from agent.skills.league import LeagueMixin
from agent.skills.fishing import FishingMixin
from agent.skills.bike import BikeMixin
from agent.skills.tutor import TutorMixin
from agent.skills.gymquest import GymQuestMixin
from agent.skills.legends import LegendsMixin
from agent.skills.newgame import NewGameMixin
from agent.skills.services import ServicesMixin
from agent.skills.state import SkillState
from agent.skills.nav import NavMixin
from agent.skills.errands import ErrandsMixin
from agent.skills.gyms import GymPuzzleMixin
from agent.skills.hideout import HideoutMixin
from agent.skills.mansion import MansionMixin
from agent.skills.silph import SilphMixin
from agent.skills.victory import VictoryMixin
from agent.skills.tower import TowerMixin
from agent.skills.quests import QuestMixin
from agent.skills.party import PartyMixin
from agent.skills.pc import PCMixin
from agent.skills.overworld import OverworldMixin
from agent.skills.battle import BattleMixin
from agent.skills.movelearn import MoveLearnMixin
from agent.skills.evolution import EvolutionMixin
from agent.skills.menu import MenuMixin
from agent.skills.items import FieldItemMixin
from agent.skills.hm import HMMixin
from agent.skills.tmhm import TMHMMixin



if TYPE_CHECKING:
    from game.mgba_core import NativeMGBAClient


class AgentClient(SkillBase, SkillState, SellMixin, MoveDeleterMixin, LeagueMixin, FishingMixin, BikeMixin, TutorMixin, GymQuestMixin, LegendsMixin, NewGameMixin, ServicesMixin, GameCornerMixin, PCMixin, PartyMixin, QuestMixin, HideoutMixin, ErrandsMixin, TowerMixin, MansionMixin, SilphMixin, VictoryMixin, GymPuzzleMixin, NavMixin, OverworldMixin, BattleMixin, MoveLearnMixin, EvolutionMixin, MenuMixin, FieldItemMixin, HMMixin, TMHMMixin):

    def __init__(self, mgba: "NativeMGBAClient", reader: LeafGreenReader, ltm: LongTermMemory):
        self.llm    = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
        self.mgba   = mgba
        self.reader = reader
        self.ltm    = ltm
        from game.tilemap_reader import TilemapReader
        self.tilemap = TilemapReader(mgba)   # for walk_to pathfinding
        self.messages: list[dict] = []
        self._current_opponent: str = ""  # set by set_opponent tool call
        # Cumulative LLM usage for spend tracking (#64). resp.usage may be absent
        # on some endpoints, so token totals are best-effort; call count is exact.
        self.llm_calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cached_tokens = 0         # prompt tokens the server served from its prompt cache (when it reports them)

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    run_log = NullRunLog()   # class default; main.run_episode swaps in a real RunLog

    MAX_HISTORY = 20  # keep last ~10 user/assistant turns (text only for old turns)
    MAX_TOOL_ROUNDS = 6  # cap model tool-call rounds per decision step, then re-observe

    def set_system(self, prompt: str):
        if self.messages and self.messages[0]["role"] == "system":
            self.messages[0] = {"role": "system", "content": prompt}
        else:
            self.messages = [{"role": "system", "content": prompt}]
        # Trim only at user-turn boundaries so a tool_calls/tool-response group
        # is never split (which the API rejects with a 400).
        self.messages = trim_messages(self.messages, self.MAX_HISTORY)

    @staticmethod
    def _strip_images(content) -> str:
        """Extract only text from a (possibly multipart) message content.
        Images in older history turns are removed to keep the context window lean —
        the model only needs the current screenshot, not a history of game frames."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [part["text"] for part in content
                     if isinstance(part, dict) and part.get("type") == "text"]
            return " ".join(texts)
        return str(content)

    def _trim_image_history(self):
        """Strip image_url parts from all user messages except the most recent one.
        Called just before sending to the API. Each screenshot is ~8K tokens;
        keeping only the latest one makes the context ~10x smaller."""
        latest_user_idx = None
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i]["role"] == "user":
                latest_user_idx = i
                break
        for i, msg in enumerate(self.messages):
            if msg["role"] != "user":
                continue
            if i == latest_user_idx:
                continue  # keep images in the most recent user turn
            if isinstance(msg.get("content"), list):
                # Replace multipart content with text-only string
                self.messages[i] = {**msg,
                                     "content": self._strip_images(msg["content"])}

    def capture_screenshot(self) -> str | None:
        """Take a screenshot via mGBA and return base64-encoded PNG, or None on error."""
        try:
            self.mgba.screenshot(SCREENSHOT_PATH)
            time.sleep(0.05)
            with open(SCREENSHOT_PATH, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except Exception:
            log_once("client.capture_screenshot", "client.capture_screenshot: tolerated failure (continuing with a default)")
            return None

    _map_b64_cache: dict[Path, str] = {}

    @classmethod
    def load_area_map(cls, bank: int, id: int) -> tuple[str | None, str]:
        """Return (base64 PNG | None, human map name). Caches per file path."""
        path = get_map_image_path(bank, id)
        name = MAP_NAMES.get((bank, id), f"bank={bank},id={id}")
        if path is None:
            return None, name
        cached = cls._map_b64_cache.get(path)
        if cached is None:
            with open(path, "rb") as f:
                cached = base64.b64encode(f.read()).decode()
            cls._map_b64_cache[path] = cached
        return cached, name

    # Matches a Qwen3-style <think>...</think> block (possibly multi-line)
    _THINK_RE = re.compile(r"<think>(.*?)</think>\s*", re.DOTALL)

    def _extract_response(self, msg) -> tuple[str, str]:
        """Parse a model reply into (reasoning_for_display, content_for_history).

        Qwen3 thinking models embed reasoning inside <think>...</think> tags
        in msg.content.  Storing those tags in history and replaying them to
        the API on the next turn causes a parse error (the garbage characters
        seen in the 400 error).  This method always strips the think block from
        the stored content.

        Returns
        -------
        reasoning : str
            The thinking text (for console display).  Empty string for
            non-thinking models or when no think block is present.
        clean_content : str
            msg.content with all <think>…</think> blocks removed — safe to
            store in message history and replay to the API.
        """
        raw = strip_control_tokens(msg.content or "")

        if ENABLE_THINKING:
            m = self._THINK_RE.search(raw)
            if m:
                thinking    = m.group(1).strip()
                clean       = self._THINK_RE.sub("", raw).strip()
                return thinking, clean
            # No inline tags — some LM Studio builds surface reasoning_content
            # as a separate field instead.
            extra = getattr(msg, "model_extra", {}) or {}
            reasoning = (extra.get("reasoning_content") or "").strip()
            if reasoning:
                return reasoning, raw   # raw has no tags to strip here

        return "", raw

    def step(self, observation: str, screenshot_b64: str | None = None,
             area_map_b64: str | None = None, area_map_name: str = "") -> tuple[str, list[str]]:
        """Run one decision step. Returns (reasoning_text, actions).

        If `area_map_b64` is provided, attaches it as an additional reference image
        (overhead map of the current area). Use only on area entry — re-injecting
        every tick wastes context."""
        if screenshot_b64 or area_map_b64:
            user_content: list[dict] = []
            if area_map_b64:
                label = (f"Overhead reference map of {area_map_name} (you just entered this area). "
                         f"Use it to plan your route — exits, paths, key buildings. "
                         f"Your current position is shown in the live screenshot below.")
                user_content.append({"type": "text", "text": label})
                user_content.append({"type": "image_url",
                                     "image_url": {"url": f"data:image/png;base64,{area_map_b64}"}})
            user_content.append({"type": "text", "text": observation})
            if screenshot_b64:
                user_content.append({"type": "image_url",
                                     "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}})
        else:
            user_content = observation

        checkpoint = len(self.messages)     # roll back to here if this step fails (#69)
        self.messages.append({"role": "user", "content": user_content})
        self._trim_image_history()
        actions: list[str] = []
        last_reasoning = ""

        # Bounded tool-call loop: a model can otherwise keep calling tools forever
        # within a single decision (making MAX_STEPS meaningless and acting on a
        # stale screenshot). After MAX_TOOL_ROUNDS we return control so the main
        # loop re-observes (fresh screenshot + observation).
        for _round in range(self.MAX_TOOL_ROUNDS):
            flush = getattr(getattr(self, "mgba", None), "flush_viewer", None)
            if flush:
                flush()           # the window only presents ~60×/s: show the latest frame before we wait on the LLM
            try:
                resp = call_with_retry(
                    lambda: self.llm.chat.completions.create(
                        model=MODEL_NAME, messages=self.messages,
                        tools=tools_for(self._tool_context()), tool_choice="auto",
                        temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
                        timeout=LLM_TIMEOUT or None,   # bound a single call (see config)
                    ),
                    tries=LLM_RETRIES,
                    on_retry=lambda e, n, wait: events.emit("note", f"LLM call failed ({type(e).__name__}) — retry {n}/{LLM_RETRIES} in {wait:.0f}s", log=False),
                )
            except Exception:
                # A failed LLM call (e.g. an LLM_TIMEOUT) must not leave a dangling user
                # turn — or a half-finished tool_calls group — in history: the API would
                # reject the next request, and each retried step would pile on another,
                # inflating token cost. Roll back everything this step appended (#69).
                del self.messages[checkpoint:]
                raise
            self.llm_calls += 1
            usage = getattr(resp, "usage", None)
            if usage:
                self.total_prompt_tokens     += getattr(usage, "prompt_tokens", 0) or 0
                self.total_completion_tokens += getattr(usage, "completion_tokens", 0) or 0
            cached = cached_prompt_tokens(usage)
            self.total_cached_tokens += cached or 0
            msg = resp.choices[0].message

            # Split thinking from the actual response BEFORE storing in history.
            # <think>...</think> blocks must never be replayed to the API —
            # LM Studio rejects them with a 400 parse error on subsequent turns.
            reasoning, clean_content = self._extract_response(msg)
            last_reasoning = reasoning or clean_content

            self.run_log.event(
                "llm", n=self.llm_calls, round=_round,
                prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
                cached_tokens=cached,
                reasoning=(reasoning or "")[:1500], content=(clean_content or "")[:500],
                tool_calls=[[tc.function.name, tc.function.arguments]
                            for tc in (msg.tool_calls or [])])
            history_entry: dict = {"role": "assistant", "content": clean_content}
            if msg.tool_calls:
                history_entry["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
            self.messages.append(history_entry)

            if not msg.tool_calls:
                return last_reasoning, actions

            for tc in msg.tool_calls:
                # A malformed/truncated tool call (bad JSON args, missing keys)
                # must NOT raise out of this loop: the assistant message carrying
                # tool_calls is already in history, so bailing here would orphan it
                # and every subsequent API request would 400 (tool_calls without
                # matching tool responses). Instead, turn any failure into a tool
                # response the model can see and recover from.
                _t0 = time.time()
                try:
                    result = self._execute(tc.function.name, tc.function.arguments)
                except Exception as e:
                    log_once("client.step", "client.step: tolerated failure (continuing with a default)")
                    result = self._failure_text(tc.function.name, tc.function.arguments, e)
                self._log_tool(tc.function.name, tc.function.arguments, result,
                               time.time() - _t0)
                events.tool(tc.function.name, tc.function.arguments, result, time.time() - _t0)
                events.observe(getattr(self, "reader", None))
                self.messages.append({
                    "role": "tool", "tool_call_id": tc.id, "content": str(result)
                })
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except (json.JSONDecodeError, ValueError):
                    args = {}
                if tc.function.name == "press_button":
                    actions.append(f"press:{args.get('button', '?')}")
                else:
                    actions.append(tc.function.name)

        return last_reasoning, actions

    def _tool_context(self):
        """The screen the tool list is gated on (re-read every round: a go_to can turn into a battle mid-step). Any
        failure to read it means 'offer everything'."""
        try:
            from game.state import GameContext
            ctx = self.reader.detect_context()
            if ctx == GameContext.IN_BATTLE:
                try:
                    if self._in_safari_battle():
                        return SAFARI_CONTEXT
                except Exception:
                    log_once("client._tool_context.safari", "client._tool_context: could not tell if this is a Safari battle")
            return ctx
        except Exception:
            log_once("client._tool_context", "client._tool_context: tolerated failure (continuing with a default)")
            return None

    @staticmethod
    def _failure_text(name: str, args_json: str, error: Exception) -> str:
        """'Tool X failed: …' — and for a missing argument (a bare KeyError such as "'move'") the tool's own signature and what was sent, so the model can fix the call."""
        if isinstance(error, KeyError):
            try:
                sent = json.loads(args_json) if args_json else {}
            except (json.JSONDecodeError, ValueError):
                sent = {}
            _args, problem = repair_args(name, sent, tool_schema(name))
            if problem:
                return f"Tool {name} failed: {problem}"
            return f"Tool {name} failed: missing argument {error} — {signature(name, tool_schema(name) or {})}"
        return f"Tool {name} failed: {error}"

    def _log_tool(self, name: str, args_json: str, result, secs: float) -> None:
        """Run-log one tool execution with a cheap post-call state snapshot."""
        snap = {}
        try:
            st = self.reader.read_state()
            snap = {"ctx": st.context.name, "map": [st.map_bank, st.map_id],
                    "pos": [st.player_x, st.player_y],
                    "hp": [[p.current_hp, p.max_hp] for p in st.party]}
        except Exception:
            log_once("client._log_tool", "client._log_tool: tolerated failure (continuing with a default)")
            pass
        shot = self._failure_shot(name, result)
        stall = self._stall_snapshot(name, result)
        self.run_log.event("tool", name=name, args=args_json, secs=round(secs, 2),
                           result=str(result)[:800], **({"shot": shot} if shot else {}), **({"stall": stall} if stall else {}), **snap)

    def _stall_snapshot(self, name: str, result) -> str:
        """On the 5th identical failing result in a row, save the emulator state under `<run dir>/stalls/` (loadable as a live-test fixture) and return its path relative to the run dir."""
        from agent.failure_shots import note_stall
        try:
            run_dir, save = getattr(self.run_log, "dir", None), getattr(self.mgba, "save_state_file", None)
            if not note_stall(self._stall_log, name, result) or not run_dir or save is None:
                return ""
            rel = f"stalls/{time.time() - self.run_log.t0:08.1f}_{name}.ss1"
            (run_dir / "stalls").mkdir(parents=True, exist_ok=True)
            save(str(run_dir / rel))
            events.emit("note", f"stall: {name} failed the same way {self._stall_log['run']}× — state saved to {rel}", log=False)
            return rel
        except Exception:
            log_once("client._stall_snapshot", "client._stall_snapshot: could not save a stall snapshot (ignored)")
            return ""

    def _failure_shot(self, name: str, result) -> str:
        """When a tool's result reads like a failure, save the current frame under the run directory and return its path relative to it ('' when not saved)."""
        from agent.failure_shots import should_save
        try:
            run_dir, grab = getattr(self.run_log, "dir", None), getattr(self.mgba, "screenshot", None)
            if not run_dir or grab is None or not should_save(self._shot_log, name, result, time.time()):
                return ""
            rel = f"shots/{time.time() - self.run_log.t0:08.1f}_{name}.png"
            (run_dir / "shots").mkdir(parents=True, exist_ok=True)
            grab(str(run_dir / rel))
            return rel
        except Exception:
            log_once("client._failure_shot", "client._failure_shot: could not save a failure screenshot (ignored)")
            return ""

    def _progress_signature(self):
        """What 'making progress' means to the watchdog: location, party growth, money, and (in a
        battle) the foe's species/HP. Deliberately NOT our own HP/PP or the menu state — a stalemate
        like Growl-spam or a Bag<->Run bounce keeps changing those while nothing real advances."""
        r = self.reader
        sig = (r.read_current_map(), r.read_player_pos(),
               tuple((p.species_id, p.level) for p in r.read_party()), r.read_money(), r.read_coins())
        from game.state import GameContext
        if r.detect_context() == GameContext.IN_BATTLE:
            foe = r.read_enemy_lead()
            if foe:
                sig += (foe.species_id, foe.current_hp)
        return sig

    def _execute(self, name: str, args_json: str) -> str:
        """Run one tool under a frame budget: a skill that spins (or stops making progress) is cut off
        with an explanation instead of running for half an hour with no model in the loop."""
        from agent.budgets import budget_for
        from game.watchdog import FrameWatchdog, SkillBudgetExceeded
        budget = budget_for(name)
        setter = getattr(self.mgba, "set_watchdog", None)
        if budget is None or setter is None:
            return self._execute_inner(name, args_json)
        setter(FrameWatchdog(budget[0], budget[1], probe=self._progress_signature))
        try:
            return self._execute_inner(name, args_json)
        except SkillBudgetExceeded as e:
            self.run_log.event("watchdog", tool=name, reason=e.reason, frames=e.frames,
                               stalled=e.stalled)
            where = ""
            try:
                st = self.reader.read_state()
                where = (f" Now: {st.context.name} on map {st.map_bank}/{st.map_id} at "
                         f"({st.player_x},{st.player_y}).")
            except Exception:
                log_once("client._execute", "client._execute: tolerated failure (continuing with a default)")
                pass
            if e.stalled:
                return (f"{name} was stopped: {e.reason}.{where} Whatever it was doing isn't working — "
                        "read the observation (close_menus / advance_dialog if a menu or text box is "
                        "stuck) and try a different approach.")
            return (f"{name} hit its time limit ({e.reason}) while still making progress.{where} Nothing "
                    f"was lost — call {name} again to continue, or do something else first.")
        finally:
            setter(None)

    _ABANDONS_GRIND = frozenset({"go_to", "go_to_map", "walk_to", "heal", "shop", "challenge_leader", "fly_to",
                                 "quest", "pc", "pick_up_items",
                                 "use_hm", "teach_move", "forget_move", "fish", "tutor", "rename_pokemon", "daycare", "load_state"})

    def _execute_inner(self, name: str, args_json: str) -> str:
        args = json.loads(args_json) if args_json else {}
        args, _problem = repair_args(name, args, tool_schema(name))       # a renamed / stringified argument is the model's habit, not an error; a truly missing one still raises (see _failure_text)
        events.observe(getattr(self, "reader", None))      # register a battle already under way before the tool runs
        if name in self._ABANDONS_GRIND and self._grind_run:
            self._grind_abandon()              # the model moved on: a stale session must not pin the floor
        match name:
            case "press_button":
                # Clamp defensively — a model can ignore the schema's maximum.
                times = max(1, min(int(args.get("times", 1)), 10))
                # Accept compass synonyms (West→Left, N→Up, …) the model emits.
                button = normalize_button(args["button"])
                # In battle, short taps are dropped during text printing/animations —
                # the game only accepts input once idle. Use the reliable path so
                # the model's FIGHT/move/A presses actually register.
                from game.state import GameContext
                from game.menu import _healthy_roster, forced_party_screen
                if forced_party_screen(self.mgba, self.reader):        # a fainted lead: A/B cannot get out of this screen
                    return (f"Your Pokémon fainted — the game is forcing a replacement; button presses will not leave this "
                            f"screen. Call switch_pokemon('<name or slot>'). Healthy: {_healthy_roster(self.reader)}.")
                in_battle = self.reader.detect_context() == GameContext.IN_BATTLE
                for _ in range(times):
                    if in_battle:
                        self._battle_press(button)
                    else:
                        self.mgba.tap(button)
                return f"Pressed {button} × {times}"
            case "walk_to":
                return self._walk_to_tool(int(args["x"]), int(args["y"]))
            case "go_to_map":
                return self._go_to_map(args["direction"])
            case "go_to":
                return self._go_to_tool(args.get("destination", ""), bool(args.get("force", False)),
                                        bool(args.get("auto_trainers", False)))
            case "quest":
                return self._quest_tool(str(args.get("name", "") or ""), bool(args.get("auto_trainers", False)))
            case "inspect_pokemon":
                return self._inspect_pokemon(str(args["pokemon"]))
            case "team_report":
                from knowledge.team import team_report
                return team_report(self.reader.read_party(), self.reader.read_boxes(),
                                   self.ltm.data.get("gyms_beaten", []), "\n".join(n for n in (self._money_note(), self._tm_shop_note(), self._dex_note()) if n))
            case "pc":
                return self._pc_tool(str(args.get("action", "") or ""), str(args.get("pokemon", "") or ""),
                                     str(args.get("box_pokemon", "") or ""), bool(args.get("detail", False)),
                                     bool(args.get("force", False)))
            case "reorder_party":
                second = str(args.get("second", "") or "")
                return (self._reorder_party(str(args["first"]), second) if second else self._set_lead(str(args["first"])))
            case "teach_move":
                return self._teach_move(str(args["tm"]), str(args.get("pokemon", "") or ""),
                                        str(args.get("forget", "") or ""), bool(args.get("confirm", False)))
            case "tutor":
                return self._tutor(str(args["move"]), str(args.get("pokemon", "") or ""), str(args.get("forget", "") or ""))
            case "fish":
                return self._fish(int(args.get("casts", 3) or 3))
            case "rename_pokemon":
                return self._rename_pokemon(str(args["pokemon"]), str(args["nickname"]))
            case "daycare":
                return self._daycare(str(args["action"]), str(args.get("pokemon", "") or ""))
            case "forget_move":
                return self._forget_move(str(args["pokemon"]), str(args["move"]), bool(args.get("force", False)))
            case "fly_to":
                return self._fly_to(str(args["town"]))
            case "use_hm":
                return self._use_hm(str(args["move"]))
            case "open_menu":
                return self._open_menu(str(args["menu"]))
            case "answer_prompt":
                return self._answer_prompt(str(args["answer"]))
            case "advance_dialog":
                return self._advance_dialog()
            case "close_menus":
                return self._close_menus()
            case "heal":
                return self._heal()
            case "shop":
                if args.get("sell"):
                    return self._sell(str(args.get("item", "") or ""), int(args.get("quantity", 1) or 1))
                return self._shop(str(args.get("item", "") or ""), int(args.get("quantity", 1) or 1))
            case "pick_up_items":
                return self._pick_up_items()
            case "use_item":
                from game.state import GameContext
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    return self._use_item(args["item"], str(args.get("move", "") or ""))
                if str(args["item"]).lower().strip() in ("bicycle", "bike"):
                    return self._use_bicycle()
                return self._field_use_item(args["item"], str(args.get("target", "") or ""), str(args.get("move", "") or ""))
            case "game_corner":
                return self._game_corner(str(args.get("action", "status") or "status"), int(args.get("amount", 0) or 0))
            case "save_game":
                return self._save_game()
            case "safari":
                return self._safari(str(args.get("action", "")), str(args.get("nickname", "") or ""))
            case "give_item":
                return self._give_item(str(args["item"]), str(args.get("pokemon", "") or ""))
            case "switch_pokemon":
                return self._switch_pokemon(str(args["target"]))
            case "challenge_leader":
                return self._challenge_leader()
            case "use_move":
                return self._use_move(args["move"])
            case "flee_battle":
                return self._flee_battle()
            case "catch":
                return self._catch(str(args.get("nickname", "") or ""))
            case "enter_name":
                return self._enter_name(str(args["name"]))
            case "grind":
                ab = args.get("auto_battles")              # None = not given: balancing sessions default to autopilot
                return self._grind(int(args.get("level", 0) or 0), bool(args.get("catch", True)),
                                   None if ab is None else int(ab or 0))
            case "train_party":
                return self._train_party()
            case "read_game_state":
                s = self.reader.read_state()
                party_summary = [
                    {"slot": p.slot, "species": p.species_name or f"#{p.species_id}",
                     "level": p.level, "hp": f"{p.current_hp}/{p.max_hp}",
                     "status": p.status, "moves": [m for m in p.move_names if m]}
                    for p in s.party
                ]
                return json.dumps({
                    "context": s.context.name, "badges": s.badges,
                    "party": party_summary, "map": [s.map_bank, s.map_id],
                    "pos": [s.player_x, s.player_y],
                })
            case "save_state":
                slot = args.get("slot", 0)
                ok = self.mgba.save_state(slot)
                return f"State saved to slot {slot}." if ok else \
                       f"Save to slot {slot} FAILED (state not written)."
            case "load_state":
                slot = args.get("slot", 0)
                if hasattr(self.mgba, "saved_this_session") and not self.mgba.saved_this_session(slot):
                    return (f"Slot {slot} has no state saved THIS session — loading a leftover file from an older run would reset "
                            "the game. save_state(slot) first (before a gym leader or a risky fight); after a loss you can load it.")
                ok = self.mgba.load_state(slot)
                return f"State loaded from slot {slot}." if ok else \
                       f"Load from slot {slot} FAILED — no saved state in that slot yet."
            case "wait_frames":
                # Advance the emulator. The native backend only progresses when
                # frames are stepped, so a real-time sleep would leave the game
                # frozen; tick() advances both backends (native steps frames, the
                # HTTP backend sleeps while its emulator runs on its own).
                # Clamp defensively — a model can ignore the schema's maximum and
                # a huge/negative frame count would freeze the run (HTTP) or fast-
                # forward the game thousands of steps (native).
                frames = max(0, min(int(args.get("frames", 30)), 120))
                self.mgba.tick(frames)
                return f"Waited {frames} frames."
            case "record_milestone":
                ms_name = args.get("name", "")
                if ms_name not in MILESTONES:
                    return f"Invalid milestone '{ms_name}'. Valid: {', '.join(MILESTONES)}"
                from agent.story import make_done_check
                from knowledge.milestone_evidence import verify, is_verifiable
                ok, why = verify(ms_name, make_done_check(self.reader, self.ltm))
                if not ok:
                    return f"Not recorded: {why}"
                added = self.ltm.add_milestone(ms_name, args.get("note", ""), source="model")
                return (f"Milestone '{ms_name}' {'recorded' if added else 'already recorded'}"
                        + ("" if is_verifiable(ms_name) else " (the game has no signal for this one — taken on your word)") + ".")
            case _:
                return f"Unknown tool: {name}"

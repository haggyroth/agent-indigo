# CLAUDE.md — Pokemon LeafGreen LLM Agent
**Project root:** `/Users/kylec/Projects/pokemon-agent`
**Platform:** macOS (Apple Silicon, arm64)
**Python:** 3.14 (project `.venv`) — all required packages compatible

> The code is cross-platform (paths use `pathlib`/`tempfile`); only the environment
> locations and shell commands below are host-specific. This file documents the macOS host.

> **For AI coding assistants:** This is the *operational* reference — what you need to
> build, run, and not break. Deep reference material (mGBA-http API, Gen III data
> structures/decryption, the type chart, game strategy) moved to
> [HISTORY.md](HISTORY.md); version history is in [CHANGELOG.md](CHANGELOG.md).

---

## Emulator Backend

Two backends, selected by `MGBA_BACKEND` in `.env`:

- **`native` (default)** — drives libmgba **in-process** via a cffi binding. No mGBA
  GUI, no Lua, no mGBA-http, no HTTP. The agent owns the emulator and steps frames
  directly (~50× real-time, deterministic). This is the recommended path.
- **`http` (legacy)** — the old mGBA GUI + Lua socket + mGBA-http .NET transport.
  Kept as a fallback; full endpoint reference + canonical `MGBAClient` in [HISTORY.md](HISTORY.md).

### Native backend

| Component | Location | Notes |
|-----------|----------|-------|
| libmgba | Homebrew (`brew install mgba`) — `/opt/homebrew/lib/libmgba.dylib` | Provides the core + headers the binding builds against |
| Binding source | `game/_mgba_build.py` | cffi builder → `game/_mgba_native*.so` (gitignored) |
| Native client | `game/mgba_core.py` (`NativeMGBAClient`) | Drop-in for `MGBAClient` |
| LeafGreen ROM | `~/mgba-http/Pokemon_LeafGreen.gba` (override with `ROM_PATH`) | US v1.0, 16 MB |
| LLM (local or cloud) | `MODEL_NAME` + `LLM_BASE_URL`/`LLM_API_KEY` in `.env` — a tool-capable model | Local: LM Studio on port 1234. Cloud: point `LLM_BASE_URL` at any OpenAI-compatible endpoint (OpenAI, OpenRouter, …). Text-only models: `USE_VISION=false`; ensure `MAX_TOKENS` fits the loaded context |

Build the binding once (or after upgrading libmgba):
```fish
cd /Users/kylec/Projects/pokemon-agent
source .venv/bin/activate.fish        # bash/zsh: source .venv/bin/activate
python -m game._mgba_build            # compiles game/_mgba_native*.so
```
The binding reads/writes memory with the **same absolute GBA bus addresses** as the
HTTP API, so `game/constants.py` and `memory_reader.py` are backend-agnostic.

**Booting from a save.** `NativeMGBAClient.load_save(path)` loads a battery `.sav`
into cartridge memory; call it before `reset()` so the title screen offers
"Continue":  `m.load_save("game.sav"); m.reset()`. (This is the cartridge save, not
an mGBA save state — the binding does not read mGBA's compressed `.ss*`/`.svs`
state files.)

**Watching it play (live window).** The native backend is headless by default. Set
`SHOW_WINDOW=true` (needs `pip install pygame`) to open a window that renders
libmgba's framebuffer each frame (`game/viewer.py`). It's smooth during actions and
holds the last frame still while the LLM thinks (the game only advances when the
agent runs frames). Tunables: `VIEWER_SCALE` (window size), `VIEWER_FPS` (playback
cap; 0 = full emulator speed). Close the window or press Esc to stop cleanly.
The framebuffer is 32-bit color, laid out `[R,G,B,pad]` (RGBX) per pixel.

### Legacy `http` backend (fallback, `MGBA_BACKEND=http`)

| Component | Location |
|-----------|----------|
| mGBA emulator | `/Applications/mGBA.app` |
| mGBA-http binary | `~/mgba-http/mGBA-http-0.8.2-osx-arm64-self-contained` (self-contained Mach-O) |
| Lua socket script | `~/mgba-http/mGBASocketServer.lua` (load in mGBA scripting console) |

First-run note for that binary: it's a downloaded, unsigned Mach-O — if Gatekeeper
blocks it, run `chmod +x` and `xattr -d com.apple.quarantine <binary>` once.

---

## Architecture

```
Pokemon_LeafGreen.gba
        │
   ┌────────────────── native (default) ──────────────────┐
   │  libmgba (Homebrew)  ──cffi──►  game/_mgba_native.so  │   in-process,
   │                                 game/mgba_core.py     │   ~50× realtime
   └───────────────────────────────────────────────────────┘
        │                     (or, legacy http backend:)
        │            mGBA GUI → Lua socket → mGBA-http → REST :5000 → game/mgba_client.py
        │
   main.py                      build_runtime() + run_episode() decision loop; thin main()
                                (run controls: START_FROM_SAVE, MAX_STEPS, MAX_LLM_CALLS,
                                 TOKEN_BUDGET). run_episode(goal=…) returns an EpisodeResult;
                                the eval harness reuses it so eval and real runs never diverge.
   Python Agent
   ├── game/mgba_core.py        NativeMGBAClient — in-process libmgba (default)
   ├── game/mgba_client.py      MGBAClient — legacy REST wrapper (http backend)
   ├── game/memory_reader.py    WRAM decoder — XOR decryption + detect_context
   ├── game/state.py            GameState, PokemonStatus, StateDiff, helpers
   ├── game/constants.py        Memory addresses (authoritative), lookup tables, charset
   ├── game/tilemap_reader.py   ROM tile passability, warps, connections (navigation)
   ├── game/pathfinding.py      A* grid pathfinding + door_centers + find_path_spin (arrow-tile slides: Rocket Hideout, Silph Co.) (pure, testable)
   ├── game/viewer.py           Optional pygame window (SHOW_WINDOW)
   ├── agent/skills/victory.py  quest('victory_road'): Route 22/23 by go_to, then Victory Road's boulder puzzles (knowledge/boulder_puzzle.py + vr_route.py) to Indigo Plateau
   ├── agent/skills/silph.py    quest('silph_co'): Card Key → Lapras → Giovanni → Master Ball over knowledge/silph_route.py (floors × tiles, stairs, pads, card-key doors)
   ├── agent/skills/hideout.py  quest('rocket_hideout'): Game Corner poster → 4 floors (spinner maze, Lift Key, elevator) → Giovanni → Silph Scope
   ├── agent/lm_studio_client.py OpenAI-compat client (local OR cloud), tool calling +
   │                            the nav/battle skills (walk_to/go_to/go_to_map/use_move)
   ├── agent/tools.py           Tool schemas + button-name normalization
   ├── agent/history.py         Message trimming + control-token stripping (dependency-light)
   ├── memory/short_term.py     Current context (in-process)
   ├── memory/long_term.py      Persistent progress → logs/progress.json
   ├── memory/battle_journal.py JSONL log + retrieval
   └── knowledge/
       ├── type_chart.py        Gen III type effectiveness
       ├── leafgreen_data.py    Gyms, moves (type/power), Pokémon types, milestones
       ├── navigation.py        Map names, route/building guidance, area maps
       ├── map_graph.py         GENERATED map connection+warp graph + BFS routing
       │                        (tools/gen_map_graph.py, from the pokefirered decomp)
       ├── battle.py            Battle observation builder (best-move ranking)
       └── system_prompt.py     Dynamic system prompt builder
   └── evals/                   Eval harness (python -m evals)
       ├── goals.py             Goal predicates (reach_map/badges_at_least/…) — pure
       ├── scenarios.py         Scenario registry (start state + goal + step budget)
       └── runner.py            Runs scenarios via main.run_episode → scorecard JSON/table
```

**Module boundaries — never cross these:**
- `game/` drives the emulator (native binding or legacy mGBA-http) and does memory decoding. No LLM, no scoring logic.
- `agent/` talks only to LM Studio. Interacts with the game only through tool execution.
- `memory/` reads/writes memory structures only. No network I/O.
- `knowledge/` is pure data and string construction. Zero I/O.
- `evals/` — `goals.py`/`scenarios.py` are pure/light (CI-testable); only `runner.py` imports the heavy agent stack (`main`).

---

## Memory Addresses & Context Detection

**`game/constants.py` (the `Addr` class) and `game/memory_reader.py` are the
authoritative source.** All are full GBA bus addresses (usable directly with the
native binding's reads, or `/core/read8|16|32|readrange`). Do not hand-copy the
full map here — several addresses were re-derived empirically during development
(diffing live save states) and a duplicate list drifts. The notable, hard-won
ones:

| What | Address | Notes |
|------|---------|-------|
| Party count / data | `0x02024284` / `0x02024288` | 6 × 100-byte structs (Gen III XOR, see HISTORY.md) |
| Badges | `0x02025968` | u8 bitmask; popcount = badge count |
| Map bank / id | `0x02031DBC` / `0x02031DBD` | |
| Player X/Y | deref `PLAYER_PTR` `0x03005008` +0/+2 | DMA-protected block; camera = player tile |
| `gMain.callback2` | `0x030030F4` | live "current screen" dispatcher — the context gate |
| Menu flag | `0x03002415` | set while a field menu is open, but **over-stays** after a full-screen menu closes — pair with screen-fade, never use alone |
| Script engine | `0x03000EB0` | byte[0] ≠ 0 while a map script/dialog runs |
| Screen fade | `0x03000F9C` | 1 while a menu is on screen **or** mid-fade; clears the instant a menu closes |
| `gBattleTypeFlags` | `0x02022B4C` | TRAINER bit `0x08`; set at battle init, read at battle start |
| Bag key-items pocket | `gSaveBlock1(0x03005008) + 0x3B8` | 30 slots; count non-empty for the `key_item` event |
| Current map (bank/id) | deref `PLAYER_PTR` `+0x04`/`+0x05` | the TRUE current map (interior-aware); the absolute `0x02031DBC/DBD` is the stale *parent outdoor* map |
| `gEnemyParty[0]` | `0x0202402C` | opponent's active Pokémon — same 100-byte Gen III struct as gPlayerParty; fixed global. `read_enemy_lead()` |
| `gObjectEvents` | `0x02036E38` (= OW slot 0) | NPCs on screen; 36-byte stride, `currentCoords` at +0x10/+0x12 = grid coord **+7**. walk_to routes around them |
| `gBattlerControllerFuncs[0]` | `0x03004FE0` | `== 0x0802EA11` (HandleInputChooseMove) ⇒ FIGHT move menu is open (use_move gate) |
| `gMoveSelectionCursor` | `0x02023FFC` | move slot A commits (2×2 grid); use_move writes the target slot here, then presses A |

### Context Detection (verified live — implemented in `memory_reader.detect_context`)

⚠ The old `OVERWORLD_FLAG` / `BATTLE_FLAGS` approach was **wrong** and has been
removed: `OVERWORLD_FLAG` (`0x0202287C`) reads 0 during free-roam, and
`BATTLE_FLAGS` (`0x02022880`) is transient during battle and stale afterward. The
correct gate is `gMain.callback2`:

`MENU_OPEN` alone is **not** a safe gate: after a full-screen menu (Pokédex/Bag/…)
closes it stays `1` back on the field, which trapped the agent in a phantom
`IN_MENU` forever. The fix pairs it with `SCREEN_FADE`, which *does* clear when a
menu closes (an open menu is `MENU_OPEN && SCREEN_FADE`; a stale flag has
`SCREEN_FADE == 0` and reads OVERWORLD):

```python
cb2  = read32(GMAIN_CALLBACK2)            # 0x030030F4
menu = read8(MENU_OPEN) != 0             # 0x03002415  (over-stays; never under-reports)
fade = read8(SCREEN_FADE) == 1          # 0x03000F9C  (on-screen menu OR fade; clears on close)
if cb2 == CB2_BATTLE:                     # 0x08011101   -> IN_BATTLE
elif cb2 == CB2_OVERWORLD:                # 0x080565B5   (field callback)
    if menu and fade:                     #              -> IN_MENU  (Start/Save overlay)
    elif fade:                            #              -> TRANSITIONING  (warp/map fade)
    elif read8(SCRIPT_RAM) != 0:          # byte[0]      -> DIALOG_OPEN  (NPC/sign/script)
    else:                                 #              -> OVERWORLD  (stale MENU_OPEN lands here)
else:                                     # full-screen menu has its own callback
    if menu:                              #              -> IN_MENU  (Pokédex/Party/Bag/Option/…)
    else:                                 #              -> TRANSITIONING  (warps, load screens)
```

`GameContext` values: `OVERWORLD`, `IN_BATTLE`, `DIALOG_OPEN`, `IN_MENU`,
`TRANSITIONING`, `UNKNOWN`. The `CB2_*` and menu addresses are specific to this
LeafGreen build; re-derive by diffing live states if OVERWORLD is misdetected.

Party-data XOR decryption, the 100-byte struct layout, and the Gen III charset are
documented in [HISTORY.md](HISTORY.md) (implemented in `memory_reader.py` /
`constants.py`). Dialog/event detection via state-diffing is also in HISTORY.md.

---

## Agent Behavior

### Tool List

Navigation, battle, party, PC and menu actions are all HIGH-LEVEL SKILLS — deterministic code drives the emulator; the LLM only
picks the intent (destination / move / item / target). Each skill self-verifies via memory and is resumable / clean-failing rather
than mashing buttons. Encounters (wild or trainer) END `go_to` / `grind` / the quest tools so the model plays them. The model is
only offered the tools that fit the screen (`agent.tools.tools_for`: ~1.2k tokens in battle, ~3.9k on the overworld, everything
elsewhere). The table below is generated — `python tools/gen_tool_docs.py` — and a test keeps it current.

<!-- TOOLS:START (generated by tools/gen_tool_docs.py — do not edit) -->
| Tool | Offered in | Arguments | What it does |
|---|---|---|---|
| `press_button` | battle + overworld | button, times? | Press a GBA button.  Use for menus, battle, and movement. |
| `walk_to` | overworld | x, y | Walk the player to tile (x, y) on the CURRENT map. |
| `go_to_map` | overworld | direction | Leave the current map by crossing a seamless connection on the given edge (see 'Map edges' in the observation). |
| `go_to` | overworld | destination?, force?, auto_trainers? | Travel to a named map ('Pewter City') or waypoint ('Pokemon Center', 'Mart', 'Gym'). |
| `challenge_leader` | overworld | — | Walk up to the Gym Leader and start the battle (inside the gym, healed and save_state'd first). |
| `heal` | overworld | — | Restore the whole party (HP, PP, status) at the nearest Pokémon Center — or at home with Mom in Pallet Town when that is nearer (free; once Gary is beaten) — travels there, fleeing wild battles on the way (never a shiny: catch it). |
| `shop` | overworld | sell?, item?, quantity? | Restock at a Poké Mart (travels there if needed): buys the badge-scaled par levels of Balls, Potions and cures with the money you have. |
| `switch_pokemon` | battle | target | Switch your active Pokémon (species name or 1-based slot). |
| `use_item` | battle + overworld | item, target?, move? | Use a Bag item.  In battle: on your ACTIVE Pokémon (costs your turn) — a Potion or a status cure; Elixir restores every move's PP. |
| `give_item` | overworld | item, pokemon | Make a party Pokémon HOLD a Bag item (Leftovers, Exp. |
| `pick_up_items` | overworld | — | Collect the item balls on this map (see 'Items on the ground:' in the observation). |
| `use_move` | battle | move | Use one of your active Pokémon's moves by name (the 'Your moves' list). |
| `grind` | overworld | level?, catch?, auto_battles? | Level up on wild Pokémon in tall grass (or the Mansion floor). |
| `quest` | overworld | name?, auto_trainers? | The story, start to Elite Four.  quest() lists every beat: ✔ done / ▶ next / … blocked. |
| `inspect_pokemon` | battle + overworld | pokemon | Look closely at ONE Pokémon: real stats, IVs, EVs, nature, Hidden Power and a quality grade for what its species is used for, compared with your team. |
| `team_report` | battle + overworld | — | Read-only team analysis: the types your KNOWN moves hit super effectively, shared weaknesses, who can carry each HM, whether the team answers the NEXT gym and — if not — what to catch and where (or which PC Pokémon to swap in with pc). |
| `pc` | overworld | action, pokemon?, box_pokemon?, detail?, force? | The Pokémon PC (box storage).  action='list' shows what is stored (reads memory, works anywhere; detail=true adds box:slot, types, moves, HM ability and a quality grade — use it to pick who to withdraw). |
| `reorder_party` | overworld | first, second? | Out of battle, swap two party members (Start → POKéMON → SWITCH, driven for you) — or, with `second` omitted, make `first` your LEAD (slot 1, fights first; a fainted one can't lead). |
| `teach_move` | overworld | tm, pokemon?, forget?, confirm? | Teach a TM/HM to a party Pokémon via the TM Case. |
| `forget_move` | overworld | pokemon, move, force? | Delete a move at the Move Deleter in Fuchsia (travels there): the only way to remove an HM move. |
| `rename_pokemon` | overworld | pokemon, nickname | Change a Pokémon's nickname at the Name Rater in Lavender Town (travels there). |
| `daycare` | overworld | action, pokemon? | Route 5 Day Care (travels there): action='deposit' leaves one Pokémon (it gains 1 exp per step you walk; another must be able to fight); 'withdraw' takes it back for ¥100 + ¥100 per level gained. |
| `tutor` | overworld | move, pokemon?, forget? | Learn a move from its Kanto tutor (free, once each; travels there): Counter, Softboiled, Seismic Toss, Rock Slide, Thunder Wave, Double-Edge, Substitute… `pokemon` optional. |
| `fish` | overworld | casts? | Cast your best rod at the nearest water (walks to a shore) up to `casts` times; a wild Pokémon on the hook becomes a battle. |
| `fly_to` | overworld | town | Fly to a visited town (needs a Pokémon that knows Fly + the Thunder Badge, outdoors): Pallet, Viridian, Pewter, Cerulean, Lavender, Vermilion, Celadon, Fuchsia, Cinnabar, Saffron, Indigo Plateau. |
| `use_hm` | overworld | move | Use a field move: Surf (at the nearest shore, then walk_to / go_to_map cross water), Cut (nearest tree), Rock Smash, Strength (then walk into the boulder), Flash (lights a cave). |
| `open_menu` | overworld | menu | Open a Start-menu entry and land on its screen: Pokemon, Bag, Pokedex, Player, Save, Option or Exit. |
| `answer_prompt` | battle + overworld | answer | Answer an open YES/NO box (e.g.  'Would you like to save?', shop or NPC questions). |
| `advance_dialog` | battle + overworld | — | Press A through NPC/sign/system dialogue until it finishes or a choice (Yes/No / menu) needs your decision. |
| `close_menus` | battle + overworld | — | Back out of every open menu, prompt and dialogue with B until you are on the free field again. |
| `flee_battle` | battle | — | Run from a WILD battle (trainer battles can't be fled). |
| `safari` | menus / naming screens | action, nickname? | One turn of a SAFARI ZONE battle (the menu is BALL / BAIT / GO NEAR / RUN — no moves, party or Bag). |
| `catch` | battle | nickname? | Throw a Poké Ball at the WILD Pokémon you're fighting (never a trainer's) — ALWAYS catch a SHINY. |
| `enter_name` | menus / naming screens | name | Type a name on the naming screen when one is open (a nickname, or the player/rival name in a new game) and confirm it. |
| `read_game_state` | overworld | — | Read current game state: party HP, battle status, badges, location. |
| `game_corner` | overworld | action?, amount? | The Celadon Game Corner (needs the Coin Case: quest('coin_case')). |
| `save_game` | overworld | — | Write a REAL cartridge save (the in-game SAVE: Start → Save → Yes → Yes), confirmed by the game's save counter. |
| `save_state` | overworld | slot? | Save state to a slot.  Call before gym leaders and Elite Four. |
| `load_state` | overworld | slot? | Load a save state — to retry a CATCH (slot 9). |
| `wait_frames` | overworld | frames | Wait N frames (60fps).  Use during animations and transitions. |
| `record_milestone` | overworld | name, note? | Record a story milestone to long-term memory right after it happens: starter_chosen, delivered_oaks_parcel, got_cut, got_flash, cleared_rock_tunnel, got_silph_scope, rescued_mr_fuji, got_poke_flute, got_surf, got_strength, got_fly, woke_snorlax_12, woke_snorlax_16. |

Other contexts (menus, dialog, transitions, unknown) are offered every tool. `?` marks an optional argument. 41 tools in total.
<!-- TOOLS:END -->

The opponent is identified from memory (`gEnemyParty`), so there is no
`set_opponent` tool — it's shown in the observation automatically.

### Battle Decision Priority

1. Opponent + types are auto-detected (shown in the obs) — no need to set them.
2. `use_move("<name>")` to attack — prefer the super-effective / highest-power move with PP.
3. `switch_pokemon(...)` if the opponent has a 2× type advantage and you have a better counter.
4. Heal a low mon mid-battle with `use_item("Potion")`; out of battle `heal()` if HP/PP low.
5. `catch()` a weakened wild Pokémon to build a team (a lone mon can't sustain a dungeon/E4).
6. Save state before every gym leader and every E4 trainer. After a loss do NOT load it: the whiteout heals the party and the Exp the loss earned is kept — train, then retry (load_state is for retrying a catch).

### Run statistics (there is no reward)

The old shaped→sparse reward was a scoreboard nothing read (never shown to the model, Elite Four / Champion terms never wired), so it
was removed (#212). What a run did is read from the event stream (`agent/events.py`): `events.run_stats()` — battles by outcome
(won / lost / fled / caught / drew), trainer wins, catches, level-ups, evolutions, faints, blackouts, badges, new towns, key items,
heals — printed at the end of a run (`events.stats_line()`), stored in the eval scorecard (`EpisodeResult.stats`) and in `run.jsonl`'s
`end` record. Cumulative counters (`battles_won/lost/fled/caught`, `pokemon_caught`) live in `logs/progress.json`.

## Development Reference

### Errors to Never Repeat

- mGBA is a **GBA** emulator. ROM must be `.gba`. Never `.nds`.
- mGBA-http is a **self-contained binary** (bundles its own .NET runtime). Never run with Python. Run it directly.
- Correct repo: `nikouu/mGBA-http`. Not `mgba-emu/mgbahttp`.
- Memory reads: `/core/read8|16|32|readrange` with **full absolute GBA addresses**.
- **No** `/core/memory/domain` endpoint — it doesn't exist.
- **No** `/core/state/save` — correct is `/core/savestateslot`.
- **No** `/core/frame/forward` — doesn't exist.
- Response from `/core/read8`: `"255"` (plain text decimal). Parse with `int(r.text.strip())`.
- Response from `/core/readrange`: `"d3,00,ea,66"` (comma-sep hex). Parse: `bytes(int(h,16) for h in r.text.strip().split(","))`.
- `slot` param for savestateslot/loadstateslot is a **string**, not integer: `params={"slot": "0"}`

### Startup Order (Every Session)

**Native backend (default) — two steps:**
```
1. LM Studio: load the model named in .env (MODEL_NAME), server port 1234, tools enabled
2. Terminal (fish): cd /Users/kylec/Projects/pokemon-agent → source .venv/bin/activate.fish → python main.py
```
main.py loads the ROM (`ROM_PATH`) in-process. No GUI, no Lua, no mGBA-http.
First time only: `python -m game._mgba_build` to compile the binding.

Run controls (env vars, native backend): `START_FROM_SAVE=<path.sav>` boots from a
battery save and drives to "Continue" (real gameplay instead of the new-game
intro); `MAX_STEPS=<n>` bounds a run for smoke/eval; `CHECKPOINT_EVERY=<ticks>` (default 20) saves emulator states under
`logs/runs/<ts>/checkpoints/`; `RESUME=latest` (or a `.ss1` path) continues from the last one; `BATTLE_STYLE=shift|set|` (default `shift` — the free switch after a trainer's Pokémon faints; see `game/options.py`); `LLM_RETRIES=<n>` (default 8 — transient LLM failures are retried with a 2→60 s backoff before the error budget is charged; `agent/llm_retry.py`); `LEAGUE_LOSS_RULE=advise|wall|off` + `LEAGUE_LOSS_BUMP=<levels>` (default `advise`, 2 — the optional rule that raises the Elite Four's recommended levels per loss in the League: `advise` nudges once per loss and then lets the model decide, `wall` refuses until the raised levels are met, `off` keeps the base levels only; the base level shortfall is always a wall — see `knowledge/beat_readiness.py`); `LOG_LEVEL=quiet|events|debug` (default `events`) sets how much of the live
game-event stream prints (catches, KOs, level-ups, badges, battle results, heals, every tool call; `STATUS_EVERY=<ticks>` adds
a status line) — see `agent/events.py`; `START_NEW_GAME=true` boots to the title screen with no save (the model starts the game with `quest('new_game')`; see CHANGELOG; `STARTER` / `PLAYER_NAME` / `RIVAL_NAME` choose the starter and the two names, call options override); `USE_RUNNING_SHOES=false` makes the agent always walk (by default it holds B outdoors once it owns the Running Shoes); `USE_VISION=false` runs
text-only (for text models or unstable vision). Example bounded text-only run:
`USE_VISION=false MAX_STEPS=20 START_FROM_SAVE=~/mgba-http/Pokemon_LeafGreen.sav python main.py`

**Legacy http backend (`MGBA_BACKEND=http`):**
```
1. Open /Applications/mGBA.app → File → Load ROM → ~/mgba-http/Pokemon_LeafGreen.gba
2. mGBA: Tools → Scripting → File → Load Script → ~/mgba-http/mGBASocketServer.lua
3. Terminal: ~/mgba-http/mGBA-http-0.8.2-osx-arm64-self-contained  (leave running)
4. LM Studio: load the model, server port 1234, tools enabled
5. Terminal (fish): cd .../pokemon-agent → source .venv/bin/activate.fish → python main.py
```

### Verification Commands

```fish
# Native backend: verify the binding loads the ROM in-process
cd /Users/kylec/Projects/pokemon-agent
source .venv/bin/activate.fish
python -c "from game.mgba_core import NativeMGBAClient as C; m=C(); print(m.get_game_title(), m.get_game_code(), m.verify_connection())"
# Expected: POKEMON LEAF AGB-BPGE True

# Legacy http backend (only if MGBA_BACKEND=http and the server is running):
#   curl http://localhost:5000/core/getgametitle      -> "POKEMON LEAF"
#   curl http://localhost:5000/core/getgamecode        -> "AGB-BPGE"
#   curl "http://localhost:5000/core/read32?address=0x02024284"  -> 0-6
#   curl -X POST "http://localhost:5000/mgba-http/button/tap?button=A"

# Live suite (real ROM + fixtures in saves/live, never in CI): one command, preflight + summary; --post-status attests a PR via the `live-suite` commit status
python tools/live_suite.py --changed origin/main --post-status      # see docs/live-ci.md

# Test Python imports  (fish shell)
cd /Users/kylec/Projects/pokemon-agent
source .venv/bin/activate.fish
python -c "import requests, openai, rich; print('OK')"
```

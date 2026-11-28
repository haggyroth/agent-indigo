# Live tests

Part of [Agent Indigo](../../README.md); see the [testing guide](../../docs/testing.md).

Replay real bugs against the **real ROM** through the in-process libmgba binding. They are skipped when
the binding, ROM or fixtures are missing, so CI (no ROM) simply skips them.

```bash
python -m pytest tests/live -v          # needs: built binding, ROM, fixtures in saves/live/
```

One command with a preflight (is the ROM / every fixture / the binding there?), a summary, and an optional commit-status attestation for pull requests (#279; background and the options
considered in [docs/live-ci.md](../../docs/live-ci.md)):

```bash
python tools/live_suite.py                                          # everything
python tools/live_suite.py -k articuno                              # a subset (never attested)
python tools/live_suite.py --changed origin/main --post-status      # only if the diff touches guarded code; then publish the `live-suite` status for HEAD
```

## Regenerating fixtures (no play-through, no model)
```bash
python tools/make_live_fixtures.py --list                  # recipes, and whether each fixture exists
python tools/make_live_fixtures.py                         # make every missing one from work.sav
python tools/make_live_fixtures.py --only vermilion --force
```
`tools/make_live_fixtures.py` boots from `work.sav`, stages the situation with the harness helpers (`fly_to`, `add_mon`, `patch_mon`, flags, badges; the agent's own `go_to` walks out of the starting
building) and writes the state. A generated fixture matches its recipe's description, not necessarily the original play-through's exact party or tile; a recipe is a few lines in the tool.
`Live.warp_to((bank, id), x?, y?)` (the harness's teleport: SaveBlock1's position + map and the game's own map loader, so it works from indoors where Fly is refused) stages the dungeon recipes: `mt_moon_1f`, `rock_tunnel_1f`, `silph_co_1f`, `victory_road_1f`.
Currently: `threemon`, `vermilion`, `league_door`, `cable_club_counter` (Viridian Pokémon Center 2F, Bulbasaur + Kadabra L30: the two-core link-cable trade test), `partner_counter` (the same counter, Bulbasaur + a Rattata: the trade partner's side).

**The trade partner (#363).** `trade_evolve` links the running game to a second core restored from `saves/partner/partner_counter.ss1`; make it with `python tools/make_live_fixtures.py --only partner_counter --out saves/partner` (needs `work.sav` and the link module, `python -m game._mgba_link_build`). The live tests build their own into a temp folder.
**The FireRed partner (`link_trade`, #363).** `python tools/make_live_fixtures.py --firered` (or `--only partner_firered_1,partner_firered_2`, `--out saves/partner`) stages the FireRed exclusives into a FireRed core's party, starting from a FireRed state standing at a Pokémon Center 2F counter (`FIRERED_STATE`, default `~/mgba-http/firered_trade_counter.ss0`; ROM `FIRERED_ROM_PATH`). FireRed shares LeafGreen's RAM and callback addresses, so the link code is unchanged. The ROM and states stay local; the tests skip without them.
**Live runs never write `work.sav`.** The cartridge save is file-backed, and the Cable Club asks "Would you like to save?" before every link-up, so the runtime and the fixture tool boot from a *copy* (a test that loads the battery save itself must copy it too); the session fails if the real file changes.

## Fixtures (`saves/live/`, gitignored — ROM-derived)
| file | what it is |
|---|---|
| `work.sav` | battery save the runtime boots from (Pallet/Viridian, Bulbasaur L8) |
| `threemon.ss1` | Viridian City, party Bulbasaur L8 / Pikachu L5 / Caterpie L5 |
| `fullparty.ss1` | inside a Pokémon Center with a FULL party of six (Zubat, Ivysaur, Spearow, Beedrill, Pikachu, Pidgey) and Sandshrew boxed — the PC swap that looped on WITHDRAW (run `20261119-210923`, checkpoint 1, walked to the Center) |
| `fuchsia_by_land.ss1` | Route 16 (41,7), 4 badges, Poké Flute in the bag, Route 12's Snorlax already awake (flag 0x253), no Bicycle — the watched stall on the way to Fuchsia (run `20261120-172153`, checkpoint 21) |
| `cycling_road.ss1` | Route 16's east end (Celadon's exit), Bicycle in the bag (voucher + flags 0x241/0x271), Route 16's Snorlax gone (flag 0x080), trainers beaten — Celadon -> Fuchsia over the Cycling Road |
| `disabled.ss1` | mid-battle, the lead's Tackle is Disabled (found via `gDisableStructs` 0x02023E0C) |
| `post_misty.ss1` | Route 24 (north of Cerulean), Misty beaten, Ivysaur L26, no SS Ticket yet |
| `vermilion_gym_surge.ss1` | Vermilion Gym, 2 badges, Ivysaur L30 with five L22 teammates, in front of Surge's trainers (run checkpoint `ckpt_00117_OVERWORLD`) |
| `league_door.ss1` | Indigo Plateau Pokémon Center 1F, 8 badges, a boosted L70 lead (made by the elite_four live test's staging; used by the `elite_four` eval scenario) |
| `league_agatha.ss1` | Agatha's room just entered (Lorelei and Bruno beaten), a boosted L70 team — for the League loss-path test |
| `league_champion.ss1` | The Champion's room just entered, a boosted L70 team — for the Hall of Fame / credits test |
| `post_hof.ss1` | **Post-game**: Pallet Town after the Hall of Fame, the credits and the soft reset (`FLAG_SYS_GAME_CLEAR` set, 8 badges, a boosted L72 lead + five teammates, Seagallop scene `VAR_MAP_SCENE_VERMILION_CITY` = 3). Written as a side-effect of `test_the_credits_end_in_a_soft_reset_and_continue_lands_in_pallet_town` — the start of the Sevii / Mewtwo / roaming-beast work (#261-#265) |
| `route3_weak_team.ss1` | Route 3 east end, 1 badge, Ivysaur L17 with five L11-12 teammates (run checkpoint) |
| `vr1f_wedged.ss1` | Victory Road 1F at (4,12), 8 badges, a Fly-capable team, the west boulder pushed to (4,11) (run `20261123-202826` checkpoint 61) — the wedge the floor reset recovers from |
| `vermilion.ss1` | Vermilion City (arrived via the Underground Path), Ivysaur L30, SS Ticket held, no Cut yet |
| `forced.ss1` | mid-battle, the active mon fainted → forced party screen |
| `route8.ss1` | Route 8 (east end, (71,9)), Venusaur knows Cut, Cascade Badge — the fenced tall-grass pocket sealed by two Cut trees |
| `celadon_gym_door.ss1` | Celadon City Gym door (10,16); Venusaur L35 + a lopsided team, 0 Poké Balls — Dept. Store / Erika scenarios |
| `forced_stuck.ss1` | Route 11 wild Spearow, Beedrill fainted: the forced party screen a Gemma run pressed A on for 319 tool calls (a run checkpoint) |

Point `LIVE_DIR` elsewhere to use another folder; `ROM_PATH` for the ROM.

## Staging tricks (see `harness.py`)
- `patch_mon(slot, moves, pps, level, exp)` rewrites the encrypted party struct (+ checksum). Keep **exp
  consistent with level** or the game freezes on the "gained EXP" text.
- Heal HP by writing `max_hp` into the current-HP word of each party struct (`heal_hp`).
- `wild_battle()` wanders on grass until an encounter starts; `set_foe_hp()` writes gBattleMons[1].
- To make a fixture: reach the state with a script, then `m.save_state_file("saves/live/<name>.ss1")`.

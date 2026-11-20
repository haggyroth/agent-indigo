# Live tests

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

## Fixtures (`saves/live/`, gitignored — ROM-derived)
| file | what it is |
|---|---|
| `work.sav` | battery save the runtime boots from (Pallet/Viridian, Bulbasaur L8) |
| `threemon.ss1` | Viridian City, party Bulbasaur L8 / Pikachu L5 / Caterpie L5 |
| `fullparty.ss1` | inside a Pokémon Center with a FULL party of six (Zubat, Ivysaur, Spearow, Beedrill, Pikachu, Pidgey) and Sandshrew boxed — the PC swap that looped on WITHDRAW (run `20261119-210923`, checkpoint 1, walked to the Center) |
| `disabled.ss1` | mid-battle, the lead's Tackle is Disabled (found via `gDisableStructs` 0x02023E0C) |
| `post_misty.ss1` | Route 24 (north of Cerulean), Misty beaten, Ivysaur L26, no SS Ticket yet |
| `vermilion_gym_surge.ss1` | Vermilion Gym, 2 badges, Ivysaur L30 with five L22 teammates, in front of Surge's trainers (run checkpoint `ckpt_00117_OVERWORLD`) |
| `league_door.ss1` | Indigo Plateau Pokémon Center 1F, 8 badges, a boosted L70 lead (made by the elite_four live test's staging; used by the `elite_four` eval scenario) |
| `league_agatha.ss1` | Agatha's room just entered (Lorelei and Bruno beaten), a boosted L70 team — for the League loss-path test |
| `league_champion.ss1` | The Champion's room just entered, a boosted L70 team — for the Hall of Fame / credits test |
| `post_hof.ss1` | **Post-game**: Pallet Town after the Hall of Fame, the credits and the soft reset (`FLAG_SYS_GAME_CLEAR` set, 8 badges, a boosted L72 lead + five teammates, Seagallop scene `VAR_MAP_SCENE_VERMILION_CITY` = 3). Written as a side-effect of `test_the_credits_end_in_a_soft_reset_and_continue_lands_in_pallet_town` — the start of the Sevii / Mewtwo / roaming-beast work (#261-#265) |
| `route3_weak_team.ss1` | Route 3 east end, 1 badge, Ivysaur L17 with five L11-12 teammates (run checkpoint) |
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

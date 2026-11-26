# Game knowledge

Strategy and facts about Pokémon LeafGreen that the agent's prompts and knowledge modules are built from. Most of the runtime data under `knowledge/` is now *generated* from the pokefirered decompilation (`tools/gen_*.py`); this is the human-readable background.

## Overview

### Type Chart (Gen III — no Fairy)

Row = attacking type. `2`=super effective, `½`=not very, `0`=immune.

|   | NOR | FIR | WAT | ELE | GRS | ICE | FIG | POI | GRD | FLY | PSY | BUG | ROC | GHO | DRG | DRK | STL |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
|NOR| 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |½| **0** | 1 | 1 |½|
|FIR| 1 |½|½| 1 | **2** | **2** | 1 | 1 | 1 | 1 | 1 | **2** |½| 1 |½| 1 | **2** |
|WAT| 1 | **2** |½| 1 |½| 1 | 1 | 1 | **2** | 1 | 1 | 1 | **2** | 1 |½| 1 | 1 |
|ELE| 1 | 1 | **2** |½|½| 1 | 1 | 1 | **0** | **2** | 1 | 1 | 1 | 1 |½| 1 | 1 |
|GRS| 1 |½| **2** | 1 |½| 1 | 1 |½| **2** |½| 1 |½| **2** | 1 |½| 1 | 1 |
|ICE| 1 |½|½| 1 | **2** |½| 1 | 1 | **2** | **2** | 1 | 1 | 1 | 1 | **2** | 1 |½|
|FIG| **2** | 1 | 1 | 1 | 1 | **2** | 1 |½| 1 |½|½|½| **2** | **0** | 1 | **2** | **2** |
|POI| 1 | 1 | 1 | 1 | **2** | 1 | 1 |½|½| 1 | 1 |½|½|½| 1 | 1 | **0** |
|GRD| 1 | **2** | 1 | **2** |½| 1 | 1 | **2** | 1 | **0** | 1 |½| **2** | 1 | 1 | 1 | **2** |
|FLY| 1 | 1 | 1 |½| **2** | 1 | **2** | 1 | 1 | 1 | 1 | **2** |½| 1 | 1 | 1 |½|
|PSY| 1 | 1 | 1 | 1 | 1 | 1 | **2** | **2** | 1 | 1 |½| 1 | 1 | 1 | 1 | **0** |½|
|BUG| 1 |½| 1 | 1 | **2** | 1 |½|½| 1 |½| **2** | 1 | 1 |½| 1 | **2** |½|
|ROC| 1 | **2** | 1 | 1 | 1 | **2** |½| 1 |½| **2** | 1 | **2** | 1 | 1 | 1 | 1 |½|
|GHO| **0** | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | **2** | 1 | 1 | **2** | 1 |½|½|
|DRG| 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | **2** | 1 |½|
|DRK| 1 | 1 | 1 | 1 | 1 | 1 |½| 1 | 1 | 1 | **2** | 1 | 1 | **2** | 1 |½|½|
|STL| 1 |½|½|½| 1 | **2** | 1 | 1 | 1 | 1 | 1 | 1 | **2** | 1 | 1 | 1 |½|

**Key immunities:** Ground→Electric (Flying/Levitate immune), Ghost→Normal+Fighting, Dark→Psychic, Steel→Poison.

### Gen III Physical/Special Split — Critical Rule

Damage category is determined by **move type**, not per-move. This is the biggest mechanical difference from Gen IV+.

| Physical (uses Atk vs Def) | Special (uses SpAtk vs SpDef) |
|---------------------------|-------------------------------|
| Normal, Fighting, Flying, Poison, Ground, Rock, Bug, **Ghost**, **Steel** | Fire, Water, Grass, Electric, Ice, Psychic, **Dragon**, **Dark** |

**Critical consequences:**
- **Shadow Ball** (Ghost) → Special. Useless on Machamp (high Atk, low SpAtk).
- **Crunch/Bite** (Dark) → Special. Does NOT benefit from high Attack.
- **Aerial Ace** (Flying) → Physical. Strong on high-Attack flyers.
- **Sabrina's Alakazam** uses SpAtk — bring high-SpDef counter or Bug moves (2× vs Psychic).
- **Ghost is NOT 2× vs Psychic in Gen III** (this was a Gen I bug). Ghost is immune to Psychic only if the Ghost move is used as the attacking move. Dark is 2× vs Psychic, but Dark is Special — only effective on high-SpAtk attackers.

### Starter Recommendation

**Choose Bulbasaur.** It trivializes the first two gyms (Vine Whip is Grass/Physical 2× vs Brock's Rock and Misty's Water), learns Sleep Powder for catching, and gives the agent more time to learn navigation before difficulty increases. Charmander is the hardest early game.

### Gym Order and Strategy

| # | Leader | City | Type | Key Threats | Counter |
|---|--------|------|------|-------------|---------|
| 1 | **Brock** | Pewter | Rock | Geodude L12, Onix L14 | Grass/Water. Vine Whip wins. |
| 2 | **Misty** | Cerulean | Water | Starmie L21 (has Recover) | Grass/Electric. Hit fast — Recover stalls. |
| 3 | **Lt. Surge** | Vermilion | Electric | Raichu L24 | Ground. Diglett from Diglett's Cave trivializes. |
| 4 | **Erika** | Celadon | Grass | Vileplume L29 (Sleep Powder) | Fire/Ice/Flying/Poison. Lum Berry blocks sleep. |
| 5 | **Koga** | Fuchsia | Poison | Weezing L43 (Self-Destruct) | Ground/Psychic. Bring Antidotes + Full Heals. |
| 6 | **Sabrina** | Saffron | Psychic | Alakazam L43 | Bug (2×). Dark moves only if high SpAtk. Ghost → immune (not 2×). |
| 7 | **Blaine** | Cinnabar | Fire | Arcanine L47 | Water. Any Surf user. Requires Surf to reach. |
| 8 | **Giovanni** | Viridian | Ground | Rhydon L50 | Water/Grass/Ice. Ice Beam for Rhydon. |

### HM Requirements

| HM | Required For | Where |
|----|-------------|-------|
| **Surf (HM03)** | All water routes — required for Gym 7 | Safari Zone warden quest (Gold Teeth) |
| **Strength (HM04)** | Boulders in caves — required for Victory Road | Same warden quest |
| Cut (HM01) | Optional tree shortcuts | S.S. Anne, Vermilion |
| Fly (HM02) | Fast travel | Route 16 house (need Cut) |
| Flash (HM05) | Rock Tunnel navigation | Route 2 Oak's aide |

### Story Path

```
Pallet → Viridian → Pewter [GYM1] → Cerulean [GYM2]
  → Vermilion [GYM3] + S.S. Anne (Cut HM)
  → Lavender (via Rock Tunnel) → Celadon [GYM4] + Rocket Hideout
  → Saffron (Silph Co. rescue) [GYM6]
  → Fuchsia [GYM5] + Safari Zone warden (Surf + Strength)
  → Cinnabar Island [GYM7] (requires Surf)
  → Viridian [GYM8] → Victory Road → Indigo Plateau [Elite Four + Champion Gary]
```

**Critical blockers:** Rock Tunnel is dark without Flash. Pokémon Tower needs Silph Scope (Celadon Rocket Hideout). Snorlax blocks Routes 12/16 — need Poke Flute from Mr. Fuji (Lavender). Silph Co. must be cleared to unlock Sabrina.

### Key Items and TMs

| Item | Location | Priority |
|------|----------|----------|
| TM26 Earthquake | Silph Co. | Critical — Ground/Physical 100 power |
| TM13 Ice Beam | Celadon Game Corner (4000 coins) | Critical — covers Dragon/Ground/Flying |
| TM24 Thunderbolt | Celadon Game Corner (4000 coins) | High |
| TM35 Flamethrower | Celadon Game Corner (4000 coins) | High |
| TM29 Psychic | Saffron man in house | High |
| Lapras | Silph Co. (free, L25) | Very High — only one available |
| Silph Scope | Celadon Rocket Hideout B4F | Critical — required for Pokémon Tower |
| Poke Flute | Mr. Fuji, Lavender | Critical — wakes Snorlax |

### Elite Four

| Trainer | Biggest Threat | Counter |
|---------|---------------|---------|
| Lorelei | Lapras L60 | Electric, Rock, Fighting |
| Bruno | Machamp L58 | Psychic, Flying |
| Agatha | Gengar L58 | Ground, Psychic |
| Lance | Dragonite L62 | **Ice Beam is critical.** Dragonite survives most else. |
| Gary | Alakazam + Rhydon + starter counter | Ice Beam for Rhydon; Psychic for Fighting |

---

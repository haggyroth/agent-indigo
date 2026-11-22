from dataclasses import dataclass, field
from enum import Enum, auto
import time


class GameContext(Enum):
    TRANSITIONING = auto()
    IN_BATTLE     = auto()
    DIALOG_OPEN   = auto()
    IN_MENU       = auto()
    OVERWORLD     = auto()
    UNKNOWN       = auto()


SHINY_ODDS = 8      # a Pokémon is shiny when its shiny value is below this (8/65536)


def shiny_value(personality: int, ot_id: int) -> int:
    """GET_SHINY_VALUE from the decomp: the four 16-bit halves of the OT id and the PID XORed together."""
    return (ot_id >> 16) ^ (ot_id & 0xFFFF) ^ (personality >> 16) ^ (personality & 0xFFFF)


@dataclass
class PokemonStatus:
    slot: int
    level: int
    current_hp: int
    max_hp: int
    status: str           # "healthy" | "burned" | "paralyzed" | etc.
    species_id: int = 0   # 0 until Tier 2 decryption implemented
    species_name: str = ""
    move_ids: list[int] = field(default_factory=lambda: [0]*4)
    move_names: list[str] = field(default_factory=lambda: [""]*4)
    pp: list[int] = field(default_factory=lambda: [0]*4)
    nickname: str = ""    # the mon's given name ("" when unreadable)
    personality: int = 0  # PID: identifies the same Pokémon across party reorders, evolutions and level-ups
    ot_id: int = 0        # original trainer id (TID low 16 bits, SID high 16) — with the PID it decides shininess
    ivs: tuple = ()       # (HP, Atk, Def, Spe, SpA, SpD) individual values 0-31 — () when unreadable
    evs: tuple = ()       # same order, effort values 0-255
    friendship: int = 0
    ability_slot: int = 0
    held_item: int = 0    # item id the Pokémon is holding (0 = none)
    stats: tuple = ()     # the game's own computed (maxHP, Atk, Def, Spe, SpA, SpD) — party Pokémon only

    @property
    def is_shiny(self) -> bool:
        """Shiny in Gen III: (TID ^ SID ^ PID-high ^ PID-low) < 8 (1 in 8192). A wild Pokémon is generated with the PLAYER's ids as its OT, so this holds for a foe too."""
        return bool(self.personality) and shiny_value(self.personality, self.ot_id) < SHINY_ODDS

    @property
    def hp_percent(self) -> float:
        return self.current_hp / self.max_hp if self.max_hp > 0 else 0.0

    @property
    def is_fainted(self) -> bool:
        return self.current_hp == 0


@dataclass
class GameState:
    context:       GameContext
    badges:        int          # popcount of badge_bits (0–8), for display
    badge_bits:    int          # raw u8 badge bitmask (SaveBlock1+0xFE4), for bitwise diff
    party:         list[PokemonStatus]
    party_count:   int
    map_bank:      int
    map_id:        int
    player_x:      int
    player_y:      int
    screen_fading: bool
    timestamp:     float = field(default_factory=time.time)


@dataclass
class StateDiff:
    badges_changed:     bool = False
    hp_changed:         list[int] = field(default_factory=list)
    level_changed:      list[int] = field(default_factory=list)
    moves_changed:      list[int] = field(default_factory=list)
    party_size_changed: bool = False
    battle_started:     bool = False
    battle_ended:       bool = False
    context_changed:    bool = False
    notes:              list[str] = field(default_factory=list)

    @property
    def anything_changed(self) -> bool:
        return any([
            self.badges_changed, self.hp_changed, self.level_changed,
            self.moves_changed, self.party_size_changed,
            self.battle_started, self.battle_ended, self.context_changed,
        ])
